from datetime import datetime
import logging
from crac_protobuf.chart_pb2 import (
    WeatherResponse,
    ChartStatus,
    WeatherStatus
)
from crac_server.component.weather.weather import Weather
from crac_server.converter.chart_config import build_chart_from_config
from typing import Union


logger = logging.getLogger(__name__)

CHARTS = (
    ("wind_speed", "Vento", "weather.chart.wind"),
    ("wind_gust_speed", "Raffiche vento", "weather.chart.wind_gust"),
    ("temperature", "Temperatura", "weather.chart.temperature"),
    ("humidity", "Umidità", "weather.chart.humidity"),
    ("rain_rate", "Pioggia", "weather.chart.rain_rate"),
    ("barometer", "Barometro", "weather.chart.barometer"),
    ("barometer_trend", "Tendenza Barometro", "weather.chart.barometer_trend"),
)


class WeatherConverter:

    def convert(self, weather: Weather) -> WeatherResponse:
        response = WeatherResponse(
            charts=tuple(
                build_chart_from_config(
                    section,
                    value=getattr(weather, section)[0],
                    title=title,
                    urn=urn,
                    unit_of_measurement=getattr(weather, section)[1],
                )
                for section, title, urn in CHARTS
            ),
            updated_at=self.timestamp_or_none(weather.updated_at),
            interval=weather.time_expired
        )
        response.status = self.calculate_status(weather, response.charts)
        return response

    def validate_config(self):
        """Build every chart once with a placeholder reading, so that a broken
        threshold stops the startup instead of surfacing at the first check.
        """
        for section, title, urn in CHARTS:
            build_chart_from_config(
                section, value=0, title=title, urn=urn, unit_of_measurement=""
            )

    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp())
        else:
            return 0

    def calculate_status(self, weather, charts):
        status = WeatherStatus.WEATHER_STATUS_UNSPECIFIED
        if not weather.is_unavailable:
            for chart in charts:
                if not chart.thresholds:
                    continue
                logger.debug("chart is:")
                logger.debug(chart)
                if chart.status == ChartStatus.CHART_STATUS_UNSPECIFIED:
                    status = WeatherStatus.WEATHER_STATUS_UNSPECIFIED
                    break
                if status < WeatherStatus.WEATHER_STATUS_NORMAL and chart.status == ChartStatus.CHART_STATUS_NORMAL:
                    status = WeatherStatus.WEATHER_STATUS_NORMAL
                if status < WeatherStatus.WEATHER_STATUS_WARNING and chart.status == ChartStatus.CHART_STATUS_WARNING:
                    status = WeatherStatus.WEATHER_STATUS_WARNING
                if status < WeatherStatus.WEATHER_STATUS_DANGER and chart.status == ChartStatus.CHART_STATUS_DANGER:
                    status = WeatherStatus.WEATHER_STATUS_DANGER
                    break
                logger.debug(f"now weather status is: {status}")
        return status
