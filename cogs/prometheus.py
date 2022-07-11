from time import time

import psutil
from discord.ext import commands, tasks
from prometheus_client import Counter, Gauge, Histogram, Summary

from modules import log

logger = log.get_logger(__name__)


class Prometheus(commands.Cog):
    """Collects prometheus metrics"""

    def __init__(self, bot):
        self.bot = bot
        self.ram_gauge = Gauge(
            "memory_usage_bytes",
            "Memory usage in bytes.",
        )
        self.cpu_gauge = Gauge(
            "cpu_usage_percent",
            "CPU usage percent.",
            ["core"],
        )
        self.event_counter = Counter(
            "gateway_events_total",
            "Total number of gateway events.",
            ["event_type"],
        )
        self.command_histogram = Histogram(
            "command_response_time_seconds",
            "Command end-to-end response time in seconds.",
            ["command"],
            buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0),
        )
        self.shard_latency_summary = Summary(
            "shard_latency_seconds",
            "Latency of a shard in seconds.",
            ["shard"],
        )

    async def cog_load(self):
        self.log_system_metrics.start()
        self.log_shard_latencies.start()

    def cog_unload(self):
        self.log_system_metrics.cancel()
        self.log_shard_latencies.cancel()

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type):
        self.event_counter.labels(event_type).inc()

    @tasks.loop(seconds=1)
    async def log_shard_latencies(self):
        for shard in self.bot.shards.values():
            self.shard_latency_summary.labels(shard.id).observe(shard.latency)

    @tasks.loop(seconds=1)
    async def log_system_metrics(self):
        ram = psutil.Process().memory_info().rss
        self.ram_gauge.set(ram)
        for core, usage in enumerate(psutil.cpu_percent(interval=None, percpu=True)):
            self.cpu_gauge.labels(core).set(usage)

    @log_shard_latencies.before_loop
    async def task_waiter(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            took = time() - ctx.timer
            command = str(ctx.command)
            self.command_histogram.labels(command).observe(took)


async def setup(bot):
    await bot.add_cog(Prometheus(bot))
