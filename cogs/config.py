import discord
from discord.ext import commands
import data.database as db
import helpers.errormessages as errormsg
import helpers.utilityfunctions as util


class Config(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def welcomeconfig(self, ctx, option, *args):
        """
        `>welcomeconfig channel <textchannel>`
        `>welcomeconfig message <message...>`
        `>welcomeconfig {enable | disable}`
        """
        if option == "channel":
            if len(args) == 0:
                return await ctx.send(errormsg.missing_parameter("channel"))

            channel = await util.get_textchannel(ctx, args[0])
            if channel is None:
                return await ctx.send(errormsg.channel_not_found(args[0]))

            db.update_setting(ctx.guild.id, "welcome_channel", channel.id)
            await ctx.send(f"Welcome channel for {ctx.guild.name} set to {channel.mention}")

        elif option == "message":
            message = " ".join(args)
            db.update_setting(ctx.guild.id, "welcome_message", message)
            await ctx.send("New welcome message set:")
            await ctx.send(message.format(mention=ctx.author.mention, user=ctx.author.name))

        elif option == "enable":
            db.update_setting(ctx.guild.id, "welcome_toggle", 1)
            await ctx.send("Welcome messages **enabled**")

        elif option == "disable":
            db.update_setting(ctx.guild.id, "welcome_toggle", 0)
            await ctx.send("Welcome messages **disabled**")

        elif option == "help":
            m = "**Available options:**\n" \
                "`channel`**:** Set the channel that welcome and leave messages are sent into.\n" \
                "`message`**:** Change the welcome message. use `{name}` and `{mention}` for automatic formatting.\n" \
                "`enable | disable`**:** Enables and disables welcome messages."
            await ctx.send(m)

        else:
            await ctx.send(errormsg.invalid_method(ctx.command.name, option))

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def starboard(self, ctx, option, *args):
        if option == "channel":
            if len(args) == 0:
                return await ctx.send(errormsg.missing_parameter("channel"))

            channel = await util.get_textchannel(ctx, args[0])
            if channel is None:
                return await ctx.send(errormsg.channel_not_found(args[0]))

            db.update_setting(ctx.guild.id, "starboard_channel", channel.id)
            await ctx.send(f"{channel.mention} is now the starboard channel")

        elif option == "amount":
            if len(args) == 0:
                return await ctx.send(errormsg.missing_parameter("amount"))

            try:
                amount = int(args[0])
            except ValueError:
                return await ctx.send("**ERROR:** Please give a number")

            db.update_setting(ctx.guild.id, "starboard_amount", amount)
            await ctx.send(f"Starboard reaction amount requirement set to `{amount}`")

        elif option == "enable":
            db.update_setting(ctx.guild.id, "starboard_toggle", 1)
            await ctx.send("Starboard **enabled**")

        elif option == "disable":
            db.update_setting(ctx.guild.id, "starboard_toggle", 0)
            await ctx.send("Starboard **disabled**")

        elif option == "help":
            m = "**Available options:**\n" \
                "`channel`**:** Set the channel that starred messages are sent into.\n" \
                "`amount`**:** Change the minimum amount of reactions needed for a message to be starred\n" \
                "`enable | disable`**:** Enables and disables the starboard."
            await ctx.send(m)

        else:
            await ctx.send(errormsg.invalid_method(ctx.command.name, option))

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def votechannel(self, ctx, option, mention=None):
        if option in ['add', 'remove']:
            channel = await util.get_textchannel(ctx, mention)
            if channel is None:
                return await ctx.send(errormsg.channel_not_found(mention))

            if option == 'add':
                db.execute("INSERT OR IGNORE INTO votechannels values(?, ?)", (ctx.guild.id, channel.id))
                await ctx.send(f"{channel.mention} is now a voting channel")

            elif option == 'remove':
                db.execute("DELETE FROM votechannels where guild_id = ? and channel_id = ?", (ctx.guild.id, channel.id))
                await ctx.send(f"{channel.mention} is no longer a voting channel")

        elif option == 'list':
            channels = db.query("select channel_id from votechannels where guild_id = ?", (ctx.guild.id,))
            mentions = []
            for channel in channels:
                c = ctx.guild.get_channel(channel[0])
                if c is not None:
                    mentions.append(c.mention)
            if mentions:
                content = discord.Embed(title=f"Voting channels in {ctx.guild.name}")
                content.description = "\n".join(mentions)
                await ctx.send(embed=content)

        elif option == 'help':
            m = "**Available options:**\n" \
                "`add`**:** Add a voting channel.\n" \
                "`remove`**:** Remove a voting channel\n" \
                "`list`**:** List all voting channels on this server"
            await ctx.send(m)

        else:
            await ctx.send(errormsg.invalid_method(ctx.command.name, option))

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def roleconfig(self, ctx, option, role=""):

        if option == 'help':
            m = "**Available options:**\n" \
                "`muterole`**:** The role added when muting a user.\n" \
                "`autorole`**:** The role added automatically for new users.\n"
            return await ctx.send(m)

        thisrole = await util.get_role(ctx, role)

        if option == 'muterole':
            if thisrole is None:
                oldrole = ctx.guild.get_role(db.get_setting(ctx.guild.id, "muterole"))
                if oldrole is None:
                    return await ctx.send(errormsg.missing_parameter("role"))
                return await ctx.send(f"Muterole on this server is currently `@{oldrole.name} ({oldrole.id})`")
            db.update_setting(ctx.guild.id, "muterole", thisrole.id)
            await ctx.send(f"Muterole set to `@{thisrole.name} ({thisrole.id})`")

        elif option == 'autorole':
            if thisrole is None:
                oldrole = ctx.guild.get_role(db.get_setting(ctx.guild.id, "autorole"))
                if oldrole is None:
                    return await ctx.send(errormsg.missing_parameter("role"))
                return await ctx.send(f"Automatically assigned role on this server is currently "
                                      f"`@{oldrole.name} ({oldrole.id})`")
            db.update_setting(ctx.guild.id, "autorole", thisrole.id)
            await ctx.send(f"Automatically assigned role set to `@{thisrole.name}`")

        else:
            await ctx.send(errormsg.invalid_method(ctx.command.name, option))

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
