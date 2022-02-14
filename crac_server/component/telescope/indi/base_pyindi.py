import time
import sys
import threading
import logging
import PyIndi

def strISState(s):
    if (s == PyIndi.ISS_OFF):
        return "Off"
    else:
        return "On"
def strIPState(s):
    if (s == PyIndi.IPS_IDLE):
        return "Idle"
    elif (s == PyIndi.IPS_OK):
        return "Ok"
    elif (s == PyIndi.IPS_BUSY):
        return "Busy"
    elif (s == PyIndi.IPS_ALERT):
        return "Alert"

class IndiClient(PyIndi.BaseClient):
    def __init__(self):
        super(IndiClient, self).__init__()
    def newDevice(self, d):
        pass
    def newProperty(self, p):
        pass
    def removeProperty(self, p):
        pass
    def newBLOB(self, bp):
        global blobEvent
        print("new BLOB ", bp.name)
        blobEvent.set()
        pass
    def newSwitch(self, svp):
        pass
    def newNumber(self, nvp):
        pass
    def newText(self, tvp):
        pass
    def newLight(self, lvp):
        pass
    def newMessage(self, d, m):
        pass
    def serverConnected(self):
        pass
    def serverDisconnected(self, code):
        pass
 
# connect the server
indiclient=IndiClient()
indiclient.setServer("localhost",7624)
 
if (not(indiclient.connectServer())):
     print("No indiserver running on "+indiclient.getHost()+":"+str(indiclient.getPort())+" - Try to run")
     print("  indiserver indi_simulator_telescope indi_simulator_ccd")
     sys.exit(1)
 
# connect the scope
#telescope="Losmandy Gemini"
telescope="Telescope Simulator"
device_telescope=None
telescope_connect=None
 
# get the telescope device
device_telescope=indiclient.getDevice(telescope)
while not(device_telescope):
    time.sleep(0.5)
    device_telescope=indiclient.getDevice(telescope)
     
# wait CONNECTION property be defined for telescope
telescope_connect=device_telescope.getSwitch("CONNECTION")
while not(telescope_connect):
    time.sleep(0.5)
    telescope_connect=device_telescope.getSwitch("CONNECTION")
 
# if the telescope device is not connected, we do connect it
if not(device_telescope.isConnected()):
    # Property vectors are mapped to iterable Python objects
    # Hence we can access each element of the vector using Python indexing
    # each element of the "CONNECTION" vector is a ISwitch
    telescope_connect[0].s=PyIndi.ISS_ON  # the "CONNECT" switch
    telescope_connect[1].s=PyIndi.ISS_OFF # the "DISCONNECT" switch
    indiclient.sendNewSwitch(telescope_connect) # send this new value to the device


# We set the desired coordinates to park position
park_alt=0.1 #valore da ottnere da file ini
park_az=0.1 #valore da ottnere da file ini

# We set the desired coordinates to flat position
flat_alt=1 #valore da ottnere da file ini
flat_az=1 #valore da ottnere da file ini


# send telescope to position park
def go_park():
    telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
    while not(telescope_radec):
        time.sleep(0.5)
        telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
    telescope_radec[0].value=park_alt
    telescope_radec[1].value=park_az
    indiclient.sendNewNumber(telescope_radec)
    print("Scope Moving to position park ", telescope_radec[0].value, telescope_radec[1].value)
    park()
    
# send telescope to position flat
def go_flat():
    telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
    while not(telescope_radec):
        time.sleep(0.5)
        telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
    telescope_radec[0].value=flat_alt
    telescope_radec[1].value=flat_az
    indiclient.sendNewNumber(telescope_radec)
    print("Scope Moving to position park ", telescope_radec[0].value, telescope_radec[1].value)
    park()

# telescope in park condizion (tracking = 0 )
def park():
    print ('tele in parking')
    telescope_park=device_telescope.getSwitch("TELESCOPE_PARK")
    while not(telescope_park):
        time.sleep(0.5)
        telescope_park=device_telescope.getSwitch("TELESCOPE_PARK")
    #telescope_park[0].s=PyIndi.ISS_ON  # the "PARK" switch
    telescope_park[0].s=PyIndi.ISS_ON # the "PARK" switch    
    indiclient.sendNewSwitch(telescope_park)

action = input()
if action=='p':
    go_park()
if action=='f':   
    go_flat()

