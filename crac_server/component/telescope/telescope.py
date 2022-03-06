import importlib
from crac_server.component import telescope

from crac_server.config import Config


TELESCOPE: telescope.Telescope = importlib.import_module(f"component.telescope.{Config.getValue('driver', 'telescope')}.telescope").TELESCOPE
