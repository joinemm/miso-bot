import discord
from discord.ext import commands
from helpers import utilityfunctions as util
from helpers import log
import arrow
import asyncio
import data.database as db

logger = log.get_logger(__name__)


class Reminders(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.loop_active = False
        self.reminder_list = []
        self.cache_needs_refreshing = True

    @commands.Cog.listener()
    async def on_ready(self):
        if self.loop_active:
            # prevent multiple loops when discord is lagging
            return

        else:
            logger.info("Starting reminder loop")
            self.loop_active = True

            while True:
                try:
                    await self.check_reminders()
                except Exception as e:
                    logger.error(e)

                sleeptime = 60 - arrow.now().second
                await asyncio.sleep(sleeptime)
    
    async def check_reminders(self):
        """Checks all current reminders"""
        if self.cache_needs_refreshing:
            self.cache_needs_refreshing = False
            self.reminder_list = db.query("SELECT * FROM reminders")

        if not self.reminder_list:
            return

        for reminder in self.reminder_list:
            user_id, guild_id, created_on, timestamp, thing = reminder
            if timestamp > arrow.utcnow().timestamp + 30:
                continue
            
            user = self.client.get_user(user_id)
            if user is not None:
                guild = self.client.get_guild(guild_id)
                if guild is None:
                    guild = "Deleted guild"
                date = arrow.get(created_on)
                try:
                    await user.send(f":alarm_clock: The reminder you set {date.humanize()} `[ {date.format('DD/MM/YYYY HH:mm:ss')} ]` "
                                    f"in **{guild}** has expired!\n> {thing}")
                    logger.info(f'reminded {user} to "{thing}"')
                except discord.errors.Forbidden:
                    logger.warning(f'Unable to remind {user}, missing permissions')
            else:
                logger.info(f'deleted expired reminder by unknown user {user_id}')

            db.execute("""DELETE FROM reminders WHERE user_id = ? 
                                                  AND guild_id = ? 
                                                  AND created_on = ?
                                                  AND timestamp = ? 
                                                  AND thing = ?""", 
                       (user_id, guild_id, created_on, timestamp, thing))
            self.cache_needs_refreshing = True

    @commands.command()
    async def remindme(self, ctx, pre, *, arguments):
        """
        Set a reminder
        Reminders are accurate to the minute

        Usage:
            >remindme in <some time> to <do something>
            >remindme on <YYYY/MM/DD> [HH:mm] to <do something>
        """
        try:
            time, thing = arguments.split(' to ')
        except ValueError:
            return await util.send_command_help(ctx)

        if pre == 'on':
            # user inputs date
            date = arrow.get(time)
            seconds = date.timestamp - arrow.utcnow().timestamp

        elif pre == 'in':
            # user inputs time
            seconds = util.timefromstring(time)
            date = arrow.get(arrow.utcnow().timestamp + seconds)

        else:
            return await ctx.send(f"Invalid prefix `{pre}`\nUse `on` for date and `in` for time")
        
        db.execute("INSERT INTO reminders VALUES(?, ?, ?, ?, ?)", 
                   (ctx.author.id, ctx.guild.id, arrow.utcnow().timestamp, date.timestamp, thing))

        self.cache_needs_refreshing = True
        await ctx.send(f":pencil: Reminding you in **{util.stringfromtime(seconds)}** "
                       f"`[ {date.format('DD/MM/YYYY HH:mm')} UTC ]` to \n> {thing}")

def setup(client):
    client.add_cog(Reminders(client))
