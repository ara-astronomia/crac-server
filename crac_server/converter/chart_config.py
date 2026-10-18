import logging

from crac_protobuf.chart_pb2 import Chart  # type: ignore
from crac_server.config import Config
from crac_server.converter.chart_builder import build_chart

logger = logging.getLogger(__name__)

LEVEL_KEYS = ("warning", "danger")
SCALE_KEY = "scale"


class ChartConfigError(ValueError):
    pass


def build_chart_from_config(
    section: str, *, value: float, title: str, urn: str, unit_of_measurement: str
) -> Chart:
    try:
        keys = Config.get_section_keys(section)
    except KeyError:
        raise ChartConfigError(f"[{section}]: the section is missing in config.ini")
    _reject_unknown_keys(section, keys)
    scale = _scale(section, keys)
    claimed = {level: _level_ranges(section, level, scale) for level in LEVEL_KEYS if level in keys}
    visible_warning = _subtract(claimed.get("warning", ()), claimed.get("danger", ()))
    if claimed.get("warning") and not visible_warning:
        logger.warning(f"[{section}]: 'warning' is entirely covered by 'danger': no reading can ever show it")
    return build_chart(
        value=value,
        title=title,
        urn=urn,
        min=scale[0],
        max=scale[1],
        unit_of_measurement=unit_of_measurement,
        range_normal=_normal(scale, claimed),
        range_warn=_as_bands(visible_warning),
        range_danger=_as_bands(claimed.get("danger", ())),
    )


def _reject_unknown_keys(section, keys):
    unknown = [key for key in keys if key not in (SCALE_KEY,) + LEVEL_KEYS]
    if unknown:
        raise ChartConfigError(
            f"[{section}]: unknown keys {unknown}, the valid ones are "
            f"'{SCALE_KEY}' and the levels {list(LEVEL_KEYS)}"
        )


def _scale(section, keys):
    if SCALE_KEY not in keys:
        raise ChartConfigError(f"[{section}]: '{SCALE_KEY}' is required, in the form 'min..max'")
    lower, upper = _parse_range(section, SCALE_KEY, Config.getValue(SCALE_KEY, section))
    if lower is None or upper is None:
        raise ChartConfigError(f"[{section}]: '{SCALE_KEY}' must be closed, in the form 'min..max'")
    if lower > upper:
        raise ChartConfigError(f"[{section}]: '{SCALE_KEY}' is inverted, {lower} is above {upper}")
    return (lower, upper)


def _level_ranges(section, level, scale):
    text = Config.getValue(level, section)
    if not text:
        raise ChartConfigError(f"[{section}]: '{level}' is empty, remove it or write its ranges")
    ranges = tuple(
        _clamped_to_scale(section, level, _parse_range(section, level, part.strip()), scale, part.strip())
        for part in text.split(",")
    )
    _warn_overlapping_ranges(section, level, ranges, text)
    return ranges


def _warn_overlapping_ranges(section, level, ranges, text):
    ordered = sorted(ranges)
    for previous, following in zip(ordered, ordered[1:]):
        if following[0] < previous[1]:
            logger.warning(f"[{section}]: '{level}' ranges overlap in {text!r}: check for a range written twice")


def _parse_range(section, key, text):
    parts = text.split("..")
    if len(parts) != 2:
        raise ChartConfigError(f"[{section}]: '{key}' must be a range like '10..', '..1005' or '10..20', got {text!r}")
    try:
        endpoints = (_endpoint(parts[0]), _endpoint(parts[1]))
    except ValueError:
        raise ChartConfigError(f"[{section}]: '{key}' has a non numeric endpoint, got {text!r}")
    _warn_dotted_endpoints(section, key, parts, endpoints, text)
    return endpoints


def _warn_dotted_endpoints(section, key, parts, endpoints, text):
    for part, endpoint in zip(parts, endpoints):
        if endpoint is not None and part.strip().startswith("."):
            logger.warning(
                f"[{section}]: '{key}' endpoint {part.strip()!r} in {text!r} reads as {endpoint}: "
                f"an endpoint starting with a dot is usually a '...' typo"
            )


def _endpoint(text):
    if not text.strip():
        return None
    return float(text.strip())


def _clamped_to_scale(section, level, range_, scale, text):
    lower, upper = range_
    if lower is not None and upper is not None and lower > upper:
        raise ChartConfigError(f"[{section}]: '{level}' is inverted, got {text!r}")
    clamped = (
        scale[0] if lower is None else max(lower, scale[0]),
        scale[1] if upper is None else min(upper, scale[1]),
    )
    if clamped[0] > clamped[1]:
        raise ChartConfigError(
            f"[{section}]: '{level}' does not intersect the scale {scale[0]}..{scale[1]}, got {text!r}"
        )
    if (lower is not None and lower < scale[0]) or (upper is not None and upper > scale[1]):
        logger.warning(
            f"[{section}]: '{level}' range {text!r} extends past the scale {scale[0]}..{scale[1]}: "
            f"the part outside is clamped away"
        )
    return clamped


def _normal(scale, claimed):
    if not claimed:
        return tuple()
    lower = scale[0]
    normal = []
    for claimed_lower, claimed_upper in sorted(interval for ranges in claimed.values() for interval in ranges):
        if claimed_lower > lower:
            normal.append((lower, claimed_lower))
        lower = max(lower, claimed_upper)
    if lower < scale[1]:
        normal.append((lower, scale[1]))
    return _as_bands(normal)


def _subtract(intervals, removed):
    """The parts no removed interval covers: the wire carries non
    overlapping bands, so a gauge never paints a milder level over a
    more severe one."""
    remaining = []
    for lower, upper in sorted(intervals):
        pieces = [(lower, upper)]
        for removed_lower, removed_upper in sorted(removed):
            survived = []
            for piece_lower, piece_upper in pieces:
                if removed_upper <= piece_lower or removed_lower >= piece_upper:
                    survived.append((piece_lower, piece_upper))
                    continue
                if removed_lower > piece_lower:
                    survived.append((piece_lower, removed_lower))
                if removed_upper < piece_upper:
                    survived.append((removed_upper, piece_upper))
            pieces = survived
        remaining.extend(pieces)
    return sorted(remaining)


def _as_bands(intervals):
    return tuple({"lower_bound": lower, "upper_bound": upper} for lower, upper in intervals)
