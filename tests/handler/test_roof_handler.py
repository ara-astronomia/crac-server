import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from crac_protobuf.curtains_pb2 import CurtainStatus
from crac_protobuf.roof_pb2 import RoofAction, RoofRequest, RoofResponse, RoofStatus
from crac_protobuf.telescope_pb2 import TelescopeStatus
from crac_server.converter.roof_converter import RoofConverter, RoofMediator
from crac_server.handler.roof_handler import (
    RoofCurtainsHandler,
    RoofHandler,
    RoofTelescopeHandler,
    RoofUpsHandler,
    RoofWeatherHandler,
)


class TestRoofWeatherHandler(unittest.TestCase):
    """The roof asks the external conditions whether it may open: the
    policies of each source live in one place, not in the handler."""

    def _handle(self, roof_status, action, blocked):
        mediator = SimpleNamespace(status=roof_status, action=action, is_disabled=False)
        self.conditions = MagicMock()
        self.conditions.operation_blocked.return_value = blocked
        with (
            patch("crac_server.handler.roof_handler.external_conditions", return_value=self.conditions),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofWeatherHandler().handle(mediator)
        return mediator

    def test_opening_is_disabled_when_the_conditions_block(self):
        mediator = self._handle(RoofStatus.ROOF_CLOSED, RoofAction.OPEN, True)

        self.assertIs(True, mediator.is_disabled)

    def test_opening_is_allowed_when_the_conditions_are_clear(self):
        mediator = self._handle(RoofStatus.ROOF_CLOSED, RoofAction.OPEN, False)

        self.assertIs(False, mediator.is_disabled)

    def test_closing_never_consults_the_external_conditions(self):
        mediator = self._handle(RoofStatus.ROOF_OPENED, RoofAction.CLOSE, True)

        self.assertIs(False, mediator.is_disabled)
        self.conditions.operation_blocked.assert_not_called()

    def test_a_status_request_that_moves_no_roof_consults_nothing(self):
        mediator = self._handle(RoofStatus.ROOF_OPENED, RoofAction.CHECK_ROOF, True)

        self.assertIs(False, mediator.is_disabled)
        self.conditions.operation_blocked.assert_not_called()


class TestRoofUpsHandler(unittest.TestCase):
    """The roof asks the external conditions whether it may open: the
    policies of each source live in one place, not in the handler."""

    def _handle(self, roof_status, action, blocked):
        mediator = SimpleNamespace(status=roof_status, action=action, is_disabled=False)
        self.conditions = MagicMock()
        self.conditions.operation_blocked.return_value = blocked
        with (
            patch("crac_server.handler.roof_handler.external_conditions", return_value=self.conditions),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofUpsHandler().handle(mediator)
        return mediator

    def test_opening_is_disabled_when_the_conditions_block(self):
        mediator = self._handle(RoofStatus.ROOF_CLOSED, RoofAction.OPEN, True)

        self.assertIs(True, mediator.is_disabled)

    def test_opening_is_allowed_when_the_conditions_are_clear(self):
        mediator = self._handle(RoofStatus.ROOF_CLOSED, RoofAction.OPEN, False)

        self.assertIs(False, mediator.is_disabled)

    def test_closing_never_consults_the_external_conditions(self):
        mediator = self._handle(RoofStatus.ROOF_OPENED, RoofAction.CLOSE, True)

        self.assertIs(False, mediator.is_disabled)
        self.conditions.operation_blocked.assert_not_called()

    def test_a_status_request_that_moves_no_roof_consults_nothing(self):
        mediator = self._handle(RoofStatus.ROOF_OPENED, RoofAction.CHECK_ROOF, True)

        self.assertIs(False, mediator.is_disabled)
        self.conditions.operation_blocked.assert_not_called()


class TestRoofHandlersOnARoofInError(unittest.TestCase):
    """
    A roof in error has no known position, so each command is checked for
    the way it would move the roof: closing needs the telescope and the
    curtains out of the way, opening needs safe weather. A plain status
    request disables nothing, since it asks for no movement.
    """

    def _mediator(self, action, motor_on=False, sensors_inconsistent=False):
        roof_in_error = MagicMock()
        roof_in_error.get_status.return_value = RoofStatus.ROOF_ERROR
        roof_in_error.motor.value = int(motor_on)
        roof_in_error.sensors_inconsistent = sensors_inconsistent
        with patch("crac_server.converter.roof_converter.roof", return_value=roof_in_error):
            return RoofMediator(RoofRequest(action=action))

    def _weather_handler(self, action, blocked=True, motor_on=False):
        mediator = self._mediator(action, motor_on)
        conditions = MagicMock()
        conditions.operation_blocked.return_value = blocked
        with (
            patch("crac_server.handler.roof_handler.external_conditions", return_value=conditions),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofWeatherHandler().handle(mediator)
        return mediator

    def _telescope_handler(self, action, telescope_status, motor_on=False):
        mediator = self._mediator(action, motor_on)
        parked_telescope = SimpleNamespace(status=telescope_status, polling=True)
        with (
            patch("crac_server.handler.roof_handler.telescope", return_value=parked_telescope),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofTelescopeHandler().handle(mediator)
        return mediator

    def _curtains_handler(self, action, curtain_status, motor_on=False):
        mediator = self._mediator(action, motor_on)
        curtain = SimpleNamespace(get_status=lambda: curtain_status)
        with (
            patch("crac_server.handler.roof_handler.curtain_east", return_value=curtain),
            patch("crac_server.handler.roof_handler.curtain_west", return_value=curtain),
            patch.object(RoofConverter, "convert", return_value=RoofResponse()),
        ):
            RoofCurtainsHandler().handle(mediator)
        return mediator

    def test_opening_is_refused_when_the_conditions_block(self):
        mediator = self._weather_handler(RoofAction.OPEN, blocked=True)
        self.assertIs(True, mediator.is_disabled)

    def test_closing_is_allowed_even_when_the_conditions_block(self):
        mediator = self._weather_handler(RoofAction.CLOSE, blocked=True)
        self.assertIs(False, mediator.is_disabled)

    def test_closing_is_refused_with_the_telescope_not_secure(self):
        mediator = self._telescope_handler(RoofAction.CLOSE, TelescopeStatus.EAST)
        self.assertIs(True, mediator.is_disabled)

    def test_closing_is_allowed_with_the_telescope_secure(self):
        mediator = self._telescope_handler(RoofAction.CLOSE, TelescopeStatus.PARKED)
        self.assertIs(False, mediator.is_disabled)

    def test_opening_does_not_look_at_the_telescope(self):
        mediator = self._telescope_handler(RoofAction.OPEN, TelescopeStatus.EAST)
        self.assertIs(False, mediator.is_disabled)

    def test_closing_is_refused_with_the_curtains_out(self):
        mediator = self._curtains_handler(RoofAction.CLOSE, CurtainStatus.CURTAIN_OPENED)
        self.assertIs(True, mediator.is_disabled)

    def test_closing_is_allowed_with_the_curtains_in(self):
        mediator = self._curtains_handler(RoofAction.CLOSE, CurtainStatus.CURTAIN_DISABLED)
        self.assertIs(False, mediator.is_disabled)

    def test_a_status_request_with_the_motor_closing_checks_the_weather(self):
        mediator = self._weather_handler(RoofAction.CHECK_ROOF, blocked=True, motor_on=False)
        self.assertIs(True, mediator.is_disabled)

    def test_a_status_request_with_the_motor_closing_ignores_the_telescope(self):
        mediator = self._telescope_handler(RoofAction.CHECK_ROOF, TelescopeStatus.EAST, motor_on=False)
        self.assertIs(False, mediator.is_disabled)

    def test_a_status_request_with_the_motor_opening_checks_the_telescope(self):
        mediator = self._telescope_handler(RoofAction.CHECK_ROOF, TelescopeStatus.EAST, motor_on=True)
        self.assertIs(True, mediator.is_disabled)

    def test_a_status_request_with_the_motor_opening_checks_the_curtains(self):
        mediator = self._curtains_handler(RoofAction.CHECK_ROOF, CurtainStatus.CURTAIN_OPENED, motor_on=True)
        self.assertIs(True, mediator.is_disabled)

    def test_a_status_request_with_the_motor_opening_ignores_the_weather(self):
        mediator = self._weather_handler(RoofAction.CHECK_ROOF, blocked=True, motor_on=True)
        self.assertIs(False, mediator.is_disabled)

    def test_with_both_limit_switches_active_no_command_moves_the_roof(self):
        for action in (RoofAction.OPEN, RoofAction.CLOSE, RoofAction.CHECK_ROOF):
            with self.subTest(action=RoofAction.Name(action)):
                mediator = self._mediator(action, sensors_inconsistent=True)
                with patch.object(RoofConverter, "convert", return_value=RoofResponse()):
                    RoofHandler().handle(mediator)

                self.assertIs(True, mediator.is_disabled)
                mediator.button.open.assert_not_called()
                mediator.button.close.assert_not_called()

    def test_a_command_answers_with_the_run_it_started(self):
        for action, run in ((RoofAction.OPEN, RoofStatus.ROOF_OPENING), (RoofAction.CLOSE, RoofStatus.ROOF_CLOSING)):
            with self.subTest(action=RoofAction.Name(action)):
                mediator = self._mediator(action)
                loop = MagicMock()
                with (
                    patch("crac_server.handler.roof_handler.asyncio.get_event_loop", return_value=loop),
                    patch.object(RoofConverter, "convert", return_value=RoofResponse()),
                ):
                    RoofHandler().handle(mediator)

                loop.create_task.assert_called_once()
                self.assertEqual(run, mediator.status)
                self.assertIs(True, mediator.is_disabled)

if __name__ == "__main__":
    unittest.main()
