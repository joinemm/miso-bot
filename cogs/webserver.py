import asyncio
import yaml
from discord.ext import commands
from aiohttp import web


class WebServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.app = web.Application()
        self.app.router.add_get("/ping", self.ping_handler)
        self.app.router.add_get("/", self.index)

    @commands.Cog.listener()
    async def on_ready(self):
        with open("polls.yaml") as f:
            config = yaml.safe_load(f)

        asyncio.ensure_future(web._run_app(self.app, host=config["host"], port=config["port"]))
        self.running = True

    async def index(self, request):
        return web.Response(text="Hi I'm Miso Bot!")

    async def ping_handler(self, request):
        return web.Response(text="pong")


def setup(bot):
    bot.add_cog(WebServer(bot))
