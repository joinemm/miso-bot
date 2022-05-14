import uvloop
import discord
import traceback
import asyncio
import io
import json
import logging
import textwrap
import websockets
from contextlib import redirect_stdout
from discord.ext import commands
from time import time
from modules import util, maria, cache

uvloop.install()


class MONDAYBotCluster(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        # clustering stuff
        self.pipe = kwargs.pop("pipe")
        self.cluster_name = kwargs.pop("cluster_name")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        kwargs["command_prefix"] = util.determine_prefix
        super().__init__(**kwargs, loop=loop)
        self.websocket = None
        self._last_result = None
        self.ws_task = None
        self.responses = asyncio.Queue()
        self.eval_wait = False
        log = logging.getLogger(f"Cluster#{self.cluster_name}")
        log.setLevel(logging.DEBUG)
        log.handlers = [
            logging.FileHandler(f"cluster-{self.cluster_name}.log", encoding="utf-8", mode="a")
        ]
        log.info(f'[Cluster#{self.cluster_name}] {kwargs["shard_ids"]}, {kwargs["shard_count"]}')
        self.log = log

        # my stuff
        self.default_prefix = kwargs.pop("default_prefix")
        self.start_time = time()
        self.global_cd = commands.CooldownMapping.from_cooldown(15, 60, commands.BucketType.member)
        self.db = maria.MariaDB(self)
        self.cache = cache.Cache(self)
        self.version = "4.0"

        self.loop.create_task(self.ensure_ipc())

        for extension in kwargs.pop("extensions"):
            try:
                self.load_extension(f"cogs.{extension}")
                log.info(f"Loaded [ {extension} ]")
            except Exception as error:
                log.error(f"Error loading [ {extension} ]")
                traceback.print_exception(type(error), error, error.__traceback__)

        self.load_extension("jishaku")

        self.before_invoke(self.before_any_command)
        self.add_check(self.check_for_blacklist)
        self.add_check(self.cooldown_check)

        self.start_time = time()
        self.run(kwargs["token"])

    async def on_ready(self):
        self.log.info(f"[Cluster#{self.cluster_name}] Ready called.")
        try:
            self.pipe.send(1)
            self.pipe.close()
        except OSError as e:
            self.log.info(f"ignored OSError in on_ready: {e}")

    async def on_shard_ready(self, shard_id):
        self.log.info(f"[Cluster#{self.cluster_name}] Shard {shard_id} ready")

    async def close(self, *args, **kwargs):
        await self.db.cleanup()
        await self.websocket.close()
        await super().close()

    async def on_message(self, message):
        if not self.is_ready():
            return

        await super().on_message(message)

    async def before_any_command(self, ctx):
        """Runs before any command"""
        ctx.timer = time()
        try:
            await ctx.trigger_typing()
        except discord.errors.Forbidden:
            pass

    async def check_for_blacklist(self, ctx):
        """Check command invocation context for blacklist triggers"""
        return await util.is_blacklisted(ctx)

    async def cooldown_check(self, ctx):
        """Global bot cooldown to prevent spam"""
        # prevent users getting rate limited when help command does filter_commands()
        if str(ctx.invoked_with).lower() == "help":
            return True

        bucket = ctx.bot.global_cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after)
        return True

    async def ensure_ipc(self):
        try:
            self.websocket = w = await websockets.connect("ws://localhost:42069")
        except ConnectionRefusedError:
            self.log.warning("Connection to ipc websocket was refused")
            self.websocket = None
            return

        await w.send(self.cluster_name.encode("utf-8"))
        try:
            await w.recv()
            self.ws_task = self.loop.create_task(self.websocket_loop())
            self.log.info("ws connection succeeded")
        except websockets.ConnectionClosed as exc:
            self.log.warning(f"! couldnt connect to ws: {exc.code} {exc.reason}")
            self.websocket = None
            raise

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])

        # remove `foo`
        return content.strip("` \n")

    async def exec_code(self, code):
        env = {"bot": self, "_": self._last_result}
        env.update(globals())
        body = self.cleanup_code(code)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return f"{e.__class__.__name__}: {e}"

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            f"{value}{traceback.format_exc()}"
        else:
            value = stdout.getvalue()

            if ret is None:
                if value:
                    return str(value)
                else:
                    return "None"
            else:
                self._last_result = ret
                return f"{value}{ret}"

    async def websocket_loop(self):
        while True:
            print("ws looping", self.websocket)
            try:
                msg = await self.websocket.recv()
            except websockets.ConnectionClosed as exc:
                if exc.code == 1000:
                    return
                raise
            data = json.loads(msg, encoding="utf-8")
            print(data)
            if self.eval_wait and data.get("response"):
                await self.responses.put(data)
            cmd = data.get("command")
            if not cmd:
                continue

            if cmd == "ping":
                ret = {"response": f"{self.latency}"}
                self.log.info("received command [ping]")

            elif cmd == "eval":
                self.log.info(f"received command [eval] ({data['content']})")
                content = data["content"]
                data = await self.exec_code(content)
                ret = {"response": str(data)}

            else:
                ret = {"response": "unknown command"}

            ret["author"] = self.cluster_name
            self.log.info(f"responding: {ret}")
            try:
                await self.websocket.send(json.dumps(ret).encode("utf-8"))
            except websockets.ConnectionClosed as exc:
                if exc.code == 1000:
                    return
                raise
