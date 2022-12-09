import math
import re
import urllib.parse
from enum import Enum, auto
from typing import TYPE_CHECKING, Annotated, Optional

import arrow
import discord
import orjson
from discord.ext import commands
from discord.utils import escape_markdown

from modules import exceptions, util
from modules.lastfm import LastFmApi, LastFmImage, Period
from modules.misobot import LastFmContext, MisoBot, MisoContext
from modules.ui import RowPaginator


class PeriodArgument(commands.Converter):
    async def convert(self, ctx: MisoContext, argument: str):
        match argument.lower():
            case "7day" | "7days" | "weekly" | "week" | "1week" | "7d":
                return Period.WEEK
            case "30day" | "30days" | "monthly" | "month" | "1month":
                return Period.MONTH
            case "90day" | "90days" | "3months" | "3month":
                return Period.QUARTER
            case "180day" | "180days" | "6months" | "6month" | "halfyear":
                return Period.HALFYEAR
            case "365day" | "365days" | "1year" | "year" | "12months" | "12month" | "1y":
                return Period.YEAR
            case "overall" | "alltime":
                return Period.OVERALL
            case _:
                raise commands.BadArgument(f"Cannot convert `{argument}` into a timeframe")


class ArtistSubcommand(Enum):
    TOPTRACKS = auto()
    TOPALBUMS = auto()
    OVERVIEW = auto()


class ArtistSubcommandArgument(commands.Converter):
    async def convert(self, ctx: MisoContext, argument: str):
        match argument.lower():
            case "toptracks" | "tt":
                return ArtistSubcommand.TOPTRACKS
            case "topalbums" | "talb":
                return ArtistSubcommand.TOPALBUMS
            case "overview" | "ov" | "profile":
                return ArtistSubcommand.OVERVIEW
            case _:
                raise commands.BadArgument(f"No such command `{argument}`")


class LastFm(commands.Cog):
    """LastFM commands"""

    ICON = "🎵"
    LASTFM_RED = "e31c23"
    LASTFM_ICON_URL = "https://i.imgur.com/dMeDkPH.jpg"

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.api = LastFmApi(bot)

        with open("html/fm_chart.min.html", "r", encoding="utf-8") as file:
            self.chart_html = file.read().replace("\n", "")

    @commands.group(aliases=["lastfm", "lfm", "lf"])
    async def fm(self, ctx: MisoContext):
        """Interact with LastFM using your linked account"""
        if not await util.command_group_help(ctx):
            await create_lastfm_context(ctx)

    @fm.group()
    async def voting(self, ctx: MisoContext):
        """Configure nowplaying voting reactions"""
        await util.command_group_help(ctx)

    @voting.command(name="enabled", usage="<yes | no>")
    async def voting_enabled(self, ctx: MisoContext, status: bool):
        """Toggle whether the voting is enabled for you or not"""
        await self.bot.db.execute(
            """
            INSERT INTO lastfm_vote_setting (user_id, is_enabled)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                is_enabled = VALUES(is_enabled)
            """,
            ctx.author.id,
            status,
        )
        await util.send_success(
            ctx,
            f"Nowplaying reactions for your messages turned **{'on' if status else 'off'}**",
        )

    @voting.command(name="upvote")
    @util.patrons_only()
    async def voting_upvote(self, ctx: MisoContext, emoji: str):
        """Set the upvote emoji"""
        await ctx.message.add_reaction(emoji)
        await self.bot.db.execute(
            """
            INSERT INTO lastfm_vote_setting (user_id, upvote_emoji)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                upvote_emoji = VALUES(upvote_emoji)
            """,
            ctx.author.id,
            emoji,
        )
        await util.send_success(ctx, f"Your upvote reaction emoji is now {emoji}")

    @voting.command(name="downvote")
    @util.patrons_only()
    async def voting_downvote(self, ctx: commands.Context, emoji: str):
        """Set the downvote emoji"""
        await ctx.message.add_reaction(emoji)
        await self.bot.db.execute(
            """
            INSERT INTO lastfm_vote_setting (user_id, downvote_emoji)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                downvote_emoji = VALUES(downvote_emoji)
            """,
            ctx.author.id,
            emoji,
        )
        await util.send_success(ctx, f"Your downvote reaction emoji is now {emoji}")

    @fm.group(name="blacklist")
    @commands.has_permissions(manage_guild=True)
    async def fm_blacklist(self, ctx: MisoContext):
        """Blacklist members from appearing on whoknows and other server wide lists"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if ctx.invoked_subcommand:
            return

        data = await self.bot.db.fetch_flattened(
            """
            SELECT user_id FROM lastfm_blacklist WHERE guild_id = %s
            """,
            ctx.guild.id,
        )
        rows = ["> Use `add` and `remove` subcommands to manage", ""]
        for user_id in data:
            user = self.bot.get_user(user_id)
            rows.append(f"{user.mention if user else '@?'} ({user or user_id})")
        content = discord.Embed(
            title=":no_entry_sign: Current LastFM blacklist",
            color=int(self.LASTFM_RED, 16),
        )
        await ctx.paginate(content, rows)

    @fm_blacklist.command(name="add")
    async def fm_blacklist_add(self, ctx: MisoContext, *, member: discord.Member):
        """Add a member to the blacklist"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        await self.bot.db.execute(
            """
            INSERT INTO lastfm_blacklist (user_id, guild_id)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id)
            """,
            member.id,
            ctx.guild.id,
        )
        await ctx.success(f"{member.mention} will no longer appear on the lastFM leaderboards.")

    @fm_blacklist.command(name="remove")
    async def fm_blacklist_remove(self, ctx: MisoContext, *, member: discord.Member):
        """Remove a member from the blacklist"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        await self.bot.db.execute(
            """
            DELETE FROM lastfm_blacklist WHERE user_id = %s AND guild_id = %s
            """,
            member.id,
            ctx.guild.id,
        )
        await ctx.success(f"{member.mention} is no longer blacklisted.")

    @fm.command()
    async def set(self, ctx: MisoContext, username: str):
        """Save your Last.fm username"""
        content = await self.get_userinfo_embed(username)
        if content is None:
            raise exceptions.CommandWarning(
                f"Last.fm profile `{username}` was not found. Make sure you didn't leave the brackets in."
            )

        await self.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, lastfm_username)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                lastfm_username = VALUES(lastfm_username)
            """,
            ctx.author.id,
            username,
        )

        await ctx.send(
            f"{ctx.author.mention} Last.fm username saved as `{username}`",
            embed=content,
        )

    @fm.command()
    async def unset(self, ctx: MisoContext):
        """Unlink your Last.fm"""
        await self.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, lastfm_username)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                lastfm_username = VALUES(lastfm_username)
            """,
            ctx.author.id,
            None,
        )
        await ctx.send(":broken_heart: Removed your Last.fm username from the database")

    @fm.command()
    async def profile(self, ctx: MisoContext):
        """See your Last.fm profile"""
        await ctx.send(embed=await self.get_userinfo_embed(ctx.lastfmcontext.username))

    @fm.command()
    async def milestone(self, ctx: MisoContext, n: int):
        """See what your n:th scrobble was"""
        if n < 1:
            raise exceptions.CommandWarning(
                "Please give a number between 1 and your total amount of listened tracks."
            )
        PER_PAGE = 100
        pre_data = await self.api.user_get_recent_tracks(
            ctx.lastfmcontext.username,
            limit=PER_PAGE,
        )

        total = int(pre_data["@attr"]["total"])
        if n > total:
            raise exceptions.CommandWarning(
                f"You have only listened to **{total}** tracks! Unable to show {util.ordinal(n)} track"
            )

        remainder = total % PER_PAGE
        total_pages = int(pre_data["recenttracks"]["@attr"]["totalPages"])
        if n > remainder:
            n = n - remainder
            containing_page = total_pages - math.ceil(n / PER_PAGE)
        else:
            containing_page = total_pages

        final_data = await self.api.user_get_recent_tracks(
            ctx.lastfmcontext.username,
            limit=PER_PAGE,
            page=containing_page,
        )

        tracks = list(reversed(final_data["recenttracks"]["track"]))
        nth_track = tracks[(n % 100) - 1]
        await ctx.send(
            f"Your {util.ordinal(n)} scrobble was ***{nth_track['name']}*** by **{nth_track['artist']['#text']}**"
        )

    @fm.command(aliases=["np", "no"])
    async def nowplaying(self, ctx: MisoContext):
        """See your currently playing song"""
        track = await self.api.user_get_now_playing(ctx.lastfmcontext.username)
        artist_name = track["artist"]["#text"]
        album_name = track["album"]["#text"]
        track_name = track["name"]
        image = LastFmImage.from_url(track["image"][-1]["#text"])
        if image.is_missing() and track["album"].get("image") is not None:
            image = LastFmImage.from_url(track["album"]["image"][-1]["#text"])

        content = discord.Embed(
            color=await self.image_color(image),
            description=f":cd: **{escape_markdown(album_name)}**",
            title=f"**{escape_markdown(artist_name)} — *{escape_markdown(track_name)}* **",
        )
        content.set_thumbnail(url=image.as_full())

        # tags and playcount
        track_info = await self.api.track_get_info(
            artist_name, track_name, ctx.lastfmcontext.username
        )
        if track_info is not None:
            play_count = int(track_info["userplaycount"])
            if play_count > 0:
                content.description = f"{content.description}\n> {format_playcount(play_count)}"
            content.set_footer(text=", ".join(tag["name"] for tag in track_info["toptags"]["tag"]))

        # play state
        if track["nowplaying"]:
            state = "> Now Playing"
        else:
            state = "- Last track"
            content.timestamp = arrow.get(int(track["date"]["uts"])).datetime

        content.set_author(
            name=f"{util.displayname(ctx.lastfmcontext.target_user, escape=False)} {state}",
            icon_url=ctx.lastfmcontext.target_user.display_avatar.url,
        )

        message = await ctx.send(embed=content)

        voting_settings = await self.bot.db.fetch_row(
            """
            SELECT is_enabled, upvote_emoji, downvote_emoji
            FROM lastfm_vote_setting WHERE user_id = %s
            """,
            ctx.author.id,
        )
        if voting_settings:
            (voting_mode, upvote, downvote) = voting_settings
            if voting_mode:
                await message.add_reaction(upvote or "👍")
                await message.add_reaction(downvote or "👎")

    @fm.command(aliases=["ta"], usage="[timeframe]")
    async def topartists(
        self, ctx: MisoContext, timeframe: Annotated[Period, PeriodArgument] = Period.OVERALL
    ):
        """See your top 100 artists for given timeframe"""
        data = await self.api.user_get_top_artists(
            ctx.lastfmcontext.username,
            timeframe,
            100,
        )

        await self.paginated_embed(
            ctx,
            self.ranked_list(
                [(int(artist["playcount"]), artist["name"]) for artist in data["artist"]]
            ),
            f"Top 100 Artists ({timeframe.display()})",
            image=await self.api.get_artist_image(data["artist"][0]["name"]),
            footer=f'Total unique artists: {data["@attr"]["total"]}',
        )

    @fm.command(aliases=["tt"], usage="[timeframe]")
    async def toptracks(
        self, ctx: MisoContext, timeframe: Annotated[Period, PeriodArgument] = Period.OVERALL
    ):
        """See your top 100 tracks for given timeframe"""
        data = await self.api.user_get_top_tracks(
            ctx.lastfmcontext.username,
            timeframe,
            100,
        )

        await self.paginated_embed(
            ctx,
            self.ranked_list(
                [
                    (int(track["playcount"]), f'{track["artist"]["name"]} — {track["name"]}')
                    for track in data["track"]
                ]
            ),
            f"Top 100 Tracks ({timeframe.display()})",
            image=await self.api.scrape_track_image(data["track"][0]["url"]),
            footer=f'Total unique tracks: {data["@attr"]["total"]}',
        )

    @fm.command(aliases=["talb"], usage="[timeframe]")
    async def topalbums(
        self, ctx: MisoContext, timeframe: Annotated[Period, PeriodArgument] = Period.OVERALL
    ):
        """See your top 100 albums for given timeframe"""
        data = await self.api.user_get_top_albums(
            ctx.lastfmcontext.username,
            timeframe,
            100,
        )

        await self.paginated_embed(
            ctx,
            self.ranked_list(
                [
                    (int(album["playcount"]), f'{album["artist"]["name"]} — {album["name"]}')
                    for album in data["album"]
                ]
            ),
            f"Top 100 Tracks ({timeframe.display()})",
            image=LastFmImage.from_url(data["album"][0]["image"][0]["#text"]),
            footer=f'Total unique albums: {data["@attr"]["total"]}',
        )

    @fm.command(aliases=["re", "recents"])
    async def recent(self, ctx: MisoContext):
        """See your 100 most recent scrobbles"""
        data = await self.api.user_get_recent_tracks(
            ctx.lastfmcontext.username,
            100,
        )
        rows = []
        for track in data["track"]:
            try:
                timestamp = f'<t:{track["date"]["uts"]}:R>'
            except KeyError:
                timestamp = discord.utils.format_dt(arrow.now().datetime, "R")
            rows.append(f'**{track["artist"]["#text"]} — {track["name"]}** {timestamp}')

        await self.paginated_embed(
            ctx,
            rows,
            "Recently played",
            image=LastFmImage.from_url(data["track"][0]["image"][0]["#text"]),
            footer=f'Total scrobbles: {data["@attr"]["total"]}',
        )

    @fm.command(aliases=["yt"], usage="")
    async def youtube(self, ctx: MisoContext):
        """Find your currently playing track on youtube"""
        track = await self.api.user_get_now_playing(ctx.lastfmcontext.username)

        artist_name = track["artist"]["#text"]
        track_name = track["name"]
        state = "Now playing" if track["nowplaying"] else "Last track"

        YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3/search"
        YOUTUBE_VIDEO_BASE_URL = "https://youtube.com/watch?v="

        params = {
            "part": "snippet",
            "type": "video",
            "maxResults": 1,
            "q": f"{artist_name} {track_name}",
            "key": self.bot.keychain.GCS_DEVELOPER_KEY,
        }

        async with self.bot.session.get(
            YOUTUBE_API_BASE_URL,
            params=params,
        ) as response:
            data = await response.json(loads=orjson.loads)

        video_id = data["items"][0]["id"]["videoId"]
        video_url = YOUTUBE_VIDEO_BASE_URL + video_id

        await ctx.send(
            f"**{util.displayname(ctx.lastfmcontext.target_user)} — {state}** :cd:\n{video_url}"
        )

    @fm.command(aliases=["a"], usage="[timeframe] <toptracks | topartists | topalbums> <artist>")
    async def artist(
        self,
        ctx: MisoContext,
        timeframe: Optional[Annotated[Period, PeriodArgument]] = Period.OVERALL,
        command: Optional[
            Annotated[ArtistSubcommand, ArtistSubcommandArgument]
        ] = ArtistSubcommand.OVERVIEW,
        *,
        artist: str,
    ):
        """
        See top tracks, albums or overview for specific artist

        Usage:
            >fm artist [timeframe] [toptracks | topalbums | profile] <artist name>

        Examples:
            >fm artist weekly toptracks metallica
            >fm artist talb dreamcatcher
            >fm artist bts
        """
        # dumb type checker doesnt get it
        if TYPE_CHECKING:
            assert timeframe is not None

        match command:
            case ArtistSubcommand.OVERVIEW:
                await self.artist_overview(ctx, timeframe, artist)
            case ArtistSubcommand.TOPALBUMS:
                await self.artist_topalbums(ctx, timeframe, artist)
            case ArtistSubcommand.TOPTRACKS:
                await self.artist_toptracks(ctx, timeframe, artist)

    # helpers

    async def artist_overview(self, ctx: MisoContext, timeframe: Period, artist: str):
        albums = []
        tracks = []
        artistinfo = await self.api.artist_get_info(
            artist, ctx.lastfmcontext.username, autocorrect=True
        )
        url = f"https://last.fm/user/{ctx.lastfmcontext.username}/library/music/{urllib.parse.quote_plus(artist)}"
        soup = await self.api.scrape_page(url, params={"date_preset": timeframe.web_format()})

        try:
            albumsdiv, tracksdiv, _ = soup.findAll("tbody", {"data-playlisting-add-entries": ""})
        except ValueError:
            artist_escaped = discord.utils.escape_markdown(artist)
            if timeframe == Period.OVERALL:
                return await ctx.send(f"You have never listened to **{artist_escaped}**!")
            return await ctx.send(
                f"You have not listened to **{artist_escaped}** in the past {timeframe}!"
            )

        for container, destination in zip([albumsdiv, tracksdiv], [albums, tracks]):
            items = container.findAll("tr", {"class": "chartlist-row"})
            for item in items:
                name = item.find("td", {"class": "chartlist-name"}).find("a").get("title")
                playcount = (
                    item.find("span", {"class": "chartlist-count-bar-value"})
                    .text.replace("scrobbles", "")
                    .replace("scrobble", "")
                    .strip()
                )
                destination.append((name, int(playcount.replace(",", ""))))

        metadata = []
        for metadata_item in soup.select("metadata-display"):
            metadata.append(int(metadata_item.text.replace(",", "")))

        scrobbles, albums_count, tracks_count = metadata

        img = soup.select_one("span.library-header-image img")
        header = soup.select_one("h2.library-header-title")
        formatted_name = header.text.strip() if header else artist

        listeners = artistinfo["artist"]["stats"]["listeners"]
        globalscrobbles = artistinfo["artist"]["stats"]["playcount"]
        similar = [a["name"] for a in artistinfo["artist"]["similar"]["artist"]]
        tags = [t["name"] for t in artistinfo["artist"]["tags"]["tag"]]

        content = discord.Embed()
        if img:
            image = LastFmImage.from_url(img.attrs["src"])
            content.set_thumbnail(url=image.as_full())
            content.colour = await self.image_color(image)

        content.set_author(
            name=f"{util.displayname(ctx.lastfmcontext.target_user, escape=False)} — {formatted_name} "
            + (f"{timeframe.display().capitalize()} " if timeframe != timeframe.OVERALL else "")
            + "overview",
            icon_url=ctx.lastfmcontext.target_user.display_avatar.url,
            url=f"{url}?date_preset={timeframe.web_format()}",
        )

        content.set_footer(text=f"{', '.join(tags)}")

        crownstate = ""
        if ctx.guild:
            crown_holder_id = await self.bot.db.fetch_value(
                """
                SELECT user_id FROM artist_crown WHERE guild_id = %s AND artist_name = %s
                """,
                ctx.guild.id,
                formatted_name,
            )
            if crown_holder_id == ctx.lastfmcontext.target_user.id:
                crownstate = " :crown:"

        content.add_field(name="Listeners", value=f"**{listeners}**")
        content.add_field(name="Scrobbles", value=f"**{globalscrobbles}**")
        content.add_field(name="Your scrobbles", value=f"**{scrobbles}**{crownstate}")

        content.add_field(
            name=f":cd: {albums_count} Albums",
            value="\n".join(
                f"`#{i:2}` **{discord.utils.escape_markdown(item)}** ({playcount})"
                for i, (item, playcount) in enumerate(albums, start=1)
            ),
            inline=True,
        )
        content.add_field(
            name=f":musical_note: {tracks_count} Tracks",
            value="\n".join(
                f"`#{i:2}` **{discord.utils.escape_markdown(item)}** ({playcount})"
                for i, (item, playcount) in enumerate(tracks, start=1)
            ),
            inline=True,
        )

        if similar:
            content.add_field(name="Similar artists", value=", ".join(similar), inline=False)

        await ctx.send(embed=content)

    async def artist_topalbums(self, ctx: MisoContext, timeframe: Period, artist: str):
        pass

    async def artist_toptracks(self, ctx: MisoContext, timeframe: Period, artist: str):
        pass

    async def paginated_embed(
        self,
        ctx: MisoContext,
        rows: list[str],
        title: str,
        image: Optional[LastFmImage] = None,
        footer: Optional[str] = None,
    ):
        content = discord.Embed()
        if image:
            content.color = await self.image_color(image)
            content.set_thumbnail(url=image.as_full())

        content.set_author(
            name=f"{util.displayname(ctx.lastfmcontext.target_user, escape=False)} — {title}",
            icon_url=ctx.lastfmcontext.target_user.display_avatar.url,
        )

        if footer:
            content.set_footer(text=footer)

        await RowPaginator(content, rows).run(ctx)

    def ranked_list(self, data: list[tuple[int, str]]):
        rows = []
        for i, (playcount, name) in enumerate(data, start=1):
            rows.append(f"`#{i:2}` {format_playcount(playcount)} • **{escape_markdown(name)}**")
        return rows

    async def get_userinfo_embed(self, username: str):
        user = await self.api.user_get_info(username)

        avatar = LastFmImage.from_url(user["image"][-1]["#text"])
        timestamp = arrow.get(int(user["registered"]["unixtime"]))

        content = discord.Embed(color=int(self.LASTFM_RED, 16))
        content.set_author(
            icon_url=self.LASTFM_ICON_URL,
            name=user["name"] + (" `LAST.FM PRO`" if user["subscriber"] == "1" else ""),
            url=user["url"],
        )
        content.add_field(
            name=f"{user['playcount']} Scrobbles",
            value="\n".join(
                [
                    f"**{user['track_count']}** Tracks",
                    f"**{user['album_count']}** Albums",
                    f"**{user['artist_count']}** Artists",
                ]
            ),
        )
        content.add_field(
            name="Registered",
            value=f"{timestamp.humanize()}\n{timestamp.format('DD/MM/YYYY')}",
        )
        content.add_field(name="Country", value=user["country"])
        content.set_thumbnail(url=avatar.as_full())

        return content

    async def image_color(self, image: LastFmImage):
        """Get the dominant color of lastfm image, cache if new."""
        cached_color = await self.bot.db.fetch_value(
            "SELECT hex FROM image_color_cache WHERE image_hash = %s",
            image.hash,
        )
        if cached_color:
            return int(cached_color, 16)

        # color not cached yet, compute and store

        color = await util.rgb_from_image_url(
            self.bot.session,
            image.as_64s(),
        )
        if color is None:
            return int(self.LASTFM_RED, 16)

        hex_color = util.rgb_to_hex(color)
        await self.bot.db.execute(
            "INSERT IGNORE image_color_cache (image_hash, r, g, b, hex) VALUES (%s, %s, %s, %s, %s)",
            image.hash,
            color.r,
            color.g,
            color.b,
            hex_color,
        )

        return int(hex_color, 16)


async def setup(bot):
    await bot.add_cog(LastFm(bot))


async def create_lastfm_context(ctx: MisoContext):
    if not ctx.invoked_subcommand or ctx.invoked_subcommand.name in ["set", "unset", "blacklist"]:
        return

    target_user = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
    targets_author = target_user == ctx.author

    lastfm_username: str | None = await ctx.bot.db.fetch_value(
        "SELECT lastfm_username FROM user_settings WHERE user_id = %s",
        target_user.id,
    )
    if lastfm_username is None:
        if targets_author:
            msg = f"No last.fm username saved! Please use `{ctx.prefix}fm set <username>` (without brackets) to save your username (last.fm account required)"
        else:
            msg = f"{target_user.mention} has not saved their lastfm username yet!"

        raise exceptions.CommandWarning(msg)

    ctx.lastfmcontext = LastFmContext(target_user, targets_author, lastfm_username)


def remove_mentions(text):
    """Remove mentions from string"""
    return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()


def format_playcount(count: int):
    return f"**{count}** play" if count == 1 else f"**{count}** plays"
