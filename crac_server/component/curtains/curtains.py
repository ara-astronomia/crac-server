import logging
import threading
import time
from typing import Union
from gpiozero import RotaryEncoder, DigitalInputDevice, Motor
from crac_server.config import Config
from crac_protobuf.curtains_pb2 import CurtainStatus
from crac_server.status_log import ErrorCause, StatusLogger


logger = logging.getLogger(__name__)

BOTTOM_STEP = 0


class Curtain:
    """Follows a target with its encoder, and goes down to its closed switch,
    which the encoder is not reliable enough to replace. The lock is taken by
    the public methods and the GPIO callbacks only."""

    def __init__(self, encoder: dict[str, int], closed_switch: dict[str, int], open_switch: dict[str, int], motor: dict[str, int], orientation: str):
        self._full_travel = Config.getInt("n_step_corsa", "encoder_step")
        self._safety_step = Config.getInt("n_step_sicurezza", "encoder_step")
        self._tolerance_steps = Config.getInt("tolerance_steps", "encoder_step")
        self._reverse_pause = Config.getFloat("reverse_pause", "motor_board")
        self._target: Union[None, int] = None
        self._to_disable = False
        self._orientation = orientation
        self._status_log = StatusLogger(logger, orientation, CurtainStatus)
        self._lock = threading.Lock()
        self._resting: Union[None, threading.Timer] = None
        self._resting_direction = 0
        self._last_direction = 0
        self._stopped_at = 0.0
        self._encoder = RotaryEncoder(**encoder)
        self._closed_switch = DigitalInputDevice(**closed_switch)
        self._open_switch = DigitalInputDevice(**open_switch)
        self._motor = Motor(**motor)
        self._closed_switch.when_activated = self._on_switch
        self._open_switch.when_activated = self._on_switch
        self._encoder.when_rotated = self._on_rotation

    @property
    def full_travel(self) -> int:
        """Steps of a full opening, read once at startup."""
        return self._full_travel

    def steps(self) -> int:
        return self._encoder.steps

    def get_status(self) -> CurtainStatus:
        """Each pin is read once, so that a motor starting halfway through
        cannot make the reading inconsistent."""
        motor = self._motor.value
        enabled = self._motor.enable_device.value
        closed = self._closed_switch.is_active
        opened = self._open_switch.is_active
        steps = self.steps()

        if steps > self._safety_step:
            status = CurtainStatus.CURTAIN_DANGER
        elif closed and not motor and not enabled:
            status = CurtainStatus.CURTAIN_DISABLED
        elif motor == 1:
            status = CurtainStatus.CURTAIN_OPENING
        elif motor == -1:
            status = CurtainStatus.CURTAIN_DISABLING if self._to_disable else CurtainStatus.CURTAIN_CLOSING
        elif closed and opened:
            status = CurtainStatus.CURTAIN_ERROR
        elif closed:
            status = CurtainStatus.CURTAIN_CLOSED
        elif opened or steps >= self._full_travel:
            status = CurtainStatus.CURTAIN_OPENED
        else:
            status = CurtainStatus.CURTAIN_STOPPED

        if status is CurtainStatus.CURTAIN_ERROR:
            self._status_log.record(
                status, ErrorCause.STATE_NOT_RECOGNIZED,
                detail=f"closed={closed} open={opened} motor={motor}",
            )
        else:
            self._status_log.record(status)

        return status

    def move(self, step: int):
        """Move towards step, unless the motor is disabled or the curtain is
        already moving; during a reversal rest only the target changes. Step 0
        means down to the closed switch."""
        with self._lock:
            if not self._motor.enable_device.value:
                return
            if self._resting:
                if not self._to_disable:
                    self._target = step
                return
            if self.get_status() > CurtainStatus.CURTAIN_OPENED or self._motor.value:
                return

            logger.debug("Curtain %s: from step %s to %s", self._orientation, self.steps(), step)
            direction = self._direction_to(step)
            if direction:
                self._target = step
                self._drive(direction)

    def disable(self, power_motor: bool = False):
        """Bring the curtain down and disable its motor on the closed switch.
        power_motor enables a disabled motor first: only for an operator's
        request, since a curtain on a broken closed switch looks halfway too."""
        with self._lock:
            logger.debug("Curtain %s: disable, power_motor=%s", self._orientation, power_motor)
            self._to_disable = True
            if self._is_down():
                self._stop()
                self._disable_motor()
                return
            if power_motor:
                self._motor.enable_device.on()
            self._bring_down()

    def enable(self):
        """Also cancels a disable() still on its way down."""
        with self._lock:
            logger.debug("Curtain %s: enable", self._orientation)
            self._to_disable = False
            self._motor.enable_device.on()

    def _bring_down(self):
        """A disabled motor gets no direction it cannot follow."""
        if self._is_down() or not self._motor.enable_device.value:
            return
        self._target = BOTTOM_STEP
        self._drive(-1)

    def _disable_motor(self):
        self._motor.enable_device.off()
        self._to_disable = False

    def _direction_to(self, target: int) -> int:
        """1 up, -1 down, 0 when already there."""
        if target <= BOTTOM_STEP:
            return 0 if self._is_down() else -1
        if self.steps() < target - self._tolerance_steps:
            return 1
        if self.steps() > target + self._tolerance_steps:
            return -1
        return 0

    def _drive(self, direction: int):
        """Turning the other way waits until reverse_pause seconds have passed
        since the stop, on a timer, so the lock and the caller are free. A
        command during the rest does not make it longer."""
        if self._resting:
            self._resting_direction = direction
            return
        if self._motor.value == direction:
            return
        if self._motor.value == -direction:
            self._stop()
        rest = self._reverse_pause - (time.monotonic() - self._stopped_at) if self._last_direction == -direction else 0
        if rest > 0:
            self._resting_direction = direction
            self._resting = threading.Timer(rest, self._after_rest)
            self._resting.daemon = True
            self._resting.start()
        else:
            self._start(direction)

    def _after_rest(self):
        """Head for the target of this moment, which may have changed."""
        with self._lock:
            if threading.current_thread() is not self._resting:
                return
            self._resting = None
            direction = self._resting_direction if self._target is None else self._direction_to(self._target)
            if direction:
                self._start(direction)

    def _start(self, direction: int):
        if direction == 1:
            self._motor.forward()
        elif direction == -1:
            self._motor.backward()

    def _stop(self):
        """Stops the motor and cancels a pending restart after a rest."""
        if self._resting:
            self._resting.cancel()
            self._resting = None
        if self._motor.value:
            self._last_direction = self._motor.value
            self._stopped_at = time.monotonic()
        self._motor.stop()

    def _on_rotation(self):
        """Stop at the target or at the safety step. A curtain going down runs
        until the closed switch, whatever the encoder says."""
        with self._lock:
            if not self._motor.value or self._closing_to_the_switch():
                return
            if (
                self._target is None or
                self._target - self._tolerance_steps <= self.steps() <= self._target or
                self.steps() >= self._safety_step or
                not self._motor.enable_device.value
            ):
                self._stop()
                logger.debug("Curtain %s: stopped at step %s, target %s", self._orientation, self.steps(), self._target)
                self._target = None

    def _on_switch(self, switch: DigitalInputDevice):
        """Set the encoder, and stop a curtain running into the switch. On the
        closed switch a curtain being disabled gets its motor disabled."""
        with self._lock:
            if switch is self._open_switch:
                self._encoder.steps = self._full_travel
                if self._motor.value == 1:
                    self._stop()
                    self._target = None
                return
            self._encoder.steps = BOTTOM_STEP
            if self._motor.value == -1:
                self._stop()
                self._target = None
            logger.debug("Curtain %s: on the closed switch, to_disable=%s", self._orientation, self._to_disable)
            if self._to_disable and not self._motor.value:
                self._stop()
                self._disable_motor()

    def _closing_to_the_switch(self) -> bool:
        return self._target is not None and self._target <= BOTTOM_STEP and self._motor.value == -1

    def _is_down(self) -> bool:
        """Only the closed switch says the curtain is down."""
        return self._closed_switch.is_active
