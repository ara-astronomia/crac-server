from datetime import datetime
import unittest
from unittest.mock import patch
from crac_server.component.weather.weather import Weather

class TestWeather(unittest.TestCase):

    def retrieve(self):
        self.weather.json = {
            "outTemp": {
                "value": self.input_temperature[0],
                "unit_of_measurement": self.input_temperature[1]
            }
        }
        self.weather.updated_at = datetime.now().strftime(self.format)

    def setUp(self) -> None:
        self.format = "%Y-%m-%d %H:%M:%S"
        self.weather = Weather("https://ara.roma.it/meteo/current.json", self.format, 600)
        self.input_temperature = ("21,5", "°C")
        self.expected_temperature = (21.5, "°C")
    
    def tearDown(self) -> None:
        self.weather = None

    def test_is_expired(self):
        self.assertTrue(self.weather.is_expired(), "Is not Expired")
        with patch.object(Weather, '_Weather__retrieve_data', return_value=self.retrieve()) as mock_method:
            self.weather.temperature
        self.assertFalse(self.weather.is_expired(), "Is Expired")
    
    def test_get_sensor(self):
        with patch.object(Weather, '_Weather__retrieve_data', return_value=self.retrieve()) as mock_method:
            temperature = self.weather.temperature

        self.assertEqual(self.expected_temperature, temperature)
