import os
import subprocess
import sys
import unittest


MODULES = (
    "crac_server",
    "crac_server.component.roof",
    "crac_server.component.telescope",
    "crac_server.component.curtains.factory_curtain",
    "crac_server.component.weather",
    "crac_server.component.cover_mirror",
    "crac_server.component.button_control",
    "crac_server.handler.roof_handler",
    "crac_server.handler.curtains_handler",
    "crac_server.service.roof_service",
)


class TestImportHasNoSideEffects(unittest.TestCase):
    """
    Importing a module must not read the configuration nor open GPIO pins: what
    gets read at import time is frozen for the life of the process and belongs
    to whoever started it, not to whoever imported it.

    The check runs in a process pointed at a configuration file that does not
    exist and with no pin factory chosen, so any read or any device built while
    importing fails loudly.
    """

    def test_modules_import_without_configuration_and_without_gpio(self):
        environment = {
            key: value for key, value in os.environ.items()
            if key not in ("CRAC_CONFIG_PATH", "GPIOZERO_PIN_FACTORY")
        }
        environment["CRAC_CONFIG_PATH"] = "/nonexistent/config.ini"

        result = subprocess.run(
            [sys.executable, "-c", "\n".join(f"import {module}" for module in MODULES)],
            env=environment,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr[-2000:])
