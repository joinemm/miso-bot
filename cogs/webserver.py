import os
import ssl

import aiohttp_cors
from aiohttp import web
from nextcord.ext import commands, tasks

from modules import log

logger = log.get_logger(__name__)

USE_HTTPS = os.environ.get("WEBSERVER_USE_HTTPS", "no")
HOST = os.environ.get("WEBSERVER_HOSTNAME")
PORT = int(os.environ.get("WEBSERVER_PORT", 0))
SSL_CERT = os.environ.get("WEBSERVER_SSL_CERT")
SSL_KEY = os.environ.get("WEBSERVER_SSL_KEY")


class WebServer(commands.Cog):
    """Internal web server to provice realtime statistics to the website."""

    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.cached = {"guilds": 0, "users": 0, "commands": 0}
        self.app.router.add_route("GET", "/", self.index)
        self.app.router.add_route("GET", "/guilds", self.guild_count)
        self.app.router.add_route("GET", "/users", self.user_count)
        self.app.router.add_route("GET", "/ping", self.ping_handler)
        self.app.router.add_route("GET", "/stats", self.website_statistics)
        self.app.router.add_route("GET", "/commands", self.command_count)
        self.app.router.add_route("GET", "/documentation", self.command_list)
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

        self.bot.loop.create_task(self.run())
        self.cache_stats.start()

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

    async def index(self, request):
        return web.Response(text="Hi I'm Miso Bot!")

    async def ping_handler(self, request):
        return web.Response(text=f"{self.bot.latency*1000}")

    async def guild_count(self, request):
        return web.Response(text=f"{len(self.bot.guilds)}")

    async def user_count(self, request):
        return web.Response(text=f"{len(set(self.bot.get_all_members()))}")

    async def command_count(self, request):
        count = await self.bot.db.execute("SELECT SUM(uses) FROM command_usage", one_value=True)
        return web.Response(text=f"{count}")

    async def website_statistics(self, request):
        return web.json_response(self.cached)

    async def command_list(self, request):
        result = await self.generate_command_list()
        return web.json_response(result)

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
                "icon": cog.getattr("icon", None),
                "commands": command_list,
            }

            result.append(cog_content)

        return result

    @tasks.loop(minutes=1)
    async def cache_stats(self):
        self.cached["commands"] = int(
            await self.bot.db.execute("SELECT SUM(uses) FROM command_usage", one_value=True)
        )
        self.cached["guilds"] = len(self.bot.guilds)
        self.cached["users"] = len(set(self.bot.get_all_members()))

    @cache_stats.before_loop
    async def before_caching(self):
        await self.bot.wait_until_ready()
        logger.info("Starting web stats caching loop")

    def cog_unload(self):
        self.cache_stats.cancel()
        self.bot.loop.create_task(self.shutdown())

    async def shutdown(self):
        await self.app.shutdown()
        await self.app.cleanup()


def setup(bot):
    bot.add_cog(WebServer(bot))
