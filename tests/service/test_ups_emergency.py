import unittest
from unittest.mock import patch

from crac_protobuf.chart_pb2 import Chart, ChartStatus
from crac_protobuf.ups_pb2 import BatteryStatus, UpsChart

from crac_server.service.ups_emergency import (
    critical_thresholds,
    enabled_checks,
    ups_emergency,
)


def emergency_config(enabled_checks):
    values = {
        ("enabled_checks", "ups_emergency"): enabled_checks,
        ("critical_time", "ups_emergency"): "300",
        ("critical_battery_percentage", "ups_emergency"): "60",
    }
    return lambda key, section="automazione": values[(key, section)]


def on_battery_chart():
    return UpsChart(
        chart=Chart(),
        battery_statuses=[BatteryStatus.BATTERY_STATUS_ONBATTERY],
    )


def online_chart():
    return UpsChart(
        chart=Chart(),
        battery_statuses=[BatteryStatus.BATTERY_STATUS_ONLINE],
    )


def current_chart(status):
    return UpsChart(chart=Chart(status=status))


class TestEnabledChecks(unittest.TestCase):

    def test_the_whitelist_is_read_from_the_config(self):
        self.assertEqual({"battery_charge", "ups_status"}, enabled_checks())

    def test_an_unknown_name_is_an_error(self):
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("battery_charge,input_voltage")):
            with self.assertRaises(RuntimeError) as ctx:
                enabled_checks()
        self.assertIn("input_voltage", str(ctx.exception))

    def test_an_empty_whitelist_is_an_error(self):
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("")):
            with self.assertRaises(RuntimeError) as ctx:
                enabled_checks()
        self.assertIn("enabled_checks", str(ctx.exception))


class TestCriticalThresholds(unittest.TestCase):

    def test_the_thresholds_are_read_from_the_config(self):
        self.assertEqual(300, critical_thresholds().critical_time)
        self.assertEqual(60, critical_thresholds().critical_battery_percentage)


class TestUpsEmergency(unittest.TestCase):
    """The two trigger checks: a low battery closes at once, a device on
    battery or with a dangerous current only after critical_time seconds."""

    def setUp(self):
        ups_emergency.cache_clear()
        self.addCleanup(ups_emergency.cache_clear)

    def _is_critical(self, reading, charts_by_key, device="apc-3000"):
        return ups_emergency().device_is_critical(device, reading, charts_by_key)

    def _can_be_judged(self, reading, charts_by_key, device="apc-3000"):
        return ups_emergency().can_be_judged(device, reading, charts_by_key)

    def test_a_battery_at_the_critical_percentage_is_critical_at_once(self):
        self.assertTrue(self._is_critical({"battery_charge": "60", "ups_status": "OL"}, {"battery_charge": online_chart()}))
    def test_a_battery_below_the_critical_percentage_is_critical_at_once(self):
        self.assertTrue(self._is_critical({"battery_charge": "20", "ups_status": "OL"}, {"battery_charge": online_chart()}))

    def test_a_battery_above_the_critical_percentage_is_not_critical(self):
        self.assertFalse(self._is_critical({"battery_charge": "61", "ups_status": "OL"}, {"battery_charge": online_chart()}))

    def test_a_device_on_battery_is_not_critical_before_critical_time(self):
        with patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0]):
            self.assertFalse(self._is_critical({"battery_charge": "100", "ups_status": "OB"}, {"battery_charge": on_battery_chart()}))

    def test_a_device_on_battery_is_critical_after_critical_time(self):
        charts = {"battery_charge": on_battery_chart()}
        reading = {"battery_charge": "100", "ups_status": "OB"}
        with patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 300, 300]):
            self.assertFalse(self._is_critical(reading, charts))
            self.assertTrue(self._is_critical(reading, charts))

    def test_the_sustained_count_starts_over_when_the_condition_stops(self):
        charts_on_battery = {"battery_charge": on_battery_chart()}
        charts_online = {"battery_charge": online_chart()}
        on_battery = {"battery_charge": "100", "ups_status": "OB"}
        online = {"battery_charge": "100", "ups_status": "OL"}
        with patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 100, 100, 200, 200, 499, 499, 500, 500]):
            self.assertFalse(self._is_critical(on_battery, charts_on_battery))
            self.assertFalse(self._is_critical(online, charts_online))
            self.assertFalse(self._is_critical(on_battery, charts_on_battery))
            self.assertFalse(self._is_critical(on_battery, charts_on_battery))
            self.assertTrue(self._is_critical(on_battery, charts_on_battery))

    def test_a_dangerous_current_needs_critical_time_too(self):
        reading = {"battery_charge": "100", "ups_status": "OL"}
        charts = {"battery_charge": online_chart(), "output_current": current_chart(ChartStatus.CHART_STATUS_DANGER)}
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("battery_charge,ups_status,output_current")), \
             patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 299, 299, 300, 300]):
            self.assertFalse(self._is_critical(reading, charts))
            self.assertFalse(self._is_critical(reading, charts))
            self.assertTrue(self._is_critical(reading, charts))

    def test_on_battery_and_a_dangerous_current_hold_the_same_count(self):
        reading = {"battery_charge": "100", "ups_status": "OB"}
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("battery_charge,ups_status,output_current")), \
             patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 300, 300]):
            self.assertFalse(self._is_critical(reading, {"battery_charge": on_battery_chart(), "output_current": current_chart(ChartStatus.CHART_STATUS_NORMAL)}))
            self.assertTrue(self._is_critical(reading, {"battery_charge": online_chart(), "output_current": current_chart(ChartStatus.CHART_STATUS_DANGER)}))

    def test_a_normal_current_never_becomes_critical(self):
        reading = {"battery_charge": "100", "ups_status": "OL"}
        charts = {"battery_charge": online_chart(), "output_current": current_chart(ChartStatus.CHART_STATUS_NORMAL)}
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("battery_charge,ups_status,output_current")), \
             patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 600, 600]):
            self.assertFalse(self._is_critical(reading, charts))
            self.assertFalse(self._is_critical(reading, charts))

    def test_device_lost_starts_the_sustained_count_over(self):
        reading = {"battery_charge": "100", "ups_status": "OB"}
        charts = {"battery_charge": on_battery_chart()}
        with patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 400, 400]):
            self.assertFalse(self._is_critical(reading, charts))
            ups_emergency().device_lost("apc-3000")
            self.assertFalse(self._is_critical(reading, charts))

    def test_an_enabled_check_without_a_reading_is_an_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._is_critical({"battery_charge": None, "ups_status": "OL"}, {"battery_charge": online_chart()})
        self.assertIn("battery_charge", str(ctx.exception))

    def test_an_enabled_ups_status_without_a_reading_is_an_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            self._is_critical({"battery_charge": "100"}, {"battery_charge": online_chart()})
        self.assertIn("ups_status", str(ctx.exception))

    def test_an_enabled_output_current_without_a_chart_is_an_error(self):
        reading = {"battery_charge": "100", "ups_status": "OL"}
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("battery_charge,ups_status,output_current")):
            with self.assertRaises(RuntimeError) as ctx:
                self._is_critical(reading, {"battery_charge": online_chart()})
        self.assertIn("output_current", str(ctx.exception))

    def test_a_complete_reading_can_be_judged(self):
        reading = {"battery_charge": "100", "ups_status": "OL"}
        charts = {"battery_charge": online_chart()}
        self.assertTrue(self._can_be_judged(reading, charts))

    def test_a_reading_without_an_enabled_check_cannot_be_judged(self):
        charts = {"battery_charge": online_chart()}
        self.assertFalse(self._can_be_judged({"ups_status": "OL"}, charts))

    def test_an_enabled_ups_status_without_the_battery_chart_cannot_be_judged(self):
        reading = {"battery_charge": "100", "ups_status": "OL"}
        self.assertFalse(self._can_be_judged(reading, {}))

    def test_an_enabled_output_current_without_a_chart_cannot_be_judged(self):
        reading = {"battery_charge": "100", "ups_status": "OL"}
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("battery_charge,ups_status,output_current")):
            self.assertFalse(self._can_be_judged(reading, {"battery_charge": online_chart()}))

    def test_a_check_that_is_not_enabled_is_never_evaluated(self):
        reading = {"ups_status": "OL"}
        charts = {"battery_charge": online_chart()}
        with patch("crac_server.service.ups_emergency.Config.getValue", side_effect=emergency_config("ups_status")), \
             patch("crac_server.service.ups_emergency.monotonic", side_effect=[0, 0, 600, 600]):
            self.assertFalse(self._is_critical(reading, charts))
            self.assertFalse(self._is_critical(reading, charts))


if __name__ == "__main__":
    unittest.main()
