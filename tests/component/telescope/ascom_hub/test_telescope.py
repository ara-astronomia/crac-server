from typing import Any
import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, MagicMock, patch
from crac_server.component.telescope.ascom_hub.telescope import Telescope
from crac_protobuf.telescope_pb2 import (
    AltazimutalCoords, 
    EquatorialCoords, 
    TelescopeSpeed
)

class TestTelescope(unittest.TestCase):
    
    def setUp(self) -> None:
        self._host = "ara.test"
        self._port = 1
        self.telescope = Telescope(hostname=self._host, port=self._port)
        self.telescope._has_tracking_off_capability = True
        self.telescope._flat_coordinate = AltazimutalCoords(alt=0, az=2)
        self.telescope._merge_client_information = self.mocked_merge_client_information

    def mocked_put_request(self):
        response = MagicMock()
        response.json.return_value = {
            "ErrorNumber": 0,
            "ErrorMessage": "string"
        }
        request = MagicMock()
        request.put.return_value = response
        return request

    def mocked_get_request(self):
        response = MagicMock()
        response.json.return_value = {
            "ErrorNumber": 0,
            "ErrorMessage": "string",
            "Value": "0"
        }
        request = MagicMock()
        request.get.return_value = response
        return request
    
    def mocked_has_tracking_off_capability(self):
        return True

    def mocked_merge_client_information(self, data: dict[str, Any] = {}):
        return data | {"ClientId": 1, "ClientTransactionID": 1}
    
    def mocked_calculate_eq_coords_of_park_position(self, started_at):
        return EquatorialCoords(dec=0, ra=0)

    @patch('requests.put')
    def test_sync(self, request):
        request.return_value = self.mocked_put_request()
        self.telescope._calculate_eq_coords_of_park_position = self.mocked_calculate_eq_coords_of_park_position
        self.telescope.sync(datetime.now())
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/tracking', data={"Tracking": True, "ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/unpark', data={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/synctocoordinates', data={"RightAscension": 0, "Declination": 0, "ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/setpark', data={"ClientId": 1, "ClientTransactionID": 1})
        request.reset_mock()

    @patch('requests.put')
    def test_set_speed(self, request):
        request.return_value = self.mocked_put_request()
        self.telescope.set_speed(TelescopeSpeed.SPEED_TRACKING)
        request.assert_called_with(f'http://{self._host}:{self._port}/api/v1/telescope/0/tracking', data={"Tracking": True, "ClientId": 1, "ClientTransactionID": 1})
        request.reset_mock()

    @patch('requests.put')
    def test_park(self, request):
        request.return_value = self.mocked_put_request()
        self.telescope.park()
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/park', data={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/tracking', data={"Tracking": False, "ClientId": 1, "ClientTransactionID": 1})
        request.reset_mock()

    @patch('requests.put')
    def test_flat(self, request):
        request.return_value = self.mocked_put_request()
        eq_coords = self.telescope._altaz2radec(aa_coords=self.telescope._flat_coordinate, obstime=datetime.utcnow(), decimal_places=3)
        self.telescope.flat()
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/slewtocoordinates', data={"RightAscension": eq_coords.ra, "Declination": eq_coords.dec, "ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/tracking', data={"Tracking": False, "ClientId": 1, "ClientTransactionID": 1})
        request.reset_mock()
    
    @patch('requests.get')
    def test_retrieve(self, request):
        request.return_value = self.mocked_get_request()
        self.telescope.retrieve()
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/altitude', params={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/azimuth', params={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/declination', params={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/rightascension', params={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/tracking', params={"ClientId": 1, "ClientTransactionID": 1})
        request.assert_any_call(f'http://{self._host}:{self._port}/api/v1/telescope/0/slewing', params={"ClientId": 1, "ClientTransactionID": 1})
    
    def test_retrieve_mocked_get(self):
        az_coords = AltazimutalCoords(alt=0, az=0)
        eq_coords = EquatorialCoords(dec=45, ra=5)
        self.telescope._retrieve_aa_coords = MagicMock(return_value=az_coords)
        self.telescope._retrieve_eq_coords = MagicMock(return_value=eq_coords)
        self.telescope._retrieve_speed = MagicMock(return_value=TelescopeSpeed.SPEED_TRACKING)
        indicators = self.telescope.retrieve()
        self.assertEqual(indicators, (eq_coords, az_coords, TelescopeSpeed.SPEED_TRACKING, ANY))

    def test_rounded_radec2altaz(self):
        eq_coords = EquatorialCoords(ra=9.364493538084828, dec=47.962112290530065)
        aa_coords = self.telescope._radec2altaz(eq_coords, datetime(2020, 12, 6, 15, 29, 43, 79060, tzinfo=timezone.utc), 2)
        self.assertEqual(aa_coords.az, 0.20)
        self.assertEqual(aa_coords.alt, 0.1)
    
    def test_rounded_altaz2radec(self):
        eq_coords = AltazimutalCoords(az=0.20000345603265943, alt=0.09999827706661533)
        eq_coords = self.telescope._altaz2radec(eq_coords, datetime(2020, 12, 6, 15, 29, 43, 79060, tzinfo=timezone.utc), 2)
        self.assertEqual(eq_coords.ra, 9.36)
        self.assertEqual(eq_coords.dec, 47.96)
