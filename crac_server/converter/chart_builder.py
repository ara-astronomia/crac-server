from crac_protobuf.chart_pb2 import (
    Chart, # type: ignore
    Threshold, # type: ignore
    ThresholdType, # type: ignore
    ChartStatus,  # type: ignore
)
from typing import Union
  

def build_chart(
    value: float, 
    title: str, 
    urn: str, 
    min: float, 
    max: float, 
    unit_of_measurement: str, 
    range_normal: tuple[dict[str,float]], 
    range_warn: Union[tuple[dict[str,float]],tuple] = tuple(), 
    range_danger: Union[tuple[dict[str,float]],tuple] = tuple()
) -> Chart:
    chart = Chart(
        value=value,
        title=title,
        urn=urn,
        min=min,
        max=max,
        unit_of_measurement=unit_of_measurement
    )
    for normal in range_normal:
        chart.thresholds.append(
            Threshold(
                threshold_type=ThresholdType.THRESHOLD_TYPE_NORMAL,
                upper_bound=normal["upper_bound"],
                lower_bound=normal["lower_bound"],
            )
        )
    for warn in range_warn:
        chart.thresholds.append(
            Threshold(
                threshold_type=ThresholdType.THRESHOLD_TYPE_WARNING,
                upper_bound=warn["upper_bound"],
                lower_bound=warn["lower_bound"],
            )
        )
    for danger in range_danger:
        chart.thresholds.append(
            Threshold(
                threshold_type=ThresholdType.THRESHOLD_TYPE_DANGER,
                upper_bound=danger["upper_bound"],
                lower_bound=danger["lower_bound"],
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
