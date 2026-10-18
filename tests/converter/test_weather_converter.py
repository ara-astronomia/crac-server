import unittest
from unittest.mock import patch

from crac_protobuf.chart_pb2 import ChartStatus, WeatherStatus
from crac_server.converter.chart_builder import build_chart
from crac_server.converter.chart_config import ChartConfigError
from crac_server.converter.weather_converter import WeatherConverter


class FakeWeather:
    wind_speed = (7, "km/h")
    wind_gust_speed = (8, "km/h")
    temperature = (27, "°C")
    humidity = (70, "%")
    rain_rate = (0.5, "mm/h")
    barometer = (1015, "mbar")
    barometer_trend = (0, "mbar")
    updated_at = None
    time_expired = 660
    is_unavailable = False


class TestWeatherConverter(unittest.TestCase):

    def _convert(self, **readings):
        weather = FakeWeather()
        for name, value in readings.items():
            setattr(weather, name, (value, "x"))
        return WeatherConverter().convert(weather)

    def test_convert_builds_a_chart_for_every_configured_section(self):
        response = self._convert()

        self.assertEqual(
            {
                "weather.chart.wind",
                "weather.chart.wind_gust",
                "weather.chart.temperature",
                "weather.chart.humidity",
                "weather.chart.rain_rate",
                "weather.chart.barometer",
                "weather.chart.barometer_trend",
            },
            {chart.urn for chart in response.charts},
        )

    def test_a_reading_below_every_threshold_reports_normal(self):
        response = self._convert()

        self.assertEqual(WeatherStatus.WEATHER_STATUS_NORMAL, response.status)

    def test_a_high_wind_is_a_danger_above_and_a_warning_below(self):
        response = self._convert(wind_speed=20)
        self.assertEqual(WeatherStatus.WEATHER_STATUS_WARNING, response.status)

        response = self._convert(wind_speed=38)
        self.assertEqual(WeatherStatus.WEATHER_STATUS_DANGER, response.status)

    def test_a_low_barometer_is_a_danger_below_and_a_warning_above(self):
        response = self._convert(barometer=995)
        self.assertEqual(WeatherStatus.WEATHER_STATUS_WARNING, response.status)

        response = self._convert(barometer=985)
        self.assertEqual(WeatherStatus.WEATHER_STATUS_DANGER, response.status)

    def test_an_informative_chart_does_not_make_the_weather_unknown(self):
        informative = build_chart(value=5, title="t", urn="informative", min=0, max=40, unit_of_measurement="x", range_normal=tuple())
        classified = build_chart(
            value=5, title="t", urn="classified", min=0, max=40, unit_of_measurement="x",
            range_normal=({"lower_bound": 0, "upper_bound": 40},),
        )

        status = WeatherConverter().calculate_status(FakeWeather(), [informative, classified])

        self.assertEqual(WeatherStatus.WEATHER_STATUS_NORMAL, status)

    def test_validate_config_raises_on_a_broken_section(self):
        with patch(
            "crac_server.converter.weather_converter.build_chart_from_config",
            side_effect=ChartConfigError("[wind_speed]: broken"),
        ):
            with self.assertRaises(ChartConfigError):
                WeatherConverter().validate_config()


if __name__ == "__main__":
    unittest.main()
