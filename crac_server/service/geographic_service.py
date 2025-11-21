# crac_server/service/geographic_service.py
from crac_protobuf import geographic_pb2
from crac_protobuf import geographic_pb2_grpc
from crac_server.config import Config # Supponendo che esista
import re

class GeographicServicer(geographic_pb2_grpc.GeographicServiceServicer):
    def GetGeographicInfo(self, request, context):
        # 1. Ottieni i dati dal config.ini
        geo_config = Config.get_section("geography")
        lat_str=(geo_config.get("lat"))
        lon_str=(geo_config.get("lon"))
        elev_str=(geo_config.get("height"))

        match_lat = re.search(r'(\d+)d([\d.]+)m', lat_str)
        if match_lat:
            try:
                gradi_lat  = float(match_lat.group(1))
                minuti_lat = float(match_lat.group(2))
                # Calcolo sessagesimale
                lat = gradi_lat + (minuti_lat / 60.0)
            except ValueError:
                print(f"ERRORE: Impossibile convertire Latitudine in float: {lat_str}")

        # 3. Conversione Longitudine
        match_lon = re.search(r'(\d+)d([\d.]+)m', lon_str)
        if match_lon:
            try:
                gradi_lon  = float(match_lon.group(1))
                minuti_lon = float(match_lon.group(2))
                # Calcolo sessagesimale
                lon = gradi_lon + (minuti_lon / 60.0)
            except ValueError:
                print(f"ERRORE: Impossibile convertire Longitudine in float: {lon_str}")

        # 4. Conversione Elevazione
        try:
            elev = float(elev_str)
        except ValueError:
            print(f"ERRORE: Impossibile convertire Elevazione in float: {elev_str}")
            elev = 0.0

        # 2. Popola e restituisci il messaggio Protobuf
        print("Geographic info requested: lat={}, lon={}, elev={}".format(lat, lon, elev))
        return geographic_pb2.GeographicData(
            latitude=lat,
            longitude=lon,
            elevation_meters=elev
        )