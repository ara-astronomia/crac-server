import logging

from gpiozero import RotaryEncoder, DigitalInputDevice, Motor
from config import Config
from crac_protobuf.curtains_pb2 import CurtainStatus


logger = logging.getLogger(__name__)


class Curtain:
    def __init__(self, rotary_encoder, curtain_closed, curtain_open, motor):
        self.__base__()
        self.rotary_encoder = RotaryEncoder(**rotary_encoder)
        self.curtain_closed = DigitalInputDevice(**curtain_closed)
        self.curtain_open = DigitalInputDevice(**curtain_open)
        self.motor = Motor(**motor)
        self.motor.enable_device.off()
        self.__event_detect__()

    def __base__(self):
        self.__sub_min_step__ = -5
        self.__min_step__ = 0
        self.__max_step__ = Config.getInt("n_step_corsa", "encoder_step")
        self.__security_step__ = Config.getInt("n_step_sicurezza", "encoder_step")
        self.target = None

    def __event_detect__(self):
        self.curtain_closed.when_activated = self.__reset_steps__
        self.curtain_open.when_activated = self.__reset_steps__
        self.rotary_encoder.when_rotated = self.__check_and_stop__

    def __remove_event_detect__(self):
        self.rotary_encoder.when_rotated = None
        self.curtain_closed.when_activated = None
        self.curtain_open.when_activated = None

    def __open__(self):
        self.motor.forward()

    def __close__(self):
        self.motor.backward()

    def __stop__(self):
        self.motor.stop()

    def __check_and_stop__(self):
        logger.debug("Number of steps: %s", self.steps())
        logger.debug("target: %s", self.target)
        if (
            self.target is None or
            self.steps() == self.target or
            self.steps() >= self.__security_step__ or
            self.steps() <= self.__sub_min_step__
        ):
            self.__stop__()
            self.target = None

    def __reset_steps__(self, open_or_closed):
        self.__stop__()

        if open_or_closed == self.curtain_open:
            self.rotary_encoder.steps = self.__max_step__
        elif open_or_closed == self.curtain_closed:
            self.rotary_encoder.steps = self.__min_step__

    def __is_danger__(self):
        return (
            self.steps() > self.__max_step__ or self.steps() < self.__min_step__ or
            (self.steps() == self.__max_step__ and not self.curtain_open.is_active and self.motor.value == 1) or
            (self.steps() == self.__min_step__ and not self.curtain_closed.is_active and self.motor.value == -1)
        )

    def __is_disabled__(self):
        return self.curtain_closed.is_active and not self.motor.value and not self.motor.enable_device.value

    def __is_opening__(self):
        return self.motor.value == 1

    def __is_closing__(self):
        return self.motor.value == -1

    def __is_open__(self):
        return self.curtain_open.is_active and not self.curtain_closed.is_active and not self.motor.value

    def __is_closed__(self):
        return self.curtain_closed.is_active and not self.curtain_open.is_active and not self.motor.value

    def __is_stopped__(self):
        return not self.curtain_closed.is_active and not self.curtain_open.is_active and not self.motor.value

    def manual_reset(self):

        """ Reset the steps counter with the help of the edge switchers """

        if not self.motor.enable_device.value:
            return

        status = self.get_status()
        if status != CurtainStatus.CURTAIN_STOPPED and status != CurtainStatus.CURTAIN_DANGER:
            return
        self.__remove_event_detect__()

        distance_to_min_step = abs(self.steps() - self.__min_step__)
        distance_to_max_step = abs(self.__max_step__ - self.steps())

        if distance_to_min_step <= distance_to_max_step:
            if self.steps() > self.__min_step__:
                self.__close__()
            else:
                self.__open__()
            self.curtain_closed.wait_for_active()
            self.__stop__()
            self.rotary_encoder.steps = self.__min_step__
        else:
            if self.steps() > self.__max_step__:
                self.__close__()
            else:
                self.__open__()
            self.curtain_open.wait_for_active()
            self.__stop__()
            self.rotary_encoder.steps = self.__max_step__

        self.__event_detect__()

    def steps(self):
        return self.rotary_encoder.steps

    def get_status(self):

        """ Read the status of the curtain based on the pin of motor, encoder and switches """

        status = CurtainStatus.CURTAIN_ERROR

        if self.__is_danger__():
            status = CurtainStatus.CURTAIN_DANGER
        elif self.__is_disabled__():
            status = CurtainStatus.CURTAIN_DISABLED
        elif self.__is_opening__():
            status = CurtainStatus.CURTAIN_OPENING
        elif self.__is_closing__():
            status = CurtainStatus.CURTAIN_CLOSING
        elif self.__is_open__():
            status = CurtainStatus.CURTAIN_OPENED
        elif self.__is_closed__():
            status = CurtainStatus.CURTAIN_CLOSED
        elif self.__is_stopped__():
            status = CurtainStatus.CURTAIN_STOPPED

        return status

    def move(self, step):

        """ Move the motor in a direction based on the starting and target steps """

        # if curtains are disabled, we don't want to move them
        if not self.motor.enable_device.value:
            return

        status = self.get_status()
        logger.debug("Status in move method: %s", status)
        
        # while the motors are moving we don't want to start another movement
        if status > CurtainStatus.CURTAIN_OPENED or self.motor.value:
            return

        self.target = step

        # deciding the movement direction
        if self.steps() < self.target:
            self.__open__()
        elif self.steps() > self.target:
            self.__close__()

    def open_up(self):

        """
            Open up the curtain completely
            It's a shortcut to move()
        """

        self.move(self.__max_step__)

    def bring_down(self):

        """
            Bring down the curtain completely
            It's a shortcut to move()
        """

        self.move(self.__min_step__)

    def disable(self):
        self.bring_down()
        self.motor.enable_device.off()

    def enable(self):
        self.motor.enable_device.on()

    def motor_stop(self):

        """
            disable motor
        """

        self.__stop__()
