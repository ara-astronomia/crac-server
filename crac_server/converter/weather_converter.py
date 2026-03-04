from datetime import datetime
import logging
from crac_protobuf.chart_pb2 import (
    WeatherResponse,
    Chart,
    Threshold,
    ThresholdType,
    ChartStatus,
    WeatherStatus 
)
from crac_server.component.weather.weather import Weather
from crac_server.config import Config
from crac_server.converter.chart_builder import build_chart
from typing import Union, List


logger = logging.getLogger(__name__)


class WeatherConverter:
    def convert(self, weather: Weather) -> WeatherResponse:
        
        sensor_data = [
            (weather.wind_speed, "Vento", "weather.chart.wind", "wind_speed"),
            (weather.wind_gust_speed, "Raffiche vento", "weather.chart.wind_gust", "wind_gust_speed"),
            (weather.temperature, "Temperatura", "weather.chart.temperature", "temperature"),
            (weather.humidity, "Umidità", "weather.chart.humidity", "humidity"),
            (weather.rain_rate, "Pioggia", "weather.chart.rain_rate", "rain_rate"),
            (weather.barometer, "Barometro", "weather.chart.barometer", "barometer"),
            (weather.barometer_trend, "Tendenza Barometro", "weather.chart.barometer_trend", "barometer_trend"),
        ]

        charts: List[Chart] = []
        
        for sensor_val, title, urn, config_section in sensor_data:
            val = sensor_val[0]
            unit = sensor_val[1]
            
            if val == 'N/A':
                logger.debug(f"Salto la creazione del grafico per {title} perché il valore è N/A")
                continue
                
            try:
                # Recupero i valori con dei default per evitare crash se mancano chiavi (es. 'error' nella temperatura)
                low = Config.getFloat("lower_bound", config_section)
                warn = Config.getFloat("warning", config_section)
                # Se manca 'error', usiamo 'upper_bound' come fallback per non rompere la logica
                try:
                    err = Config.getFloat("error", config_section)
                except:
                    err = Config.getFloat("upper_bound", config_section)
                high = Config.getFloat("upper_bound", config_section)

                # Logica differenziata per barometro (pericolo è in basso) e altri (pericolo è in alto)
                if config_section in ["barometer", "barometer_trend"]:
                    # Barometro: Normal (Warn -> High), Warn (Error -> Warn), Danger (Low -> Error)
                    range_normal = ({"upper_bound": high, "lower_bound": warn},)
                    range_warn = ({"upper_bound": warn, "lower_bound": err},)
                    range_danger = ({"upper_bound": err, "lower_bound": low},)
                else:
                    # Altri: Normal (Low -> Warn), Warn (Warn -> Error), Danger (Error -> High)
                    range_normal = ({"upper_bound": warn, "lower_bound": low},)
                    range_warn = ({"upper_bound": err, "lower_bound": warn},)
                    range_danger = ({"upper_bound": high, "lower_bound": err},)

                charts.append(
                    build_chart(
                        value=val,
                        title=title,
                        urn=urn,
                        min=low,
                        max=high,
                        unit_of_measurement=unit,
                        range_normal=range_normal,
                        range_warn=range_warn,
                        range_danger=range_danger
                    )
                )
            except Exception as e:
                logger.error(f"Errore critico config per {config_section}: {e}. Invio grafico base.")
                charts.append(Chart(value=val, title=title, urn=urn, unit_of_measurement=unit))
        
        status = WeatherStatus.WEATHER_STATUS_NORMAL
        for chart in charts:
            if chart.status is ChartStatus.CHART_STATUS_DANGER:
                status = WeatherStatus.WEATHER_STATUS_DANGER
                logger.warning(f"RILEVATO PERICOLO nel grafico: {chart.title} (Valore: {chart.value})")
                break
            if chart.status is ChartStatus.CHART_STATUS_WARNING:
                status = WeatherStatus.WEATHER_STATUS_WARNING

        response = WeatherResponse(
            charts=charts,
            updated_at=self.timestamp_or_none(weather.updated_at),
            status=status,
            interval=weather.time_expired
        )
        return response

    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp())
        else:
            return 0

    def __value_or_zero(self, value):
        if value == 'N/A':
            return 0
        return value
