# Use it on raspberry PI5
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

We are using UV as a dependency management and packaging
Requisite for poetry:

```
sudo apt-get install python3-distutils
sudo apt-get install python3-dev
```
pip install uv
uv venv #crea l'ambiente virtuale
uv pip sync -E dev #installa le dipendenze e le dev-dependencies
uv pip add new-package #aggiunge nuove dipendenze 

Before using this project, you should clone the crac-protobuf project 
alongside this one so that the dependency expressed on pyprject.toml 
can find the package to install.



# Execute the service

You can start the server with the following commands
```
cd crac_server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
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

# Deploy in produzione (Pi5)

Setup una tantum sul Pi:

```bash
# 1. clona il repo in /home/pi/crac-server e installa le dipendenze
git clone <url> /home/pi/crac-server
cd /home/pi/crac-server && uv sync --no-dev

# 2. installa il servizio systemd
sudo cp deploy/crac-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crac-server

# 3. permetti all'utente pi di riavviare il servizio senza password (serve al deploy da SSH)
echo 'pi ALL=(root) NOPASSWD: /usr/bin/systemctl restart crac-server' | sudo tee /etc/sudoers.d/crac-server
```

Il deploy gira interamente su GitHub Actions (runner ospitato da GitHub, non
sul Pi): usa un `ProxyJump` SSH attraverso `cloud.ara`, che fa da bastion
verso `crac.server.ara.local` (rete privata dell'osservatorio, non
raggiungibile da fuori) - stesso pattern di `alkcxy/home`. Servono due
chiavi dedicate al deploy (generate apposta, non riusano quelle personali
ne' quelle gia' presenti sul bastion), autorizzate una per hop e salvate
come secret nel repo GitHub:

- `CLOUD_ARA_SSH_KEY`: autorizzata in `~/.ssh/authorized_keys` di `indigo`
  su cloud.ara (primo salto).
- `CRAC_SERVER_SSH_KEY`: autorizzata in `~/.ssh/authorized_keys` di `pi`
  su crac.server.ara.local (secondo salto, via ProxyJump).

Per i deploy successivi: tab "Actions" → workflow "Deploy su Pi5" → "Run workflow",
scegliendo branch/tag/commit da mettere in produzione. Aggiorna il repo gia'
clonato sul Pi, gira `uv sync`, ricopia `deploy/crac-server.service` in
`/etc/systemd/system/` solo se e' cambiato (con `daemon-reload`), e riavvia
il servizio - nessun accesso manuale.

`config.ini` e `.env` non vengono mai toccati dal deploy (`git reset --hard`
sovrascrive solo file tracciati che sono effettivamente cambiati; `.env` e'
untracked e git non lo tocca mai). I valori che devono differire dal
default committato in `config.ini` vanno messi in `.env` (override via
`{SEZIONE}_{CHIAVE}`, vedi `crac_server/config.py`), non editati a mano in
`config.ini` sul Pi.

Log del servizio: `journalctl -u crac-server -f`.

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
