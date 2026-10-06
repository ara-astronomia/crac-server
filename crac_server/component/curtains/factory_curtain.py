from functools import lru_cache
from crac_protobuf.curtains_pb2 import CurtainOrientation
from crac_server.config import Config
from crac_server.component.curtains.curtains import Curtain


def build_curtain(orientation: CurtainOrientation, mock: bool = False) -> Curtain:
    """Build a curtain from config.ini and bring it down: whatever position it
    starts in, it ends up disabled on its closed switch."""
    if orientation is CurtainOrientation.CURTAIN_EAST:
        side, motor_side = "e", "E"
    elif orientation is CurtainOrientation.CURTAIN_WEST:
        side, motor_side = "w", "W"
    else:
        raise ValueError("Orientation invalid")

    if mock:
        from crac_server.component.curtains.simulator.curtains import MockCurtain as CurtainClass
    else:
        CurtainClass = Curtain

    curtain = CurtainClass(
        encoder={
            "a": Config.getInt(f"clk_{side}", "encoder_board"),
            "b": Config.getInt(f"dt_{side}", "encoder_board"),
            "max_steps": Config.getInt("n_step_sicurezza", "encoder_step"),
        },
        closed_switch={"pin": Config.getInt(f"curtain_{motor_side}_verify_closed", "curtains_limit_switch"), "pull_up": True},
        open_switch={"pin": Config.getInt(f"curtain_{motor_side}_verify_open", "curtains_limit_switch"), "pull_up": True},
        motor={
            "forward": Config.getInt(f"motor{motor_side}_A", "motor_board"),
            "backward": Config.getInt(f"motor{motor_side}_B", "motor_board"),
            "enable": Config.getInt(f"motor{motor_side}_E", "motor_board"),
            "pwm": False,
        },
        orientation=CurtainOrientation.Name(orientation),
    )
    curtain.disable(power_motor=True)
    return curtain


@lru_cache(maxsize=1)
def curtain_east() -> Curtain:
    return build_curtain(CurtainOrientation.CURTAIN_EAST, mock=Config.getBoolean("gpio_mock", "server"))


@lru_cache(maxsize=1)
def curtain_west() -> Curtain:
    return build_curtain(CurtainOrientation.CURTAIN_WEST, mock=Config.getBoolean("gpio_mock", "server"))
