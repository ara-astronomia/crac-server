import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crac_protobuf.curtains_pb2 import CurtainsAction, CurtainsResponse, CurtainStatus
from crac_protobuf.telescope_pb2 import TelescopeSpeed, TelescopeStatus
from crac_server.converter.curtains_converter import CurtainsConverter
from crac_protobuf.roof_pb2 import RoofStatus
from crac_server.handler.curtains_handler import (
    CurtainsDisableHandler,
    CurtainsMoveHandler,
    CurtainsRoofHandler,
    CurtainsTelescopeHandler,
)
from crac_server.service.curtains_service import CurtainsService


class TestTheMoveAsksTheGate(unittest.TestCase):
    """The gate answers where the movement is decided: a move that opens
    waits for the world outside, one that closes always goes."""

    def _move(self, steps, steps_east, steps_west, blocked):
        east, west = MagicMock(full_travel=200), MagicMock(full_travel=200)
        mediator = SimpleNamespace(
            is_disabled=False,
            steps_east=steps_east,
            steps_west=steps_west,
            curtain_east=east,
            curtain_west=west,
        )
        self.conditions = MagicMock()
        self.conditions.operation_blocked.return_value = blocked
        scope = MagicMock(speed=TelescopeSpeed.SPEED_NOT_TRACKING)
        with (
            patch("crac_server.handler.curtains_handler.external_conditions", return_value=self.conditions),
            patch("crac_server.handler.curtains_handler.telescope", return_value=scope),
            patch.object(CurtainsMoveHandler, "_calculate_curtains_steps", return_value=steps),
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            CurtainsMoveHandler().handle(mediator)
        return mediator, east, west

    def test_a_move_that_opens_is_disabled_when_the_conditions_block(self):
        mediator, east, west = self._move({"east": 100, "west": 100}, 10, 10, True)

        self.assertIs(True, mediator.is_disabled)
        east.move.assert_not_called()
        west.move.assert_not_called()

    def test_a_move_that_opens_is_allowed_when_the_conditions_are_clear(self):
        mediator, east, west = self._move({"east": 100, "west": 100}, 10, 10, False)

        self.assertIs(False, mediator.is_disabled)
        east.move.assert_called_once_with(100)
        west.move.assert_called_once_with(100)

    def test_a_move_that_closes_goes_even_with_the_conditions_blocked(self):
        mediator, east, west = self._move({"east": 0, "west": 0}, 50, 50, True)

        self.assertIs(False, mediator.is_disabled)
        east.move.assert_called_once_with(0)
        west.move.assert_called_once_with(0)

    def test_a_move_that_leaves_the_curtains_consults_nothing(self):
        mediator, _, _ = self._move({"east": None, "west": None}, 10, 10, True)

        self.assertIs(False, mediator.is_disabled)
        self.conditions.operation_blocked.assert_not_called()

    def test_a_move_that_opens_one_side_only_waits_for_the_conditions(self):
        mediator, east, west = self._move({"east": 100, "west": 10}, 10, 10, True)

        self.assertIs(True, mediator.is_disabled)
        east.move.assert_not_called()
        west.move.assert_not_called()


class TestCurtainsDisableHandler(unittest.TestCase):
    """DISABLE brings each curtain down whatever it is doing, powering its
    motor: the operator asked for it and is watching."""

    def _disable(self, status_east, status_west):
        east, west = MagicMock(), MagicMock()
        mediator = SimpleNamespace(
            action=CurtainsAction.DISABLE,
            status_east=status_east,
            status_west=status_west,
            curtain_east=east,
            curtain_west=west,
        )
        with patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()):
            CurtainsDisableHandler().handle(mediator)
        return east, west

    def test_a_moving_curtain_does_not_stop_the_other_from_being_disabled(self):
        east, west = self._disable(CurtainStatus.CURTAIN_OPENED, CurtainStatus.CURTAIN_OPENING)

        east.disable.assert_called_once_with(power_motor=True)
        west.disable.assert_called_once_with(power_motor=True)

    def test_curtains_in_danger_or_error_are_disabled_too(self):
        east, west = self._disable(CurtainStatus.CURTAIN_DANGER, CurtainStatus.CURTAIN_ERROR)

        east.disable.assert_called_once_with(power_motor=True)
        west.disable.assert_called_once_with(power_motor=True)


    def test_disable_stops_the_chain_so_no_move_overrides_it(self):
        next_handler = MagicMock()
        handler = CurtainsDisableHandler()
        handler.set_next(next_handler)
        mediator = SimpleNamespace(action=CurtainsAction.DISABLE, curtain_east=MagicMock(), curtain_west=MagicMock())

        with patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()):
            handler.handle(mediator)

        next_handler.handle.assert_not_called()


class TestCurtainsDisableReachesTheCurtainsAnyway(unittest.IsolatedAsyncioTestCase):
    """With the roof closed and the telescope off, DISABLE still brings the
    curtains down and powers their motors: it can do no harm."""

    async def test_disable_with_the_roof_closed_and_the_telescope_off(self):
        east, west = MagicMock(), MagicMock()
        mediator = SimpleNamespace(action=CurtainsAction.DISABLE, curtain_east=east, curtain_west=west, is_disabled=False)
        with (
            patch("crac_server.service.curtains_service.CurtainsMediator", return_value=mediator),
            patch("crac_server.handler.curtains_handler.roof") as roof,
            patch("crac_server.handler.curtains_handler.telescope") as scope,
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            roof.return_value.get_status.return_value = RoofStatus.ROOF_CLOSED
            scope.return_value.polling = False
            await CurtainsService().SetAction(None, None)

        east.disable.assert_called_once_with(power_motor=True)
        west.disable.assert_called_once_with(power_motor=True)


class TestCurtainsTelescopeHandler(unittest.TestCase):

    def test_a_telescope_off_disables_the_curtains_without_powering_their_motors(self):
        east, west = MagicMock(), MagicMock()
        mediator = SimpleNamespace(curtain_east=east, curtain_west=west, is_disabled=False)
        with (
            patch("crac_server.handler.curtains_handler.telescope") as scope,
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            scope.return_value.polling = False
            CurtainsTelescopeHandler().handle(mediator)

        east.disable.assert_called_once_with()
        west.disable.assert_called_once_with()


class TestCurtainsRoofHandler(unittest.TestCase):

    def test_a_roof_not_open_disables_the_curtains_without_powering_their_motors(self):
        east, west = MagicMock(), MagicMock()
        mediator = SimpleNamespace(curtain_east=east, curtain_west=west, is_disabled=False)
        with (
            patch("crac_server.handler.curtains_handler.roof") as roof,
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            roof.return_value.get_status.return_value = RoofStatus.ROOF_CLOSED
            CurtainsRoofHandler().handle(mediator)

        east.disable.assert_called_once_with()
        west.disable.assert_called_once_with()


class TestCurtainsMoveHandler(unittest.TestCase):

    def test_full_opening_uses_the_travel_the_curtains_read_at_startup(self):
        east, west = MagicMock(full_travel=180), MagicMock(full_travel=180)
        mediator = SimpleNamespace(is_disabled=False, steps_east=0, steps_west=0, curtain_east=east, curtain_west=west)
        scope = MagicMock(speed=TelescopeSpeed.SPEED_TRACKING, status=TelescopeStatus.EAST)
        scope.aa_coords.alt = 80
        scope.is_below_curtains_area.return_value = False
        scope.is_above_curtains_area.return_value = True
        conditions = MagicMock()
        conditions.operation_blocked.return_value = False
        with (
            patch("crac_server.handler.curtains_handler.telescope", return_value=scope),
            patch("crac_server.handler.curtains_handler.external_conditions", return_value=conditions),
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            CurtainsMoveHandler().handle(mediator)

        east.move.assert_called_once_with(180)
        west.move.assert_called_once_with(180)

    def _move_with_telescope_in(self, status):
        east, west = MagicMock(full_travel=180), MagicMock(full_travel=180)
        mediator = SimpleNamespace(is_disabled=False, curtain_east=east, curtain_west=west)
        scope = MagicMock(speed=TelescopeSpeed.SPEED_TRACKING, status=status)
        scope.aa_coords.alt = 40
        scope.is_below_curtains_area.return_value = False
        scope.is_above_curtains_area.return_value = False
        scope.is_within_curtains_area.return_value = True
        with (
            patch("crac_server.handler.curtains_handler.telescope", return_value=scope),
            patch.object(CurtainsConverter, "convert", return_value=CurtainsResponse()),
        ):
            CurtainsMoveHandler().handle(mediator)
        return east, west

    def test_a_telescope_with_no_known_position_moves_no_curtain(self):
        east, west = self._move_with_telescope_in(TelescopeStatus.LOST)

        east.move.assert_not_called()
        west.move.assert_not_called()

    def test_a_telescope_status_with_no_rule_moves_no_curtain(self):
        east, west = self._move_with_telescope_in(TelescopeStatus.FLATTER)

        east.move.assert_not_called()
        west.move.assert_not_called()


if __name__ == "__main__":
    unittest.main()
