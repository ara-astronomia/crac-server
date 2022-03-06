from crac_server.config import Config


if Config.getBoolean("gpio_mock", "server"):
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory
    if Device.pin_factory is not None:
        Device.pin_factory.reset()
    Device.pin_factory = MockFactory()