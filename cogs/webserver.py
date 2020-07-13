import asyncio
import yaml
from discord.ext import commands
from aiohttp import web


class WebServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/guilds", self.guild_count)
        self.app.router.add_get("/ping", self.ping_handler)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.running:
            with open("polls.yaml") as f:
                config = yaml.safe_load(f)

            asyncio.ensure_future(web._run_app(self.app, host=config["host"], port=config["port"]))
            self.running = True

    async def index(self, request):
        return web.Response(text="Hi I'm Miso Bot!")

    async def ping_handler(self, request):
        return web.Response(text=f"{self.bot.latency*1000}")

    async def guild_count(self, request):
        return web.Response(text=f"{len(self.bot.guilds)}")


def setup(bot):
    bot.add_cog(WebServer(bot))
