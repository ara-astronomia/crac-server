import configparser
import os
from distutils.util import strtobool
from threading import Lock

from dotenv import load_dotenv


load_dotenv()

CONFIG_PATH = os.environ.get("CRAC_CONFIG_PATH", os.path.join(os.path.dirname(__file__), 'config.ini'))
"""
Which configuration file gets read. It is an environment variable because the
components read Config while being imported - the test suite has to redirect it
before importing anything, and there is no later moment to do it in.
"""

_parser = None
_parsed_from = None
_parse_lock = Lock()


def _file_stamp():
    """
    Identity of the file on disk: path, modification time and size. A missing
    file has a stamp of its own, so that it gets picked up as soon as it
    appears instead of being parsed over and over.
    """
    try:
        stat = os.stat(CONFIG_PATH)
    except OSError:
        return (CONFIG_PATH, None, None)
    return (CONFIG_PATH, stat.st_mtime_ns, stat.st_size)


def _get_parser():
    """
    config.ini parsed once and kept in memory, parsed again only when the file
    changes on disk. Every getter used to parse it from scratch - 54 parses for
    a single weather response - and a parse costs about a millisecond against
    the microseconds of a stat. Editing the file on a running server keeps
    taking effect without a restart, which is how thresholds and log levels get
    changed on the test stack.
    """
    global _parser, _parsed_from
    stamp = _file_stamp()
    if _parser is not None and _parsed_from == stamp:
        return _parser
    with _parse_lock:
        if _parser is None or _parsed_from != stamp:
            parser = configparser.ConfigParser()
            parser.read(CONFIG_PATH)
            _parser, _parsed_from = parser, stamp
    return _parser


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
