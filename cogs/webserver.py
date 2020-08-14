import asyncio
import yaml
from discord.ext import commands
from aiohttp import web


class WebServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/guilds", self.guild_count)
        self.app.router.add_get("/ping", self.ping_handler)
        self.app.router.add_get("/userinfo", self.userinfo)
        self.app.router.add_get("/guildinfo", self.serverinfo)
        self.bot.loop.create_task(self.run())

    async def run(self):
        with open("polls.yaml") as f:
            config = yaml.safe_load(f)

        self.allowed_domains = config.get("allowed_domains", "*")
        asyncio.ensure_future(web._run_app(self.app, host=config["host"], port=config["port"]))

    async def index(self, request):
        return web.Response(text="Hi I'm Miso Bot!")

    async def ping_handler(self, request):
        return web.Response(text=f"{self.bot.latency*1000}")

    async def guild_count(self, request):
        return web.Response(text=f"{len(self.bot.guilds)}")

    async def serverinfo(self, request):
        try:
            guildid = request.rel_url.query["guildid"]
            guild = self.bot.get_guild(int(guildid))
            return web.json_response({
                "name": guild.name,
                "id": guild.id,
                "icon": str(guild.icon_url),
                "owner_id": guild.owner_id
            }, headers={
                "Access-Control-Allow-Origin": self.allowed_domains
            })
        except Exception as e:
            return web.Response(text=f"Error: {e}")

    async def userinfo(self, request):
        try:
            userid = request.rel_url.query["userid"]
            user = self.bot.get_user(int(userid))
            return web.json_response({
                "name": user.name,
                "id": user.id,
                "discriminator": user.discriminator,
                "avatar": str(user.avatar_url),
                "bot": user.bot
            }, headers={
                "Access-Control-Allow-Origin": self.allowed_domains
            })
        except Exception as e:
            return web.Response(text=f"Error: {e}")

    def cog_unload(self):
        self.bot.loop.create_task(self.shutdown())

    async def shutdown(self):
        await self.app.shutdown()
        await self.app.cleanup()


def setup(bot):
    bot.add_cog(WebServer(bot))
