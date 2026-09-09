CALLING_COMPONENT = 2
"""Keeps filename and lineno in the log pointing at the component that
detected the failure, instead of at this module."""


class ErrorCause:
    """Names of what went wrong, shared by every component so that the same
    failure reads the same way in the log wherever it happens."""

    DEVICE_UNREACHABLE = "device_unreachable"
    MOVEMENT_NOT_CONFIRMED = "movement_not_confirmed"
    SENSORS_INCONSISTENT = "sensors_inconsistent"
    BLOCKED_BY_SAFETY = "blocked_by_safety"
    STATE_NOT_RECOGNIZED = "state_not_recognized"
    UNEXPECTED_FAILURE = "unexpected_failure"


class StatusLogger:
    """Writes a component's failures to the log once per transition.

    Status is read by polling every few seconds, so logging every reading
    would bury the moment a fault appeared under thousands of identical
    lines. Only changes are written: the failure when it starts, and the
    recovery when it ends, which is what tells how long a fault lasted.
    """

    def __init__(self, logger, component: str, status_enum) -> None:
        self._logger = logger
        self._component = component
        self._status_enum = status_enum
        self._last_recorded = None

    def record(self, status, cause: str = None, detail: str = None) -> None:
        current = (status, cause)
        if current == self._last_recorded:
            return

        was_failing = self._last_recorded is not None and self._last_recorded[1] is not None
        self._last_recorded = current
        status_name = self._status_enum.Name(status)

        if cause:
            self._logger.error(
                "[%s] %s: %s%s",
                self._component, status_name, cause,
                f" ({detail})" if detail else "",
                stacklevel=CALLING_COMPONENT,
            )
        elif was_failing:
            self._logger.info(
                "[%s] recovered: %s", self._component, status_name,
                stacklevel=CALLING_COMPONENT,
            )
