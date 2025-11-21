# crac_server/service/geographic_service.py
from crac_protobuf import geographic_pb2
from crac_protobuf import geographic_pb2_grpc
from crac_server.config import Config # Supponendo che esista
import re

class GeographicServicer(geographic_pb2_grpc.GeographicServiceServicer):
    def GetGeographicInfo(self, request, context):
        # 1. Ottieni i dati dal config.ini
        geo_config = Config.get_section("geography")
        lat=(geo_config.get("lat"))
        lon=(geo_config.get("lon"))
        elev=(geo_config.get("height"))
        match_lat = re.search(r'(\d+)d([\d.]+)m', lat)
        match_lon = re.search(r'(\d+)d([\d.]+)m', lon)
        if match_lat and match_lon:
            # Estrai i gruppi e convertili in float
            gradi_lat  = float(match_lat.group(1))   # 42.0
            minuti_lat = float(match_lat.group(2))  # 13.76
            lat = float(gradi_lat + (minuti_lat / 60.0))  
            gradi_lon  = float(match_lon.group(1))   # 42.0
            minuti_lon = float(match_lon.group(2))  # 13.76
            lat = float(gradi_lon + (minuti_lon / 60.0))   
        elev = float(geo_config.get("height", 0.0))

        # 2. Popola e restituisci il messaggio Protobuf
        print("Geographic info requested: lat={}, lon={}, elev={}".format(lat, lon, elev))
        return geographic_pb2.GeographicData(
            latitude=lat,
            longitude=lon,
            elevation_meters=elev
        )