import importlib
from crac_server.component.ups.ups import Ups
from crac_server.config import Config


UPS: Ups = importlib.import_module(f"crac_server.component.ups.{Config.getValue('driver', 'ups')}.ups").Ups(host=Config.getValue("hostname", "ups"), login=Config.getValue("login", "ups"), password=Config.getValue("password", "ups"), time_expired=Config.getInt("time_expired", "ups"))
