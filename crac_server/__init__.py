from crac_server.config import Config
import logging

logger = logging.getLogger(__name__)

if Config.getBoolean("gpio_mock", "server"):
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory
        if Device.pin_factory is not None:
            Device.pin_factory.reset()
        Device.pin_factory = MockFactory()
    except ImportError:
        logger.warning("gpiozero non installato. I test hardware o i mock gpiozero non funzioneranno.")
