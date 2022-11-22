from time import time

import psutil
from discord.ext import commands, tasks
from prometheus_client import Counter, Gauge, Summary

from modules import log
from modules.misobot import MisoBot

logger = log.get_logger(__name__)


class Prometheus(commands.Cog):
    """Collects prometheus metrics"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.ram_gauge = Gauge(
            "miso_memory_usage_bytes",
            "Memory usage of the bot process in bytes.",
        )
        self.cpu_gauge = Gauge(
            "system_cpu_usage_percent",
            "CPU usage of the system in percent.",
            ["core"],
        )
        self.event_counter = Counter(
            "miso_gateway_events_total",
            "Total number of gateway events.",
            ["event_type"],
        )
        self.command_response_time_summary = Summary(
            "miso_command_response_time",
            "Command end-to-end response time in seconds.",
            ["command"],
        )
        self.shard_latency_summary = Gauge(
            "miso_shard_latency",
            "Latency of a shard in seconds.",
            ["shard"],
        )
        self.guild_count = Gauge(
            "miso_cached_guild_count",
            "Total amount of guilds cached.",
        )
        self.member_count = Gauge(
            "miso_cached_member_count",
            "Sum of all guilds' member counts",
        )
        self.user_count = Gauge(
            "miso_cached_user_count",
            "Total amount of users cached",
        )

    async def cog_load(self):
        self.log_system_metrics.start()
        self.log_shard_latencies.start()
        self.log_cache_contents.start()

    def cog_unload(self):
        self.log_system_metrics.cancel()
        self.log_shard_latencies.cancel()
        self.log_cache_contents.cancel()

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type):
        self.event_counter.labels(event_type).inc()

    @tasks.loop(seconds=10)
    async def log_shard_latencies(self):
        for shard in self.bot.shards.values():
            self.shard_latency_summary.labels(shard.id).set(shard.latency)

    @tasks.loop(minutes=1)
    async def log_cache_contents(self):
        guild_count = self.bot.guild_count
        member_count = len(self.bot.users)
        self.guild_count.set(guild_count)
        self.member_count.set(member_count)
        self.user_count.set(self.bot.member_count)

    @tasks.loop(seconds=10)
    async def log_system_metrics(self):
        ram = psutil.Process().memory_info().rss
        self.ram_gauge.set(ram)
        cpus: list = psutil.cpu_percent(interval=None, percpu=True)  # type: ignore
        for core, usage in enumerate(cpus):
            self.cpu_gauge.labels(core).set(usage)

    @log_shard_latencies.before_loop
    @log_cache_contents.before_loop
    async def task_waiter(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            took = time() - ctx.timer
            command = str(ctx.command)
            self.command_response_time_summary.labels(command).observe(took)


async def setup(bot):
    await bot.add_cog(Prometheus(bot))
