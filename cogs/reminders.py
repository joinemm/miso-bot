import discord
import arrow
from discord.ext import commands, tasks
from helpers import utilityfunctions as util
from helpers import log, exceptions

logger = log.get_logger(__name__)


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_list = []
        self.cache_needs_refreshing = True
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(seconds=5.0)
    async def reminder_loop(self):
        try:
            await self.check_reminders()
        except Exception as e:
            logger.error(f"reminder loop error: {e}")

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Starting reminder loop")

    async def check_reminders(self):
        """Check all current reminders"""
        if self.cache_needs_refreshing:
            self.cache_needs_refreshing = False
            self.reminder_list = await self.bot.db.execute(
                """
                SELECT user_id, guild_id, created_on, reminder_date, content, original_message_url
                FROM reminder
                """
            )

        if not self.reminder_list:
            return

        now_ts = arrow.utcnow().timestamp
        for (
            user_id,
            guild_id,
            created_on,
            reminder_date,
            content,
            original_message_url,
        ) in self.reminder_list:
            reminder_ts = reminder_date.timestamp()
            if reminder_ts > now_ts:
                continue

            user = self.bot.get_user(user_id)
            if user is not None:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    guild = "Unknown guild"

                date = arrow.get(created_on)
                if now_ts - reminder_ts > 86400:
                    logger.info(
                        f"Deleting reminder set for {date.format('DD/MM/YYYY HH:mm:ss')} for being 24 hours late"
                    )
                else:
                    embed = discord.Embed(
                        color=int("d3a940", 16),
                        title=":alarm_clock: Reminder!",
                        description=content,
                    )
                    embed.add_field(
                        name="context",
                        value=f"[Jump to message]({original_message_url})",
                        inline=True,
                    )
                    embed.set_footer(text=f"{guild}")
                    embed.timestamp = created_on
                    try:
                        await user.send(embed=embed)
                        logger.info(f'Reminded {user} to "{content}"')
                    except discord.errors.Forbidden:
                        logger.warning(f"Unable to remind {user}, missing DM permissions!")
            else:
                logger.info(f"Deleted expired reminder by unknown user {user_id}")

            await self.bot.db.execute(
                """
                DELETE FROM reminder
                    WHERE user_id = %s AND guild_id = %s AND original_message_url = %s
                """,
                user_id,
                guild_id,
                original_message_url,
            )
            self.cache_needs_refreshing = True

    @commands.command()
    async def remindme(self, ctx, pre, *, arguments):
        """
        Set a reminder

        Usage:
            >remindme in <some time> to <something>
            >remindme on <YYYY/MM/DD> [HH:mm:ss] to <something>
        """
        try:
            time, content = arguments.split(" to ")
        except ValueError:
            return await util.send_command_help(ctx)

        now = arrow.now()

        if pre == "on":
            # user inputs date
            date = arrow.get(time)
            seconds = date.timestamp - now.timestamp

        elif pre == "in":
            # user inputs time delta
            seconds = util.timefromstring(time)
            date = now.shift(seconds=+seconds)

        else:
            return await ctx.send(
                f"Invalid operation `{pre}`\nUse `on` for date and `in` for time delta"
            )

        if seconds < 1:
            raise exceptions.Info("You must give a valid time at least 1 second in the future!")

        await self.bot.db.execute(
            """
            INSERT INTO reminder (user_id, guild_id, created_on, reminder_date, content, original_message_url)
                VALUES(%s, %s, %s, %s, %s, %s)
            """,
            ctx.author.id,
            ctx.guild.id,
            now.datetime,
            date.datetime,
            content,
            ctx.message.jump_url,
        )

        self.cache_needs_refreshing = True
        await ctx.send(
            embed=discord.Embed(
                color=int("ccd6dd", 16),
                description=(
                    f":pencil: I'll message you on **{date.to('utc').format('DD/MM/YYYY HH:mm:ss')}"
                    f" UTC** to remind you of:\n```{content}```"
                ),
            )
        )


def setup(bot):
    bot.add_cog(Reminders(bot))
