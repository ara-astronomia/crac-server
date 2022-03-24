# Install Dependencies and Configure environment

We are using Poetry as a dependency management and packaging
Go to https://python-poetry.org/ and install it

Before using this project, you should clone the crac-protobuf project 
alongside this one so that the dependency expressed on pyprject.toml 
can find the package to install.

```
sudo apt install libatlas3-base libgfortran5 libopenjp2-7 libavcodec-dev libavformat-dev libswscale-dev libgtk-3-dev python3.9-dev (if some dependencies need to be compiled)
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
