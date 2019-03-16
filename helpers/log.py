import logging
import sys

FORMATTER = logging.Formatter("[ %(asctime)s | %(levelname)s | %(name)s.%(funcName)s() ]:: %(message)s",
                              datefmt='%y/%m/%d %H:%M:%S')
FORMATTER_COMMANDS = logging.Formatter("[ %(asctime)s | COMMAND | %(message)s",
                                       datefmt='%y/%m/%d %H:%M:%S')


def get_logger(logger_name):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)  # better to have too much log than not enough

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER)
    logger.addHandler(console_handler)

    # with this pattern, it's rarely necessary to propagate the error up to parent
    logger.propagate = False

    return logger


def get_command_logger():
    logger = logging.getLogger("commands")
    logger.setLevel(logging.DEBUG)  # better to have too much log than not enough

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER_COMMANDS)
    logger.addHandler(console_handler)

    # with this pattern, it's rarely necessary to propagate the error up to parent
    logger.propagate = False

    return logger


def log_command(ctx):
    return f"{ctx.command}() | {ctx.guild} ]:: {ctx.author} \"{ctx.message.content}\""
