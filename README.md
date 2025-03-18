# Use it on raspberry PI Zero 2 or greater
* enable SSH by touch ssh on the root of the boot disk https://phoenixnap.com/kb/enable-ssh-raspberry-pi
* enable wifi by creating wpa_supplicant on the root of the boot disk and putting this inside:
    ```
    country=<country_code>
    ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
    update_config=1

    network={
    scan_ssid=1
    ssid="your_wifi_ssid"
    psk="your_wifi_password"
    }
    ```
* 


# Pre-requisite

```
sudo apt install libopencv-dev python3-opencv
```

# Install Dependencies and Configure environment

We are using Poetry as a dependency management and packaging
Requisite for poetry:

```
sudo apt-get install python3-distutils
sudo apt-get install python3-dev
```

Go to https://python-poetry.org/ and install it

Before using this project, you should clone the crac-protobuf project 
alongside this one so that the dependency expressed on pyprject.toml 
can find the package to install.

```
sudo apt install libatlas3-base libgfortran5 libopenjp2-7 libavcodec-dev libavformat-dev libswscale-dev libgtk-3-dev python3.9-dev
poetry shell
poetry install
```

# Execute the service

You can start the server with the following commands
```
cd crac_server
python app.py
```

Then you can test the connectivity by executing a python repl:

```
python
```

and inside it:

```
from crac_protobuf.roof_pb2 import *
from crac_protobuf.roof_pb2_grpc import *
import grpc
channel = grpc.insecure_channel("localhost:50051")
client = RoofStub(channel)
request = RoofRequest(action=RoofAction.OPEN)
client.SetAction(request)
```

or you can clone the crac-client repository (https://github.com/ara-astronomia/crac-client) and start it

# Test

## unit tests:

run the unit tests:

```
coverage run -m unittest discover
```

produce the report for coverage:

```
coverage report -m -i
coverage html -i
```