from datetime import datetime
import logging
from crac_protobuf.chart_pb2 import (
    WeatherResponse, # type: ignore
    Chart, # type: ignore
    Threshold, # type: ignore
    ThresholdType, # type: ignore
    ChartStatus,  # type: ignore
)
from crac_server.component.weather.weather import Weather
from crac_server.config import Config
from crac_server.converter.chart_builder import build_chart
from typing import Union


logger = logging.getLogger(__name__)


class WeatherConverter:
    def convert(self, weather: Weather) -> WeatherResponse:
        response = WeatherResponse(
            charts=(
                build_chart(
                    value=weather.wind_speed[0],
                    title="Vento",
                    urn="weather.chart.wind",
                    min=Config.getInt("lower_bound", "wind_speed"),
                    max=Config.getInt("upper_bound", "wind_speed"),
                    unit_of_measurement=weather.wind_speed[1],
                    range_normal=({
                        "upper_bound": Config.getInt("warning", "wind_speed"),
                        "lower_bound": Config.getInt("lower_bound", "wind_speed"),
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("error", "wind_speed"),
                        "lower_bound": Config.getInt("warning", "wind_speed"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getInt("upper_bound", "wind_speed"),
                        "lower_bound": Config.getInt("error", "wind_speed"),
                    },)
                ),
                build_chart(
                    value=weather.wind_gust_speed[0],
                    title="Raffiche vento",
                    urn="weather.chart.wind_gust",
                    min=Config.getInt("lower_bound", "wind_gust_speed"),
                    max=Config.getInt("upper_bound", "wind_gust_speed"),
                    unit_of_measurement=weather.wind_gust_speed[1],
                    range_normal=({
                        "upper_bound": Config.getInt("warning", "wind_gust_speed"),
                        "lower_bound": Config.getInt("lower_bound", "wind_gust_speed"),
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("error", "wind_gust_speed"),
                        "lower_bound": Config.getInt("warning", "wind_gust_speed"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getInt("upper_bound", "wind_gust_speed"),
                        "lower_bound": Config.getInt("error", "wind_gust_speed"),
                    },)
                ),
                build_chart(
                    value=weather.temperature[0],
                    title="Temperatura",
                    urn="weather.chart.temperature",
                    min=Config.getInt("lower_bound", "temperature"),
                    max=Config.getInt("upper_bound", "temperature"),
                    unit_of_measurement=weather.temperature[1],
                    range_normal=({
                        "upper_bound": Config.getInt("warning", "temperature"),
                        "lower_bound": Config.getInt("lower_bound", "temperature"),
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("upper_bound", "temperature"),
                        "lower_bound": Config.getInt("warning", "temperature"),
                    },),
                ),
                build_chart(
                    value=weather.humidity[0],
                    title="Umidità",
                    urn="weather.chart.humidity",
                    min=Config.getInt("lower_bound", "humidity"),
                    max=Config.getInt("upper_bound", "humidity"),
                    unit_of_measurement=weather.humidity[1],
                    range_normal=({
                        "upper_bound": Config.getInt("warning", "humidity"),
                        "lower_bound": Config.getInt("lower_bound", "humidity"),
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("error", "humidity"),
                        "lower_bound": Config.getInt("warning", "humidity"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getInt("upper_bound", "humidity"),
                        "lower_bound": Config.getInt("error", "humidity"),
                    },)
                ),
                build_chart(
                    value=weather.rain_rate[0],
                    title="Pioggia",
                    urn="weather.chart.rain_rate",
                    min=Config.getInt("lower_bound", "rain_rate"),
                    max=Config.getInt("upper_bound", "rain_rate"),
                    unit_of_measurement=weather.rain_rate[1],
                    range_normal=({
                        "upper_bound": Config.getInt("warning", "rain_rate"),
                        "lower_bound": Config.getInt("lower_bound", "rain_rate"),
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("error", "rain_rate"),
                        "lower_bound": Config.getInt("warning", "rain_rate"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getInt("upper_bound", "rain_rate"),
                        "lower_bound": Config.getInt("error", "rain_rate"),
                    },)
                ),
                build_chart(
                    value=weather.barometer[0],
                    title="Barometro",
                    urn="weather.chart.barometer",
                    min=Config.getInt("lower_bound", "barometer"),
                    max=Config.getInt("upper_bound", "barometer"),
                    unit_of_measurement=weather.barometer[1],
                    range_normal=({
                        "upper_bound": Config.getFloat("upper_bound", "barometer"),
                        "lower_bound": Config.getFloat("warning", "barometer")
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("warning", "barometer"),
                        "lower_bound": Config.getInt("error", "barometer"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getInt("error", "barometer"),
                        "lower_bound": Config.getInt("lower_bound", "barometer"),
                    },)
                ),
                build_chart(
                    value=weather.barometer_trend[0],
                    title="Tendenza Barometro",
                    urn="weather.chart.barometer_trend",
                    min=Config.getInt("lower_bound", "barometer_trend"),
                    max=Config.getInt("upper_bound", "barometer_trend"),
                    unit_of_measurement=weather.barometer_trend[1],
                    range_normal=({
                        "upper_bound": Config.getFloat("upper_bound", "barometer_trend"),
                        "lower_bound": Config.getFloat("warning", "barometer_trend")
                    },),
                    range_warn=({
                        "upper_bound": Config.getInt("warning", "barometer_trend"),
                        "lower_bound": Config.getInt("error", "barometer_trend"),
                    },),
                    range_danger=({
                        "upper_bound": Config.getInt("error", "barometer_trend"),
                        "lower_bound": Config.getInt("lower_bound", "barometer_trend"),
                    },)
                )
            ),
            updated_at=self.timestamp_or_none(weather.updated_at),
            interval=weather.time_expired
        )
        response.status = self.calculate_status(weather, response.charts)
        return response
    
    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp()) 
        else: 
            return 0

    def calculate_status(self, weather, charts):
        status = WeatherStatus.WEATHER_STATUS_UNSPECIFIED
        if not weather.is_unavailable:
            for chart in charts:
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
    
    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp()) 
        else: 
            return 0

    def __value_or_zero(self, value):
        if value == 'N/A':
            return 0
        return value
    
    def build_chart(self, value: Union[float,str], title: str, urn: str, min: float, max: float, unit_of_measurement: str, range_normal: Union[dict[str,float],None], range_warn: Union[dict[str,float],None] = None, range_danger: Union[dict[str,float],None] = None) -> Chart:
        chart = Chart(
            value=self.__value_or_zero(value),
            title=title,
            urn=urn,
            min=min,
            max=max,
            unit_of_measurement=unit_of_measurement
        )
        if range_normal:
            chart.thresholds.append(
                Threshold(
                    threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                    upper_bound=range_normal["upper_bound"],
                    lower_bound=range_normal["lower_bound"],
                )
            )
        if range_warn:
            chart.thresholds.append(
                Threshold(
                    threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                    upper_bound=range_warn["upper_bound"],
                    lower_bound=range_warn["lower_bound"],
                )
            )
        if range_danger:
            chart.thresholds.append(
                Threshold(
                    threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                    upper_bound=range_danger["upper_bound"],
                    lower_bound=range_danger["lower_bound"],
                )
            )

        chart.status = ChartStatus.CHART_STATUS_UNSPECIFIED
        if value != 'N/A':
            for threashold in chart.thresholds:
                if threashold.lower_bound <= chart.value <= threashold.upper_bound:
                    if threashold.threshold_type == ThresholdType.THRESHOLD_TYPE_NORMAL:
                        chart.status = ChartStatus.CHART_STATUS_NORMAL
                    elif threashold.threshold_type == ThresholdType.THRESHOLD_TYPE_WARNING:
                        chart.status = ChartStatus.CHART_STATUS_WARNING
                    elif threashold.threshold_type == ThresholdType.THRESHOLD_TYPE_DANGER:
                        chart.status = ChartStatus.CHART_STATUS_DANGER
                    break
        
        return status