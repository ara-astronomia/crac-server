import importlib
from crac_server.component.telescope.telescope import Telescope
from crac_server.config import Config


TELESCOPE: Telescope = importlib.import_module(f"component.telescope.{Config.getValue('driver', 'telescope')}.telescope").TELESCOPE
