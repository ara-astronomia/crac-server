import logging.handlers
import logging
import os
from crac_server.config import Config

class Logger:

    def __init__(self, dir_path=os.path.dirname(os.path.realpath(__file__))+os.path.sep):
        formatter = logging.Formatter('%(levelname)s %(asctime)s file %(filename)s linea %(lineno)d %(message)s')
        # create console handler and set level
        ch = logging.StreamHandler()
        if Config.getValue("loggingLevel") is not None:
            ch.setLevel(Config.getInt("loggingLevel"))
        ch.setFormatter(formatter)

        # create file handler and set level
        fh = logging.handlers.TimedRotatingFileHandler(dir_path+'server.log', 'D')
        if Config.getValue("loggingLevel") is not None:
            fh.setLevel(Config.getInt("loggingLevel"))
        fh.setFormatter(formatter)

        self.file_logger = logging.getLogger()
        self.file_logger.setLevel(Config.getInt("loggingLevel"))
        self.file_logger.addHandler(ch)
        self.file_logger.addHandler(fh)

    @staticmethod
    def getLogger():
        logger = Logger()
        return logger.file_logger


class LoggerClient:

    def __init__(self, dir_path=os.path.dirname(os.path.realpath(__file__))+os.path.sep):
        formatter = logging.Formatter('%(levelname)s %(asctime)s file %(filename)s linea %(lineno)d %(message)s')

        # create console handler and set level
        ch = logging.StreamHandler()
        if Config.getValue("loggingLevel") is not None:
            ch.setLevel(Config.getInt("loggingLevel"))
        ch.setFormatter(formatter)

        # create file handler and set level
        fh = logging.handlers.TimedRotatingFileHandler(dir_path+'client.log', 'D')
        if Config.getValue("loggingLevel") is not None:
            fh.setLevel(Config.getInt("loggingLevel"))
        fh.setFormatter(formatter)

        self.file_logger_client = logging.getLogger()
        self.file_logger_client.setLevel(Config.getInt("loggingLevel"))
        self.file_logger_client.addHandler(ch)
        self.file_logger_client.addHandler(fh)

    @staticmethod
    def getLogger():
        logger = LoggerClient()
        return logger.file_logger_client
