from datetime import datetime
import html
import logging
from threading import (Thread, Lock)
from time import sleep
from typing import Union
from urllib.error import HTTPError, URLError
import urllib.request
import json


logger = logging.getLogger(__name__)


class Weather:
    def __init__(self, url: str, fallback_url: str, time_format: str, time_expired: int, retry_interval: int):
        self._url = url
        self._fallback_url = fallback_url
        self._json = {}
        self._updated_at : Union[datetime, None] = None
        self._last_attempt_at : Union[datetime, None] = None
        self._time_format = time_format
        self._time_expired = time_expired
        self._retry_interval = retry_interval
        
        # Avvia il thread di background per il recupero dei dati
        self.t = Thread(target=self._retrieve_async, daemon=True)
        self.t.start()

    @property
    def url(self):
        return self._url

    @property
    def fallback_url(self):
        return self._fallback_url

    @property
    def updated_at(self):
        return self._updated_at

    @updated_at.setter
    def updated_at(self, value: str):
        self._updated_at = datetime.strptime(value, self._time_format)

    @property
    def last_attempt_at(self):
        return self._last_attempt_at
    
    @last_attempt_at.setter
    def last_attempt_at(self, value: datetime):
        self._last_attempt_at = value

    @property
    def json(self):
        return self._json

    @json.setter
    def json(self, value):
        self._json = value

    @property
    def temperature(self):
        return self._get_sensor("outTemp")

    @property
    def humidity(self):
        return self._get_sensor("humidity")

    @property
    def wind_speed(self):
        return self._get_sensor("windSpeed")

    @property
    def wind_gust_speed(self):
        return self._get_sensor("windGust")

    @property
    def rain_rate(self):
        return self._get_sensor("rainRate")

    @property
    def barometer(self):
        return self._get_sensor("barometer")
    
    @property
    def barometer_trend(self):
        return self._get_sensor("barometerTrend")
    
    @property
    def time_expired(self) -> int:
        return self._time_expired

    def is_expired(self) -> bool:
        return not self.updated_at or (datetime.now() - self.updated_at).seconds >= self._time_expired
    
    def is_retriable(self) -> bool:
        return not self.last_attempt_at or (datetime.now() - self.last_attempt_at).seconds >= self._retry_interval
    
    @property
    def is_unavailable(self) -> bool:
        return self.updated_at != None and (datetime.now() - self.updated_at).seconds >= self._time_expired * 3
    
    def _retrieve_async(self):
        while True:
            if self.is_expired() and self.is_retriable():
                success = False
                logger.debug("Tentativo recupero dati meteo in background...")
                
                # Tentativo 1: URL Principale
                try:
                    self.json, self.updated_at = self._retrieve_data()
                    logger.info("Dati meteo aggiornati con successo (URL principale).")
                    success = True
                except Exception as e:
                    logger.warning(f"URL principale non raggiungibile: {e}. Provo fallback immediato...")
                
                # Tentativo 2: Fallback (solo se il primo è fallito)
                if not success:
                    try:
                        self.json, self.updated_at = self._retrieve_fallback_data()
                        logger.info("Dati meteo aggiornati tramite fallback.")
                        success = True
                    except Exception as ef:
                        logger.error(f"Errore critico: anche il fallback è fallito: {ef}")
                
                # Aggiorna il timestamp dell'ultimo tentativo solo se entrambi sono falliti
                # oppure dopo un successo per far ripartire il timer del retry_interval
                self.last_attempt_at = datetime.now()
            
            # Controllo frequente dello stato (ogni 5 secondi il thread si sveglia)
            sleep(5)

    def _retrieve_data(self):
        with urllib.request.urlopen(self.url, timeout=5) as url:
            json_result = json.loads(url.read().decode())
        
        return json_result["current"], json_result["time"]

    def _retrieve_fallback_data(self):
        with urllib.request.urlopen(self.fallback_url, timeout=5) as url:
            json_result = json.loads(url.read().decode())
        
        return json_result["current"], json_result["time"]


    def _get_sensor(self, name: str) -> tuple[Union[float, str], str]:
        if not self.json or name not in self.json:
            return 'N/A', ''
        
        sensor = self.json[name]
        return self.__convert_to_float(sensor["value"]), html.unescape(sensor["unit_of_measurement"]).strip()

    def __convert_to_float(self, value: str):
        value = value.strip().replace(',', '.')
        try:
            return float(value)
        except ValueError:
            logger.warning(f"Impossibile convertire '{value}' in float, restituisco 'N/A'")
            return 'N/A'
