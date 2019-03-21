import discord
from discord.ext import commands
import data.database as db
import helpers.errormessages as errormsg
import helpers.utilityfunctions as util
import asyncio


class Rolepicker(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.group()
    async def rolepicker(self, ctx):
        """Setup the role picker"""
        await util.command_group_help(ctx)

    @rolepicker.command()
    async def add(self, ctx, name, role):
        """<name> <role>"""
        role_to_add = await util.get_role(ctx, role)
        if role_to_add is None:
            return await ctx.send(errormsg.role_not_found(role))

        db.execute("REPLACE INTO roles VALUES(?, ?, ?)", (ctx.guild.id, name, role_to_add.id))
        await ctx.send(f"New role **{role_to_add.name}** added to picker as `{name}`")

    @rolepicker.command()
    async def remove(self, ctx, name):
        """<name>"""
        roles = db.query("select rolename from roles where guild_id = ?", (ctx.guild.id,))
        if name in [x[0] for x in roles]:
            db.execute("DELETE FROM roles WHERE guild_id = ? and rolename = ?", (ctx.guild.id, name))
            await ctx.send(f"Removed `{name}` from role picker.")
        else:
            await ctx.send(errormsg.role_not_found(name))

    @rolepicker.command()
    async def channel(self, ctx, channel):
        """<channel>"""
        this_channel = await util.get_textchannel(ctx, channel)
        if this_channel is None:
            return await ctx.send(errormsg.channel_not_found(channel))
        db.update_setting(ctx.guild.id, "rolepicker_channel", this_channel.id)
        await ctx.send(f"Rolepicker channel set to {this_channel.mention}\n"
                       f"New messages in the channel will be deleted automatically")

    @rolepicker.command()
    async def list(self, ctx):
        data = db.query("select rolename, role_id from roles where guild_id = ?", (ctx.guild.id,))
        content = discord.Embed(title=f"Available roles in {ctx.guild.name}")
        if data is not None:
            content.description = ""
            for name, role_id in data:
                print(name, role_id)
                role = ctx.guild.get_role(role_id)
                if role is not None:
                    content.description += f"\n`{name}` : {role.mention if role is not None else 'None'}"
        else:
            content.description = "No roles set on this server"
        await ctx.send(embed=content)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Rolechannel message handler"""
        if message.channel.id == db.get_setting(message.guild.id, "rolepicker_channel"):
            if not message.author == self.client.user:
                command = message.content[0]
                rolename = message.content[1:].strip()
                if command in ["+", "-"]:
                    role = message.guild.get_role(db.rolepicker_role(rolename))
                    if role is None:
                        await message.channel.send(errormsg.role_not_found(rolename))
                    else:
                        if command == "+":
                            await message.author.add_roles(role)
                            await message.channel.send(f"Added you the role **{role.name}!**")
                        elif command == "-":
                            await message.author.remove_roles(role)
                            await message.channel.send(f"Removed the role **{role.name}** from you")
                else:
                    await message.channel.send(f"**Invalid command** `{command}`\n"
                                               f"Use `+` to add a role and `-` to remove a role")
            await asyncio.sleep(5)
            await message.delete()


def setup(client):
    client.add_cog(Rolepicker(client))
