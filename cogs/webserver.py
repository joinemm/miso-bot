from modules import log
from discord.ext import commands
from aiohttp import web
import aiohttp_cors
import ssl
import os

logger = log.get_logger(__name__)


class WebServer(commands.Cog):
    """Internal web server for getting ping and checking uptime"""

    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.app.router.add_route("GET", "/", self.index)
        self.app.router.add_route("GET", "/guilds", self.guild_count)
        self.app.router.add_route("GET", "/users", self.user_count)
        self.app.router.add_route("GET", "/ping", self.ping_handler)
        self.app.router.add_route("GET", "/stats", self.website_statistics)
        self.app.router.add_route("GET", "/commands", self.command_count)
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

        self.bot.loop.create_task(self.run())

    async def run(self):
        USE_HTTPS = os.environ.get("WEBSERVER_USE_HTTPS", "no")
        HOST = os.environ.get("WEBSERVER_HOSTNAME")
        PORT = int(os.environ.get("WEBSERVER_PORT", 0))
        SSL_CERT = os.environ.get("WEBSERVER_SSL_CERT")
        SSL_KEY = os.environ.get("WEBSERVER_SSL_KEY")

        # https
        if USE_HTTPS == "yes":
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(SSL_CERT, SSL_KEY)
        else:
            ssl_context = None

        if HOST is not None:
            try:
                logger.info(f"Starting webserver on {HOST}:{PORT}")
                await web._run_app(
                    self.app,
                    host=HOST,
                    port=PORT,
                    access_log=logger,
                    print=None,
                    ssl_context=ssl_context,
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
        command_count = await self.bot.db.execute(
            "SELECT SUM(uses) FROM command_usage", one_value=True
        )
        guild_count = len(self.bot.guilds)
        user_count = len(set(self.bot.get_all_members()))
        return web.json_response(
            {
                "commands": int(command_count),
                "guilds": guild_count,
                "users": user_count,
            }
        )

    def cog_unload(self):
        self.bot.loop.create_task(self.shutdown())

    async def shutdown(self):
        await self.app.shutdown()
        await self.app.cleanup()


def setup(bot):
    bot.add_cog(WebServer(bot))
