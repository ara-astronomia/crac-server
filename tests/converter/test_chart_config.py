import unittest
from unittest.mock import patch

from crac_protobuf.chart_pb2 import ChartStatus, ThresholdType
from crac_server.converter.chart_config import ChartConfigError, build_chart_from_config


def build(sections, section, value):
    with patch(
        "crac_server.converter.chart_config.Config.get_section_keys",
        side_effect=lambda name: list(sections[name]),
    ), patch(
        "crac_server.converter.chart_config.Config.getValue",
        side_effect=lambda key, section="": sections[section][key],
    ):
        return build_chart_from_config(
            section, value=value, title="Titolo", urn=f"test.chart.{section}", unit_of_measurement="x"
        )


def bands(chart):
    return [
        (ThresholdType.Name(threshold.threshold_type), threshold.lower_bound, threshold.upper_bound)
        for threshold in chart.thresholds
    ]


class TestConfiguredBands(unittest.TestCase):
    def test_danger_above(self):
        chart = build(
            {"wind_speed": {"scale": "0..40", "warning": "10..", "danger": "36.."}},
            "wind_speed", value=20,
        )

        self.assertEqual(
            [
                ("THRESHOLD_TYPE_NORMAL", 0.0, 10.0),
                ("THRESHOLD_TYPE_WARNING", 10.0, 36.0),
                ("THRESHOLD_TYPE_DANGER", 36.0, 40.0),
            ],
            bands(chart),
        )
        self.assertEqual(0.0, chart.min)
        self.assertEqual(40.0, chart.max)

    def test_danger_below(self):
        chart = build(
            {"barometer": {"scale": "980..1045", "warning": "..1005", "danger": "..990"}},
            "barometer", value=1000,
        )

        self.assertEqual(
            [
                ("THRESHOLD_TYPE_NORMAL", 1005.0, 1045.0),
                ("THRESHOLD_TYPE_WARNING", 990.0, 1005.0),
                ("THRESHOLD_TYPE_DANGER", 980.0, 990.0),
            ],
            bands(chart),
        )

    def test_danger_on_both_sides_of_the_safe_range(self):
        chart = build(
            {"input_voltage": {"scale": "0..250", "warning": "..209", "danger": "241.5.."}},
            "input_voltage", value=220,
        )

        self.assertEqual(
            [
                ("THRESHOLD_TYPE_NORMAL", 209.0, 241.5),
                ("THRESHOLD_TYPE_WARNING", 0.0, 209.0),
                ("THRESHOLD_TYPE_DANGER", 241.5, 250.0),
            ],
            bands(chart),
        )

    def test_danger_in_the_middle_leaves_normal_on_both_sides(self):
        chart = build(
            {"metric": {"scale": "0..30", "danger": "10..20"}},
            "metric", value=15,
        )

        self.assertEqual(
            [
                ("THRESHOLD_TYPE_NORMAL", 0.0, 10.0),
                ("THRESHOLD_TYPE_NORMAL", 20.0, 30.0),
                ("THRESHOLD_TYPE_DANGER", 10.0, 20.0),
            ],
            bands(chart),
        )

    def test_warning_only_keeps_the_chart_informative_below_it(self):
        chart = build(
            {"temperature": {"scale": "-10..40", "warning": "35.."}},
            "temperature", value=20,
        )

        self.assertEqual(
            [
                ("THRESHOLD_TYPE_NORMAL", -10.0, 35.0),
                ("THRESHOLD_TYPE_WARNING", 35.0, 40.0),
            ],
            bands(chart),
        )

    def test_a_section_with_no_levels_builds_an_informative_chart(self):
        chart = build({"metric": {"scale": "0..40"}}, "metric", value=5)

        self.assertEqual([], bands(chart))
        self.assertEqual(ChartStatus.CHART_STATUS_UNSPECIFIED, chart.status)

    def test_a_comma_repeats_the_level(self):
        chart = build(
            {"metric": {"scale": "0..250", "danger": "..209, 241.5.."}},
            "metric", value=220,
        )

        self.assertEqual(
            [
                ("THRESHOLD_TYPE_NORMAL", 209.0, 241.5),
                ("THRESHOLD_TYPE_DANGER", 0.0, 209.0),
                ("THRESHOLD_TYPE_DANGER", 241.5, 250.0),
            ],
            bands(chart),
        )


class TestConfiguredStatus(unittest.TestCase):
    def _status(self, value):
        chart = build(
            {"wind_speed": {"scale": "0..40", "warning": "10..", "danger": "36.."}},
            "wind_speed", value=value,
        )
        return chart.status

    def test_the_value_falls_into_the_expected_level(self):
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, self._status(5))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._status(20))
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._status(38))

    def test_a_boundary_belongs_to_the_more_severe_level(self):
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, self._status(10))
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._status(36))

    def test_a_reading_past_the_scale_keeps_the_outermost_level(self):
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, self._status(120))
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, self._status(-5))


class TestBrokenConfigurations(unittest.TestCase):
    def test_a_section_without_scale_is_refused(self):
        with self.assertRaises(ChartConfigError) as ctx:
            build({"metric": {"warning": "10.."}}, "metric", value=0)
        self.assertIn("scale", str(ctx.exception))

    def test_an_unknown_key_is_refused(self):
        with self.assertRaises(ChartConfigError) as ctx:
            build({"metric": {"scale": "0..40", "erorr": "36.."}}, "metric", value=0)
        self.assertIn("erorr", str(ctx.exception))

    def test_a_range_without_separator_is_refused(self):
        with self.assertRaises(ChartConfigError):
            build({"metric": {"scale": "0..40", "danger": "36"}}, "metric", value=0)

    def test_an_inverted_range_is_refused(self):
        with self.assertRaises(ChartConfigError) as ctx:
            build({"metric": {"scale": "0..40", "danger": "30..20"}}, "metric", value=0)
        self.assertIn("30..20", str(ctx.exception))

    def test_a_range_outside_the_scale_is_refused(self):
        with self.assertRaises(ChartConfigError) as ctx:
            build({"metric": {"scale": "0..40", "danger": "50..60"}}, "metric", value=0)
        self.assertIn("50..60", str(ctx.exception))

    def test_a_non_numeric_endpoint_is_refused(self):
        with self.assertRaises(ChartConfigError):
            build({"metric": {"scale": "0..40", "danger": "thirty.."}}, "metric", value=0)

    def test_an_emptied_level_is_refused(self):
        with self.assertRaises(ChartConfigError) as ctx:
            build({"metric": {"scale": "0..40", "warning": ""}}, "metric", value=0)
        self.assertIn("warning", str(ctx.exception))

    def test_a_missing_section_is_refused(self):
        with self.assertRaises(ChartConfigError) as ctx:
            build({}, "metric", value=0)
        self.assertIn("missing", str(ctx.exception))


class TestConfiguredSmells(unittest.TestCase):
    """A smell reads different from what it says: it does not stop the
    startup, but it is logged every time the config is parsed."""

    def test_a_dotted_endpoint_is_logged(self):
        with self.assertLogs("crac_server.converter.chart_config", level="WARNING") as logs:
            build({"metric": {"scale": "0..40", "danger": "0...5"}}, "metric", value=0)

        self.assertIn("0...5", "".join(logs.output))

    def test_a_range_clamped_to_the_scale_is_logged(self):
        with self.assertLogs("crac_server.converter.chart_config", level="WARNING") as logs:
            build({"metric": {"scale": "0..40", "danger": "20..60"}}, "metric", value=0)

        self.assertIn("20..60", "".join(logs.output))

    def test_a_warning_entirely_covered_by_danger_is_logged(self):
        with self.assertLogs("crac_server.converter.chart_config", level="WARNING") as logs:
            build({"metric": {"scale": "0..40", "warning": "10..20", "danger": "0..40"}}, "metric", value=0)

        self.assertIn("covered", "".join(logs.output))

    def test_overlapping_ranges_of_the_same_level_are_logged(self):
        with self.assertLogs("crac_server.converter.chart_config", level="WARNING") as logs:
            build({"metric": {"scale": "0..40", "danger": "10..20, 15..25"}}, "metric", value=0)

        self.assertIn("overlap", "".join(logs.output))

    def test_a_clean_section_logs_nothing(self):
        with self.assertNoLogs("crac_server.converter.chart_config", level="WARNING"):
            build({"wind_speed": {"scale": "0..40", "warning": "10..", "danger": "36.."}}, "wind_speed", value=20)


if __name__ == "__main__":
    unittest.main()
