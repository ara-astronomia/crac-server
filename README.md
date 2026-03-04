# CRAC Server
Server for controlling the Dome and the Telescope of an astronomical observatory.

## Setup on Raspberry Pi (Zero 2, 4, 5)
* Enable SSH by touching `ssh` on the root of the boot disk.
* Enable wifi by creating `wpa_supplicant.conf` on the root of the boot disk.

## Pre-requisites
Install system dependencies:
```bash
sudo apt update
sudo apt install swig libopencv-dev python3-opencv libatlas3-base libgfortran5 libopenjp2-7 libavcodec-dev libavformat-dev libswscale-dev libgtk-3-dev
```

## Install Dependencies (using uv)
We use [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/ara-astronomia/crac-server
cd crac-server

# Create virtual environment and sync dependencies
# Use --extra hardware only on Raspberry Pi for GPIO support
uv sync --extra hardware --extra dev
```

Note: This project depends on `crac-protobuf`. The dependency is managed via git in `pyproject.toml`.

## Execute the Service
Start the gRPC server:
```bash
uv run python crac_server/app.py
```

### Testing Connectivity (Python REPL)
```python
import grpc
from crac_protobuf.roof_pb2 import RoofRequest, RoofAction
from crac_protobuf.roof_pb2_grpc import RoofStub

channel = grpc.insecure_channel("localhost:50051")
client = RoofStub(channel)
request = RoofRequest(action=RoofAction.OPEN)
client.SetAction(request)
```

Alternatively, use the [crac-client](https://github.com/ara-astronomia/crac-client) GUI.

## Tests
Run unit tests and generate coverage report:
```bash
uv run coverage run -m unittest discover tests
uv run coverage report -m
uv run coverage html
```
