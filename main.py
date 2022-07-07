import logging  # noqa: F401
import os
import sys

import uvloop
from dotenv import load_dotenv

from modules import log
from modules.gateway_proxy import ProxiedBot, patch_with_gateway
from modules.misobot import MisoBot

uvloop.install()
load_dotenv()
logger = log.get_logger(__name__)

developer_mode = "dev" in sys.argv
maintenance_mode = "maintenance" in sys.argv
API_GATEWAY_PROXY = None  # "http://gateway:7878"

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
    "webserver",
    "reddit",
    "crypto",
    "kpop",
    "stats",
]

if maintenance_mode:
    logger.info("maintenance mode is ON")
    prefix = prefix * 2

    extensions = [
        "errorhandler",
        "owner",
    ]


def main():
    if API_GATEWAY_PROXY:
        patch_with_gateway()
        bot = ProxiedBot(
            extensions=extensions,
            default_prefix=prefix,
        )
    else:
        bot = MisoBot(
            extensions=extensions,
            default_prefix=prefix,
        )
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
