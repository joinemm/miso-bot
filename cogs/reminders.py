import discord
import arrow
from data import database as db
from discord.ext import commands, tasks
from helpers import utilityfunctions as util
from helpers import log

logger = log.get_logger(__name__)


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_list = []
        self.cache_needs_refreshing = True
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(seconds=1.0)
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
        """Checks all current reminders"""
        if self.cache_needs_refreshing:
            self.cache_needs_refreshing = False
            self.reminder_list = db.query("SELECT * FROM reminders")

        if not self.reminder_list:
            return

        now = arrow.utcnow().timestamp
        for reminder in self.reminder_list:
            # check if timestamp is in future
            # don't set variables yet to make runs as lightweight as possible
            if reminder[3] > now:
                continue

            user_id, guild_id, created_on, timestamp, thing, message_link = reminder
            user = self.bot.get_user(user_id)
            if user is not None:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    guild = "Deleted guild"
                date = arrow.get(created_on)
                if now - reminder[3] > 86400:
                    logger.info(
                        f"deleting reminder set for {date.format('DD/MM/YYYY HH:mm:ss')} for being 24 hours late"
                    )
                else:

                    try:
                        await user.send(
                            f":alarm_clock: The reminder you set {date.humanize()} "
                            f"`[ {date.format('DD/MM/YYYY HH:mm:ss')} ]` "
                            f"in **{guild}** has expired!\n> {thing}\nContext: {message_link}"
                        )
                        logger.info(f'reminded {user} to "{thing}"')
                    except discord.errors.Forbidden:
                        logger.warning(f"Unable to remind {user}, missing permissions")
            else:
                logger.info(f"deleted expired reminder by unknown user {user_id}")

            db.execute(
                """DELETE FROM reminders
                WHERE user_id = ? AND guild_id = ? AND message_link = ?""",
                (user_id, guild_id, message_link),
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
            time, thing = arguments.split(" to ")
        except ValueError:
            return await util.send_command_help(ctx)

        now = arrow.utcnow()

        if pre == "on":
            # user inputs date
            date = arrow.get(time)
            seconds = date.timestamp - now.timestamp

        elif pre == "in":
            # user inputs time delta
            seconds = util.timefromstring(time)
            date = now.shift(seconds=+seconds)

        else:
            return await ctx.send(f"Invalid prefix `{pre}`\nUse `on` for date and `in` for time")

        if seconds < 1:
            return await ctx.send(
                ":warning: You must give a valid time at least 1 second in the future"
            )

        db.execute(
            "INSERT INTO reminders VALUES(?, ?, ?, ?, ?, ?)",
            (
                ctx.author.id,
                ctx.guild.id,
                now.timestamp,
                date.timestamp,
                thing,
                ctx.message.jump_url,
            ),
        )

        self.cache_needs_refreshing = True
        await ctx.send(
            f":pencil: Reminding you in **{util.stringfromtime(seconds)}** "
            f"`[ {date.format('DD/MM/YYYY HH:mm:ss')} UTC ]` to \n> {thing}"
        )


def setup(bot):
    bot.add_cog(Reminders(bot))
