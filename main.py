import logging  # noqa: F401
import os
import sys

import uvloop
from dotenv import load_dotenv
from loguru import logger

# dotenv has to be loaded before importing MisoBot
load_dotenv()

from modules.misobot import MisoBot  # noqa: E402


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)

uvloop.install()

developer_mode = "dev" in sys.argv

if developer_mode:
    logger.info("Developer mode is ON")
    TOKEN = os.environ["MISO_BOT_TOKEN_BETA"]
    prefix = "<"
else:
    TOKEN = os.environ["MISO_BOT_TOKEN"]
    prefix = ">"

logger.info(f'Launching with default prefix "{prefix}"')

extensions = [
    "errorhandler",
    "events",
    "configuration",
    "customcommands",
    "fishy",
    "information",
    "roles",
    "mod",
    "owner",
    "notifications",
    "misc",
    "media",
    "lastfm",
    "user",
    "utility",
    "typings",
    "crypto",
    "kpop",
]

infrastructure_extensions = [
    "webserver",
    "prometheus",
]


def main():
    bot: MisoBot = MisoBot(
        extensions=extensions + (infrastructure_extensions if not developer_mode else []),
        default_prefix=prefix,
    )
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
