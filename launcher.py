import asyncio
import multiprocessing
import signal
import os
import sys
import time
import requests
import discord
from bot import MisoBotCluster
from modules.help import EmbedHelpCommand
from modules.log import get_logger
from dotenv import load_dotenv

load_dotenv(verbose=True)

DEV = "dev" in sys.argv
maintainance_mode = "maintainance" in sys.argv

log = get_logger("Cluster#Launcher")
# log.setLevel(logging.DEBUG)
# hdlr = logging.StreamHandler()
# hdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
# fhdlr = logging.FileHandler("cluster-Launcher.log", encoding="utf-8")
# fhdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
# log.handlers = [hdlr, fhdlr]

if DEV:
    log.info("Developer mode is ON")
    TOKEN = os.environ["MISO_BOT_TOKEN_BETA"]
    prefix = "<"
else:
    TOKEN = os.environ["MISO_BOT_TOKEN"]
    prefix = ">"

if maintainance_mode:
    log.info("Maintainance mode is ON")
    prefix = prefix * 2
    starting_activity = discord.Activity(
        type=discord.ActivityType.playing, name="Maintainance mode"
    )
else:
    starting_activity = discord.Activity(type=discord.ActivityType.playing, name="Booting up...")

maintainance_extensions = [
    "errorhandler",
    "migratedb",
    "owner",
]

extensions = [
    "errorhandler",
    "events",
    "configuration",
    "customcommands",
    "fishy",
    "information",
    "rolepicker",
    "mod",
    "owner",
    "notifications",
    "miscellaneous",
    "media",
    "lastfm",
    "user",
    "images",
    "utility",
    "typings",
    # "webserver",
    "reddit",
    "crypto",
    "kpop",
]

if maintainance_mode:
    extensions = maintainance_extensions

CLUSTER_NAMES = (
    "Alpha",
    "Beta",
    "Charlie",
    "Delta",
    "Echo",
    "Foxtrot",
    "Golf",
    "Hotel",
    "India",
    "Juliett",
    "Kilo",
    "Mike",
    "November",
    "Oscar",
    "Papa",
    "Quebec",
    "Romeo",
    "Sierra",
    "Tango",
    "Uniform",
    "Victor",
    "Whisky",
    "X-ray",
    "Yankee",
    "Zulu",
)
NAMES = iter(CLUSTER_NAMES)


class Launcher:
    def __init__(self, loop):
        log.info("Hello, world!")
        self.cluster_queue = []
        self.clusters = []
        self.shards_per_cluster = 3

        self.fut = None
        self.loop = loop
        self.alive = True

        self.keep_alive = None
        self.init = time.perf_counter()

    def get_shard_count(self):
        data = requests.get(
            "https://discordapp.com/api/v7/gateway/bot",
            headers={
                "Authorization": "Bot " + TOKEN,
                "User-Agent": "MisoBot/4.0 Python/3.9 aiohttp/3.6.1",
            },
        )
        data.raise_for_status()
        content = data.json()
        log.info(
            f"Successfully got shard count of {content['shards']} ({data.status_code, data.reason})"
        )
        return content["shards"]

    def start(self):
        self.fut = asyncio.ensure_future(self.startup(), loop=self.loop)

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.shutdown())
        finally:
            self.cleanup()

    def cleanup(self):
        log.info("cleaning up")
        self.loop.stop()
        if sys.platform == "win32":
            print("press ^C again")
        self.loop.close()

    def task_complete(self, task):
        if task.exception():
            task.print_stack()
            self.keep_alive = self.loop.create_task(self.rebooter())
            self.keep_alive.add_done_callback(self.task_complete)

    async def startup(self):
        shards = list(range(self.get_shard_count()))
        size = [
            shards[x : x + self.shards_per_cluster]
            for x in range(0, len(shards), self.shards_per_cluster)
        ]
        log.info(f"Core count: {multiprocessing.cpu_count()}")
        log.info(f"Preparing {len(size)} clusters")
        for shard_ids in size:
            self.cluster_queue.append(Cluster(self, next(NAMES), shard_ids, len(shards)))

        await self.start_cluster()
        self.keep_alive = self.loop.create_task(self.rebooter())
        self.keep_alive.add_done_callback(self.task_complete)
        log.info(f"Startup completed in {time.perf_counter()-self.init}s")

    async def shutdown(self):
        log.info("Shutting down clusters")
        self.alive = False
        if self.keep_alive:
            self.keep_alive.cancel()
        for cluster in self.clusters:
            cluster.stop()
        # self.cleanup()

    async def rebooter(self):
        while self.alive:
            # log.info("Cycle!")
            if not self.clusters:
                log.warning("All clusters appear to be dead")
                asyncio.ensure_future(self.shutdown())
            to_remove = []
            for cluster in self.clusters:
                if not cluster.process.is_alive():
                    if cluster.process.exitcode != 0:
                        # ignore safe exits
                        log.info(
                            f"Cluster#{cluster.name} exited with code {cluster.process.exitcode}"
                        )
                        log.info(f"Restarting cluster#{cluster.name}")
                        await cluster.start()
                    else:
                        log.info(f"Cluster#{cluster.name} found dead")
                        to_remove.append(cluster)
                        cluster.stop()  # ensure stopped
            for rem in to_remove:
                self.clusters.remove(rem)
            await asyncio.sleep(5)

    async def start_cluster(self):
        if self.cluster_queue:
            cluster = self.cluster_queue.pop(0)
            log.info(f"Starting Cluster#{cluster.name}")
            await cluster.start()
            log.info("Done!")
            self.clusters.append(cluster)
            await self.start_cluster()
        else:
            log.info("All clusters launched")


class Cluster:
    def __init__(self, launcher, name, shard_ids, max_shards):
        self.launcher = launcher
        self.process = None
        self.kwargs = dict(
            token=TOKEN,
            cluster_name=name,
            default_prefix=prefix,
            shard_ids=shard_ids,
            shard_count=max_shards,
            owner_id=133311691852218378,
            help_command=EmbedHelpCommand(),
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False),
            max_messages=10000,
            guild_ready_timeout=10,
            intents=discord.Intents(
                guilds=True,
                members=True,  # requires verification
                bans=True,
                emojis=True,
                integrations=False,
                webhooks=False,
                invites=False,
                voice_states=False,
                presences=True,  # requires verification
                messages=True,
                reactions=True,
                typing=False,
            ),
            # activity=starting_activity,
            extensions=extensions,
        )
        self.name = name
        self.log = get_logger(f"Cluster#{name}")
        # self.log.setLevel(logging.DEBUG)
        # hdlr = logging.StreamHandler()
        # hdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
        # fhdlr = logging.FileHandler("cluster-Launcher.log", encoding="utf-8")
        # fhdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
        # self.log.handlers = [hdlr, fhdlr]
        self.log.info(f"Initialized with shard ids {shard_ids}, total shards {max_shards}")

    def wait_close(self):
        return self.process.join()

    async def start(self, *, force=False):
        if self.process and self.process.is_alive():
            if not force:
                self.log.warning(
                    "Start called with already running cluster, pass `force=True` to override"
                )
                return
            self.log.info("Terminating existing process")
            self.process.terminate()
            self.process.close()

        stdout, stdin = multiprocessing.Pipe()
        kw = self.kwargs
        kw["pipe"] = stdin
        self.process = multiprocessing.Process(target=MisoBotCluster, kwargs=kw, daemon=True)
        self.process.start()
        self.log.info(f"Process started with PID {self.process.pid}")

        if await self.launcher.loop.run_in_executor(None, stdout.recv) == 1:
            stdout.close()
            self.log.info("Process started successfully")

        return True

    def stop(self, sign=signal.SIGINT):
        self.log.info(f"Shutting down with signal {sign!r}")
        try:
            os.kill(self.process.pid, sign)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    Launcher(loop).start()
