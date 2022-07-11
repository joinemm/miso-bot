import os
import ssl

import aiohttp_cors
from aiohttp import web
from discord.ext import commands, tasks
from prometheus_async import aio

from modules import log

logger = log.get_logger(__name__)

USE_HTTPS = os.environ.get("WEBSERVER_USE_HTTPS", "no")
HOST = os.environ.get("WEBSERVER_HOSTNAME")
PORT = int(os.environ.get("WEBSERVER_PORT", 0))
SSL_CERT = os.environ.get("WEBSERVER_SSL_CERT")
SSL_KEY = os.environ.get("WEBSERVER_SSL_KEY")


class WebServer(commands.Cog):
    """Internal web server to provice realtime statistics to the website"""

    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.cached = {"guilds": 0, "users": 0, "commands": 0}
        self.cached_command_list = []
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/ping", self.ping_handler)
        self.app.router.add_get("/stats", self.website_statistics)
        self.app.router.add_get("/documentation", self.command_list)
        self.app.router.add_get("/donators", self.donator_list)
        self.app.router.add_get("/metrics", aio.web.server_stats)
        # Configure default CORS settings.
        self.cors = aiohttp_cors.setup(
            self.app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                )
            },
        )

        # Configure CORS on all routes.
        for route in list(self.app.router.routes()):
            self.cors.add(route)

        # https
        if USE_HTTPS == "yes":
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(SSL_CERT, SSL_KEY)
        else:
            self.ssl_context = None

    async def cog_load(self):
        self.cache_stats.start()
        self.bot.loop.create_task(self.run())

    async def cog_unload(self):
        self.cache_stats.cancel()
        await self.shutdown()

    @tasks.loop(minutes=1)
    async def cache_stats(self):
        self.cached["commands"] = int(
            await self.bot.db.execute("SELECT SUM(uses) FROM command_usage", one_value=True)
        )
        self.cached["guilds"] = len(self.bot.guilds)
        self.cached["users"] = len(set(self.bot.get_all_members()))
        self.cached["donators"] = await self.update_donator_list()
        self.cached_command_list = await self.generate_command_list()

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
        await self.bot.wait_until_ready()
        if HOST is not None:
            try:
                logger.info(f"Starting webserver on {HOST}:{PORT}")
                await web._run_app(
                    self.app,
                    host=HOST,
                    port=PORT,
                    access_log=logger,
                    print=None,
                    ssl_context=self.ssl_context,
                )
            except OSError as e:
                logger.warning(e)

    @staticmethod
    async def index(request):
        return web.Response(text="Hi I'm Miso Bot!")

    async def update_donator_list(self):
        donators = []
        data = await self.bot.db.execute(
            """
            SELECT user_id, amount
            FROM donator WHERE currently_active = 1
            """
        )
        for user_id, amount in sorted(data, key=lambda x: x[1], reverse=True):
            user = self.bot.get_user(user_id)
            donators.append(
                {"name": user.name, "avatar": user.display_avatar.url, "amount": amount}
            )
        return donators

    async def donator_list(self, request):
        return web.json_response(self.cached["donators"])

    async def ping_handler(self, request):
        return web.Response(text=f"{self.bot.latency*1000}")

    async def website_statistics(self, request):
        return web.json_response(self.cached)

    async def command_list(self, request):
        return web.json_response(self.cached_command_list)

    def get_command_structure(self, command):
        if command.hidden or not command.enabled:
            return None

        subcommands = []
        if hasattr(command, "commands"):
            for subcommand in command.commands:
                subcommand_structure = self.get_command_structure(subcommand)
                if subcommand_structure:
                    subcommands.append(subcommand_structure)

        result = {
            "name": command.name,
            "usage": command.usage or command.signature,
            "description": command.short_doc,
            "subcommands": subcommands,
        }

        return result

    async def generate_command_list(self):
        ignored_cogs = ["Jishaku", "Owner"]
        result = []
        for cog in self.bot.cogs.values():
            if cog.qualified_name in ignored_cogs:
                continue

            commands = cog.get_commands()
            if not commands:
                continue

            command_list = []
            for command in commands:
                command_structure = self.get_command_structure(command)
                if command_structure:
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
