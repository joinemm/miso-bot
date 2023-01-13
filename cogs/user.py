import asyncio
from typing import Optional, Union

import arrow
import bleach
import discord
import humanize
from discord.ext import commands

from modules import emojis, exceptions, queries, util
from modules.misobot import MisoBot


class User(commands.Cog):
    """User related commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "👤"
        self.proposals = set()
        self.medal_emoji = [":first_place:", ":second_place:", ":third_place:"]
        with open("html/profile.min.html", "r", encoding="utf-8") as file:
            self.profile_html = file.read()

    @commands.command(aliases=["dp", "av", "pfp"])
    async def avatar(
        self, ctx: commands.Context, *, user: Union[discord.Member, discord.User, None] = None
    ):
        """Get user's profile picture"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if user is None:
            user = ctx.author

        assets = []
        if isinstance(user, discord.Member) and user.guild_avatar:
            assets.append((user.guild_avatar, "Server avatar"))
        if user.avatar:
            assets.append((user.avatar, "Avatar"))
        else:
            assets.append((user.default_avatar, "Default avatar"))

        pages = []

        asset: discord.Asset
        for asset, description in assets:
            content = discord.Embed()
            content.set_author(name=f"{user} / {description}", url=asset.url)
            content.set_image(url=asset.url)
            stats = await util.image_info_from_url(self.bot.session, asset.url)
            color = await util.color_from_image_url(
                self.bot.session, asset.replace(size=64, format="png").url
            )
            content.colour = int(color, 16)
            if stats is not None:
                content.set_footer(
                    text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
                )
            pages.append(content)

        if len(pages) == 1:
            return await ctx.send(embed=pages[0])

        pages = util.TwoWayIterator(pages, loop=True)
        msg = await ctx.send(embed=pages.current())

        async def switch():
            content = pages.next()
            await msg.edit(embed=content)

        functions = {"↔️": switch}

        asyncio.ensure_future(util.reaction_buttons(ctx, msg, functions))

    @commands.command(aliases=["uinfo"])
    @commands.cooldown(3, 30, type=commands.BucketType.user)
    async def userinfo(
        self, ctx: commands.Context, *, user: Union[discord.Member, discord.User, None] = None
    ):
        """Get information about discord user"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if user is None:
            user = ctx.author

        content = discord.Embed(
            title=f"{':robot: ' if user.bot else ''}{user.name}#{user.discriminator}"
        )
        content.set_thumbnail(url=user.display_avatar.url)
        content.set_footer(text=f"#{user.id}")
        content.add_field(name="Badges", value="> " + " ".join(util.flags_to_badges(user)))
        content.add_field(name="Mention", value=user.mention)
        content.add_field(name="Account created", value=user.created_at.strftime("%d/%m/%Y %H:%M"))

        if isinstance(user, discord.Member):
            content.colour = user.color

            member_number = 1
            for member in ctx.guild.members:
                if member.joined_at and user.joined_at and member.joined_at < user.joined_at:
                    member_number += 1

            boosting_date = None
            if user.premium_since:
                boosting_date = humanize.naturaldelta(discord.utils.utcnow() - user.premium_since)

            content.add_field(name="Member", value=f"#{member_number} / {len(ctx.guild.members)}")
            content.add_field(
                name="Boosting", value=f"For {boosting_date}" if boosting_date else "No"
            )

            content.add_field(
                name="Joined server",
                value=user.joined_at.strftime("%d/%m/%Y %H:%M") if user.joined_at else "Unknown",
            )

            if self.bot.intents.presences:
                activity_display = util.UserActivity(user.activities).display()
                if user.is_on_mobile():  # and user.status is discord.Status.online:
                    status = "mobile"
                else:
                    status = user.status.name
                status_display = f"{emojis.Status[status].value} {user.status.name.capitalize()}"

                content.add_field(name="Status", value=status_display)
                content.add_field(name="Activity", value=activity_display or "Unavailable")

            content.add_field(
                name="Roles",
                value=" ".join(x.mention for x in reversed(user.roles[1:])),
                inline=False,
            )
        else:
            content.colour = int(
                await util.color_from_image_url(
                    self.bot.session,
                    user.display_avatar.replace(size=64, format="png").url,
                ),
                16,
            )

        await ctx.send(embed=content)

    @commands.command()
    async def hug(self, ctx: commands.Context, *, huggable=None):
        """Hug your friends"""
        emoji = emojis.random_hug()

        if huggable is not None:
            for word in huggable.split():
                user = await util.get_member(ctx, word)
                if user is not None:
                    huggable = huggable.replace(word, user.mention)

            await ctx.send(f"{huggable} {emoji}")
        else:
            await ctx.send(f"{emoji}")

    @commands.command()
    async def members(self, ctx: commands.Context):
        """Show the newest members of this server"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        sorted_members = sorted(ctx.guild.members, key=lambda x: x.joined_at or 0, reverse=True)
        membercount = len(sorted_members)
        content = discord.Embed(title=f"{ctx.guild.name} members")
        rows = []
        for i, member in enumerate(sorted_members):
            if member.joined_at:
                jointime = member.joined_at.strftime("%y%m%d %H:%M")
                rows.append(f"[`{jointime}`] **#{membercount-i}** : **{member}**")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def banner(self, ctx: commands.Context, *, user: Optional[discord.User] = None):
        """Get user's banner"""
        # banners are not cached so an api call is required
        user = await self.bot.fetch_user(user.id if user else ctx.author.id)

        content = discord.Embed()

        if not user.banner:
            if not user.accent_color:
                raise exceptions.CommandWarning(f"**{user}** has not set banner or accent color.")

            content.color = user.accent_color
            content.description = f":art: Solid color `{user.accent_color}`"
            content.set_author(name=f"{user} Banner", icon_url=user.display_avatar.url)
            return await ctx.send(embed=content)

        content.set_author(
            name=f"{user} Banner", url=user.banner.url, icon_url=user.display_avatar.url
        )

        content.set_image(url=user.banner.url)
        stats = await util.image_info_from_url(self.bot.session, user.banner.url)
        color = await util.color_from_image_url(
            self.bot.session, user.banner.replace(size=64, format="png").url
        )
        content.colour = int(color, 16)
        if stats is not None:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        await ctx.send(embed=content)

    @commands.command(aliases=["sbanner", "guildbanner"])
    async def serverbanner(self, ctx: commands.Context, *, guild: Optional[discord.Guild] = None):
        """Get server's banner"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if guild is None:
            guild = ctx.guild

        guild = ctx.guild
        content = discord.Embed()

        if not guild.banner:
            raise exceptions.CommandWarning("This server has no banner")

        content.set_author(
            name=f"{guild} Banner",
            url=guild.banner.url,
            icon_url=guild.icon.url if guild.icon else None,
        )

        content.set_image(url=guild.banner.url)
        stats = await util.image_info_from_url(self.bot.session, guild.banner.url)
        color = await util.color_from_image_url(
            self.bot.session, guild.banner.replace(size=64, format="png").url
        )
        content.colour = int(color, 16)
        if stats is not None:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        await ctx.send(embed=content)

    @commands.command(aliases=["sinfo", "guildinfo"])
    async def serverinfo(self, ctx: commands.Context, *, guild: Optional[discord.Guild] = None):
        """Get various information on server"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if guild is None:
            guild = ctx.guild

        content = discord.Embed(title=f"{guild.name}")
        content.set_footer(text=f"#{guild.id}")
        if guild.icon:
            color = await util.color_from_image_url(
                self.bot.session, guild.icon.replace(format="png", size=64).url
            )
            content.color = int(color, 16)
            content.set_thumbnail(url=guild.icon.url)

        if guild.banner:
            content.set_image(url=guild.banner.url)

        content.description = guild.description
        content.add_field(name="Owner", value=str(guild.owner))
        content.add_field(
            name="Boosts",
            value=f"{guild.premium_subscription_count} (level {guild.premium_tier})",
        )
        content.add_field(name="Members", value=str(guild.member_count))
        content.add_field(
            name="Channels",
            value=(f"{len(guild.text_channels)} Text, {len(guild.voice_channels)} Voice"),
        )
        content.add_field(name="Roles", value=str(len(guild.roles)))
        content.add_field(name="Threads", value=str(len(guild.threads)))
        content.add_field(name="NSFW filter", value=guild.explicit_content_filter.name)
        content.add_field(name="Emojis", value=f"{len(guild.emojis)} / {guild.emoji_limit}")
        content.add_field(name="Stickers", value=f"{len(guild.stickers)} / {guild.sticker_limit}")
        content.add_field(name="Created at", value=guild.created_at.strftime("%d/%m/%Y %H:%M"))
        if guild.features:
            content.add_field(
                name="Features",
                value=" ".join(f"`{feature}`" for feature in guild.features),
                inline=False,
            )

        await ctx.send(embed=content)

    @commands.command(aliases=["roles"])
    async def roleslist(self, ctx: commands.Context):
        """List the roles of this server"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        content = discord.Embed(title=f"Roles in {ctx.guild.name}")
        rows = []
        for role in reversed(ctx.guild.roles):
            rows.append(
                f"[`{role.id} | {str(role.color)}`] **x{len(role.members)}**"
                f"{':warning:' if len(role.members) == 0 else ''}: {role.mention}"
            )

        await util.send_as_pages(ctx, content, rows)

    @commands.group(case_insensitive=True, aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context):
        """Show various leaderboards"""
        await util.command_group_help(ctx)

    @leaderboard.command(name="fishy")
    async def leaderboard_fishy(self, ctx: commands.Context, scope=""):
        """Fishy leaderboard"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        global_data = scope.lower() == "global"
        data = await self.bot.db.fetch(
            "SELECT user_id, fishy_count FROM fishy ORDER BY fishy_count DESC"
        )

        rows = []
        medal_emoji = [":first_place:", ":second_place:", ":third_place:"]
        i = 1
        if data:
            for user_id, fishy_count in data:
                if global_data:
                    user = self.bot.get_user(user_id)
                else:
                    user = ctx.guild.get_member(user_id)

                if user is None or fishy_count == 0:
                    continue

                if i <= len(medal_emoji):
                    ranking = medal_emoji[i - 1]
                else:
                    ranking = f"`#{i:2}`"

                rows.append(f"{ranking} **{util.displayname(user)}** — **{fishy_count}** fishy")
                i += 1
        if not rows:
            raise exceptions.CommandInfo("Nobody has any fish yet!")

        content = discord.Embed(
            title=f":fish: {'Global' if global_data else ctx.guild.name} fishy leaderboard",
            color=int("55acee", 16),
        )
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="wpm", aliases=["typing"])
    async def leaderboard_wpm(self, ctx: commands.Context, scope=""):
        """Typing speed leaderboard"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        _global_ = scope == "global"

        data = await self.bot.db.fetch(
            """
            SELECT user_id, MAX(wpm) as wpm, test_date, word_count FROM typing_stats
            GROUP BY user_id ORDER BY wpm DESC
            """
        )

        rows = []
        i = 1
        if data:
            for userid, wpm, test_date, word_count in data:
                if _global_:
                    user = self.bot.get_user(userid)
                else:
                    user = ctx.guild.get_member(userid)

                if user is None:
                    continue

                if i <= len(self.medal_emoji):
                    ranking = self.medal_emoji[i - 1]
                else:
                    ranking = f"`#{i:2}`"

                rows.append(
                    f"{ranking} **{util.displayname(user)}** — **{int(wpm)}** WPM ({word_count} words, {arrow.get(test_date).to('utc').humanize()})"
                )
                i += 1

        if not rows:
            rows = ["No data."]

        content = discord.Embed(
            title=f":keyboard: {ctx.guild.name} WPM leaderboard",
            color=int("99aab5", 16),
        )
        await util.send_as_pages(ctx, content, rows)

    @leaderboard.command(name="crowns")
    async def leaderboard_crowns(self, ctx: commands.Context):
        """Last.fm artist crowns leaderboard"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        data = await self.bot.db.fetch(
            """
            SELECT user_id, COUNT(1) as amount FROM artist_crown
            WHERE guild_id = %s GROUP BY user_id ORDER BY amount DESC
            """,
            ctx.guild.id,
        )
        rows = []
        if data:
            for i, (user_id, amount) in enumerate(data, start=1):
                user = ctx.guild.get_member(user_id)
                if user is None:
                    continue

                if i <= len(self.medal_emoji):
                    ranking = self.medal_emoji[i - 1]
                else:
                    ranking = f"`#{i:2}`"

                rows.append(f"{ranking} **{util.displayname(user)}** — **{amount}** crowns")
        if not rows:
            rows = ["No data."]

        content = discord.Embed(
            color=int("ffcc4d", 16),
            title=f":crown: {ctx.guild.name} artist crowns leaderboard",
        )

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def profile(
        self, ctx: commands.Context, user: Union[discord.Member, discord.User, None] = None
    ):
        """Your personal customizable user profile"""
        if user is None:
            user = ctx.author

        badges = []
        badge_classes = {
            "dev": "fab fa-dev",
            "patreon": "fab fa-patreon",
            "lastfm": "fab fa-lastfm",
            "sunsign": "fas fa-sun",
            "location": "fas fa-compass",
            "bot": "fas fa-robot",
        }

        def get_font_size(username):
            length = len(username)
            if length < 15:
                return "24px"
            if length < 20:
                return "18px"
            if length < 25:
                return "15px"
            return "11px"

        def make_badge(classname):
            return f'<li class="badge-container"><i class="corner-logo {classname}"></i></li>'

        if user.id == self.bot.owner_id:
            badges.append(make_badge(badge_classes["dev"]))

        if user.bot:
            badges.append(make_badge(badge_classes["bot"]))

        if await queries.is_donator(ctx, user):
            badges.append(make_badge(badge_classes["patreon"]))

        user_settings = await self.bot.db.fetch_row(
            "SELECT lastfm_username, sunsign, location_string FROM user_settings WHERE user_id = %s",
            user.id,
        )
        if user_settings:
            if user_settings[0] is not None:
                badges.append(make_badge(badge_classes["lastfm"]))
            if user_settings[1] is not None:
                badges.append(make_badge(badge_classes["sunsign"]))
            if user_settings[2] is not None:
                badges.append(make_badge(badge_classes["location"]))

        if user.bot:
            description = "I am a bot<br>BEEP BOOP"
        else:
            description = "You should change this by using<br>>editprofile description"

        profile_data = await self.bot.db.fetch_row(
            """
            SELECT description, background_url, background_color, show_graph
            FROM user_profile WHERE user_id = %s
            """,
            user.id,
        )

        fishy = await self.bot.db.fetch_value(
            """
            SELECT fishy_count FROM fishy WHERE user_id = %s
            """,
            user.id,
        )

        if profile_data:
            description, background_url, background_color, _show_graph = profile_data
            if description is not None:
                description = bleach.clean(
                    description.replace("\n", "<br>"),
                    tags=bleach.sanitizer.ALLOWED_TAGS + ["br"],
                )
            background_url = background_url or ""
            background_color = (
                ("#" + background_color) if background_color is not None else user.color
            )
        else:
            background_color = user.color
            background_url = ""

        command_uses = await self.bot.db.fetch_value(
            """
            SELECT SUM(uses) FROM command_usage WHERE user_id = %s
            GROUP BY user_id
            """,
            user.id,
        )

        replacements = {
            "BACKGROUND_IMAGE": background_url,
            "WRAPPER_CLASS": "custom-bg" if background_url != "" else "",
            "SIDEBAR_CLASS": "blur" if background_url != "" else "",
            "OVERLAY_CLASS": "overlay" if background_url != "" else "",
            "USER_COLOR": background_color,
            "AVATAR_URL": user.display_avatar.replace(size=128, format="png").url,
            "USERNAME": user.name,
            "DISCRIMINATOR": f"#{user.discriminator}",
            "DESCRIPTION": description,
            "FISHY_AMOUNT": fishy or 0,
            "SERVER_LEVEL": 0,
            "GLOBAL_LEVEL": 0,
            "ACTIVITY_DATA": [],
            "CHART_MAX": 0,
            "COMMANDS_USED": command_uses or 0,
            "BADGES": "\n".join(badges),
            "USERNAME_SIZE": get_font_size(user.name),
            "SHOW_GRAPH": "false",
            "DESCRIPTION_HEIGHT": "350px",
        }

        payload = {
            "html": util.format_html(self.profile_html, replacements),
            "width": 600,
            "height": 400,
            "imageFormat": "png",
        }
        buffer = await util.render_html(self.bot, payload)
        await ctx.send(file=discord.File(fp=buffer, filename=f"profile_{user.name}.png"))

    @commands.command()
    async def marry(self, ctx: commands.Context, user: discord.Member):
        """Marry someone"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if user == ctx.author:
            return await ctx.send("You cannot marry yourself...")
        if {user.id, ctx.author.id} in self.bot.cache.marriages:
            return await ctx.send("You two are already married!")
        for el in self.bot.cache.marriages:
            if ctx.author.id in el:
                pair = list(el)
                if ctx.author.id == pair[0]:
                    partner = ctx.guild.get_member(pair[1]) or self.bot.get_user(pair[1])
                else:
                    partner = ctx.guild.get_member(pair[0]) or self.bot.get_user(pair[0])
                return await ctx.send(
                    f":confused: You are already married to **{util.displayname(partner)}**! You must divorce before marrying someone else..."
                )
            if user.id in el:
                return await ctx.send(
                    f":grimacing: **{user}** is already married to someone else, sorry!"
                )

        if (user.id, ctx.author.id) in self.proposals:
            await self.bot.db.execute(
                "INSERT INTO marriage VALUES (%s, %s, %s)",
                user.id,
                ctx.author.id,
                arrow.now().datetime,
            )
            self.bot.cache.marriages.append({user.id, ctx.author.id})
            await ctx.send(
                embed=discord.Embed(
                    color=int("dd2e44", 16),
                    description=f":revolving_hearts: **{util.displayname(user)}** and **{util.displayname(ctx.author)}** are now married :wedding:",
                )
            )
            new_proposals = set()
            for el in self.proposals:
                if el[0] not in [user.id, ctx.author.id]:
                    new_proposals.add(el)
            self.proposals = new_proposals
        else:
            self.proposals.add((ctx.author.id, user.id))
            await ctx.send(
                embed=discord.Embed(
                    color=int("f4abba", 16),
                    description=f":heartpulse: *You propose to **{util.displayname(user)}***",
                )
            )

    @commands.command()
    async def divorce(self, ctx: commands.Context):
        """End your marriage"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        partner = ""
        to_remove = []
        for el in self.bot.cache.marriages:
            if ctx.author.id in el:
                to_remove.append(el)
                pair = list(el)
                if ctx.author.id == pair[0]:
                    partner = ctx.guild.get_member(pair[1]) or self.bot.get_user(pair[1])
                else:
                    partner = ctx.guild.get_member(pair[0]) or self.bot.get_user(pair[0])

        if partner == "":
            return await ctx.send(":thinking: You are not married!")

        content = discord.Embed(
            description=f":broken_heart: Divorce **{util.displayname(partner)}**?",
            color=int("dd2e44", 16),
        )
        msg = await ctx.send(embed=content)

        async def confirm():
            for x in to_remove:
                self.bot.cache.marriages.remove(x)
            await self.bot.db.execute(
                "DELETE FROM marriage WHERE first_user_id = %s OR second_user_id = %s",
                ctx.author.id,
                ctx.author.id,
            )
            await ctx.send(
                embed=discord.Embed(
                    color=int("ffcc4d", 16),
                    description=f":pensive: You and **{util.displayname(partner)}** are now divorced...",
                )
            )

        async def cancel():
            pass

        functions = {"✅": confirm, "❌": cancel}
        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )

    @commands.command()
    async def marriage(
        self, ctx: commands.Context, member: discord.Member | discord.User | None = None
    ):
        """Check your marriage status"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        member = member or ctx.author

        data = await self.bot.db.fetch_row(
            """
            SELECT first_user_id, second_user_id, marriage_date
                FROM marriage
            WHERE first_user_id = %s OR second_user_id = %s
            """,
            member.id,
            member.id,
        )
        if data:
            if data[0] == member.id:
                partner = ctx.guild.get_member(data[1]) or self.bot.get_user(data[1])
            else:
                partner = ctx.guild.get_member(data[0]) or self.bot.get_user(data[0])
            marriage_date = data[2]
            length = humanize.naturaldelta(
                arrow.utcnow().timestamp() - marriage_date.timestamp(), months=False
            )
            await ctx.send(
                embed=discord.Embed(
                    color=int("f4abba", 16),
                    description=(
                        f":wedding: {'You have' if member == ctx.author else f'**{member}** has'} "
                        f"been married to **{util.displayname(partner)}** for **{length}**"
                    ),
                )
            )
        else:
            await ctx.send("You are not married!")

    @commands.command()
    async def marriages(self, ctx: commands.Context):
        """View the longest surviving marriages"""
        content = discord.Embed(title=":wedding: Longest marriages")

        data = (
            await self.bot.db.fetch(
                """
            SELECT first_user_id, second_user_id, marriage_date
            FROM marriage ORDER BY marriage_date
            """
            )
            or []
        )

        rows = []
        for first_user_id, second_user_id, marriage_date in data:
            first_user = self.bot.get_user(first_user_id)
            second_user = self.bot.get_user(second_user_id)

            # if neither user is reachable then ignore this marriage
            if first_user is None and second_user is None:
                continue

            length = humanize.naturaldelta(
                arrow.utcnow().timestamp() - marriage_date.timestamp(), months=False
            )

            rows.append(
                f"{first_user.name if first_user else first_user_id}"
                " :heart: "
                f"{second_user.name if second_user else second_user_id}"
                f" - **{length}**"
            )

        if not rows:
            raise exceptions.CommandWarning("No one is married yet!")

        await util.send_as_pages(ctx, content, rows)


async def setup(bot):
    await bot.add_cog(User(bot))
