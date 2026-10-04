import logging
import threading
from time import sleep
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
        """Read from the motor, the encoder and the switches."""
        if self._is_danger():
            status = CurtainStatus.CURTAIN_DANGER
        elif self._is_disabled():
            status = CurtainStatus.CURTAIN_DISABLED
        elif self._motor.value == 1:
            status = CurtainStatus.CURTAIN_OPENING
        elif self._motor.value == -1:
            status = CurtainStatus.CURTAIN_DISABLING if self._to_disable else CurtainStatus.CURTAIN_CLOSING
        elif self._is_open():
            status = CurtainStatus.CURTAIN_OPENED
        elif self._is_closed():
            status = CurtainStatus.CURTAIN_CLOSED
        elif self._is_stopped():
            status = CurtainStatus.CURTAIN_STOPPED
        else:
            status = CurtainStatus.CURTAIN_ERROR

        if status is CurtainStatus.CURTAIN_ERROR:
            self._status_log.record(
                status, ErrorCause.STATE_NOT_RECOGNIZED,
                detail=f"closed={self._closed_switch.is_active} open={self._open_switch.is_active} motor={self._motor.value}",
            )
        else:
            self._status_log.record(status)

        return status

    def move(self, step: int):
        """Move towards step, unless the motor is disabled or the curtain is
        already moving. Step 0 means down to the closed switch."""
        with self._lock:
            if not self._motor.enable_device.value:
                return
            if self.get_status() > CurtainStatus.CURTAIN_OPENED or self._motor.value:
                return

            logger.debug("Curtain %s: from step %s to %s", self._orientation, self.steps(), step)
            if step <= BOTTOM_STEP:
                self._bring_down()
            elif self.steps() < step - self._tolerance_steps:
                self._target = step
                self._open()
            elif self.steps() > step + self._tolerance_steps:
                self._target = step
                self._close()

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
        if self._is_down():
            return
        self._target = BOTTOM_STEP
        self._close()

    def _disable_motor(self):
        self._motor.enable_device.off()
        self._to_disable = False

    def _open(self):
        self._stop_before_reversing(1)
        self._motor.forward()

    def _close(self):
        self._stop_before_reversing(-1)
        self._motor.backward()

    def _stop(self):
        self._motor.stop()

    def _stop_before_reversing(self, direction: int):
        """A motor never turns the other way while running: it stops and rests
        for reverse_pause seconds first."""
        if self._motor.value == -direction:
            self._stop()
            sleep(self._reverse_pause)

    def _on_rotation(self):
        """Stop at the target or at the safety step. A curtain going down runs
        until the closed switch, whatever the encoder says."""
        with self._lock:
            if self._closing_to_the_switch():
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
        """Stop and set the encoder; the closed switch also disables the motor
        of a curtain being disabled."""
        with self._lock:
            self._target = None
            self._stop()
            if switch is self._open_switch:
                self._encoder.steps = self._full_travel
            else:
                self._encoder.steps = BOTTOM_STEP
                logger.debug("Curtain %s: on the closed switch, to_disable=%s", self._orientation, self._to_disable)
                if self._to_disable:
                    self._disable_motor()

    def _closing_to_the_switch(self) -> bool:
        return self._target is not None and self._target <= BOTTOM_STEP and self._motor.value == -1

    def _is_danger(self) -> bool:
        return self.steps() > self._safety_step

    def _is_down(self) -> bool:
        """Only the closed switch says the curtain is down."""
        return self._closed_switch.is_active

    def _is_disabled(self) -> bool:
        return self._is_down() and not self._motor.value and not self._motor.enable_device.value

    def _is_open(self) -> bool:
        """Full travel is read from the encoder: the curtains run out of
        travel before reaching the open switch."""
        return (
            (self._open_switch.is_active or self.steps() >= self._full_travel) and
            not self._closed_switch.is_active and not self._motor.value
        )

    def _is_closed(self) -> bool:
        return self._closed_switch.is_active and not self._open_switch.is_active and not self._motor.value

    def _is_stopped(self) -> bool:
        return not self._closed_switch.is_active and not self._open_switch.is_active and not self._motor.value
