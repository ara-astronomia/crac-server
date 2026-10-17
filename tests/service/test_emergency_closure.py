import asyncio
from time import monotonic
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from gpiozero import Device

from crac_protobuf.curtains_pb2 import CurtainStatus  # type: ignore
from crac_protobuf.cover_mirror_pb2 import CoverMirrorStatus  # type: ignore
from crac_protobuf.emergency_closure_pb2 import (
    EmergencyClosureBlockReason,  # type: ignore
    EmergencyClosureStatus,  # type: ignore
    EmergencyClosureTrigger,  # type: ignore
)
from crac_protobuf.roof_pb2 import RoofStatus  # type: ignore
from crac_protobuf.telescope_pb2 import AltazimutalCoords, TelescopeSpeed, TelescopeStatus  # type: ignore
from crac_server.component.roof.simulator.roof_pins import simulated_roof
from crac_server.config import Config
from crac_server.service.emergency_closure import EmergencyClosureProcedure

WEATHER = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_WEATHER
UPS = EmergencyClosureTrigger.EMERGENCY_CLOSURE_TRIGGER_UPS
IDLE = EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IDLE
IN_PROGRESS = EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_IN_PROGRESS
COMPLETED = EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_COMPLETED
BLOCKED = EmergencyClosureStatus.EMERGENCY_CLOSURE_STATUS_BLOCKED
MODULE = "crac_server.service.emergency_closure"


class FakeCurtain:

    def __init__(self):
        self.status = CurtainStatus.CURTAIN_OPENED
        self.goes_down = True
        self.disable = MagicMock(side_effect=self._disable)

    def _disable(self):
        if self.goes_down:
            self.status = CurtainStatus.CURTAIN_DISABLED

    def get_status(self):
        return self.status


class TestEmergencyClosure(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.telescope = MagicMock()
        self.telescope.polling = True
        self.telescope.status = TelescopeStatus.NORTHEAST
        self.telescope.aa_coords = AltazimutalCoords(alt=45, az=30)
        self.telescope.speed = TelescopeSpeed.SPEED_TRACKING
        self.telescope.movement_failed = False
        self.telescope.seconds_since_last_reading.return_value = 0
        self.telescope.queue_park.side_effect = self.__park
        self.roof = MagicMock()
        self.roof.get_status.return_value = RoofStatus.ROOF_OPENED
        self.roof.close = AsyncMock(side_effect=self.__close_roof)
        self.east, self.west = FakeCurtain(), FakeCurtain()
        self.cover_mirror = MagicMock()
        self.cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_CLOSED
        self.cover_mirror.close = AsyncMock()
        for name, component in {
            "telescope": self.telescope,
            "roof": self.roof,
            "curtain_east": self.east,
            "curtain_west": self.west,
            "cover_mirror": self.cover_mirror,
        }.items():
            patcher = patch(f"{MODULE}.{name}", return_value=component)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.procedure = EmergencyClosureProcedure()

    def __park(self):
        self.telescope.status = TelescopeStatus.PARKED
        self.telescope.aa_coords = AltazimutalCoords(alt=1, az=359)
        self.telescope.speed = TelescopeSpeed.SPEED_NOT_TRACKING

    async def __close_roof(self):
        self.roof.get_status.return_value = RoofStatus.ROOF_CLOSED
        return True

    async def __closure(self, trigger=WEATHER, critical=True):
        self.procedure.report(trigger, critical)
        if self.procedure._task:
            await self.procedure._task
        return self.procedure.state()

    async def test_nothing_critical_is_idle(self):
        state = await self.__closure(critical=False)

        self.assertEqual(IDLE, state.status)
        self.assertEqual([], list(state.triggers))
        self.roof.close.assert_not_awaited()

    async def test_before_any_report_the_closure_is_idle_not_unspecified(self):
        self.assertEqual(IDLE, self.procedure.state().status)

    async def test_a_telescope_out_of_safety_is_parked_then_curtains_then_roof(self):
        state = await self.__closure()

        self.telescope.queue_park.assert_called_once_with()
        self.east.disable.assert_called_once_with()
        self.west.disable.assert_called_once_with()
        self.roof.close.assert_awaited_once_with()
        self.telescope.polling_end.assert_called_once_with()
        self.assertEqual(COMPLETED, state.status)
        self.assertEqual([WEATHER], list(state.triggers))
        self.assertEqual(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_UNSPECIFIED, state.block_reason)

    async def test_a_telescope_already_safe_is_not_parked(self):
        self.telescope.status = TelescopeStatus.SECURE
        self.telescope.aa_coords = AltazimutalCoords(alt=5, az=30)

        state = await self.__closure()

        self.telescope.queue_park.assert_not_called()
        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_an_open_cover_mirror_is_closed_before_the_telescope_is_parked(self):
        self.cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_OPENED
        order = []

        def park():
            order.append("park")
            self.__park()

        self.cover_mirror.close.side_effect = lambda: order.append("cover")
        self.telescope.queue_park.side_effect = park

        state = await self.__closure()

        self.assertEqual(["cover", "park"], order)
        self.assertEqual(COMPLETED, state.status)

    async def test_a_closed_cover_mirror_is_not_commanded_again(self):
        state = await self.__closure()

        self.cover_mirror.close.assert_not_awaited()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_cover_mirror_already_closing_is_left_alone(self):
        self.cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_CLOSING

        state = await self.__closure()

        self.cover_mirror.close.assert_not_awaited()
        self.assertEqual(COMPLETED, state.status)

    async def test_an_open_cover_mirror_is_closed_even_when_the_telescope_is_unreadable(self):
        self.cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_OPENED
        self.telescope.status = TelescopeStatus.LOST

        state = await self.__closure()

        self.cover_mirror.close.assert_awaited_once_with()
        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        self.roof.close.assert_not_awaited()

    async def test_a_cover_mirror_that_fails_to_close_does_not_stop_the_closure(self):
        self.cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_OPENED
        self.cover_mirror.close.side_effect = OSError("indigo not answering")

        with self.assertLogs(MODULE, level="WARNING"):
            state = await self.__closure()

        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_cover_mirror_in_error_is_told_to_close_anyway(self):
        self.cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_ERROR

        state = await self.__closure()

        self.cover_mirror.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_cover_mirror_status_that_cannot_be_read_does_not_stop_the_closure(self):
        self.cover_mirror.get_status.side_effect = OSError("indigo gone")

        with self.assertLogs(MODULE, level="WARNING"):
            state = await self.__closure()

        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_the_closure_is_in_progress_while_it_runs(self):
        self.procedure.report(WEATHER, True)

        self.assertEqual(IN_PROGRESS, self.procedure.state().status)
        await self.procedure._task

    async def test_a_telescope_nobody_polls_is_polled_by_the_closure(self):
        self.telescope.polling = False
        self.telescope.seconds_since_last_reading.return_value = float("inf")
        self.telescope.polling_start.side_effect = self.__readings_arrive

        state = await self.__closure()

        self.telescope.polling_start.assert_called_once_with()
        self.telescope.queue_park.assert_called_once_with()
        self.assertEqual(COMPLETED, state.status)

    def __readings_arrive(self):
        self.telescope.polling = True
        self.telescope.seconds_since_last_reading.return_value = 0

    async def test_an_unreadable_telescope_blocks_without_moving_anything(self):
        for status in (TelescopeStatus.LOST, TelescopeStatus.ERROR, TelescopeStatus.DISCONNECTED,
                       TelescopeStatus.TELESCOPE_DEFAULT_STATUS, None):
            with self.subTest(status=status):
                self.setUp()
                self.telescope.status = status

                state = await self.__closure()

                self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
                self.telescope.queue_park.assert_not_called()
                self.east.disable.assert_not_called()
                self.roof.close.assert_not_awaited()

    async def test_a_movement_that_failed_high_up_is_parked_again(self):
        self.telescope.status = TelescopeStatus.ERROR
        self.telescope.movement_failed = True

        state = await self.__closure()

        self.telescope.queue_park.assert_called_once_with()
        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_failed_movement_cleared_before_the_next_reading_is_not_a_block(self):
        self.telescope.status = TelescopeStatus.ERROR
        self.telescope.movement_failed = True
        self.telescope.queue_park.side_effect = self.__park_clearing_the_error_first

        state = await self.__closure()

        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    def __park_clearing_the_error_first(self):
        self.telescope.movement_failed = False
        asyncio.get_running_loop().call_later(0.15, self.__park)

    async def test_a_telescope_lost_or_in_error_blocks_without_waiting_for_a_reading(self):
        for status in (TelescopeStatus.LOST, TelescopeStatus.ERROR):
            with self.subTest(status=status):
                self.setUp()
                self.procedure.max_reading_age = 60
                self.telescope.status = status

                async with asyncio.timeout(1):
                    state = await self.__closure()

                self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)

    async def test_coordinates_missing_out_of_range_or_too_old_block_the_closure(self):
        cases = {
            "missing": lambda: setattr(self.telescope, "aa_coords", None),
            "altitude out of range": lambda: setattr(self.telescope, "aa_coords", AltazimutalCoords(alt=91, az=30)),
            "azimuth out of range": lambda: setattr(self.telescope, "aa_coords", AltazimutalCoords(alt=45, az=360)),
            "too old": lambda: setattr(self.telescope.seconds_since_last_reading, "return_value", 3600),
        }
        for case, make_unreadable in cases.items():
            with self.subTest(case):
                self.setUp()
                make_unreadable()

                state = await self.__closure()

                self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
                self.roof.close.assert_not_awaited()

    async def test_a_telescope_lost_while_parking_blocks_the_closure(self):
        self.telescope.queue_park.side_effect = lambda: setattr(self.telescope, "status", TelescopeStatus.LOST)

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        self.east.disable.assert_not_called()
        self.roof.close.assert_not_awaited()

    async def test_a_park_not_reached_in_time_blocks_the_closure(self):
        self.telescope.queue_park.side_effect = None

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED)
        self.east.disable.assert_not_called()
        self.roof.close.assert_not_awaited()

    async def test_a_parked_switch_is_not_enough_to_close_the_roof(self):
        cases = {
            "park still slewing": (TelescopeSpeed.SPEED_SLEWING, 1),
            "park dropped but echoed": (TelescopeSpeed.SPEED_TRACKING, 60),
        }
        for case, (speed, alt) in cases.items():
            with self.subTest(case):
                self.setUp()
                self.telescope.queue_park.side_effect = None
                self.telescope.status = TelescopeStatus.PARKED
                self.telescope.speed = speed
                self.telescope.aa_coords = AltazimutalCoords(alt=alt, az=359)

                state = await self.__closure()

                self.telescope.queue_park.assert_called_once_with()
                self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED)
                self.roof.close.assert_not_awaited()

    async def test_a_parked_mount_with_its_coordinates_in_alert_is_safe(self):
        self.telescope.status = TelescopeStatus.PARKED
        self.telescope.speed = TelescopeSpeed.SPEED_ERROR
        self.telescope.aa_coords = AltazimutalCoords(alt=0.5, az=359)

        state = await self.__closure()

        self.telescope.queue_park.assert_not_called()
        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_reading_from_before_the_closure_is_not_trusted(self):
        self.telescope.status = TelescopeStatus.SECURE
        self.telescope.aa_coords = AltazimutalCoords(alt=5, az=30)
        read_at = monotonic() - 0.2
        self.telescope.seconds_since_last_reading.side_effect = lambda: monotonic() - read_at

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_TELESCOPE_UNKNOWN)
        self.east.disable.assert_not_called()
        self.roof.close.assert_not_awaited()

    async def test_a_telescope_moved_while_the_curtains_go_down_keeps_the_roof_open(self):
        self.east.goes_down = False
        self.west.disable.side_effect = self.__unpark_and_lower_both_curtains

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_PARK_NOT_REACHED)
        self.roof.close.assert_not_awaited()

    def __unpark_and_lower_both_curtains(self):
        self.east.status = self.west.status = CurtainStatus.CURTAIN_DISABLED
        self.telescope.aa_coords = AltazimutalCoords(alt=45, az=30)

    async def test_curtains_not_disabled_in_time_block_the_closure(self):
        self.west.goes_down = False

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_CURTAINS_NOT_DISABLED)
        self.roof.close.assert_not_awaited()

    async def test_a_roof_that_does_not_close_blocks_the_closure(self):
        self.roof.close = AsyncMock(return_value=False)

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_ROOF_NOT_CLOSED)
        self.telescope.polling_end.assert_not_called()

    async def test_an_unexpected_failure_blocks_the_closure_and_is_logged(self):
        self.east.disable.side_effect = OSError("gpio busy")

        with self.assertLogs(MODULE, level="ERROR") as captured:
            state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_INTERNAL_ERROR)
        self.assertIsNotNone(captured.records[0].exc_info)
        self.roof.close.assert_not_awaited()

    async def test_the_start_names_its_triggers(self):
        with self.assertLogs(MODULE, level="INFO") as captured:
            await self.__closure()

        self.assertIn("EMERGENCY_CLOSURE_TRIGGER_WEATHER", captured.records[0].getMessage())

    async def test_a_block_is_logged_once(self):
        self.telescope.status = TelescopeStatus.LOST

        with self.assertLogs(MODULE, level="ERROR") as captured:
            for _ in range(3):
                await self.__closure()

        self.assertEqual(1, len([record for record in captured.records if record.levelname == "ERROR"]))
        self.assertIn("TELESCOPE_UNKNOWN", captured.records[0].getMessage())

    async def test_a_closure_in_progress_is_not_started_twice(self):
        self.procedure.report(WEATHER, True)
        self.procedure.report(WEATHER, True)
        self.procedure.report(UPS, True)
        await self.procedure._task

        self.telescope.queue_park.assert_called_once_with()
        self.roof.close.assert_awaited_once_with()

    async def test_a_telescope_readable_again_resumes_the_closure(self):
        self.telescope.status = TelescopeStatus.LOST
        await self.__closure()
        self.telescope.status = TelescopeStatus.NORTHEAST

        state = await self.__closure()

        self.telescope.queue_park.assert_called_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_telescope_still_unreadable_stays_blocked_since_the_first_time(self):
        self.telescope.status = TelescopeStatus.LOST
        first = await self.__closure()

        with patch(f"{MODULE}.time", return_value=first.status_since + 100):
            again = await self.__closure()

        self.assertEqual(BLOCKED, again.status)
        self.assertEqual(first.status_since, again.status_since)

    async def test_a_polling_stopped_while_blocked_is_started_again(self):
        self.telescope.status = TelescopeStatus.LOST
        await self.__closure()
        self.telescope.polling = False

        await self.__closure()

        self.telescope.polling_start.assert_called_with()

    async def test_a_park_not_reached_is_retried(self):
        self.telescope.queue_park.side_effect = None
        await self.__closure()
        self.telescope.queue_park.side_effect = self.__park

        state = await self.__closure()

        self.assertEqual(2, self.telescope.queue_park.call_count)
        self.assertEqual(COMPLETED, state.status)

    async def test_a_park_retried_in_vain_is_logged_once_and_keeps_its_time(self):
        self.telescope.queue_park.side_effect = None
        with patch(f"{MODULE}.time", return_value=1000):
            first = await self.__closure()

        with self.assertNoLogs(MODULE, level="INFO"):
            with patch(f"{MODULE}.time", return_value=2000):
                again = await self.__closure()

        self.assertEqual(2, self.telescope.queue_park.call_count)
        self.assertEqual(BLOCKED, again.status)
        self.assertEqual(first.status_since, again.status_since)

    async def test_curtains_or_roof_blocks_are_not_retried(self):
        self.west.goes_down = False
        await self.__closure()

        state = await self.__closure()

        self.__assert_blocked(state, EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_CURTAINS_NOT_DISABLED)
        self.assertEqual(1, self.east.disable.call_count)

    async def test_a_blocked_closure_with_the_roof_found_closed_is_completed(self):
        self.roof.close = AsyncMock(return_value=False)
        await self.__closure()
        self.roof.get_status.return_value = RoofStatus.ROOF_CLOSED

        state = await self.__closure()

        self.assertEqual(COMPLETED, state.status)
        self.assertEqual(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_UNSPECIFIED, state.block_reason)

    async def test_a_blocked_closure_with_nothing_critical_goes_idle(self):
        self.telescope.status = TelescopeStatus.LOST
        await self.__closure()

        state = await self.__closure(critical=False)

        self.assertEqual(IDLE, state.status)
        self.assertEqual([], list(state.triggers))
        self.assertEqual(EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_UNSPECIFIED, state.block_reason)

    async def test_a_roof_already_closed_completes_the_closure_without_moving_anything(self):
        self.roof.get_status.return_value = RoofStatus.ROOF_CLOSED

        state = await self.__closure()

        self.assertEqual(COMPLETED, state.status)
        self.assertEqual([WEATHER], list(state.triggers))
        self.telescope.queue_park.assert_not_called()
        self.roof.close.assert_not_awaited()

    async def test_a_roof_in_error_may_be_open_and_is_closed(self):
        self.roof.get_status.return_value = RoofStatus.ROOF_ERROR

        state = await self.__closure()

        self.roof.close.assert_awaited_once_with()
        self.assertEqual(COMPLETED, state.status)

    async def test_a_roof_opened_again_while_critical_starts_the_closure_again(self):
        await self.__closure()
        self.roof.get_status.return_value = RoofStatus.ROOF_OPENED
        self.telescope.status = TelescopeStatus.NORTHEAST

        state = await self.__closure()

        self.assertEqual(2, self.roof.close.await_count)
        self.assertEqual(COMPLETED, state.status)

    async def test_a_completed_closure_goes_idle_when_nothing_is_critical(self):
        await self.__closure()

        state = await self.__closure(critical=False)

        self.assertEqual(IDLE, state.status)
        self.assertEqual([], list(state.triggers))

    async def test_triggers_are_kept_until_idle(self):
        self.procedure.report(WEATHER, True)
        self.procedure.report(UPS, True)
        self.procedure.report(WEATHER, False)

        self.assertEqual([WEATHER, UPS], list(self.procedure.state().triggers))
        await self.procedure._task
        self.assertEqual([WEATHER, UPS], list(self.procedure.state().triggers))

    async def test_status_since_marks_the_last_change_of_status(self):
        with patch(f"{MODULE}.time", return_value=1000.7):
            self.procedure.report(WEATHER, True)
        self.assertEqual(1000, self.procedure.state().status_since)

        with patch(f"{MODULE}.time", return_value=2000):
            await self.procedure._task
            self.procedure.report(WEATHER, True)
        self.assertEqual(COMPLETED, self.procedure.state().status)
        self.assertEqual(2000, self.procedure.state().status_since)

    def __assert_blocked(self, state, reason):
        self.assertEqual(BLOCKED, state.status)
        self.assertEqual(reason, state.block_reason)


class TestEmergencyClosureReachesTheRoof(unittest.IsolatedAsyncioTestCase):
    """The roof motor is driven from the event loop: the closure is only
    useful if the real roof control ends up closed."""

    def setUp(self):
        Device.pin_factory.reset()
        self.addCleanup(Device.pin_factory.reset)
        self.roof = simulated_roof(travel_seconds=0.1)
        telescope = MagicMock()
        telescope.status = TelescopeStatus.PARKED
        telescope.aa_coords = AltazimutalCoords(alt=0, az=0)
        telescope.speed = TelescopeSpeed.SPEED_NOT_TRACKING
        telescope.seconds_since_last_reading.return_value = 0
        curtain = MagicMock()
        curtain.get_status.return_value = CurtainStatus.CURTAIN_DISABLED
        cover_mirror = MagicMock()
        cover_mirror.get_status.return_value = CoverMirrorStatus.COVER_MIRROR_CLOSED
        for name, double in {
            "roof": self.roof,
            "telescope": telescope,
            "curtain_east": curtain,
            "curtain_west": curtain,
            "cover_mirror": cover_mirror,
        }.items():
            patcher = patch(f"{MODULE}.{name}", return_value=double)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.procedure = EmergencyClosureProcedure()

    async def test_the_roof_is_closed_when_the_closure_is_over(self):
        await self.roof.open()

        self.procedure.report(WEATHER, True)
        await self.procedure._task

        self.assertEqual(RoofStatus.ROOF_CLOSED, self.roof.get_status())
        self.assertEqual(COMPLETED, self.procedure.state().status)

    async def test_a_roof_that_did_not_close_blocks_the_closure(self):
        await self.roof.open()
        self.roof.timeout = 0

        self.procedure.report(WEATHER, True)
        await self.procedure._task

        self.assertEqual(BLOCKED, self.procedure.state().status)
        self.assertEqual(
            EmergencyClosureBlockReason.EMERGENCY_CLOSURE_BLOCK_REASON_ROOF_NOT_CLOSED,
            self.procedure.state().block_reason,
        )


class TestEmergencyClosureConfiguration(unittest.TestCase):

    def test_every_timeout_is_required_at_startup(self):
        real_get_value = Config.getValue
        for key in ("park_timeout", "curtains_timeout", "max_reading_age"):
            with self.subTest(key=key):
                def without_key(name, section="automazione"):
                    return "" if (name, section) == (key, "emergency_closure") else real_get_value(name, section)

                with patch(f"{MODULE}.Config.getValue", side_effect=without_key):
                    with self.assertRaises(ValueError):
                        EmergencyClosureProcedure()
