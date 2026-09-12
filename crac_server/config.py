import configparser
import os
from distutils.util import strtobool
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.ini')


def _config_path():
    """Which configuration file gets read, overridable from the environment."""
    return os.environ.get("CRAC_CONFIG_PATH", DEFAULT_CONFIG_PATH)


@lru_cache(maxsize=1)
def _parse(path, stamp):
    """The stamp is not read: it makes the cache miss when the file changes."""
    parser = configparser.ConfigParser()
    parser.read(path)
    return parser


def _file_stamp(path):
    """Modification time and size of the file, None when it is not there."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _get_parser():
    """config.ini parsed once, and parsed again only when it changes on disk."""
    path = _config_path()
    return _parse(path, _file_stamp(path))


class Config:

    def __init__(self):
        self.configparser = _get_parser()

    @staticmethod
    def getValue(key, section='automazione'):
        config = Config()
        env_value = Config.__check_environ__(key, section=section)
        if env_value:
            return env_value
        return config.configparser[section][key]

    @staticmethod
    def getFloat(key, section='automazione'):
        config = Config()
        env_value = Config.__check_environ__(key, section=section)
        if env_value:
            return float(env_value)
        env_value = config.configparser[section][key]
        if env_value:
            return config.configparser[section].getfloat(key)
        return 0

    @staticmethod
    def getRequiredFloat(key, section='automazione'):
        """
        Like getFloat but without a fallback: raises when the key is missing,
        empty or not numeric, instead of silently returning 0. Use it for the
        values safety decisions are taken on, where a made up 0 is
        indistinguishable from a real threshold.
        """
        value = Config.getValue(key, section)
        if not value:
            raise ValueError(f"{section}.{key} non impostata in config.ini")
        return float(value)

    @staticmethod
    def getRequiredBoolean(key, section='automazione'):
        """
        Like getBoolean but without a fallback: raises when the key is missing,
        empty or not a boolean, instead of silently returning None. Use it for
        the switches safety decisions are taken on, where an absent key turns
        a check off without leaving any trace.
        """
        value = Config.getValue(key, section)
        if not value:
            raise ValueError(f"{section}.{key} is not set in config.ini")
        return bool(strtobool(value))

    @staticmethod
    def getInt(key, section='automazione'):
        config = Config()
        env_value = Config.__check_environ__(key, section=section)
        if env_value:
            return int(env_value)
        env_value = config.configparser[section][key]
        if env_value:
            return config.configparser[section].getint(key)
        return 0

    
    @staticmethod
    def getBoolean(key, section='automazione'):
        config = Config()
        env_value = Config.__check_environ__(key, section=section)
        if env_value is not None:
            return strtobool(env_value)
        return config.configparser[section].getboolean(key)

    @staticmethod
    def __check_environ__(key: str, section='automazione'):
        env_key = section.upper() + '_' + key.upper()
        env_value = os.environ.get(env_key)
        return env_value
    
    @staticmethod
    def get_section(section_name: str):
        config = Config()
        section = config.configparser[section_name]
        raw_list = {key: config.getValue(key, section_name) for key in section}
        return {key: value for key, value in raw_list.items() if value}

    @staticmethod
    def get_section_keys(section_name: str):
        """
        Every key of the section, including the empty ones that get_section
        drops, so that a key emptied by mistake can be spotted instead of
        silently disappearing.
        """
        return list(Config().configparser[section_name])
