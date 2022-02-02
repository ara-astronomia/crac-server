import configparser
import os
#from base.singleton import Singleton


class Config:

    def __init__(self):
        self.configparser = configparser.ConfigParser()
        configpath = os.path.join(os.path.dirname(__file__), 'config.ini')
        self.configparser.read(configpath)

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
        return config.configparser[section].getfloat(key)

    @staticmethod
    def getInt(key, section='automazione'):
        config = Config()
        env_value = Config.__check_environ__(key, section=section)
        if env_value:
            return int(env_value)
        return config.configparser[section].getint(key)

    @staticmethod
    def __check_environ__(key: str, section='automazione'):
        env_key = section.upper() + '_' + key.upper()
        env_value = os.environ.get(env_key)
        return env_value
