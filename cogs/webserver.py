# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import os

from aiohttp import web
from discord.ext import commands, tasks
from loguru import logger
from prometheus_async import aio

from modules.misobot import MisoBot

HOST = os.environ.get("WEBSERVER_HOSTNAME")
PORT = int(os.environ.get("WEBSERVER_PORT", 8080))


class WebServer(commands.Cog):
    """Internal web server to provice realtime statistics to the website"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.app = web.Application()
        self.cached = {
            "guilds": 0,
            "users": 0,
            "commands": 0,
            "donators": [],
        }
        self.cached_command_list = []
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/ping", self.ping_handler)
        self.app.router.add_get("/stats", self.website_statistics)
        self.app.router.add_get("/documentation", self.command_list)
        self.app.router.add_get("/donators", self.donator_list)
        self.app.router.add_get("/metrics", aio.web.server_stats)
        self.app.router.add_post("/webhook", self.webhook)

    async def cog_load(self):
        self.cache_stats.start()
        self.cached_command_list = self.generate_command_list()
        self.cached["donators"] = []
        self.bot.loop.create_task(self.run())

    async def cog_unload(self):
        self.cache_stats.cancel()
        await self.shutdown()

    @tasks.loop(minutes=5)
    async def cache_stats(self):
        command_count = (
            await self.bot.db.fetch_value("SELECT SUM(uses) FROM command_usage") or 0
        )
        self.cached["commands"] = int(command_count)
        self.cached["guilds"] = self.bot.guild_count
        self.cached["users"] = self.bot.member_count
        self.cached["donators"] = await self.update_donator_list()

    @cache_stats.before_loop
    async def task_waiter(self):
        await self.bot.wait_until_ready()

    @cache_stats.error
    async def cache_stats_error(self, error):
        logger.error(error)

    async def shutdown(self):
        await self.app.shutdown()
        await self.app.cleanup()

    async def run(self):
        if HOST is not None:
            try:
                logger.info(f"Starting webserver on {HOST}:{PORT}")
                await web._run_app(
                    self.app,
                    host=HOST,
                    port=PORT,
                    access_log=None,
                )
            except OSError as e:
                logger.warning(e)

    @staticmethod
    async def index(request):
        return web.Response(text="Hi I'm Miso Bot!")

    async def update_donator_list(self):
        donators = []
        data = await self.bot.db.fetch(
            """
            SELECT user_id, amount
            FROM donator WHERE currently_active = 1
            """
        )
        if data:
            for user_id, amount in sorted(data, key=lambda x: x[1], reverse=True):
                user = self.bot.get_user(user_id)
                if user is None:
                    user = self.bot.donator_cache.get(user_id, 0)
                    if user == 0:
                        user = await self.bot.fetch_user(user_id)
                        if user is None or user.name.startswith("Deleted User "):
                            self.bot.donator_cache[user_id] = None
                            continue
                        self.bot.donator_cache[user_id] = user
                        await asyncio.sleep(1)

                if user:
                    donators.append(
                        {
                            "name": user.name,
                            "avatar": user.display_avatar.url,
                            "amount": amount,
                        }
                    )
        return donators

    async def donator_list(self, request):
        return web.json_response(self.cached["donators"])

    async def ping_handler(self, request):
        return web.Response(text=f"{self.bot.latency * 1000}")

    async def website_statistics(self, request):
        return web.json_response(self.cached)

    async def webhook(self, request):
        x_github_event: str | None = request.headers.get("x-github-event")
        if not x_github_event:
            return web.HTTPBadRequest()
        if x_github_event == "ping":
            return web.json_response({"status": "pong"})
        if x_github_event != "sponsorship":
            return web.HTTPMethodNotAllowed(x_github_event, ["sponsorship", "ping"])

        data = await request.json()
        action = data["action"]
        data = data["sponsorship"]
        tier = data["tier"]

        if data["privacy_level"] == "private":
            sponsor = {
                "login": "Anonymous",
                "html_url": "",
                "avatar_url": "https://gutegymnasiet.se/wp-content/uploads/2023/12/anonymous-icon-0.png",
            }
        else:
            sponsor = data["sponsor"]

        color = "333333"

        if action == "created":
            description = (
                f"Just sponsored with **${tier['monthly_price_in_dollars']}**"
                f" {'one time' if tier['is_one_time'] else 'per month'}! :heart:"
            )
            color = "6cc644"
        elif action == "cancelled":
            description = "Just cancelled their sponsorship :("
            color = "bd2c00"
        else:
            description = action
            print("unknown webhook data:", data)

        embed_data = {
            "embeds": [
                {
                    "color": int(color, 16),
                    "author": {
                        "name": sponsor["login"],
                        "url": sponsor["html_url"],
                        "icon_url": sponsor["avatar_url"],
                    },
                    "description": description,
                }
            ]
        }
        async with self.bot.session.post(
            self.bot.keychain.SPONSORS_WEBHOOK_URL,
            json=embed_data,
        ) as response:
            return web.json_response({"status": response.status})

    async def command_list(self, request):
        return web.json_response(self.cached_command_list)

    def get_command_structure(self, command):
        if command.hidden or not command.enabled:
            return None

        subcommands = []
        if hasattr(command, "commands"):
            for subcommand in command.commands:
                if subcommand_structure := self.get_command_structure(subcommand):
                    subcommands.append(subcommand_structure)

        return {
            "name": command.name,
            "usage": command.usage or command.signature,
            "description": command.short_doc,
            "subcommands": subcommands,
        }

    def generate_command_list(self):
        ignored_cogs = ["Jishaku", "Owner"]
        result = []
        for cog in self.bot.cogs.values():
            if cog.qualified_name in ignored_cogs:
                continue

            cog_commands = cog.get_commands()
            if not cog_commands:
                continue

            command_list = []
            for command in cog_commands:
                if command_structure := self.get_command_structure(command):
                    command_list.append(command_structure)

            if not command_list:
                continue

            cog_content = {
                "name": cog.qualified_name,
                "description": cog.description,
                "icon": getattr(cog, "icon", None),
                "commands": command_list,
            }

            result.append(cog_content)

        return result


async def setup(bot):
    await bot.add_cog(WebServer(bot))
