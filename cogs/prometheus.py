# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import statistics

from discord.ext import commands, tasks
from prometheus_client import Counter, Gauge

from modules.misobot import MisoBot


class Prometheus(commands.Cog):
    """Collects prometheus metrics"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.event_counter = Counter(
            "miso_gateway_events_total",
            "Total number of gateway events.",
            ["event_type"],
        )
        self.commands_used = Counter(
            "miso_commands_used",
            "Total number of commands used.",
            ["command"],
        )
        self.shard_latency_summary = Gauge(
            "miso_shard_latency",
            "Latency of a shard in seconds.",
            ["shard"],
        )
        self.ping = Gauge("miso_ping", "Bot's average latency.")
        self.guilds_total = Gauge(
            "miso_guilds_total",
            "Total amount of guilds.",
        )
        self.guilds_cached = Gauge(
            "miso_guilds_cached",
            "Total amount of guilds cached.",
        )
        self.users_total = Gauge(
            "miso_users_total",
            "Sum of all guilds' member counts",
        )
        self.users_cached = Gauge(
            "miso_users_cached",
            "Total amount of users cached",
        )
        self.median_member_count = Gauge(
            "miso_median_member_count",
            "Median guild size.",
        )
        self.outgoing_requests = Counter(
            "miso_outgoing_requests",
            "Aiohttp clientsession total requests per domain.",
            ["host", "status_code"],
        )

    async def cog_load(self):
        self.log_shard_latencies.start()
        self.log_member_data.start()

    async def cog_unload(self):
        self.log_shard_latencies.cancel()
        self.log_member_data.cancel()

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type):
        self.event_counter.labels(event_type).inc()

    @tasks.loop(seconds=5)
    async def log_shard_latencies(self):
        self.ping.set(self.bot.latency)
        for shard in self.bot.shards.values():
            self.shard_latency_summary.labels(shard.id).set(shard.latency)

    @tasks.loop(minutes=1)
    async def log_member_data(self):
        guilds_total = len(self.bot.guilds)
        guilds_chunked = len(list(filter(lambda g: g.chunked, self.bot.guilds)))

        users_total = self.bot.member_count
        users_cached = len(self.bot.users)

        median_member_count = statistics.median(
            guild.member_count or 0 for guild in self.bot.guilds
        )

        self.guilds_total.set(guilds_total)
        self.guilds_cached.set(guilds_chunked)
        self.users_total.set(users_total)
        self.users_cached.set(users_cached)
        self.median_member_count.set(median_member_count)

    @log_shard_latencies.before_loop
    @log_member_data.before_loop
    async def task_waiter(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            command = str(ctx.command)
            self.commands_used.labels(command).inc()


async def setup(bot):
    await bot.add_cog(Prometheus(bot))
