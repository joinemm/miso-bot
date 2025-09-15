# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import logging  # noqa: F401
import os
import signal
import sys

import discord
import discord.http
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

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


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
    "kpop",
    "prometheus",
]

infrastructure_extensions = [
    "webserver",
]


def main():
    if "DISCORD_PROXY" in os.environ:
        discord.http.Route.BASE = (
            f"{os.environ['DISCORD_PROXY']}/api/v{discord.http.INTERNAL_API_VERSION}"
        )

    bot: MisoBot = MisoBot(
        extensions=extensions + ([] if developer_mode else infrastructure_extensions),
        default_prefix=prefix,
    )
    if developer_mode:
        bot.debug = True

    bot.run(TOKEN, log_handler=None)


# Docker by default sends a SIGTERM to a container
# and waits 10 seconds for it to stop before killing it with a SIGKILL.
# This makes ctrl-c work as normal even in a docker container.


def handle_sigterm(*args):
    raise KeyboardInterrupt(*args)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    main()
