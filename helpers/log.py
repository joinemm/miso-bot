import logging
import sys

FORMATTER = logging.Formatter("[ %(asctime)s | %(levelname)-7s | %(funcName)s() ]:: %(message)s",
                              datefmt='%d/%m/%y %H:%M:%S')
FORMATTER_COMMANDS = logging.Formatter("[ %(asctime)s | COMMAND | %(message)s",
                                       datefmt='%d/%m/%y %H:%M:%S')
FORMATTER_COMMANDS_LEVELS = logging.Formatter("[ %(asctime)s | %(levelname)-7s | %(message)s",
                                              datefmt='%d/%m/%y %H:%M:%S')


def get_logger(logger_name):
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    # logger not created yet, assign options
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER)
    logger.addHandler(console_handler)

    return logger


def get_command_logger(showlevel=False):
    logger = logging.getLogger("commands" + ("withlevels" if showlevel else ""))
    if logger.handlers:
        return logger

    # logger not created yet, assign options
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    if showlevel:
        console_handler.setFormatter(FORMATTER_COMMANDS_LEVELS)
    else:
        console_handler.setFormatter(FORMATTER_COMMANDS)
    logger.addHandler(console_handler)

    return logger


def log_command(ctx):
    text = f"{(str(ctx.command)+'()'):>15} | {(ctx.guild.name if ctx.guild is not None else 'DM'):15} ] " \
           f"{ctx.author:15} \"{ctx.message.content}\""
    return text


def custom_command_format(ctx, keyword):
    return f"{f'custom({keyword})':>15} | {ctx.guild.name:15} ] {ctx.author:15} \"{ctx.message.content}\""
