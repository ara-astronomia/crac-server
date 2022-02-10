# Install Dependencies and Configure environment

We are using Poetry as a dependency management and packaging
Go to https://python-poetry.org/ and install it

Before using this project, you should clone the crac-protobuf project 
alongside this one so that the dependency expressed on pyprject.toml 
can find the package to install.

```
poetry shell
poetry install
```

# Execute the service

Currently we have only the roof service, so it is handy to execute it with:

```
cd crac_server/service
python roof_service.py
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