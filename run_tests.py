"""Run only mock/simulator tests: service, converter and integration (GPIO simulators)."""
import sys
import unittest

TEST_DIRS = [
    "tests/unit/service",
    "tests/unit/converter",
    "tests/integration",
]

loader = unittest.TestLoader()
suite = unittest.TestSuite()
for path in TEST_DIRS:
    suite.addTests(loader.discover(path, top_level_dir="."))

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
