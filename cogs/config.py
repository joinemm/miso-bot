import discord
from discord.ext import commands
import data.database as db
import helpers.errormessages as errormsg
import helpers.utilityfunctions as util


class Config(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(hidden=True)
    @commands.is_owner()
    async def help2(self, ctx):
        pages = []
        for cog in self.client.cogs:
            this_cog_commands = self.client.get_cog(cog).get_commands()
            if this_cog_commands:
                this_page = discord.Embed(title=f"{cog}")
                for command in this_cog_commands:
                    this_page.add_field(name=command.name +
                                             (f' [{" | ".join(command.aliases)}]' if command.aliases else ""),
                                        inline=False,
                                        value=command.short_doc or "-no help yet-")
                pages.append(this_page)
        await util.page_switcher(ctx, self.client, pages)

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def welcomeconfig(self, ctx):
        await util.command_group_help(ctx)

    @welcomeconfig.command(name="channel")
    async def welcome_channel(self, ctx, textchannel):
        channel = await util.get_textchannel(ctx, textchannel)
        if channel is None:
            return await ctx.send(errormsg.channel_not_found(textchannel))

        db.update_setting(ctx.guild.id, "welcome_channel", channel.id)
        await ctx.send(f"Welcome channel set to {channel.mention}")

    @welcomeconfig.command(name="message")
    async def welcome_message(self, ctx, *, message):
        db.update_setting(ctx.guild.id, "welcome_message", message)
        await ctx.send("New welcome message set:")
        await ctx.send(message.format(mention=ctx.author.mention, user=ctx.author.name))

    @welcomeconfig.command(name="enable")
    async def welcome_enable(self, ctx):
        db.update_setting(ctx.guild.id, "welcome_toggle", 1)
        await ctx.send("Welcome messages **enabled**")

    @welcomeconfig.command(name="disable")
    async def welcome_disable(self, ctx):
        db.update_setting(ctx.guild.id, "welcome_toggle", 0)
        await ctx.send("Welcome messages **disabled**")

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def starboard(self, ctx):
        await util.command_group_help(ctx)

    @starboard.command(name="channel")
    async def starboard_channel(self, ctx, textchannel):
        channel = await util.get_textchannel(ctx, textchannel)
        if channel is None:
            return await ctx.send(errormsg.channel_not_found(textchannel))

        db.update_setting(ctx.guild.id, "starboard_channel", channel.id)
        await ctx.send(f"{channel.mention} is now the starboard channel")

    @starboard.command(name="amount")
    async def starboard_amount(self, ctx, amount):
        try:
            amount = int(amount)
        except ValueError:
            return await ctx.send(f"**ERROR:** {amount} is not a number.")

        db.update_setting(ctx.guild.id, "starboard_amount", amount)
        await ctx.send(f"Starboard reaction amount requirement set to `{amount}`")

    @starboard.command(name="enable")
    async def starboard_enable(self, ctx):
        db.update_setting(ctx.guild.id, "starboard_toggle", 1)
        await ctx.send("Starboard **enabled**")

    @starboard.command(name="disable")
    async def starboard_disable(self, ctx):
        db.update_setting(ctx.guild.id, "starboard_toggle", 0)
        await ctx.send("Starboard **disabled**")

    @commands.group()
    @commands.has_permissions(manage_channels=True)
    async def votechannel(self, ctx):
        await util.command_group_help(ctx)

    @votechannel.command(name="add")
    async def votechannel_add(self, ctx, textchannel):
        channel = await util.get_textchannel(ctx, textchannel)
        if channel is None:
            return await ctx.send(errormsg.channel_not_found(textchannel))

        db.execute("INSERT OR IGNORE INTO votechannels values(?, ?)", (ctx.guild.id, channel.id))
        await ctx.send(f"{channel.mention} is now a voting channel")

    @votechannel.command(name="remove")
    async def votechannel_remove(self, ctx, textchannel):
        channel = await util.get_textchannel(ctx, textchannel)
        if channel is None:
            try:
                channel_id = int(textchannel)
            except ValueError:
                return await ctx.send(errormsg.channel_not_found(textchannel))
        else:
            channel_id = channel.id

        if db.query("SELECT * FROM votechannels WHERE guild_id = ? and channel_id = ?",
                    (ctx.guild.id, channel_id)) is None:
            return await ctx.send("**ERROR:** Given channel is not a voting channel.")

        db.execute("DELETE FROM votechannels where guild_id = ? and channel_id = ?", (ctx.guild.id, channel_id))
        await ctx.send(f"{channel.mention} is no longer a voting channel")

    @votechannel.command(name="list")
    async def votechannel_list(self, ctx):
        channels = db.query("select channel_id from votechannels where guild_id = ?", (ctx.guild.id,))
        mentions = []
        for channel in channels:
            c = ctx.guild.get_channel(channel[0])
            if c is not None:
                mentions.append(c.mention)
            else:
                mentions.append(channel[0])
        if mentions:
            content = discord.Embed(title=f"Voting channels in {ctx.guild.name}")
            content.description = "\n".join(mentions)
            await ctx.send(embed=content)

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def muterole(self, ctx, role=""):
        thisrole = await util.get_role(ctx, role)
        if thisrole is None:
            oldrole = ctx.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
            if oldrole is None:
                return await ctx.send(errormsg.missing_parameter("role"))
            return await ctx.send(f"Muterole on this server is currently `@{oldrole.name} ({oldrole.id})`")
        db.update_setting(ctx.guild.id, "muterole", thisrole.id)
        await ctx.send(f"Muterole set to `@{thisrole.name} ({thisrole.id})`")

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx, role=""):
        thisrole = await util.get_role(ctx, role)
        if thisrole is None:
            oldrole = ctx.guild.get_role(db.get_setting(ctx.guild.id, "autorole"))
            if oldrole is None:
                return await ctx.send(errormsg.missing_parameter("role"))
            return await ctx.send(f"Automatically assigned role on this server is currently "
                                  f"`@{oldrole.name} ({oldrole.id})`")
        db.update_setting(ctx.guild.id, "autorole", thisrole.id)
        await ctx.send(f"Automatically assigned role set to `@{thisrole.name}`")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def levelupmessages(self, ctx, value):
        value = value.lower()
        if value == 'enable':
            v = 1
        elif value == 'disable':
            v = 0
        else:
            return await ctx.send(f"**ERROR:** Invalid value `{value}`, use `enable` or `disable`")
        db.update_setting(ctx.guild.id, "levelup_toggle", v)
        await ctx.send(f"Levelup messages **{value}d**")


def setup(client):
    client.add_cog(Config(client))
