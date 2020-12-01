import yaml
from helpers import log
from discord.ext import commands
from aiohttp import web

logger = log.get_logger(__name__)


class WebServer(commands.Cog):
    """Internal web server for getting ping and checking uptime"""

    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/guilds", self.guild_count)
        self.app.router.add_get("/users", self.user_count)
        self.app.router.add_get("/ping", self.ping_handler)
        self.bot.loop.create_task(self.run())

    async def run(self):
        with open("polls.yaml") as f:
            config = yaml.safe_load(f)

        self.allowed_domains = config.get("allowed_domains", "*")
        try:
            logger.info(f"Starting webserver on {config['host']}:{config['port']}")
            await web._run_app(
                self.app, host=config["host"], port=config["port"], access_log=logger, print=None
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

    def cog_unload(self):
        self.bot.loop.create_task(self.shutdown())

    async def shutdown(self):
        await self.app.shutdown()
        await self.app.cleanup()


def setup(bot):
    bot.add_cog(WebServer(bot))
