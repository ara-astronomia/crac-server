from crac_protobuf.curtains_pb2 import CurtainOrientation
from crac_server.config import Config
from crac_server.component.curtains.curtains import Curtain


class BuilderCurtain:

    def __init__(self) -> None:
        self._rotary_encoder: dict[str, int] = None
        self._verify_closed: dict[str, int] = None
        self._verify_open: dict[str, int] = None
        self._motor: dict[str, int] = None

    @property
    def rotary_encoder(self):
        return self._rotary_encoder

    @rotary_encoder.setter
    def rotary_encoder(self, rotary_encoder):
        self._rotary_encoder = rotary_encoder

    @property
    def verify_open(self):
        return self._verify_open

    @verify_open.setter
    def verify_open(self, verify_open):
        self._verify_open = verify_open

    @property
    def verify_closed(self):
        return self._verify_closed

    @verify_closed.setter
    def verify_closed(self, verify_closed):
        self._verify_closed = verify_closed

    @property
    def motor(self):
        return self._motor

    @motor.setter
    def motor(self, motor):
        self._motor = motor

    def build(self, mock: bool) -> Curtain:
        if mock:
            from crac_server.component.curtains.simulator.curtains import MockCurtain as Curtain
        else:
            from crac_server.component.curtains.curtains import Curtain

        return Curtain(
            self.rotary_encoder,
            self.verify_closed,
            self.verify_open,
            self.motor
        )


class FactoryCurtain:

    @staticmethod
    def __builder__(forward: int, backward: int, enable: int, a: int, b: int, pin_open: int, pin_closed: int):
        builder_curtain = BuilderCurtain()
        builder_curtain.motor = {
            "forward": forward,
            "backward": backward,
            "enable": enable,
            "pwm": False
        }
        builder_curtain.rotary_encoder = {
            "a": a,
            "b": b,
            "max_steps": Config.getInt("n_step_sicurezza", "encoder_step")
        }
        builder_curtain.verify_open = {
            "pin": pin_open,
            "pull_up": True
        }
        builder_curtain.verify_closed = {
            "pin": pin_closed,
            "pull_up": True
        }
        return builder_curtain

    @staticmethod
    def curtain(orientation: CurtainOrientation, mock=False):
        if orientation is CurtainOrientation.CURTAIN_EAST:
            builder_curtain = FactoryCurtain.__builder__(
                Config.getInt("motorE_A", "motor_board"),
                Config.getInt("motorE_B", "motor_board"),
                Config.getInt("motorE_E", "motor_board"),
                Config.getInt("clk_e", "encoder_board"),
                Config.getInt("dt_e", "encoder_board"),
                Config.getInt("curtain_E_verify_open", "curtains_limit_switch"),
                Config.getInt("curtain_E_verify_closed", "curtains_limit_switch")
            )
        elif orientation is CurtainOrientation.CURTAIN_WEST:
            builder_curtain = FactoryCurtain.__builder__(
                Config.getInt("motorW_A", "motor_board"),
                Config.getInt("motorW_B", "motor_board"),
                Config.getInt("motorW_E", "motor_board"),
                Config.getInt("clk_w", "encoder_board"),
                Config.getInt("dt_w", "encoder_board"),
                Config.getInt("curtain_W_verify_open", "curtains_limit_switch"),
                Config.getInt("curtain_W_verify_closed", "curtains_limit_switch")
            )
        else:
            raise ValueError("Orientation invalid")

        return builder_curtain.build(mock)


CURTAIN_EAST = FactoryCurtain.curtain(orientation=CurtainOrientation.CURTAIN_EAST, mock=Config.getBoolean("gpio_mock", "server"))
CURTAIN_WEST = FactoryCurtain.curtain(orientation=CurtainOrientation.CURTAIN_WEST, mock=Config.getBoolean("gpio_mock", "server"))