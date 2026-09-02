from datetime import datetime
from typing import Any
import time
from astropy import units as u
from astropy.coordinates import EarthLocation
from astropy.time import Time
from crac_protobuf.telescope_pb2 import (
    EquatorialCoords,
    AltazimutalCoords,
    TelescopeSpeed,
    TelescopeStatus,  # type: ignore
)
from crac_server import config
from crac_server.component.telescope.telescope import Telescope as TelescopeBase
from crac_server.component.indigo_client import get_indigo_client
import logging
logger = logging.getLogger(__name__)


class Telescope(TelescopeBase):

    # default port 7624
    def __init__(self, hostname=config.Config.getValue("hostname", "telescope"), port=config.Config.getInt("port", "telescope")) -> None:
        super().__init__(hostname=hostname, port=port)
        self._name = config.Config.getValue("name", "indigo")
        self._client = get_indigo_client(hostname, port)
        # Niente connect_device() qui: la connessione al mount va stabilita
        # dall'operatore dal pannello INDIGO (mount.html/ctrl.html) prima
        # che crac la usi, non forzata da crac stesso - vedi retrieve().
        self._geo_synced = False
        self.__sync_geographic_coordinates()
        self._park_position_synced = False
        self._uses_raw_socket = False

    def __sync_geographic_coordinates(self):
        # Mount Simulator parte a lat/lon 0°,0° ("null island") finché non
        # gliela mandiamo esplicitamente: la stessa coppia RA/DEC risulta a
        # un'altitudine completamente diversa a 0° di quella vista dal
        # nostro calcolo (fatto sulla posizione reale dell'osservatorio),
        # facendo atterrare qualunque slew (es. flat) in un punto sbagliato.
        # Va ritentata (non solo in __init__, vedi retrieve()) perché il
        # send() qui è fire-and-forget: se il socket del client condiviso
        # non è ancora pronto al primo tentativo, fallirebbe in silenzio e
        # non verrebbe mai più rimandata.
        if self._geo_synced:
            return
        location = EarthLocation(
            lat=config.Config.getValue("lat", "geography"),
            lon=config.Config.getValue("lon", "geography"),
            height=config.Config.getInt("height", "geography") * u.m,
        )
        self._geo_synced = self.__call(
                    {"newNumberVector":
                        {
                            "device": self._name, "name": "GEOGRAPHIC_COORDINATES", "items":
                            [
                                { "name": "LATITUDE", "value": location.lat.deg},
                                { "name": "LONGITUDE", "value": location.lon.deg % 360},
                                { "name": "ELEVATION", "value": location.height.value}
                            ]
                        }
                    }
                    )

    def __sync_park_position(self):
        # HA/DEC (non alt/az) perché per un punto ad alt/az fissi sono le
        # uniche coordinate equatoriali time-invariant (alt/az = f(HA, dec,
        # lat): a parità di HA/dec il punto resta sempre allo stesso alt/az,
        # qualunque sia l'ora - a differenza di RA, che va ricalcolata ad
        # ogni istante). Sincronizzata una sola volta (da park(), mai in modo
        # eager da __init__/retrieve()). Dopo il primo successo il park
        # nativo la userà da solo ad ogni richiesta, senza bisogno che
        # crac-server gliela reinvii ogni volta.
        if self._park_position_synced:
            return
        # Solo per i driver che espongono davvero una posizione di park
        # scrivibile (il Mount Simulator): su un mount reale
        # (indigo_mount_lx200 / TeenAstro) MOUNT_PARK_POSITION non esiste -
        # la posizione di park vive nel mount ed è INDIGO a mandarcelo lì -
        # e scriverci sopra sarebbe solo rumore verso l'hardware.
        if not self._client.get_property(self._name, "MOUNT_PARK_POSITION", timeout=0):
            return
        # indigo_mount_simulator.c rifiuta le scritture su
        # MOUNT_PARK_POSITION mentre il mount è parcheggiato (come già
        # capita per MOUNT_EQUATORIAL_COORDINATES) e il simulatore parte
        # parcheggiato: si sincronizza al primo park utile, cioè quando il
        # telescopio è stato sparcheggiato e mosso davvero.
        if self.__retrieve_status_park():
            return
        obstime = datetime.utcnow()
        aa_coords = AltazimutalCoords(
            alt=config.Config.getFloat("park_alt", "telescope"),
            az=config.Config.getFloat("park_az", "telescope"),
        )
        eq_coords = self._altaz2radec(aa_coords, obstime=obstime)
        lat = config.Config.getValue("lat", "geography")
        lon = config.Config.getValue("lon", "geography")
        lst = Time(obstime).sidereal_time("apparent", longitude=lon)
        ha = (lst.hour - eq_coords.ra) % 24
        if ha > 12:
            ha -= 24
        self._park_position_synced = self.__call(
                    {"newNumberVector":
                        {
                            "device": self._name, "name": "MOUNT_PARK_POSITION", "items":
                            [
                                { "name": "HA", "value": ha},
                                { "name": "DEC", "value": eq_coords.dec}
                            ]
                        }
                    }
                    )
        # Niente CONFIG_SAVE: se il solo indigo_server viene riavviato, la
        # riconnessione azzera _park_position_synced (vedi retrieve()) e la
        # posizione viene rimandata al primo park utile - persisterla su
        # disco non aggiungerebbe nulla.

    def sync(self, started_at: datetime):
        # NOTA: questi tre __call originariamente inviavano stringhe XML
        # (residuo del driver "indi" da cui è stato copiato), non JSON valido
        # per il protocollo INDIGO - comportamento preesistente, non toccato
        # qui perché fuori dallo scope di questo refactor.
        self.__call(
            f"""
                <setNumberVector device="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                    <oneNumber name="SLEW">
                        Off
                    </oneNumeber>
                    <oneNumber name="TRACK">
                        Off
                    </oneNumber>
                    <oneNumber name="SYNC">
                        On
                    </oneNumber>
                </oneNumberVector>
            """
        )
        eq_coords = self._calculate_eq_coords_of_park_position(started_at)
        self.__call(
            f"""
                <defNumberVector device="{self._name}" name="MOUNT_EQUATORIAL_COORDINATES">
                    <oneNumber name="DEC">
                      {eq_coords.dec}
                    </oneNumber>
                    <oneNumber name="RA">
                      {eq_coords.ra}
                    </oneNumber>
                </defNumberVector>
            """
        )
        self.__call(
            f"""
                <oneNumberVector device="{self._name}" name="MOUNT_ON_COORDINATES_SET">
                    <oneNumber name="SLEW">
                        Off
                    </oneNumber>
                    <oneNumber name="TRACK">
                        On
                    </oneNumber>
                    <oneNumber name="SYNC">
                        Off
                    </oneNumber>
                </oneNumberVector>
            """
        )

    def set_speed(self, speed: TelescopeSpeed):
        tracking_on = speed is not TelescopeSpeed.SPEED_NOT_TRACKING
        self.__call(
                    {"newSwitchVector":
                            {
                                "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items":
                                [
                                    { "name": "ON", "value": tracking_on},
                                    { "name": "OFF", "value": not tracking_on}
                                ]
                            }
                        }
                    )

        # MOUNT_ON_COORDINATES_SET è una proprietà switch (TRACK/SYNC/SLEW),
        # non number: il driver la ignora silenziosamente se mandata come
        # newNumberVector, e la logica di slew di MOUNT_EQUATORIAL_COORDINATES
        # non scatta mai. indigo_mount_simulator.c implementa solo i rami
        # TRACK e SYNC per il movimento (SLEW non è gestito e non muove
        # nulla): va sempre selezionato TRACK per ottenere lo slew, che sia
        # o meno richiesto il tracking continuo dopo l'arrivo (governato a
        # parte da MOUNT_TRACKING sopra).
        self.__call(
                    {"newSwitchVector":
                        {
                            "device": self._name, "name": "MOUNT_ON_COORDINATES_SET", "state": "Ok", "items":
                            [
                                { "name": "SLEW", "value": False},
                                { "name": "TRACK", "value": True},
                                { "name": "SYNC", "value": False}
                            ]
                        }
                    }
                )


    def park(self, speed: TelescopeSpeed):
        # Nessun unpark preventivo qui: su un mount reale
        # (indigo_mount_lx200, es. TeenAstro) il driver scarta MOUNT_PARK se
        # il mount risulta ancora parked/parking/homing, ma il valore
        # PARKED=true viene comunque echeggiato indietro
        # (indigo_property_copy_values gira *prima* di quella guardia).
        # Mandare UNPARK e subito dopo PARK cadeva sempre in quel caso -
        # l'unpark è asincrono, `parked` resta true per un attimo - quindi
        # il telescopio non si muoveva mentre crac passava a PARKED.
        self.__sync_park_position()
        self.__call(
                        {"newSwitchVector":
                            {
                                "device": self._name, "name": "MOUNT_PARK", "state": "Ok", "items":
                                    [
                                        { "name": "PARKED", "value": True},
                                        { "name": "UNPARKED", "value": False}
                                    ]
                            }
                        }
                    )

        # Niente MOUNT_TRACKING OFF dopo il park (`speed` resta solo per
        # rispettare la firma): parcheggiare spegne gia' il tracking, sia
        # nel simulatore che su un mount reale, e il comando arrivava a
        # mount gia' parcheggiato - dove viene rifiutato (property in
        # Alert), o peggio raggiunge l'hardware nel bel mezzo del park.
        self.__wait_for_slew_completion()

    def __retrieve_status_park(self) -> bool:
        prop = self._client.get_property(self._name, "MOUNT_PARK", timeout=0)
        if not prop:
            return False
        for park in prop.get("items", []):
            if park.get("name") == "PARKED":
                return bool(park.get("value"))
        return False

    def __unpark(self):
        # un mount parcheggiato rifiuta qualunque comando di movimento
        # (indigo_mount_simulator.c: MOUNT_PARK_PARKED_ITEM->sw.value mette
        # MOUNT_EQUATORIAL_COORDINATES in stato ALERT "Mount is parked") -
        # va sempre sparcheggiato esplicitamente prima di uno slew, come
        # fanno già gli altri driver (vedi ascom_hub._unpark_and_track).
        self.__call(
                        {"newSwitchVector":
                            {
                                "device": self._name, "name": "MOUNT_PARK", "state": "Ok", "items":
                                    [
                                        { "name": "PARKED", "value": False},
                                        { "name": "UNPARKED", "value": True}
                                    ]
                            }
                        }
                    )

    def flat(self, speed: TelescopeSpeed):
        speed=speed
        self.__unpark()
        self.__move(
                    aa_coords=AltazimutalCoords(
                        alt=config.Config.getFloat("flat_alt", "telescope"),
                        az=config.Config.getFloat("flat_az", "telescope")
                    ),
                speed=speed
                )

        if speed is TelescopeSpeed.SPEED_NOT_TRACKING:
            # indigo_mount_simulator.c riaccende il tracking in automatico
            # non appena lo slew termina (se era spento quando lo slew è
            # stato avviato): un OFF mandato subito, prima che lo slew sia
            # concluso, verrebbe quindi sovrascritto dal driver stesso.
            # Bisogna aspettare l'arrivo e solo allora spegnerlo di nuovo.
            self.__wait_for_slew_completion()
            self.__call(
                            {"newSwitchVector":
                                {
                                    "device": self._name, "name": "MOUNT_TRACKING", "state": "Ok", "items":
                                    [
                                        { "name": "ON", "value": False},
                                        { "name": "OFF", "value": True}
                                    ]
                                }
                            }
                        )

    def __wait_for_slew_completion(self, timeout: float = 60.0):
        deadline = time.monotonic() + timeout
        # prima aspetta che INDIGO segnali di aver effettivamente preso in
        # carico il comando (stato Busy): senza questo passo, la primissima
        # lettura rischia di leggere ancora la cache con lo stato "Ok" di
        # prima dell'invio, dato che il broadcast di INDIGO non è ancora
        # arrivato (misurato: bastava meno di 1ms per leggere lo stato
        # sbagliato). Se non diventa mai Busy (slew banale/nullo), si
        # procede comunque oltre il timeout breve.
        busy_deadline = min(deadline, time.monotonic() + 5.0)
        while time.monotonic() < busy_deadline:
            coords = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES", timeout=0)
            if coords and coords.get("state") == "Busy":
                break
            time.sleep(0.1)

        while time.monotonic() < deadline:
            coords = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES", timeout=0)
            if coords and coords.get("state") != "Busy":
                return
            time.sleep(0.3)
        logger.error(f"[Telescope] Slew did not complete within {timeout}s, giving up waiting")

    def retrieve(self) -> tuple:
        # In produzione l'osservatore usa il pannello INDIGO direttamente e
        # deve ricordarsi di collegare il telescopio li' prima che crac lo
        # usi: crac non forza piu' la connessione da solo (vedi __init__),
        # quindi va rifiutata finche' il device non risulta gia' connesso
        # lato INDIGO, con uno stato chiaro invece di un falso "connesso".
        if not self._client.is_device_connected(self._name):
            return (None, None, TelescopeSpeed.SPEED_ERROR, TelescopeStatus.LOST)

        # connect_device() è idempotente (no-op se già connesso su questa
        # connessione fisica) ma va richiamato ad ogni ciclo, non solo in
        # __init__: se il client si riconnette, la cache viene svuotata e
        # senza questa richiamata qui il device non verrebbe più ri-connesso
        # né le sue proprietà più richieste, restando bloccato per sempre.
        # Il suo esito (True = riconnessione reale avvenuta) segnala anche
        # che lo stato del device è stato perso lato indigo (es. il solo
        # server INDIGO è stato riavviato mentre crac-server restava attivo)
        # - le sincronizzazioni one-shot vanno quindi ripetute.
        if self._client.connect_device(self._name):
            self._geo_synced = False
            self._park_position_synced = False
        self.__sync_geographic_coordinates()
        eq_coords = self.__retrieve_eq_coords()
        logger.debug(f"data received from cache: {eq_coords}")
        speed = self.__retrieve_speed()
        logger.debug(f"data received from cache: {speed}")
        aa_coords = self.__retrieve_aa_coords()
        logger.debug(f"data received from cache: {aa_coords}")
        status = self._retrieve_status(aa_coords)
        logger.debug(f"data received from cache: {status}")

        return (eq_coords, aa_coords, speed, status)

    def _retrieve_status(self, aa_coords: AltazimutalCoords) -> TelescopeStatus:
        if not self._polling:
            return TelescopeStatus.DISCONNECTED
        elif self.__retrieve_status_park():
            return TelescopeStatus.PARKED
        elif self.__within_flat_alt_range(aa_coords.alt) and self.__within_flat_az_range(aa_coords.az):
            return TelescopeStatus.FLATTER
        elif aa_coords.alt <= config.Config.getFloat("max_secure_alt", "telescope"):
            return TelescopeStatus.SECURE
        else:
            if config.Config.getInt("azNE", "azimut") > aa_coords.az:
                return TelescopeStatus.NORTHEAST
            elif aa_coords.az > config.Config.getInt("azNW", "azimut"):
                return TelescopeStatus.NORTHWEST
            elif config.Config.getInt("azSW", "azimut") > aa_coords.az > 180:
                return TelescopeStatus.SOUTHWEST
            elif 180 >= aa_coords.az > config.Config.getInt("azSE", "azimut"):
                return TelescopeStatus.SOUTHEAST
            elif config.Config.getInt("azSW", "azimut") < aa_coords.az <= config.Config.getInt("azNW", "azimut"):
                return TelescopeStatus.WEST
            elif config.Config.getInt("azNE", "azimut") <= aa_coords.az <= config.Config.getInt("azSE", "azimut"):
                return TelescopeStatus.EAST

    def __move(self, aa_coords: AltazimutalCoords, speed=TelescopeSpeed.SPEED_TRACKING):

        eq_coords = self._altaz2radec(aa_coords, decimal_places=2, obstime=datetime.utcnow()) if isinstance(aa_coords, (AltazimutalCoords)) else aa_coords
        logger.debug(aa_coords)
        logger.debug(eq_coords)
        # set_speed() va chiamato subito, non accodato con queue_set_speed():
        # il driver controlla MOUNT_ON_COORDINATES_SET.TRACK nello stesso
        # istante in cui riceve il nuovo MOUNT_EQUATORIAL_COORDINATES, non al
        # prossimo ciclo di polling (fino a 5s dopo, troppo tardi).
        self.set_speed(speed)
        self.__call(
                    {"newNumberVector":
                        {
                            "device": self._name, "name": "MOUNT_EQUATORIAL_COORDINATES", "state": "Ok", "items":
                            [
                                { "name": "DEC", "value": eq_coords.dec},
                                { "name": "RA", "value": eq_coords.ra}
                            ]
                        }
                    }
                    )

    def __retrieve_speed(self) -> TelescopeSpeed:
        tracking = self._client.get_property(self._name, "MOUNT_TRACKING", timeout=0)
        coords = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES", timeout=0)

        status_mount_track = None
        if tracking:
            for track in tracking.get("items", []):
                if track.get("name") == "ON":
                    status_mount_track = "ON" if track.get("value") else "OFF"

        status_mount_speed = coords.get("state") if coords else None

        if status_mount_speed == "Ok" and status_mount_track == "ON":
            return TelescopeSpeed.SPEED_TRACKING
        # indigo_mount_simulator.c non usa mai lo stato "Idle" per
        # MOUNT_EQUATORIAL_COORDINATES (solo "Ok"/"Busy"/"Alert"): a riposo
        # con tracking spento risulta comunque "Ok", non "Idle" - con quel
        # confronto SPEED_NOT_TRACKING non veniva mai rilevata, cadendo
        # sempre su SPEED_ERROR.
        if status_mount_speed == "Ok" and status_mount_track == "OFF":
            return TelescopeSpeed.SPEED_NOT_TRACKING
        if status_mount_speed == "Busy":
            return TelescopeSpeed.SPEED_SLEWING
        return TelescopeSpeed.SPEED_ERROR

    def __retrieve_eq_coords(self) -> EquatorialCoords:
        prop = self._client.get_property(self._name, "MOUNT_EQUATORIAL_COORDINATES")
        ra, dec = None, None
        if prop:
            for coord in prop.get("items", []):
                if coord.get("name") == "RA":
                    ra = round(float(coord["value"]), 5)
                elif coord.get("name") == "DEC":
                    dec = round(float(coord["value"]), 5)

        if ra is not None and dec is not None:
            return EquatorialCoords(ra=ra, dec=dec)
        raise Exception(f"RA or Dec not present. RA: {ra}, DEC: {dec}")

    def __retrieve_aa_coords(self) -> AltazimutalCoords:
        prop = self._client.get_property(self._name, "MOUNT_HORIZONTAL_COORDINATES")
        alt, az = None, None
        if prop:
            for coord in prop.get("items", []):
                if coord.get("name") == "ALT":
                    alt = round(float(coord["value"]), 5)
                elif coord.get("name") == "AZ":
                    az = round(float(coord["value"]), 5)

        if alt is not None and az is not None:
            return AltazimutalCoords(alt=alt, az=az)
        raise Exception(f"ALT or AZ not present. ALT: {alt}, AZ: {az}")

    def __call(self, script) -> bool:
        return self._client.send(script)
