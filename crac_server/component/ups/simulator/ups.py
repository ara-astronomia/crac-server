import os
from configparser import ConfigParser
from crac_server.component.ups.ups import Ups as UpsBase


class Ups(UpsBase):
    def status_for(self, device: str) -> dict[str,str]:
        ups_path = os.path.join(os.path.dirname(__file__), "ups.ini")
        ups_config = ConfigParser()
        ups_config.read(ups_path)
        voltage = ups_config.get(device, "output.voltage", fallback='220')
        battery = ups_config.get(device, "battery.charge", fallback='100')
        ups_config[device] = {"output.voltage": voltage, "battery.charge": battery}
        with open(ups_path, 'w') as ups_file:
            ups_config.write(ups_file)
        return {
            'driver.parameter.synchronous': 'no', 
            'battery.runtime.low': '120', 
            'ups.vendorid': '051d', 
            'ups.mfr': 'American Power Conversion', 
            'ups.timer.shutdown': '-1', 
            'battery.mfr.date': '2009/09/16', 
            'output.voltage': ups_config.get(device, "output.voltage", fallback='0'), 
            'driver.parameter.pollfreq': '30', 
            'battery.type': 'PbAc', 
            'ups.productid': '0002', 
            'battery.voltage': '55.4', 
            'ups.timer.start': '-1', 
            'driver.parameter.vendorId': '051d', 
            'driver.version.internal': '0.41', 
            'input.sensitivity': 'low', 
            'driver.name': 'usbhid-ups', 
            'driver.version.data': 'APC HID 0.96', 
            'ups.delay.shutdown': '20', 
            'output.frequency': '50.0', 
            'output.voltage.nominal': "230",
            'battery.runtime': '13980', 
            'device.model': 'Smart-UPS 3000 RM', 
            'input.transfer.low': '208', 
            'ups.beeper.status': 'enabled', 
            'driver.parameter.pollinterval': '2', 
            'driver.parameter.port': 'auto', 
            'battery.charge.warning': "50",
            'input.transfer.high': '253', 
            'ups.model': 'Smart-UPS 3000 RM', 
            'device.mfr': 'American Power Conversion', 
            'ups.timer.reboot': '-1', 
            'output.current': '0.00', 
            'battery.charge': ups_config.get(device, "battery.charge", fallback='0'),
            'input.voltage': '217.4', 
            'ups.firmware.aux': '7.4', 
            'device.serial': 'JS0938004696', 
            'ups.delay.start': '30', 
            'driver.version': '2.7.4', 
            'device.type': 'ups', 
            'ups.firmware': '666.6.I', 
            'ups.test.result': 'No test initiated', 
            'driver.parameter.productId': '0002', 
            'battery.temperature': '13.0', 
            'ups.load': '0.0', 
            'battery.voltage.nominal': '48.0', 
            'battery.charge.low': "10", 
            'ups.mfr.date': '2009/09/16', 
            'ups.serial': 'JS0938004696', 
            'ups.status': 'OL'
        }
