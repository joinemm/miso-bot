import logging  # noqa: F401
import os
import sys

import uvloop
from dotenv import load_dotenv

# dotenv has to be loaded before importing MisoBot
load_dotenv()

from modules import log  # noqa: E402
from modules.misobot import MisoBot  # noqa: E402

uvloop.install()
logger = log.get_logger(__name__)

developer_mode = "dev" in sys.argv
maintenance_mode = "maintenance" in sys.argv

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
    "rolepicker",
    "mod",
    "owner",
    "notifications",
    "miscellaneous",
    "media",
    "lastfm",
    "user",
    "images",
    "utility",
    "typings",
    "reddit",
    "crypto",
    "kpop",
    "webserver",
    "prometheus",
]

if maintenance_mode:
    logger.info("maintenance mode is ON")
    prefix = prefix * 2

    extensions = [
        "errorhandler",
        "owner",
    ]


def main():
    bot = MisoBot(
        extensions=extensions,
        default_prefix=prefix,
    )
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
