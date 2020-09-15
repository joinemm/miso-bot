from discord.ext import commands
from data import database as db


class LastFMError(commands.CommandError):
    pass


class RendererError(commands.CommandError):
    pass


class BlacklistTrigger(commands.CommandError):
    def __init__(self, ctx, blacklist_type):
        super().__init__()
        self.blacklist_type = blacklist_type
        delete = db.query(
            """SELECT delete_blacklisted FROM guilds
            WHERE guild_id = ?""",
            (ctx.guild.id,),
        )
        delete = delete[0][0] if delete is not None else 0
        self.do_delete = delete == 1

    def __str__(self):
        return f"Triggered {self.blacklist_type} blacklist"
