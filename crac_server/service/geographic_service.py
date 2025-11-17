# crac_server/service/geographic_service.py
from crac_protobuf import geographic_pb2
from crac_protobuf import geographic_pb2_grpc
from crac_server.config import Config # Supponendo che esista

class GeographicServicer(geographic_pb2_grpc.GeographicServiceServicer):
    def GetGeographicInfo(self, request, context):
        # 1. Ottieni i dati dal config.ini
        geo_config = Config.get_section("geography")

        lat = float(geo_config.get("lat", 0.0))
        lon = float(geo_config.get("lon", 0.0))
        elev = float(geo_config.get("height", 0.0))

        # 2. Popola e restituisci il messaggio Protobuf
        return geographic_pb2.GeographicData(
            latitude=lat,
            longitude=lon,
            elevation_meters=elev
        )