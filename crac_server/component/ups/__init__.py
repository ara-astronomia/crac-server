import importlib
from crac_server.component.ups.ups import Ups
from crac_server.config import Config


UPS: Ups = importlib.import_module(f"crac_server.component.ups.{Config.getValue('driver', 'ups')}.ups").Ups(time_expired=Config.getInt("time_expired", "ups"))
