# AGENTS.md - Development Guide for CRAC Server

This document provides comprehensive guidelines for any agent or developer working on the CRAC Server codebase. It is designed to be the single point of truth for project standards, hardware interaction, and operational workflows.

## 1. Project Overview
CRAC (Control and Remote Astronomical Center) Server is a gRPC-based middleware designed to control astronomical observatory hardware. It is specifically optimized for Raspberry Pi (Zero 2 or greater) and provides a unified interface for managing roofs, curtains, telescopes, weather stations, and UPS systems.

### Main Technologies
- **Language:** Python 3.10+ (Tested up to 3.12)
- **Dependency Management:** [uv](https://github.com/astral-sh/uv) (Migrated from Poetry, uses PEP 621)
- **Communication:** [gRPC](https://grpc.io/) with [Protocol Buffers](https://developers.google.com/protocol-buffers)
- **Hardware Interaction:** [gpiozero](https://gpiozero.readthedocs.io/), `lgpio`
- **Astronomy Libraries:** [astropy](https://www.astropy.org/) (>= 6.0.0 for Python 3.12 compatibility)
- **Asynchronous I/O:** `asyncio` (Critical for concurrent gRPC services)
- **Other:** OpenCV (image processing/logging), `nut2` (UPS monitoring via NUT)

---

## 2. Commands (using uv)

### Install Dependencies
```bash
# Basic installation (simulators and core services only)
uv sync

# Hardware installation (Raspberry Pi only, includes compiled GPIO drivers)
uv sync --extra hardware

# Development installation (includes tests and coverage tools)
uv sync --extra dev
```

### Run the Server
```bash
# Start the gRPC server (defaults to port 50051 as per config.ini)
uv run python crac_server/app.py
```

### Run Tests
```bash
# Run all tests (Unit + Integration)
uv run python -m unittest discover tests

# Run Unit Tests Only (Uses gpiozero mocks, no physical hardware required)
uv run python -m unittest discover tests/unit

# Run Integration Tests Only (Requires physical hardware or specific network access)
uv run python -m unittest discover tests/integration

# Run a specific test file
uv run python -m unittest tests/unit/service/test_weather_service.py

# Run a specific test class/method
uv run python -m unittest tests.unit.service.test_weather_service.TestWeatherService.test_get_status
```

### Coverage and Reporting
```bash
# Run tests with coverage
uv run coverage run -m unittest discover tests/unit

# View report in terminal
uv run coverage report -m -i

# Generate HTML report
uv run coverage html -i
```

---

## 3. Hardware Mocking & Cross-Platform Development

The project is designed to be developed on any OS (macOS, Windows, Linux) without physical GPIO pins.

- **Configuration**: Ensure `gpio_mock = on` is set in `config.ini` under the `[server]` section.
- **Mechanism**: When enabled, `crac_server/__init__.py` initializes the `gpiozero.pins.mock.MockFactory`. 
- **Base Dependency**: `gpiozero` is a base dependency in `pyproject.toml`, allowing the logic to run everywhere using internal mocks.
- **LGPIO**: The `lgpio` library is only for real hardware interaction and is an optional extra (`--extra hardware`). It is expected to fail compilation on non-Linux systems.

---

## 4. Code Style & Standards

### Async/Sync Safety 🔴 CRITICAL MANDATE
Most gRPC services are defined as `async def`. **Never call blocking code directly inside these methods.**
- **Blocking I/O**: Use `asyncio.to_thread()` or `run_in_executor()` for hardware wait calls (GPIO) or legacy synchronous requests (urllib).
- **Emergency Procedures**: Procedures like `_emergency_closure` (triggered by weather/UPS) must be awaitable. A common bug is launching these in a standard `Thread` and calling `async` methods (like `ROOF.close()`) without an event loop. Always use `asyncio.create_task` or similar for background async logic.

### General Guidelines
- **Indentation**: 4 spaces.
- **Line Length**: Max 79 characters (PEP 8).
- **Type Hints**: Mandatory for all function signatures (e.g., `async def GetStatus(self, request: WeatherRequest, context) -> WeatherResponse:`).
- **Imports**: 
    1. Standard library
    2. Third-party (gRPC, astropy, etc.)
    3. Local application modules
    *Separate groups with a blank line.*

### Naming Conventions
- **Modules/Packages**: `snake_case` (e.g., `roof_control.py`).
- **Classes**: `PascalCase` (e.g., `RoofService`).
- **Functions/Variables**: `snake_case` (e.g., `wind_speed`).
- **Constants**: `UPPER_SNAKE_CASE`.
- **Private members**: Prefix with `_`.

---

## 5. Architecture & Project Structure

The project follows a modular singleton pattern for hardware components.

```
crac_server/
├── app.py                  # Entry point: registers gRPC services and starts the server
├── config.py               # Config class: handles config.ini and .env overrides
├── config.ini              # Central configuration for pins, thresholds, and drivers
├── component/              # Hardware abstraction layer
│   ├── weather/            # Weather station logic (urllib fallback logic)
│   ├── telescope/          # Telescope drivers (indi, indigo, simulator, etc.)
│   ├── roof/               # Roof control logic
│   ├── curtains/           # Curtains and encoders logic
│   └── ups/                # UPS monitoring (NUT integration)
├── service/                # gRPC Servicer implementations (async)
├── handler/                # Business logic using Chain of Responsibility
├── converter/              # Mappers between internal models and Protobuf messages
└── images/                 # Static labels and UI assets

tests/
├── unit/                   # Mocked tests (no hardware/network required)
│   ├── component/
│   ├── service/
│   └── converter/
└── integration/            # Real-world tests (requires HW or specific drivers)
```

### Component Pattern
Components are singleton instances defined in their respective `__init__.py`. 
Example: `from crac_server.component.weather import WEATHER`.

---

## 6. Common Tasks for Developers/Agents

### Adding a New Component
1. Create a directory under `crac_server/component/<name>/`.
2. Implement the component class (include a `simulator/` version if possible).
3. Create `__init__.py` to export a singleton instance based on `config.ini`.
4. Add unit tests in `tests/unit/component/<name>/` using mocks.

### Adding a New gRPC Service
1. Define the service in `crac-protobuf` repository.
2. Run `generate_proto_code.py` in the protobuf project.
3. Create the service class in `crac_server/service/` inheriting from the generated `*Servicer`.
4. Register the new service in `crac_server/app.py`.
5. Implement unit tests in `tests/unit/service/`.

---

## 7. Agent Autonomy & Safeguards

To ensure efficiency and safety, the following rules apply to AI agents working on this project:

- **Autonomy**: Once a high-level plan is approved by the user, the agent is authorized to proceed through **Plan -> Act -> Validate** cycles without per-step confirmation.
- **Git User Email**: Always verify that `git config user.email` is set to `alkcxy@gmail.com` before making any commit.
- **No Remote Push**: Agents are **strictly forbidden** from executing `git push`. This action is reserved for the human user.
- **Mandatory Testing**: A commit can only be made if all relevant unit tests pass. 
- **Autonomous Fixes**: If tests fail after a modification, the agent should attempt up to **3 iterations** of autonomous fixing before stopping to consult the user.
- **Atomic Commits**: Prefer small, descriptive commits over large "catch-all" updates.
