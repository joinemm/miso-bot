import discord
import asyncio
from discord.ext import commands
from data import database as db
from helpers import utilityfunctions as util


class Rolepicker(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.group(case_insensitive=True)
    @commands.has_permissions(manage_roles=True)
    async def rolepicker(self, ctx):
        """Setup the role picker."""
        await util.command_group_help(ctx)

    @rolepicker.command()
    async def add(self, ctx, role, name):
        """Add a role to the picker."""
        role_to_add = await util.get_role(ctx, role)
        if role_to_add is None:
            return await ctx.send(":warning: Could not get this role")

        db.execute("REPLACE INTO roles VALUES(?, ?, ?)", (ctx.guild.id, name, role_to_add.id))
        await ctx.send(embed=discord.Embed(description=f"{role_to_add.mention} added to picker as `{name}`"))

    @rolepicker.command()
    async def remove(self, ctx, name):
        """Remove a role from the picker."""
        roles = db.query("select rolename from roles where guild_id = ?", (ctx.guild.id,))
        if name in [x[0] for x in roles]:
            db.execute("DELETE FROM roles WHERE guild_id = ? and rolename = ?", (ctx.guild.id, name))
            await ctx.send(f"Removed `{name}` from the role picker.")
        else:
            return await ctx.send(":warning: Could not find this role from the picker")

    @rolepicker.command()
    async def channel(self, ctx, channel):
        """Set the channel you can add roles in."""
        this_channel = await util.get_textchannel(ctx, channel)
        if this_channel is None:
            return await ctx.send(":warning: Could not get this channel")

        db.update_setting(ctx.guild.id, "rolepicker_channel", this_channel.id)
        db.update_setting(ctx.guild.id, "rolepicker_enabled", 0)

        await ctx.send(f"Rolepicker channel set to {this_channel.mention}\n"
                       f"Now enable the rolepicker once you want messages in the channel to be deleted.")

    @rolepicker.command()
    async def list(self, ctx):
        """List all the roles currently available to pick."""
        data = db.query("select rolename, role_id from roles where guild_id = ?", (ctx.guild.id,))
        content = discord.Embed(title=f"Available roles in {ctx.guild.name}")
        if data is not None:
            roleslist = []
            content.description = ""
            for name, role_id in data:
                role = ctx.guild.get_role(role_id)
                if role is not None:
                   roleslist.append((name, role))

            for name, role in sorted(roleslist, key=lambda x: x[1].position, reverse=True):
                content.description += f"\n`{name}` : {role.mention if role is not None else 'None'}"

        else:
            content.description = "No roles set on this server"
        await ctx.send(embed=content)

    @rolepicker.command(enabled=False)
    async def case(self, ctx, boolean):
        """Toggle case sensitivity."""
        if boolean.lower() == 'true':
            newvalue = 1
        elif boolean.lower() == 'false':
            newvalue = 0
        else:
            return await ctx.send("Invalid value, use `true` or `false`")
        db.update_setting(ctx.guild.id, "rolepicker_case", newvalue)
        await ctx.send(f"Roles are now {('' if newvalue == 1 else 'not ')}case sensitive!")

    @rolepicker.command()
    async def enable(self, ctx):
        """Enable the rolepicker. (if disabled)"""
        db.update_setting(ctx.guild.id, "rolepicker_enabled", 1)
        await ctx.send("Rolepicker is now **enabled**")

    @rolepicker.command()
    async def disable(self, ctx):
        """Disable the rolepicker."""
        db.update_setting(ctx.guild.id, "rolepicker_enabled", 0)
        await ctx.send("Rolepicker is now **disabled**")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Rolechannel message handler."""
        if message.guild is None:
            return
        if db.get_setting(message.guild.id, "rolepicker_enabled") == 0:
            return
        if message.channel.id == db.get_setting(message.guild.id, "rolepicker_channel"):
            if not message.author.bot:
                command = message.content[0]
                rolename = message.content[1:].strip()
                if command in ["+", "-"]:
                    #case = db.get_setting(message.guild.id, "rolepicker_case")
                    role = message.guild.get_role(db.rolepicker_role(message.guild.id, rolename))
                    if role is None:
                        await message.channel.send(f":warning: Role `{rolename}` not found")
                    else:
                        if command == "+":
                            await message.author.add_roles(role)
                            await message.channel.send(embed=discord.Embed(description=f"Added {role.mention} to your roles"))
                        elif command == "-":
                            await message.author.remove_roles(role)
                            await message.channel.send(embed=discord.Embed(description=f"Removed {role.mention} from your roles"))
                else:
                    await message.channel.send(f":warning: Unknown action `{command}`\nUse `+` to add roles or `-` to remove them.")

            await asyncio.sleep(5)
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass


def setup(bot):
    bot.add_cog(Rolepicker(bot))
