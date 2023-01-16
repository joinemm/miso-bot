import asyncio
import io
import math
import os
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Annotated, Callable, Literal, Optional, Union

import arrow
import discord
import orjson
from discord.ext import commands
from discord.utils import escape_markdown

from modules import exceptions, util
from modules.lastfm import LastFmApi, LastFmImage, Period
from modules.misobot import LastFmContext, MisoBot, MisoContext
from modules.ui import RowPaginator

# from loguru import logger


def is_small_server():
    async def predicate(ctx: MisoContext):
        if ctx.guild is None:
            return True

        await util.require_chunked(ctx.guild)
        users = await ctx.bot.db.fetch_value(
            """
            SELECT count(*) FROM user_settings WHERE user_id IN %s
            AND lastfm_username IS NOT NULL
            """,
            [user.id for user in ctx.guild.members],
        )
        if users and users > 200:
            raise exceptions.ServerTooBig(ctx.guild.member_count)

        return True

    return commands.check(predicate)


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

    @classmethod
    async def convert(cls, ctx: MisoContext, argument: str):
        match argument.lower():
            case "toptracks" | "tt":
                return cls.TOPTRACKS
            case "topalbums" | "talb":
                return cls.TOPALBUMS
            case "overview" | "ov" | "profile":
                return cls.OVERVIEW
            case _:
                raise commands.BadArgument(f"No such command `{argument}`")


# maybe possible to combine these classes so convert fn in real dataclass


@dataclass
class ChartSize:
    width: int
    height: int

    @property
    def count(self):
        return self.width * self.height

    def __str__(self):
        return f"{self.width}x{self.height}"


class ChartSizeArgument:
    async def convert(self, ctx: MisoContext, argument: str):
        try:
            size = ChartSize(int(argument), int(argument))
        except ValueError:
            try:
                size = ChartSize(*map(lambda n: int(n), argument.split("x")))
            except ValueError:
                raise commands.BadArgument(f"Cannot convert `{argument}` to size")

        return size


class StrOrNp:
    def extract(self, data: dict):
        raise NotImplementedError

    def parse(self, argument: str):
        return argument

    async def convert(self, ctx: MisoContext, argument: str):
        stripped_argument = remove_mentions(argument)
        if stripped_argument.lower() == "np":
            assert isinstance(ctx.cog, LastFm)
            if hasattr(ctx, "lastfmcontext"):
                username = ctx.lastfmcontext.username
            else:
                ctxdata = await get_lastfm_username(ctx)
                username = ctxdata[2]

            data = await ctx.cog.api.user_get_now_playing(username)
            return self.extract(data)
        else:
            return self.parse(stripped_argument)


class ArtistArgument(StrOrNp):
    def extract(self, data: dict):
        return data["artist"]["#text"]


class TrackArgument(StrOrNp):
    def extract(self, data: dict):
        return data["name"], data["artist"]["#text"]

    def parse(self, argument: str):
        splits = argument.split("|")
        if len(splits) < 2:
            splits = argument.split(" by ")
        if len(splits) < 2:
            raise commands.BadArgument(
                "Invalid format! Please use `<track> | <artist>`. Example: `one | `metallica"
            )

        return [s.strip() for s in splits]


class AlbumArgument(StrOrNp):
    def extract(self, data: dict):
        return data["album"]["name"], data["artist"]["#text"]

    def parse(self, argument: str):
        splits = argument.split("|")
        if len(splits) < 2:
            splits = argument.split(" by ")
        if len(splits) < 2:
            raise commands.BadArgument(
                "Invalid format! Please use `<album> | <artist>`. Example: `master of puppets | one`"
            )

        return [s.strip() for s in splits]


class LastFm(commands.Cog):
    """LastFM commands"""

    ICON = "🎵"
    LASTFM_RED = "e31c23"
    LASTFM_ICON_URL = "https://i.imgur.com/dMeDkPH.jpg"

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.api = LastFmApi(bot)

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

        await self.paginated_user_stat_embed(
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

        await self.paginated_user_stat_embed(
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

        await self.paginated_user_stat_embed(
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

        await self.paginated_user_stat_embed(
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
        command: Optional[ArtistSubcommand] = ArtistSubcommand.OVERVIEW,
        *,
        artist: Annotated[str, ArtistArgument],
    ):
        """
        See top tracks, albums or overview for specific artist

        Usage:
            >fm artist [timeframe] [toptracks | topalbums | profile] <artist name>

        Examples:
            >fm artist weekly toptracks bts
            >fm artist talb dreamcatcher
            >fm artist mamamoo
        """
        # dumb type checker doesnt get it
        if TYPE_CHECKING:
            assert timeframe is not None

        match command:
            case ArtistSubcommand.OVERVIEW:
                await self.artist_overview(ctx, timeframe, artist)
            case ArtistSubcommand.TOPALBUMS:
                await self.artist_top(ctx, timeframe, artist, "albums")
            case ArtistSubcommand.TOPTRACKS:
                await self.artist_top(ctx, timeframe, artist, "tracks")

    # helpers

    async def artist_overview(self, ctx: MisoContext, timeframe: Period, artist: str):
        artistinfo = await self.api.artist_get_info(
            artist, ctx.lastfmcontext.username, autocorrect=True
        )

        artist_url_format = artistinfo["url"].split("/")[-1]
        url = f"https://last.fm/user/{ctx.lastfmcontext.username}/library/music/{artist_url_format}?date_preset={timeframe.web_format()}"
        soup = await self.api.scrape_page(url, authenticated=True)

        try:
            albumsdiv, tracksdiv = soup.select(".chartlist", limit=2)
        except ValueError:
            raise_no_artist_plays(artist, timeframe)

        albums = self.api.get_library_playcounts(albumsdiv)
        tracks = self.api.get_library_playcounts(tracksdiv)

        img = soup.select_one("span.library-header-image img")
        header = soup.select_one("h2.library-header-title")
        formatted_name = header.text.strip() if header else artist

        content = discord.Embed()

        if img:
            image = LastFmImage.from_url(img.attrs["src"])
            content.set_thumbnail(url=image.as_full())
            content.colour = await self.image_color(image)

        content.set_author(
            name=f"{util.displayname(ctx.lastfmcontext.target_user, escape=False)} — {formatted_name} — "
            + (
                f"{timeframe.display().capitalize()} overview"
                if timeframe != timeframe.OVERALL
                else "Overview"
            ),
            icon_url=ctx.lastfmcontext.target_user.display_avatar.url,
            url=url,
        )

        metadata = []
        for metadata_item in soup.select(".metadata-display"):
            metadata.append(parse_playcount(metadata_item.text))

        scrobbles, albums_count, tracks_count = metadata

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
                crownstate = ":crown: "

        api_data = await asyncio.gather(
            self.api.user_get_top_artists(ctx.lastfmcontext.username, Period.OVERALL, limit=1000),
            self.api.user_get_top_artists(ctx.lastfmcontext.username, Period.MONTH, limit=1000),
            self.api.user_get_top_artists(ctx.lastfmcontext.username, Period.WEEK, limit=1000),
        )

        def filter_artist(ta_data: dict):
            try:
                matching_artist = next(
                    filter(lambda a: a["name"] == artistinfo["name"], ta_data["artist"])
                )
                field_value = (
                    f"**{matching_artist['playcount']}** (#{matching_artist['@attr']['rank']})"
                )
                return field_value
            except StopIteration:
                return None

        ta_scrobbles = filter_artist(api_data[0])
        content.add_field(
            name="Total plays",
            value=crownstate + (ta_scrobbles if ta_scrobbles else f"**{scrobbles}**"),
        )

        for ta_data, period in zip(api_data[1:], [Period.MONTH, Period.WEEK]):
            content.add_field(
                name=f"Last {str(period).lower()}", value=filter_artist(ta_data) or "None"
            )

        album_ranking = [f"**{name}** • {plays}" for (plays, name) in albums[:5]]
        track_ranking = [f"**{name}** • {plays}" for (plays, name) in tracks[:5]]
        longest_line = len(max(album_ranking, key=len)) + len(max(track_ranking, key=len))
        render_inline = longest_line < 80

        content.add_field(
            name=f":cd: {albums_count} Albums heard",
            value=">>> " + "\n".join(album_ranking),
            inline=render_inline,
        )
        content.add_field(
            name=f":musical_note: {tracks_count} Tracks heard",
            value=">>> " + "\n".join(track_ranking),
            inline=render_inline,
        )

        content.description = (
            artistinfo["bio"]["summary"].split("<a href")[0].strip().replace("\n\n\n", "\n\n")
        )

        content.set_footer(text=", ".join([x["name"] for x in artistinfo["tags"]["tag"]]))

        await ctx.send(embed=content)

    async def artist_top(
        self,
        ctx: MisoContext,
        timeframe: Period,
        artist: str,
        data_type: Literal["tracks", "albums"],
    ):
        artistinfo = await self.api.artist_get_info(
            artist, ctx.lastfmcontext.username, autocorrect=True
        )

        artist_url_format = artistinfo["url"].split("/")[-1]
        url = f"https://last.fm/user/{ctx.lastfmcontext.username}/library/music/{artist_url_format}/+{data_type}?date_preset={timeframe.web_format()}"
        soup = await self.api.scrape_page(url, authenticated=True)

        formatted_name = artistinfo["name"]
        row_items = self.api.get_library_playcounts(soup)
        row_items += await self.api.get_additional_library_pages(soup, url)

        img_tag = soup.select_one(".chartlist-image .cover-art img")
        image = LastFmImage.from_url(img_tag.attrs["src"]) if img_tag else None

        await self.paginated_user_stat_embed(
            ctx,
            self.ranked_list(row_items),
            f"{formatted_name} — "
            + (
                f"{timeframe.display().capitalize()} top {data_type}"
                if timeframe != timeframe.OVERALL
                else f"Top {data_type}"
            ),
            image,
            footer=f"Total {artistinfo['stats']['userplaycount']} plays across {len(row_items)} {data_type}",
        )

    @fm.command(name="cover", aliases=["art"])
    async def album_cover(self, ctx: MisoContext):
        """See the full album cover of your current song"""
        track = await self.api.user_get_now_playing(ctx.lastfmcontext.username)
        image = LastFmImage.from_url(track["image"][-1]["#text"])
        artist_name = track["artist"]["#text"]
        album_name = track["album"]["#text"]

        async with self.bot.session.get(image.as_full()) as response:
            buffer = io.BytesIO(await response.read())
            await ctx.send(
                f"**{artist_name} — {album_name}**",
                file=discord.File(fp=buffer, filename=image.hash + ".jpg"),
            )

    @fm.command(
        aliases=["chart"],
        usage="['album' | 'artist' | 'recent'] [timeframe] [[width]x[height]] ['notitle' | 'topster'] ['padded']",
    )
    async def collage(
        self,
        ctx: MisoContext,
        *args: Union[
            Literal["album", "artist", "recent", "notitle", "recents", "padded", "topster"],
            Annotated[Period, PeriodArgument],
            Annotated[ChartSize, ChartSizeArgument],
        ],
    ):
        """
        Collage of your top albums or artists

        Usage:
            >fm chart ['album' | 'artist' | 'recent'] [timeframe] [[width]x[height]] ['notitle' | 'topster'] ['padded']

        Examples:
            >fm chart (defaults to 3x3 weekly albums)
            >fm chart 5x5 month
            >fm chart artist
            >fm chart 4x5 year notitle
            >fm chart 5x5 3month padded topster
        """
        timeframe = Period.WEEK
        size = ChartSize(3, 3)
        for arg in args:
            if isinstance(arg, Period):
                timeframe = arg
            elif isinstance(arg, ChartSize):
                if arg.width > 12 or arg.height > 12:
                    raise exceptions.CommandWarning(
                        "The maximum width/height of the collage is `12`"
                    )
                size = arg

        chart_nodes = []
        topster_labels = []
        topster = "topster" in args
        if "artist" in args:
            chart_title = "top artist"
            data = await self.api.user_get_top_artists(
                ctx.lastfmcontext.username, timeframe, size.count
            )
            scraped_images = await self.api.library_artist_images(
                ctx.lastfmcontext.username, size.count, timeframe
            )
            for i, artist in enumerate(data["artist"]):
                name = artist["name"]
                plays = int(artist["playcount"])
                chart_nodes.append(
                    (
                        scraped_images[i],
                        f"<strong>{name}</strong></br>{plays} {'play' if plays == 1 else 'plays'}",
                    )
                )
                if topster:
                    if i > 0 and i % size.width == 0:
                        topster_labels.append(dict(text="</br>"))
                    topster_labels.append(dict(text=f"<li>{i+1}. {name}</li>"))

        elif "recent" in args or "recents" in args:
            chart_title = "recent tracks"
            data = await self.api.user_get_recent_tracks(ctx.lastfmcontext.username, size.count)
            for i, track in enumerate(data["track"]):
                name = track["name"]
                artist = track["artist"]["#text"]
                chart_nodes.append(
                    (
                        LastFmImage.from_url(track["image"][0]["#text"]),
                        f"<strong>{name}</br>{artist}</strong>",
                    )
                )
                if topster:
                    if i > 0 and i % size.width == 0:
                        topster_labels.append(dict(text="</br>"))
                    topster_labels.append(dict(text=f"<li>{i+1}. {artist} — {name}</li>"))

        else:
            chart_title = "top album"
            data = await self.api.user_get_top_albums(
                ctx.lastfmcontext.username, timeframe, size.count
            )
            for i, album in enumerate(data["album"]):
                name = album["name"]
                artist = album["artist"]["name"]
                plays = int(album["playcount"])
                chart_nodes.append(
                    (
                        LastFmImage.from_url(album["image"][0]["#text"]),
                        f"<strong>{name}</br>{artist}</strong></br>{plays} {'play' if plays == 1 else 'plays'}",
                    )
                )
                if topster:
                    if i > 0 and i % size.width == 0:
                        topster_labels.append(dict(text="</br>"))
                    topster_labels.append(dict(text=f"<li>{i+1}. {artist} — {name}</li>"))

        buffer = await self.chart_factory(
            chart_nodes,
            size,
            hide_labels="notitle" in args or topster,
            use_padding="padded" in args,
            topster_labels=topster_labels,
        )

        caption = f"**{util.displayname(ctx.lastfmcontext.target_user)} — {timeframe.display()} {size} {chart_title} collage**"
        filename = f"miso_collage_{ctx.lastfmcontext.username}_{timeframe}_{arrow.now().int_timestamp}.jpg"

        await ctx.send(caption, file=discord.File(fp=buffer, filename=filename))

    async def chart_factory(
        self,
        chart_nodes: list[tuple[LastFmImage, str]],
        size: ChartSize,
        hide_labels=True,
        use_padding=False,
        topster_labels: list[str] = list(),
    ):

        resolution = 1080
        font_size = 2.5
        if size.count > 25:
            font_size = 1.75
        if size.count > 42:
            resolution = 1440
        if size.count > 49:
            font_size = 1.25
        if size.count > 69:
            resolution = 2160
        if size.count > 104:
            font_size = 1.0

        albums = []
        for (image, label) in chart_nodes:
            albums.append(
                {"image_url": image.as_full(), "label": label if not hide_labels else ""}
            )

        image_width = (
            resolution
            if size.width >= size.height
            else int(resolution * (size.width / size.height))
        )

        render_context = {
            "ROWS": size.height,
            "COLUMNS": size.width,
            "ALBUMS": albums,
            "USE_TOPSTER": bool(topster_labels),
            "TOPSTER_LABELS": topster_labels,
            "TOPSTER_FONT_SIZE": f"{font_size}em",
            "LABEL_FONT_SIZE": f"{font_size/2}em",
            "RESOLUTION_WIDTH": f"{image_width}px",
            "RESOLUTION_HEIGHT": f"{resolution}px" if size.height > size.width else "auto",
            "WRAP_CLASSES": "with-gaps" if use_padding else "",
            "BASE_URL": "http://" + os.environ["IMAGE_SERVER_HOST"] + ":3000",
        }

        payload = {
            "templateName": "fm_collage",
            "context": orjson.dumps(render_context).decode(),
            "imageFormat": "jpg",
            "width": 1,
            "height": 1,
        }

        return await util.render_html(self.bot, payload, endpoint="template")

    async def server_lastfm_usernames(
        self, guild: discord.Guild, filter_blacklisted=False
    ) -> list[tuple[int, str]]:
        guild_user_ids = [user.id for user in guild.members]

        if filter_blacklisted:
            data = await self.bot.db.fetch(
                """
                SELECT user_id, lastfm_username FROM user_settings WHERE user_id IN %s
                AND lastfm_username IS NOT NULL
                AND user_id not in (SELECT user_id FROM lastfm_blacklist WHERE guild_id = %s)
                """,
                guild_user_ids,
                guild.id,
            )
        else:
            data = await self.bot.db.fetch(
                """
                SELECT user_id, lastfm_username FROM user_settings WHERE user_id IN %s
                AND lastfm_username IS NOT NULL
                """,
                guild_user_ids,
            )

        if data is None:
            return []

        return data

    async def user_ranking(self, ctx: MisoContext, playcount_fn: Callable, ranking_of: str):
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        fm_members = await self.server_lastfm_usernames(ctx.guild, filter_blacklisted=True)
        if not fm_members:
            raise exceptions.CommandInfo(
                "Nobody on this server has connected their Last.fm account yet!"
            )

        tasks = [playcount_fn(lastfm_username, user_id) for user_id, lastfm_username in fm_members]

        data = await asyncio.gather(*tasks)
        crown_holder = None
        crown_playcount = 0
        total = 0
        rows = []
        i = 1

        for playcount, user_id in sorted(data, reverse=True):
            if playcount == 0:
                continue

            member = ctx.guild.get_member(user_id)

            if i == 1:
                rank = ":crown:"
                crown_holder = member
                crown_playcount = playcount
            else:
                rank = f"`#{i:2}`"

            rows.append(f"{rank} **{util.displayname(member)}** — {format_playcount(playcount)}")
            total += playcount
            i += 1

        if not rows:
            raise exceptions.CommandInfo(f"Nobody on this server has listened to **{ranking_of}**")

        content = discord.Embed(title=f"Who knows **{ranking_of}**?")

        content.set_footer(text=f"Collective plays: {total}")

        return content, rows, crown_holder, crown_playcount

    @commands.command(aliases=["wk", "whomstknows"], usage="<artist> 'np'")
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknows(self, ctx: MisoContext, *, artist: Annotated[str, ArtistArgument]):
        """
        Who has listened to a given artist the most.

        Usage:
            >whoknows <artist name>
            >whoknows np
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        artistinfo = await self.api.artist_get_info(artist, autocorrect=True)
        artist_name = artistinfo["name"]

        # function to determine playcount
        async def user_playcount(lastfm_username: str, user_id: int) -> tuple[int, int]:
            data = await self.api.artist_get_info(artist, lastfm_username, autocorrect=True)
            try:
                count = int(data["stats"]["userplaycount"])
            except (KeyError, TypeError):
                count = 0

            return count, user_id

        # get whoknows ranking
        content, rows, crown_holder, crown_playcount = await self.user_ranking(
            ctx, user_playcount, artist_name
        )

        # get artist image
        image = await self.api.get_artist_image(artist_name)
        if image:
            content.set_thumbnail(url=image.as_full())
            content.colour = await self.image_color(image)

        # send pages
        await RowPaginator(content, rows).run(ctx)

        # if crown was stolen, send that as a separate message
        if crown_holder:
            previous_crown_holder_id = await self.bot.db.fetch_value(
                "SELECT user_id FROM artist_crown WHERE artist_name = %s AND guild_id = %s",
                artist_name,
                ctx.guild.id,
            )
            await self.bot.db.execute(
                """
                INSERT INTO artist_crown (guild_id, user_id, artist_name, cached_playcount)
                    VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    cached_playcount = VALUES(cached_playcount),
                    user_id = VALUES(user_id)
                """,
                ctx.guild.id,
                crown_holder.id,
                artist_name,
                crown_playcount,
            )
            if previous_crown_holder_id:
                previous_crown_holder = ctx.guild.get_member(previous_crown_holder_id)
                if previous_crown_holder is None:
                    previous_crown_holder = self.bot.get_user(previous_crown_holder_id)

                if previous_crown_holder and (previous_crown_holder != crown_holder):
                    await ctx.send(
                        f"> **{util.displayname(crown_holder)}** just stole the **{artist_name}** crown from **{util.displayname(previous_crown_holder)}**"
                    )

    @commands.command(aliases=["wkt", "whomstknowstrack"], usage="<track> | <artist> 'np'")
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknowstrack(self, ctx: MisoContext, *, track: Annotated[tuple, TrackArgument]):
        """
        Who has listened to a given song the most.

        Usage:
            >whoknowstrack <track name> | <artist name>
            >whoknowstrack np
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        track_input, artist_input = track

        trackinfo = await self.api.track_get_info(artist_input, track_input, autocorrect=True)
        track_name = trackinfo["name"]
        artist_name = trackinfo["artist"]["name"]

        # function to determine playcount
        async def user_playcount(lastfm_username: str, user_id: int) -> tuple[int, int]:
            data = await self.api.track_get_info(
                artist_input, track_input, lastfm_username, autocorrect=True
            )
            try:
                count = int(data["userplaycount"])
            except (KeyError, TypeError):
                count = 0

            return count, user_id

        # get whoknows ranking
        content, rows, _, _ = await self.user_ranking(
            ctx, user_playcount, f"{track_name}** by **{artist_name}"
        )

        # get album image
        image = LastFmImage.from_url(trackinfo["album"]["image"][0]["#text"])
        if image:
            content.set_thumbnail(url=image.as_full())
            content.colour = await self.image_color(image)

        # send pages
        await RowPaginator(content, rows).run(ctx)

    @commands.command(
        aliases=["wka", "wkalb", "whomstknowsalbum"], usage="<album> | <artist> 'np'"
    )
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknowsalbum(self, ctx: MisoContext, *, album: Annotated[tuple, AlbumArgument]):
        """
        Who has listened to a given album the most.

        Usage:
            >whoknowstrack <album name> | <artist name>
            >whoknowstrack np
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        album_input, artist_input = album

        albuminfo = await self.api.album_get_info(artist_input, album_input, autocorrect=True)
        album_name = albuminfo["name"]
        artist_name = albuminfo["artist"]["name"]

        # function to determine playcount
        async def user_playcount(lastfm_username: str, user_id: int) -> tuple[int, int]:
            data = await self.api.track_get_info(
                artist_input, album_input, lastfm_username, autocorrect=True
            )
            try:
                count = int(data["userplaycount"])
            except (KeyError, TypeError):
                count = 0

            return count, user_id

        # get whoknows ranking
        content, rows, _, _ = await self.user_ranking(
            ctx, user_playcount, f"{album_name}** by **{artist_name}"
        )

        # get album image
        image = LastFmImage.from_url(albuminfo["image"][0]["#text"])
        if image:
            content.set_thumbnail(url=image.as_full())
            content.colour = await self.image_color(image)

        # send pages
        await RowPaginator(content, rows).run(ctx)

    async def paginated_user_stat_embed(
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

    data = await get_lastfm_username(ctx)
    ctx.lastfmcontext = LastFmContext(*data)


async def get_lastfm_username(ctx: MisoContext):
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

    return target_user, targets_author, lastfm_username


def remove_mentions(text):
    """Remove mentions from string"""
    return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()


def format_playcount(count: int):
    return f"**{count}** play" if count == 1 else f"**{count}** plays"


def parse_playcount(text: str):
    return int(text.split()[0].replace(",", ""))


def raise_no_artist_plays(artist: str, timeframe: Period):
    artist_escaped = discord.utils.escape_markdown(artist)
    raise exceptions.CommandInfo(
        f"You have never listened to **{artist_escaped}**!"
        if timeframe == Period.OVERALL
        else f"You have not listened to **{artist_escaped}** in the past {timeframe}!"
    )
