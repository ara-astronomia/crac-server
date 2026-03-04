import unittest
from unittest.mock import MagicMock, PropertyMock
from crac_server.component.weather.weather import Weather
from crac_server.converter.weather_converter import WeatherConverter
from crac_protobuf.chart_pb2 import ChartStatus

class TestWeatherConverter(unittest.TestCase):
    def setUp(self):
        self.weather = MagicMock(spec=Weather)
        self.converter = WeatherConverter()

    def test_convert_with_na_values(self):
        # Mocking weather sensors returning 'N/A'
        type(self.weather).wind_speed = PropertyMock(return_value=('N/A', "m/s"))
        type(self.weather).wind_gust_speed = PropertyMock(return_value=('N/A', "m/s"))
        type(self.weather).temperature = PropertyMock(return_value=('N/A', "°C"))
        type(self.weather).humidity = PropertyMock(return_value=('N/A', "%"))
        type(self.weather).rain_rate = PropertyMock(return_value=('N/A', "mm/h"))
        type(self.weather).barometer = PropertyMock(return_value=('N/A', "mbar"))
        type(self.weather).barometer_trend = PropertyMock(return_value=('N/A', "mbar"))
        self.weather.updated_at = None
        self.weather.time_expired = 600
        self.weather.is_unavailable = False

        response = self.converter.convert(self.weather)

        # The requirement is: "avoid creating the chart" if value is non-numeric
        self.assertEqual(len(response.charts), 0)

    def test_convert_with_some_na_values(self):
        # Mixed numeric and N/A values
        type(self.weather).wind_speed = PropertyMock(return_value=(10.0, "m/s"))
        type(self.weather).wind_gust_speed = PropertyMock(return_value=('N/A', "m/s"))
        type(self.weather).temperature = PropertyMock(return_value=('N/A', "°C"))
        type(self.weather).humidity = PropertyMock(return_value=('N/A', "%"))
        type(self.weather).rain_rate = PropertyMock(return_value=('N/A', "mm/h"))
        type(self.weather).barometer = PropertyMock(return_value=('N/A', "mbar"))
        type(self.weather).barometer_trend = PropertyMock(return_value=('N/A', "mbar"))
        self.weather.updated_at = None
        self.weather.time_expired = 600
        self.weather.is_unavailable = False

        response = self.converter.convert(self.weather)

        self.assertEqual(len(response.charts), 1)
        self.assertEqual(response.charts[0].title, "Vento")
        self.assertEqual(response.charts[0].value, 10.0)

if __name__ == '__main__':
    unittest.main()
