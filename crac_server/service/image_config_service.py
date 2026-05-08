# crac_server/service/image_config_service.py

from crac_protobuf import data_image_pb2
from crac_protobuf import data_image_pb2_grpc
from crac_server.config import Config

class ImageConfigServicer(data_image_pb2_grpc.ImageConfigServiceServicer):
    def GetCCDImageData(self, request, context):
        # 1. Ottieni i dati dalla sezione [ccd_data_image]
        ccd_config = Config.get_section("ccd_data_image")

        width = float(ccd_config.get("field_of_view_width", 0.0))
        height = float(ccd_config.get("field_of_view_height", 0.0))

        # 2. Popola e restituisci il messaggio Protobuf
        return data_image_pb2.CCDImageData(
            field_of_view_width=width,
            field_of_view_height=height
        )