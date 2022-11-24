from datetime import datetime
from crac_protobuf.chart_pb2 import (
    WeatherResponse, # type: ignore
    Chart, # type: ignore
    Threshold, # type: ignore
    ThresholdType, # type: ignore
    ChartStatus,  # type: ignore
    WeatherStatus,  # type: ignore
)
from crac_server.component.weather.weather import Weather
from crac_server.config import Config
from typing import Any, Union

class WeatherConverter:
    def convert(self, weather: Weather) -> WeatherResponse:
        response = WeatherResponse(
            charts=(
                self.build_chart(
                    value=weather.wind_speed[0],
                    title="Vento",
                    urn="weather.chart.wind",
                    min=Config.getInt("lower_bound", "wind_speed"),
                    max=Config.getInt("upper_bound", "wind_speed"),
                    unit_of_measurement=weather.wind_speed[1],
                    range_normal=(
                        Config.getInt("warning", "wind_speed"),
                        Config.getInt("lower_bound", "wind_speed"),
                    ),
                    range_warn=(
                        Config.getInt("error", "wind_speed" ),
                        Config.getInt("warning", "wind_speed"),
                    ),
                    range_danger=(
                        Config.getInt( "upper_bound", "wind_speed"),
                        Config.getInt("error", "wind_speed"),
                    ),
                ),
                self.build_chart(
                    value=weather.wind_gust_speed[0],
                    title="Raffiche vento",
                    urn="weather.chart.wind_gust",
                    min=Config.getInt("lower_bound", "wind_gust_speed"),
                    max=Config.getInt("upper_bound", "wind_gust_speed"),
                    unit_of_measurement=weather.wind_gust_speed[1],
                    range_normal=(
                        Config.getInt("lower_bound", "wind_gust_speed"),
                        Config.getInt("warning", "wind_gust_speed"),
                    ),
                    range_warn=(
                        Config.getInt("warning", "wind_gust_speed"),
                        Config.getInt("error", "wind_gust_speed"),
                    ),
                    range_danger=(
                        Config.getInt("error", "wind_gust_speed"),
                        Config.getInt("upper_bound", "wind_gust_speed"),
                    ),
                ),
                self.build_chart(
                    value=weather.temperature[0],
                    title="Temperatura",
                    urn="weather.chart.temperature",
                    min=Config.getInt("lower_bound", "temperature"),
                    max=Config.getInt("upper_bound", "temperature"),
                    unit_of_measurement=weather.temperature[1],
                    range_normal=(
                        Config.getInt("lower_bound", "temperature"),
                        Config.getInt("warning", "temperature"),
                    ),
                    range_warn=(
                        Config.getInt("warning", "temperature"),
                        Config.getInt("upper_bound", "temperature"),
                    ),
                ),
                self.build_chart(
                    value=weather.humidity[0],
                    title="Umidità",
                    urn="weather.chart.humidity",
                    min=Config.getInt("lower_bound", "humidity"),
                    max=Config.getInt("upper_bound", "humidity"),
                    unit_of_measurement=weather.humidity[1],
                    range_normal=(
                        Config.getInt("warning", "humidity"),
                        Config.getInt("lower_bound", "humidity"),
                    ),
                    range_warn=(
                        Config.getInt("warning", "humidity"),
                        Config.getInt("error", "humidity"),
                    ),
                    range_danger=(
                        Config.getInt("error", "humidity"),
                        Config.getInt("upper_bound", "humidity"),
                    ),
                ),
                self.build_chart(
                    value=weather.rain_rate[0],
                    title="Pioggia",
                    urn="weather.chart.rain_rate",
                    min=Config.getInt("lower_bound", "rain_rate"),
                    max=Config.getInt("upper_bound", "rain_rate"),
                    unit_of_measurement=weather.rain_rate[1],
                    range_normal=(
                        Config.getInt("lower_bound", "rain_rate"),
                        Config.getInt("warning", "rain_rate"),
                    ),
                    range_warn=(
                        Config.getInt("warning", "rain_rate"),
                        Config.getInt("error", "rain_rate"),
                    ),
                    range_danger=(
                        Config.getInt("error", "rain_rate"),
                        Config.getInt("upper_bound", "rain_rate"),
                    ),
                ),
                self.build_chart(
                    value=weather.barometer[0],
                    title="Barometro",
                    urn="weather.chart.barometer",
                    min=Config.getInt("lower_bound", "barometer"),
                    max=Config.getInt("upper_bound", "barometer"),
                    unit_of_measurement=weather.barometer[1],
                    range_normal=(
                        Config.getInt("upper_bound", "barometer"),
                        Config.getInt("warning", "barometer"),
                    ),
                    range_warn=(
                        Config.getInt("warning", "barometer"),
                        Config.getInt("error", "barometer"),
                    ),
                    range_danger=(
                        Config.getInt("error", "barometer"),
                        Config.getInt("lower_bound", "barometer"),
                    ),
                ),
                self.build_chart(
                    value=weather.barometer_trend[0],
                    title="Tendenza Barometro",
                    urn="weather.chart.barometer_trend",
                    min=Config.getInt("lower_bound", "barometer_trend"),
                    max=Config.getInt("upper_bound", "barometer_trend"),
                    unit_of_measurement=weather.barometer_trend[1],
                    range_normal=(
                        Config.getInt("upper_bound", "barometer_trend"),
                        Config.getInt("warning", "barometer_trend"),
                    ),
                    range_warn=(
                        Config.getInt("warning", "barometer_trend"),
                        Config.getInt("error", "barometer_trend"),
                    ),
                    range_danger=(
                        Config.getInt("error", "barometer_trend"),
                        Config.getInt("lower_bound", "barometer_trend"),
                    ),
                )
            ),
            updated_at=self.timestamp_or_none(weather.updated_at)
        )

        status = WeatherStatus.WEATHER_STATUS_UNSPECIFIED
        for chart in response.charts:
            if status < WeatherStatus.WEATHER_STATUS_NORMAL and chart.status == ChartStatus.CHART_STATUS_NORMAL:
                status = WeatherStatus.WEATHER_STATUS_NORMAL
            if status < WeatherStatus.WEATHER_STATUS_WARNING and chart.status == ChartStatus.CHART_STATUS_WARNING:
                status = WeatherStatus.WEATHER_STATUS_WARNING
            if status < WeatherStatus.WEATHER_STATUS_DANGER and chart.status == ChartStatus.CHART_STATUS_DANGER:
                status = WeatherStatus.WEATHER_STATUS_DANGER
        response.status = status

        return response
    
    def timestamp_or_none(self, updated_at: Union[datetime, None]) -> int:
        if updated_at != None:
            return int(updated_at.timestamp()) 
        else: 
            return 0

    
    def build_chart(self, value: float, title: str, urn: str, min: float, max: float, unit_of_measurement: str, range_normal = None, range_warn = None, range_danger = None) -> Chart:
        chart = Chart(
            value=value,
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
                    upper_bound=range_normal[0],
                    lower_bound=range_normal[1],
                )
            )
        if range_warn:
            chart.thresholds.append(
                Threshold(
                    threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                    upper_bound=range_warn[0],
                    lower_bound=range_warn[1],
                )
            )
        if range_danger:
            chart.thresholds.append(
                Threshold(
                    threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                    upper_bound=range_danger[0],
                    lower_bound=range_danger[1],
                )
            )

        chart.status = ChartStatus.CHART_STATUS_UNSPECIFIED
        for threashold in chart.thresholds:
            if threashold.lower_bound <= chart.value <= threashold.upper_bound:
                if threashold.threshold_type == ThresholdType.THRESHOLD_TYPE_NORMAL:
                    chart.status = ChartStatus.CHART_STATUS_NORMAL
                elif threashold.threshold_type == ThresholdType.THRESHOLD_TYPE_WARNING:
                    chart.status = ChartStatus.CHART_STATUS_WARNING
                elif threashold.threshold_type == ThresholdType.THRESHOLD_TYPE_DANGER:
                    chart.status = ChartStatus.CHART_STATUS_DANGER
                break
        
        return chart
