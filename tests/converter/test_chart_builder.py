import unittest

from crac_protobuf.chart_pb2 import ChartStatus
from crac_server.converter.chart_builder import build_chart


WIND_RANGES = {
    "range_normal": ({"lower_bound": 0, "upper_bound": 10},),
    "range_warn": ({"lower_bound": 10, "upper_bound": 36},),
    "range_danger": ({"lower_bound": 36, "upper_bound": 40},),
}

BAROMETER_RANGES = {
    "range_normal": ({"lower_bound": 1005, "upper_bound": 1045},),
    "range_warn": ({"lower_bound": 990, "upper_bound": 1005},),
    "range_danger": ({"lower_bound": 980, "upper_bound": 990},),
}


def _status(value, ranges):
    chart = build_chart(
        value=value,
        title="Vento",
        urn="weather.chart.test",
        min=0,
        max=40,
        unit_of_measurement="m/s",
        **ranges,
    )
    return chart.status


class TestBuildChartStatus(unittest.TestCase):
    """
    Bounds are the scale of the gauge, not the range the measure can take:
    a reading past the end of the scale still belongs to the outermost band,
    it is not an unknown reading.
    """

    def test_reports_the_band_the_value_falls_into(self):
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, _status(5, WIND_RANGES))
        self.assertEqual(ChartStatus.CHART_STATUS_WARNING, _status(20, WIND_RANGES))
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, _status(38, WIND_RANGES))

    def test_reports_danger_above_the_top_of_the_scale(self):
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, _status(120, WIND_RANGES))

    def test_reports_danger_below_the_bottom_of_the_scale(self):
        self.assertEqual(ChartStatus.CHART_STATUS_DANGER, _status(900, BAROMETER_RANGES))

    def test_reports_normal_above_the_top_of_the_scale_when_the_top_band_is_normal(self):
        self.assertEqual(ChartStatus.CHART_STATUS_NORMAL, _status(1100, BAROMETER_RANGES))

    def test_keeps_the_measured_value_untouched_when_out_of_scale(self):
        chart = build_chart(
            value=120,
            title="Vento",
            urn="weather.chart.test",
            min=0,
            max=40,
            unit_of_measurement="m/s",
            **WIND_RANGES,
        )
        self.assertEqual(120, chart.value)

    def test_reports_unspecified_without_any_threshold(self):
        chart = build_chart(
            value=5,
            title="Vento",
            urn="weather.chart.test",
            min=0,
            max=40,
            unit_of_measurement="m/s",
            range_normal=tuple(),
        )
        self.assertEqual(ChartStatus.CHART_STATUS_UNSPECIFIED, chart.status)


if __name__ == "__main__":
    unittest.main()
