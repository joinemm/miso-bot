# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import io
import math
import random
import re
import urllib.parse
from typing import Optional

import aiohttp
import arrow
import colorgram
import discord
import kdtree
import orjson
from bs4 import BeautifulSoup
from discord.ext import commands
from loguru import logger
from PIL import Image

from modules import emojis, exceptions, util
from modules.genius import Genius
from modules.misobot import MisoBot

MISSING_IMAGE_HASH = "2a96cbd8b46e442fc41c2b86b821562f"


def is_small_server():
    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return True
        await util.require_chunked(ctx.guild)
        bot: MisoBot = ctx.bot
        users = await bot.db.fetch_value(
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


class AlbumColorNode:
    def __init__(self, rgb, image_url):
        self.rgb = rgb
        self.data = image_url

    def __len__(self):
        return len(self.rgb)

    def __getitem__(self, i):
        return self.rgb[i]

    def __str__(self):
        return f"rgb{self.rgb}"

    def __repr__(self):
        return f"AlbumColorNode({self.rgb}, {self.data})"


class LastFm(commands.Cog):
    """LastFM commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🎵"
        self.lastfm_red = "b90000"
        self.cover_base_urls = [
            "https://lastfm.freetls.fastly.net/i/u/34s/{0}",
            "https://lastfm.freetls.fastly.net/i/u/64s/{0}",
            "https://lastfm.freetls.fastly.net/i/u/174s/{0}",
            "https://lastfm.freetls.fastly.net/i/u/300x300/{0}",
            "https://lastfm.freetls.fastly.net/i/u/{0}",
        ]
        with open("html/fm_chart.min.html", "r", encoding="utf-8") as file:
            self.chart_html = file.read().replace("\n", "")

    @commands.group(case_insensitive=True, aliases=["lastfm"])
    async def fm(self, ctx: commands.Context):
        """Interact with LastFM using your linked account"""
        if ctx.invoked_subcommand is None:
            await util.command_group_help(ctx)
        else:
            await username_to_ctx(ctx)

    @fm.group(name="blacklist")
    @commands.has_permissions(manage_guild=True)
    async def fm_blacklist(self, ctx: commands.Context):
        """Blacklist members from appearing on whoknows and other server wide lists"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if ctx.invoked_subcommand is None:
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
                color=int(self.lastfm_red, 16),
            )
            await util.send_as_pages(ctx, content, rows)

    @fm_blacklist.command(name="add")
    async def fm_blacklist_add(self, ctx: commands.Context, *, member: discord.Member):
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
        await util.send_success(
            ctx, f"{member.mention} will no longer appear on the lastFM leaderboards."
        )

    @fm_blacklist.command(name="remove")
    async def fm_blacklist_remove(self, ctx: commands.Context, *, member: discord.Member):
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
        await util.send_success(ctx, f"{member.mention} is no longer blacklisted.")

    @fm.command()
    async def set(self, ctx: commands.Context, username):
        """Save your Last.fm username"""
        if ctx.foreign_target:  # type: ignore
            raise exceptions.CommandWarning("You cannot set Last.fm username for someone else!")

        content = await self.get_userinfo_embed(username)
        if content is None:
            raise exceptions.CommandWarning(f"Last.fm profile `{username}` was not found")

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
    async def unset(self, ctx: commands.Context):
        """Unlink your Last.fm"""
        if ctx.foreign_target:  # type: ignore
            raise exceptions.CommandWarning("You cannot unset someone else's Last.fm username!")

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
    async def profile(self, ctx: commands.Context):
        """See your Last.fm profile"""
        content = await self.get_userinfo_embed(ctx.username)
        if content is None:
            raise exceptions.CommandError(f"Could not get your lastfm profile (`{ctx.username}`)")
        await ctx.send(embed=content)  # type: ignore

    @fm.command()
    async def milestone(self, ctx: commands.Context, n: int):
        """See what your n:th scrobble was"""
        n_display = util.ordinal(n)
        if n < 1:
            raise exceptions.CommandWarning(
                "Please give a number between 1 and your total amount of listened tracks."
            )
        per_page = 100
        pre_data = await self.api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": per_page}  # type: ignore
        )

        total = int(pre_data["recenttracks"]["@attr"]["total"])
        if n > total:
            raise exceptions.CommandWarning(
                f"You have only listened to **{total}** tracks! Unable to show {n_display} track"
            )

        remainder = total % per_page
        total_pages = int(pre_data["recenttracks"]["@attr"]["totalPages"])
        if n > remainder:
            n -= remainder
            containing_page = total_pages - math.ceil(n / per_page)
        else:
            containing_page = total_pages

        final_data = await self.api_request(
            {
                "user": ctx.username,  # type: ignore
                "method": "user.getrecenttracks",
                "limit": per_page,
                "page": containing_page,
            }
        )

        # if user is playing something, the current nowplaying song will be appended to the list at index 101
        # cap to 100 first items after reversing to remove it
        tracks = list(reversed(final_data["recenttracks"]["track"]))[:100]
        nth_track = tracks[(n % 100) - 1]
        await ctx.send(
            f"Your {n_display} scrobble was ***{nth_track['name']}*** by **{nth_track['artist']['#text']}**"
        )

    @fm.command(aliases=["yt"])
    async def youtube(self, ctx: commands.Context):
        """See your current song on youtube"""
        data = await self.api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}  # type: ignore
        )

        tracks = data["recenttracks"]["track"]

        if not tracks:
            raise exceptions.CommandInfo("You have not listened to anything yet!")

        username = data["recenttracks"]["@attr"]["user"]
        artist = tracks[0]["artist"]["#text"]
        track = tracks[0]["name"]

        state = "Most recent track"
        track_attr = tracks[0].get("@attr")
        if track_attr is not None and "nowplaying" in track_attr:
            state = "Now Playing"

        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "type": "video",
            "maxResults": 1,
            "q": f"{artist} {track}",
            "key": self.bot.keychain.GCS_DEVELOPER_KEY,
        }

        async with self.bot.session.get(url, params=params) as response:
            data = await response.json(loads=orjson.loads)

        video_id = data["items"][0]["id"]["videoId"]
        video_url = f"https://youtube.com/watch?v={video_id}"

        await ctx.send(f"**{username} — {state}** :cd:\n{video_url}")

    @fm.group()
    async def voting(self, ctx: commands.Context):
        """Configure nowplaying voting reactions"""
        await util.command_group_help(ctx)

    @voting.command(name="enabled")
    async def voting_enabled(self, ctx: commands.Context, value: bool):
        """Toggle whether the voting is enabled for you or not"""
        await self.bot.db.execute(
            """
            INSERT INTO lastfm_vote_setting (user_id, is_enabled)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                is_enabled = VALUES(is_enabled)
            """,
            ctx.author.id,
            value,
        )
        await util.send_success(
            ctx,
            f"Nowplaying reactions for your messages turned **{'on' if value else 'off'}**",
        )

    @voting.command(name="upvote")
    @util.patrons_only()
    async def voting_upvote(self, ctx: commands.Context, emoji):
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
    async def voting_downvote(self, ctx: commands.Context, emoji):
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

    @fm.command(aliases=["np", "no"])
    async def nowplaying(self, ctx: commands.Context):
        """See your currently playing song"""
        data = await self.api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}  # type: ignore
        )

        tracks = data["recenttracks"]["track"]

        if not tracks:
            raise exceptions.CommandInfo("You have not listened to anything yet!")

        artist = tracks[0]["artist"]["#text"]
        album = tracks[0]["album"]["#text"]
        track = tracks[0]["name"]
        image_url = tracks[0]["image"][-1]["#text"]

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.description = f":cd: **{discord.utils.escape_markdown(album)}**"
        content.title = f"**{discord.utils.escape_markdown(artist)} — *{discord.utils.escape_markdown(track)}* **"
        content.set_thumbnail(url=image_url)

        # tags and playcount
        trackdata = await self.api_request(
            {
                "user": ctx.username,  # type: ignore
                "method": "track.getInfo",
                "artist": artist,
                "track": track,
            },
            ignore_errors=True,
        )
        if trackdata is not None:
            tags = []
            try:
                trackdata = trackdata["track"]
                playcount = int(trackdata["userplaycount"])
                if playcount > 0:
                    content.description += f"\n> {playcount} {format_plays(playcount)}"
                tags.extend(tag["name"] for tag in trackdata["toptags"]["tag"])
                content.set_footer(text=", ".join(tags))
            except (KeyError, TypeError):
                pass

        # play state
        np = "@attr" in tracks[0] and "nowplaying" in tracks[0]["@attr"]
        state = "> Now Playing" if np else "II Last track"
        if not np:
            content.timestamp = arrow.get(int(tracks[0]["date"]["uts"])).datetime

        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} {state}",
            icon_url=ctx.usertarget.display_avatar.url,
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

    @fm.command(aliases=["ta"], usage="[timeframe] [amount]")
    async def topartists(self, ctx: commands.Context, *args):
        """See your most listened to artists"""
        arguments = parse_arguments(args)
        if arguments["period"] == "today":
            data = await self.custom_period(ctx.username, "artist")
        else:
            data = await self.api_request(
                {
                    "user": ctx.username,  # type: ignore
                    "method": "user.gettopartists",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                }
            )
        user_attr = data["topartists"]["@attr"]
        artists = data["topartists"]["artist"][: arguments["amount"]]

        if not artists:
            raise exceptions.CommandInfo("You have not listened to anything yet!")

        rows = []
        for i, artist in enumerate(artists, start=1):
            name = discord.utils.escape_markdown(artist["name"])
            plays = artist["playcount"]
            rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} : **{name}**")

        image_url = await self.get_artist_image(artists[0]["name"])
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique artists: {user_attr['total']}")
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — {formatted_timeframe} top artists",  # type: ignore
            icon_url=ctx.usertarget.display_avatar.url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["talb"], usage="[timeframe] [amount]")
    async def topalbums(self, ctx: commands.Context, *args):
        """See your most listened to albums"""
        arguments = parse_arguments(args)
        if arguments["period"] == "today":
            data = await self.custom_period(ctx.username, "album")
        else:
            data = await self.api_request(
                {
                    "user": ctx.username,
                    "method": "user.gettopalbums",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                }
            )
        user_attr = data["topalbums"]["@attr"]
        albums = data["topalbums"]["album"][: arguments["amount"]]

        if not albums:
            raise exceptions.CommandInfo("You have not listened to anything yet!")

        rows = []
        for i, album in enumerate(albums, start=1):
            name = discord.utils.escape_markdown(album["name"])
            artist_name = discord.utils.escape_markdown(album["artist"]["name"])
            plays = album["playcount"]
            rows.append(
                f"`#{i:2}` **{plays}** {format_plays(plays)} : **{artist_name}** — ***{name}***"
            )

        image_url = albums[0]["image"][-1]["#text"]
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — {formatted_timeframe} top albums",
            icon_url=ctx.usertarget.display_avatar.url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["tt"], usage="[timeframe] [amount]")
    async def toptracks(self, ctx: commands.Context, *args):
        """See your most listened to tracks"""
        arguments = parse_arguments(args)
        if arguments["period"] == "today":
            data = await self.custom_period(ctx.username, "track")
        else:
            data = await self.api_request(
                {
                    "user": ctx.username,
                    "method": "user.gettoptracks",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                }
            )
        user_attr = data["toptracks"]["@attr"]
        tracks = data["toptracks"]["track"][: arguments["amount"]]

        if not tracks:
            raise exceptions.CommandInfo("You have not listened to anything yet!")

        image_url = await self.get_artist_image(tracks[0]["artist"]["name"])
        rows = []
        for i, track in enumerate(tracks, start=1):
            name = discord.utils.escape_markdown(track["name"])
            artist_name = discord.utils.escape_markdown(track["artist"]["name"])
            plays = track["playcount"]
            rows.append(
                f"`#{i:2}` **{plays}** {format_plays(plays)} : **{artist_name}** — ***{name}***"
            )

        formatted_timeframe = humanized_period(arguments["period"]).capitalize()

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — {formatted_timeframe} top tracks",
            icon_url=ctx.usertarget.display_avatar.url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["recents", "re"])
    async def recent(self, ctx: commands.Context, size: int = 15):
        """Get your recently listened to tracks"""
        size = abs(size)
        data = await self.api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": size}
        )
        user_attr = data["recenttracks"]["@attr"]
        tracks = data["recenttracks"]["track"][:size]

        if not tracks:
            raise exceptions.CommandInfo("You have not listened to anything yet!")

        rows = []
        for track in tracks:
            name = discord.utils.escape_markdown(track["name"])
            artist_name = discord.utils.escape_markdown(track["artist"]["#text"])
            rows.append(f"**{artist_name}** — ***{name}***")

        image_url = tracks[0]["image"][-1]["#text"]

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — Recent tracks",
            icon_url=ctx.usertarget.display_avatar.url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(usage="[timeframe] <toptracks | topartists | topalbums> <artist>")
    async def artist(self, ctx: commands.Context, timeframe, datatype, *, artistname=""):
        """
        Artist specific data.

        Usage:
            >fm artist [timeframe] toptracks <artist name>
            >fm artist [timeframe] topalbums <artist name>
            >fm artist [timeframe] overview  <artist name>
        """
        period = get_period(timeframe)
        if period in [None, "today"]:
            artistname = " ".join([datatype, artistname]).strip()
            datatype = timeframe
            period = "overall"

        artistname = remove_mentions(artistname)
        if artistname.lower() == "np":
            artistname = (await self.getnowplaying(ctx))["artist"]
            if artistname is None:
                raise exceptions.CommandWarning("Could not get currently playing artist!")

        if artistname == "":
            return await ctx.send("Missing artist name!")

        if datatype in ["toptracks", "tt", "tracks", "track"]:
            datatype = "tracks"

        elif datatype in ["topalbums", "talb", "albums", "album"]:
            datatype = "albums"

        elif datatype in ["overview", "stats", "ov"]:
            return await self.artist_overview(ctx, period, artistname)

        else:
            return await util.send_command_help(ctx)

        artist, data = await self.artist_top(ctx, period, artistname, datatype)
        if artist is None or not data:
            artistname = discord.utils.escape_markdown(artistname)
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            return await ctx.send(
                f"You have not listened to **{artistname}** in the past {period}s!"
            )

        total = 0
        rows = []
        for i, (name, playcount) in enumerate(data, start=1):
            rows.append(
                f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{discord.utils.escape_markdown(name)}**"
            )
            total += playcount

        artistname = urllib.parse.quote_plus(artistname)
        content = discord.Embed()
        content.set_thumbnail(url=artist["image_url"])
        content.colour = await self.cached_image_color(artist["image_url"])
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + f"Top {datatype} by {artist['formatted_name']}",
            icon_url=ctx.usertarget.display_avatar.url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"+{datatype}?date_preset={period_http_format(period)}",
        )
        content.set_footer(
            text=f"Total {total} {format_plays(total)} across {len(rows)} {datatype}"
        )

        await util.send_as_pages(ctx, content, rows)

    @fm.command(name="cover")
    async def cover(self, ctx: commands.Context):
        """See the full album cover of your current song"""
        data = await self.api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}
        )
        image_url = data["recenttracks"]["track"][0]["image"][-1]["#text"]
        image_hash = image_url.split("/")[-1].split(".")[0]
        big_image_url = self.cover_base_urls[4].format(image_hash)
        artist_name = data["recenttracks"]["track"][0]["artist"]["#text"]
        album_name = data["recenttracks"]["track"][0]["album"]["#text"]

        async with self.bot.session.get(big_image_url) as response:
            buffer = io.BytesIO(await response.read())
            await ctx.send(
                f"**{artist_name} — {album_name}**",
                file=discord.File(fp=buffer, filename=f"{image_hash}.jpg"),
            )

    @fm.command(name="album")
    async def album(self, ctx: commands.Context, *, album):
        """Get your top tracks from an album"""
        period = "overall"
        if album is None:
            return await util.send_command_help(ctx)

        album = remove_mentions(album)
        if album.lower() == "np":
            npd = await self.getnowplaying(ctx)
            albumname = npd["album"]
            artistname = npd["artist"]
            if None in [albumname, artistname]:
                raise exceptions.CommandWarning("Could not get currently playing album!")
        else:
            try:
                albumname, artistname = [x.strip() for x in album.split("|")]
                if "" in (albumname, artistname):
                    raise ValueError
            except ValueError:
                raise exceptions.CommandWarning("Incorrect format! use `album | artist`")

        album, data = await self.album_top_tracks(ctx, period, artistname, albumname)
        if album is None or not data:
            if period == "overall":
                return await ctx.send(
                    f"You have never listened to **{albumname}** by **{artistname}**!"
                )
            return await ctx.send(
                f"You have not listened to **{albumname}** by **{artistname}** in the past {period}s!"
            )

        artistname = album["artist"]
        albumname = album["formatted_name"]

        total_plays = 0
        rows = []
        for i, (name, playcount) in enumerate(data, start=1):
            total_plays += playcount
            rows.append(
                f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{discord.utils.escape_markdown(name)}**"
            )

        titlestring = f"top tracks from {albumname}\n— by {artistname}"
        artistname = urllib.parse.quote_plus(artistname)
        albumname = urllib.parse.quote_plus(albumname)
        content = discord.Embed()
        content.set_thumbnail(url=album["image_url"])
        content.set_footer(text=f"Total album plays: {total_plays}")
        content.colour = await self.cached_image_color(album["image_url"])
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + titlestring,
            icon_url=ctx.usertarget.display_avatar.url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"{albumname}?date_preset={period_http_format(period)}",
        )

        await util.send_as_pages(ctx, content, rows)

    async def album_top_tracks(self, ctx: commands.Context, period, artistname, albumname):
        """Scrape the top tracks of given album from lastfm library page"""
        artistname = urllib.parse.quote_plus(artistname)
        albumname = urllib.parse.quote_plus(albumname)
        url = (
            f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"{albumname}?date_preset={period_http_format(period)}"
        )
        data, error = await fetch_html(self.bot, url)
        if error:
            raise exceptions.LastFMError(404, "Album page not found")

        soup = BeautifulSoup(data, "lxml")

        album = {
            "image_url": soup.find("header", {"class": "library-header"})
            .find("img")
            .get("src")
            .replace("64s", "300s"),
            "formatted_name": soup.find("h2", {"class": "library-header-title"}).text.strip(),
            "artist": soup.find("header", {"class": "library-header"})
            .find("a", {"class": "text-colour-link"})
            .text.strip(),
        }

        all_results = get_list_contents(soup)
        all_results += await get_additional_pages(self.bot, soup, url)

        return album, all_results

    async def artist_top(self, ctx: commands.Context, period, artistname, datatype):
        """Scrape either top tracks or top albums from lastfm library page"""
        artistname = urllib.parse.quote_plus(artistname)
        url = (
            f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"+{datatype}?date_preset={period_http_format(period)}"
        )
        data, error = await fetch_html(self.bot, url)
        if error:
            raise exceptions.LastFMError(404, "Artist page not found")

        soup = BeautifulSoup(data, "lxml")

        artist = {
            "image_url": soup.find("span", {"class": "library-header-image"})
            .find("img")
            .get("src")
            .replace("avatar70s", "avatar300s"),
            "formatted_name": soup.find("a", {"class": "library-header-crumb"}).text.strip(),
        }

        all_results = get_list_contents(soup)
        all_results += await get_additional_pages(self.bot, soup, url)

        return artist, all_results

    async def artist_overview(self, ctx: commands.Context, period, artistname):
        """Overall artist view"""
        albums = []
        tracks = []
        metadata = [None, None, None]
        artistinfo = await self.api_request({"method": "artist.getInfo", "artist": artistname})
        url = (
            f"https://last.fm/user/{ctx.username}/library/music/"
            f"{urllib.parse.quote_plus(artistname)}"
            f"?date_preset={period_http_format(period)}"
        )
        data, error = await fetch_html(self.bot, url)
        if error:
            raise exceptions.LastFMError(404, "Artist page not found")

        soup = BeautifulSoup(data, "lxml")
        try:
            albumsdiv, tracksdiv, _ = soup.findAll("tbody", {"data-playlisting-add-entries": ""})

        except ValueError:
            artistname = discord.utils.escape_markdown(artistname)
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            return await ctx.send(
                f"You have not listened to **{artistname}** in the past {period}s!"
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

        metadata_list = soup.find("ul", {"class": "metadata-list"})
        for i, metadata_item in enumerate(
            metadata_list.findAll("p", {"class": "metadata-display"})
        ):
            metadata[i] = int(metadata_item.text.replace(",", ""))

        artist = {
            "image_url": soup.find("span", {"class": "library-header-image"})
            .find("img")
            .get("src")
            .replace("avatar70s", "avatar300s"),
            "formatted_name": soup.find("h2", {"class": "library-header-title"}).text.strip(),
        }

        artistname = urllib.parse.quote_plus(artistname)
        listeners = artistinfo["artist"]["stats"]["listeners"]
        globalscrobbles = artistinfo["artist"]["stats"]["playcount"]
        similar = [a["name"] for a in artistinfo["artist"]["similar"]["artist"]]
        tags = [t["name"] for t in artistinfo["artist"]["tags"]["tag"]]

        content = discord.Embed()
        content.set_thumbnail(url=artist["image_url"])
        content.colour = await self.cached_image_color(artist["image_url"])
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — {artist['formatted_name']} "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + "Overview",
            icon_url=ctx.usertarget.display_avatar.url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}"
            f"?date_preset={period_http_format(period)}",
        )

        content.set_footer(text=f"{', '.join(tags)}")

        crown_holder = await self.bot.db.fetch_value(
            """
            SELECT user_id FROM artist_crown WHERE guild_id = %s AND artist_name = %s
            """,
            ctx.guild.id,
            artist["formatted_name"],
        )

        crownstate = " :crown:" if crown_holder == ctx.usertarget.id else ""
        scrobbles, albums_count, tracks_count = metadata
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

    async def fetch_color(self, session, album_art_id):
        async def get_image(url):
            async with session.get(url) as response:
                try:
                    return Image.open(io.BytesIO(await response.read()))
                except Exception:
                    return None

        image = None
        for base_url in self.cover_base_urls:
            image = await get_image(base_url.format(album_art_id))
            if image is not None:
                break

        if image is None:
            return None

        colors = await self.bot.loop.run_in_executor(None, lambda: colorgram.extract(image, 1))
        dominant_color = colors[0].rgb

        return (
            album_art_id,
            dominant_color.r,
            dominant_color.g,
            dominant_color.b,
            util.rgb_to_hex(dominant_color),
        )

    async def get_all_albums(self, username):
        params = {
            "user": username,
            "method": "user.gettopalbums",
            "period": "overall",
            "limit": 500,  # 1000 doesnt work due to lastfm bug
        }
        data = await self.api_request(dict(params, **{"page": 1}))
        topalbums = data["topalbums"]["album"]
        total_pages = int(data["topalbums"]["@attr"]["totalPages"])

        # get additional page if exists for a total of 1000
        if total_pages > 1:
            data = await self.api_request(dict(params, **{"page": 2}))
            topalbums += data["topalbums"]["album"]

        return topalbums

    @fm.command(aliases=["colourchart"])
    async def colorchart(self, ctx: commands.Context, colour, size="3x3"):
        """
        Collage based on colors.

        Usage:
            >fm colorchart #<hex color> [NxN]
            >fm colorchart rainbow
            >fm colorchart rainbowdiagonal
        """
        rainbow = colour.lower() in ["rainbow", "rainbowdiagonal"]
        diagonal = colour.lower() == "rainbowdiagonal"
        if not rainbow:
            max_size = 30
            try:
                colour = discord.Color(value=int(colour.strip("#"), 16))
                query_color = colour.to_rgb()
            except ValueError:
                raise exceptions.CommandWarning(f"`{colour}` is not a valid hex colour")

            dim = size.split("x")
            width = int(dim[0])
            height = abs(int(dim[1])) if len(dim) > 1 else abs(int(dim[0]))
            if width + height > max_size:
                raise exceptions.CommandInfo(
                    f"Size is too big! Chart `width` + `height` total must not exceed `{max_size}`"
                )
        else:
            width = 7
            height = 7

        topalbums = await self.get_all_albums(ctx.username)

        albums = set()
        album_color_nodes = []
        for album in topalbums:
            album_art_id = album["image"][0]["#text"].split("/")[-1].split(".")[0]
            if album_art_id.strip() == "":
                continue

            albums.add(album_art_id)

        if not albums:
            raise exceptions.CommandError("There was an unknown error while getting your albums!")

        to_fetch = []
        albumcolors = await self.bot.db.fetch(
            """
            SELECT image_hash, r, g, b FROM image_color_cache WHERE image_hash IN %s
            """,
            tuple(albums),
        )
        albumcolors_dict = {}
        if albumcolors:
            for image_hash, r, g, b in albumcolors:
                albumcolors_dict[image_hash] = (r, g, b)
        warn = None

        for image_id in albums:
            color = albumcolors_dict.get(image_id)
            if color is None:
                to_fetch.append(image_id)
            else:
                album_color_nodes.append(AlbumColorNode(color, image_id))

        if to_fetch:
            to_cache = []
            tasks = [self.fetch_color(self.bot.session, image_id) for image_id in to_fetch]
            if len(tasks) > 500:
                warn = await ctx.send(
                    ":exclamation:Your library includes over 500 uncached album colours, "
                    f"this might take a while {emojis.LOADING}"
                )

            colordata = await asyncio.gather(*tasks)
            for colortuple in colordata:
                if colortuple is None:
                    continue
                image_hash, r, g, b, hexcolor = colortuple
                to_cache.append((image_hash, r, g, b, hexcolor))
                album_color_nodes.append(AlbumColorNode((r, g, b), image_hash))

            await self.bot.db.executemany(
                "INSERT IGNORE image_color_cache (image_hash, r, g, b, hex) VALUES (%s, %s, %s, %s, %s)",
                to_cache,
            )

        tree = kdtree.create(album_color_nodes)
        if rainbow:
            rainbow_colors = (
                [
                    (255, 79, 0),
                    (255, 33, 0),
                    (217, 29, 82),
                    (151, 27, 147),
                    (81, 35, 205),
                    (0, 48, 255),
                    (0, 147, 147),
                    (0, 249, 0),
                    (203, 250, 0),
                    (255, 251, 0),
                    (255, 200, 0),
                    (255, 148, 0),
                ]
                if diagonal
                else [
                    (255, 0, 0),  # red
                    (255, 127, 0),  # orange
                    (255, 255, 0),  # yellow
                    (0, 255, 0),  # green
                    (0, 0, 255),  # blue
                    (75, 0, 130),  # purple
                    (148, 0, 211),  # violet
                ]
            )
            chunks = [list(tree.search_knn(rgb, width + height)) for rgb in rainbow_colors]
            random_offset = random.randint(0, 6)
            final_albums = []
            for album_index in range(width * height):
                if diagonal:
                    choice_index = (
                        album_index % width + (album_index // height) + random_offset
                    ) % len(chunks)
                else:
                    choice_index = album_index % width

                choose_from = chunks[choice_index]
                choice = choose_from[album_index // height]
                final_albums.append(
                    (
                        self.cover_base_urls[3].format(choice[0].data.data),
                        f"rgb{choice[0].data.rgb}, dist {choice[1]:.2f}",
                    )
                )

        else:
            nearest = tree.search_knn(query_color, width * height)

            final_albums = [
                (
                    self.cover_base_urls[3].format(alb[0].data.data),
                    f"rgb{alb[0].data.rgb}, dist {alb[1]:.2f}",
                )
                for alb in nearest
            ]

        buffer = await self.chart_factory(final_albums, width, height, show_labels=False)

        if rainbow:
            colour = f"{'diagonal ' if diagonal else ''}rainbow"

        await ctx.send(
            f"`{util.displayname(ctx.usertarget)} {colour} album chart"
            + (f" | {len(to_fetch)} new`" if to_fetch else "`"),
            file=discord.File(
                fp=buffer,
                filename=f"fmcolorchart_{ctx.username}_{str(colour).strip('#').replace(' ', '_')}.jpeg",
            ),
        )

        if warn is not None:
            await warn.delete()

    @fm.command(aliases=["collage"], usage="[album | artist] [timeframe] [size] 'notitle'")
    async def chart(self, ctx: commands.Context, *args):
        """
        Collage of your top albums or artists

        Usage:
            >fm chart [album | artist] [timeframe] [width]x[height] [notitle]
        """
        arguments = parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 30:
            raise exceptions.CommandInfo(
                "Size is too big! Chart `width` + `height` total must not exceed `30`"
            )

        if arguments["period"] == "today":
            data = await self.custom_period(ctx.username, arguments["method"])
        else:
            data = await self.api_request(
                {
                    "user": ctx.username,
                    "method": arguments["method"],
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                }
            )
        chart = []
        chart_type = "ERROR"
        if arguments["method"] == "user.gettopalbums":
            chart_type = "top album"
            albums = data["topalbums"]["album"]
            for album in albums:
                name = album["name"]
                artist = album["artist"]["name"]
                plays = album["playcount"]
                chart.append(
                    (
                        album["image"][3]["#text"],
                        f"{plays} {format_plays(plays)}<br>" f"{name} — {artist}",
                    )
                )

        elif arguments["method"] == "user.gettopartists":
            chart_type = "top artist"
            artists = data["topartists"]["artist"]
            scraped_images = await self.scrape_artists_for_chart(
                ctx.username, arguments["period"], arguments["amount"]
            )
            for i, artist in enumerate(artists):
                name = artist["name"]
                plays = artist["playcount"]
                chart.append((scraped_images[i], f"{plays} {format_plays(plays)}<br>{name}"))

        elif arguments["method"] == "user.getrecenttracks":
            chart_type = "recent tracks"
            tracks = data["recenttracks"]["track"]
            for track in tracks:
                name = track["name"]
                artist = track["artist"]["#text"]
                chart.append((track["image"][3]["#text"], f"{name} — {artist}"))

        buffer = await self.chart_factory(
            chart,
            arguments["width"],
            arguments["height"],
            show_labels=arguments["showtitles"],
        )

        await ctx.send(
            f"`{util.displayname(ctx.usertarget, escape=False)} {humanized_period(arguments['period'])} "
            f"{arguments['width']}x{arguments['height']} {chart_type} chart`",
            file=discord.File(
                fp=buffer, filename=f"fmchart_{ctx.username}_{arguments['period']}.jpeg"
            ),
        )

    async def chart_factory(self, chart_items, width, height, show_labels=True):
        if show_labels:
            img_div_template = '<div class="art"><img src="{0}"><p class="label">{1}</p></div>'
        else:
            img_div_template = '<div class="art"><img src="{0}"></div>'

        img_divs = "\n".join(img_div_template.format(*chart_item) for chart_item in chart_items)

        replacements = {
            "WIDTH": 300 * width,
            "HEIGHT": 300 * height,
            "CHART_ITEMS": img_divs,
        }

        payload = {
            "html": util.format_html(self.chart_html, replacements),
            "width": 300 * width,
            "height": 300 * height,
            "imageFormat": "jpeg",
        }

        return await util.render_html(self.bot, payload)

    async def server_lastfm_usernames(self, ctx: commands.Context, filter_blacklisted=False):
        guild_user_ids = [user.id for user in ctx.guild.members]
        args = [guild_user_ids]
        if filter_blacklisted:
            args.append(ctx.guild.id)
        data = await self.bot.db.fetch(
            """
            SELECT user_id, lastfm_username FROM user_settings WHERE user_id IN %s
            AND lastfm_username IS NOT NULL
            """
            + (
                " AND user_id not in (SELECT user_id FROM lastfm_blacklist WHERE guild_id = %s)"
                if filter_blacklisted
                else ""
            ),
            *args,
        )
        return data or []

    @fm.group(aliases=["s", "guild"])
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def server(self, ctx: commands.Context):
        """Server wide Last.Fm statistics"""
        await util.command_group_help(ctx)

    @server.command(
        name="chart", aliases=["collage"], usage="[album | artist] [timeframe] [size] 'notitle'"
    )
    async def server_chart(self, ctx: commands.Context, *args):
        """
        Collage of the server's top albums or artists

        Usage:
            >fm server chart [album | artist] [timeframe] [width]x[height] [notitle]
        """
        arguments = parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 30:
            raise exceptions.CommandInfo(
                "Size is too big! Chart `width` + `height` total must not exceed `30`"
            )

        chart_total = arguments["width"] * arguments["height"]

        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(
                self.get_server_top(
                    lastfm_username,
                    "album" if arguments["method"] == "user.gettopalbums" else "artist",
                    period=arguments["period"],
                )
            )

        chart_type = "ERROR"
        content_map = {}
        if not tasks:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        data = await asyncio.gather(*tasks)
        chart = []

        if arguments["method"] == "user.gettopalbums":
            chart_type = "top album"
            for user_data in data:
                if user_data is None:
                    continue
                for album in user_data:
                    album_name = album["name"]
                    artist = album["artist"]["name"]
                    name = f"{album_name} — {artist}"
                    plays = int(album["playcount"])
                    if name in content_map:
                        content_map[name]["plays"] += plays
                    else:
                        content_map[name] = {"plays": plays, "image": album["image"][3]["#text"]}

        elif arguments["method"] == "user.gettopartists":
            chart_type = "top artist"
            for user_data in data:
                if user_data is None:
                    continue
                for artist in user_data:
                    name = artist["name"]
                    plays = int(artist["playcount"])
                    if name in content_map:
                        content_map[name]["plays"] += plays
                    else:
                        content_map[name] = {"plays": plays, "image": None}

        for i, (name, content_data) in enumerate(
            sorted(content_map.items(), key=lambda x: x[1]["plays"], reverse=True),
            start=1,
        ):
            chart.append(
                (
                    content_data["image"]
                    if chart_type == "top album"
                    else await self.get_artist_image(name),
                    f"{content_data['plays']} {format_plays(content_data['plays'])}<br>{name}",
                )
            )
            if i >= chart_total:
                break

        buffer = await self.chart_factory(
            chart,
            arguments["width"],
            arguments["height"],
            show_labels=arguments["showtitles"],
        )

        await ctx.send(
            f"`{ctx.guild} {humanized_period(arguments['period'])} "
            f"{arguments['width']}x{arguments['height']} {chart_type} chart`",
            file=discord.File(
                fp=buffer, filename=f"fmchart_{ctx.guild}_{arguments['period']}.jpeg"
            ),
        )

    @server.command(name="nowplaying", aliases=["np"])
    async def server_nowplaying(self, ctx: commands.Context):
        """What this server is currently listening to"""
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(ctx):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_np(lastfm_username, member))

        total_linked = len(tasks)
        if not tasks:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        data = await asyncio.gather(*tasks)
        listeners = [(song, member_ref) for song, member_ref in data if song is not None]
        if not listeners:
            return await ctx.send("Nobody on this server is listening to anything at the moment!")

        total_listening = len(listeners)
        maxlen = 0
        for song, member in listeners:
            dn = util.displayname(member)
            if len(dn) > maxlen:
                maxlen = len(dn)

        rows = [
            f"{util.displayname(member)} | **{discord.utils.escape_markdown(song.get('artist'))}** — ***{discord.utils.escape_markdown(song.get('name'))}***"
            for song, member in listeners
        ]
        content = discord.Embed()
        content.set_author(
            name=f"What is {ctx.guild.name} listening to?",
            icon_url=ctx.guild.icon,
        )
        if ctx.guild.icon:
            content.colour = int(
                await util.color_from_image_url(self.bot.session, str(ctx.guild.icon)),
                16,
            )
        content.set_footer(
            text=f"{total_listening} / {total_linked} Members are listening to music"
        )
        await util.send_as_pages(ctx, content, rows)

    @server.command(name="recent", aliases=["re"])
    async def server_recent(self, ctx: commands.Context):
        """What this server has recently listened to"""
        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(ctx):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_lastplayed(lastfm_username, member))

        total_linked = len(tasks)
        total_listening = 0
        if tasks:
            data = await asyncio.gather(*tasks)
            for song, member_ref in data:
                if song is not None:
                    if song.get("nowplaying"):
                        total_listening += 1
                    listeners.append((song, member_ref))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        if not listeners:
            return await ctx.send("Nobody on this server is listening to anything at the moment!")

        listeners = sorted(listeners, key=lambda listener: listener[0].get("date"), reverse=True)
        rows = []
        for song, member in listeners:
            suffix = ""
            if song.get("nowplaying"):
                suffix = ":musical_note: "
            else:
                suffix = f"({arrow.get(song.get('date')).humanize()})"

            rows.append(
                f"{util.displayname(member)} | **{discord.utils.escape_markdown(song.get('artist'))}** — ***{discord.utils.escape_markdown(song.get('name'))}*** {suffix}"
            )

        content = discord.Embed()
        content.set_author(
            name=f"What has {ctx.guild.name} been listening to?",
            icon_url=ctx.guild.icon,
        )
        if ctx.guild.icon:
            content.colour = int(
                await util.color_from_image_url(self.bot.session, str(ctx.guild.icon)),
                16,
            )
        content.set_footer(
            text=f"{total_listening} / {total_linked} Members are listening to music right now"
        )
        await util.send_as_pages(ctx, content, rows)

    @server.command(name="topartists", aliases=["ta"], usage="[timeframe]")
    async def server_topartists(self, ctx: commands.Context, *args):
        """Combined top artists of server members"""
        artist_map = {}
        tasks = []
        total_users = 0
        total_plays = 0
        arguments = parse_arguments(args)
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_server_top(lastfm_username, "artist", period=arguments["period"]))

        if tasks:
            data = await asyncio.gather(*tasks)
            for user_data in data:
                if user_data is None:
                    continue
                total_users += 1
                for data_block in user_data:
                    name = data_block["name"]
                    plays = int(data_block["playcount"])
                    total_plays += plays
                    if name in artist_map:
                        artist_map[name] += plays
                    else:
                        artist_map[name] = plays
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        rows = []
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()
        content = discord.Embed()
        content.set_author(
            name=f"{ctx.guild} — {formatted_timeframe} top artists",
            icon_url=ctx.guild.icon,
        )
        content.set_footer(text=f"Taking into account top 100 artists of {total_users} members")
        for i, (artistname, playcount) in enumerate(
            sorted(artist_map.items(), key=lambda x: x[1], reverse=True), start=1
        ):
            if i == 1:
                image_url = await self.get_artist_image(artistname)
                content.colour = await self.cached_image_color(image_url)
                content.set_thumbnail(url=image_url)

            rows.append(
                f"`#{i:2}` **{playcount}** {format_plays(playcount)} : **{discord.utils.escape_markdown(artistname)}**"
            )

        await util.send_as_pages(ctx, content, rows, 15)

    @server.command(name="topalbums", aliases=["talb"], usage="[timeframe]")
    async def server_topalbums(self, ctx: commands.Context, *args):
        """Combined top albums of server members"""
        album_map = {}
        tasks = []
        total_users = 0
        total_plays = 0
        arguments = parse_arguments(args)
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_server_top(lastfm_username, "album", period=arguments["period"]))

        if tasks:
            data = await asyncio.gather(*tasks)
            for user_data in data:
                if user_data is None:
                    continue
                total_users += 1
                for data_block in user_data:
                    name = f'{discord.utils.escape_markdown(data_block["artist"]["name"])} — *{discord.utils.escape_markdown(data_block["name"])}*'
                    plays = int(data_block["playcount"])
                    image_url = data_block["image"][-1]["#text"]
                    total_plays += plays
                    if name in album_map:
                        album_map[name]["plays"] += plays
                    else:
                        album_map[name] = {"plays": plays, "image": image_url}
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        rows = []
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()
        content = discord.Embed()
        content.set_author(
            name=f"{ctx.guild} — {formatted_timeframe} top albums",
            icon_url=ctx.guild.icon,
        )
        content.set_footer(text=f"Taking into account top 100 albums of {total_users} members")
        for i, (albumname, albumdata) in enumerate(
            sorted(album_map.items(), key=lambda x: x[1]["plays"], reverse=True),
            start=1,
        ):
            if i == 1:
                image_url = albumdata["image"]
                content.colour = await self.cached_image_color(image_url)
                content.set_thumbnail(url=image_url)

            playcount = albumdata["plays"]
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} : **{albumname}**")

        await util.send_as_pages(ctx, content, rows, 15)

    @server.command(name="toptracks", aliases=["tt"], usage="[timeframe]")
    async def server_toptracks(self, ctx: commands.Context, *args):
        """Combined top tracks of server members"""
        track_map = {}
        tasks = []
        total_users = 0
        total_plays = 0
        arguments = parse_arguments(args)
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_server_top(lastfm_username, "track", period=arguments["period"]))

        if tasks:
            data = await asyncio.gather(*tasks)
            for user_data in data:
                if user_data is None:
                    continue
                total_users += 1
                for data_block in user_data:
                    name = f'{discord.utils.escape_markdown(data_block["artist"]["name"])} — *{discord.utils.escape_markdown(data_block["name"])}*'
                    plays = int(data_block["playcount"])
                    artistname = data_block["artist"]["name"]
                    total_plays += plays
                    if name in track_map:
                        track_map[name]["plays"] += plays
                    else:
                        track_map[name] = {"plays": plays, "artist": artistname}
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        rows = []
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()
        content = discord.Embed()
        content.set_author(
            name=f"{ctx.guild} — {formatted_timeframe} top tracks",
            icon_url=ctx.guild.icon,
        )
        content.set_footer(text=f"Taking into account top 100 tracks of {total_users} members")
        for i, (trackname, trackdata) in enumerate(
            sorted(track_map.items(), key=lambda x: x[1]["plays"], reverse=True),
            start=1,
        ):
            if i == 1:
                image_url = await self.get_artist_image(trackdata["artist"])
                content.colour = await self.cached_image_color(image_url)
                content.set_thumbnail(url=image_url)

            playcount = trackdata["plays"]
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} : **{trackname}**")

        await util.send_as_pages(ctx, content, rows, 15)

    async def get_server_top(self, username, datatype, period="overall"):
        limit = 100
        if datatype == "artist":
            data = await self.api_request(
                {
                    "user": username,
                    "method": "user.gettopartists",
                    "limit": limit,
                    "period": period,
                },
                ignore_errors=True,
            )
            return data["topartists"]["artist"] if data is not None else None
        if datatype == "album":
            data = await self.api_request(
                {
                    "user": username,
                    "method": "user.gettopalbums",
                    "limit": limit,
                    "period": period,
                },
                ignore_errors=True,
            )
            return data["topalbums"]["album"] if data is not None else None
        if datatype == "track":
            data = await self.api_request(
                {
                    "user": username,
                    "method": "user.gettoptracks",
                    "limit": limit,
                    "period": period,
                },
                ignore_errors=True,
            )
            return data["toptracks"]["track"] if data is not None else None

    @commands.command(aliases=["wk", "whomstknows"])
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknows(self, ctx: commands.Context, *, artistname):
        """
        Who has listened to a given artist the most.

        Usage:
            >whoknows <artist name>
            >whoknows np
        """
        artistname = remove_mentions(artistname)
        if artistname.lower() == "np":
            artistname = (await self.getnowplaying(ctx))["artist"]
            if artistname is None:
                raise exceptions.CommandWarning("Could not get currently playing artist!")

        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_playcount(artistname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, member, name in data:
                artistname = name
                if playcount > 0:
                    listeners.append((playcount, member))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = discord.utils.escape_markdown(artistname)

        rows = []
        old_king = None
        new_king = None
        total = 0
        for i, (playcount, member) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            if i == 1:
                rank = ":crown:"
                old_king = await self.bot.db.fetch_value(
                    "SELECT user_id FROM artist_crown WHERE artist_name = %s AND guild_id = %s",
                    artistname,
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
                    member.id,
                    artistname,
                    playcount,
                )
                if old_king:
                    old_king = ctx.guild.get_member(old_king)
                new_king = member
            else:
                rank = f"`#{i:2}`"
            rows.append(
                f"{rank} **{util.displayname(member)}** — **{playcount}** {format_plays(playcount)}"
            )
            total += playcount

        if not rows:
            return await ctx.send(f"Nobody on this server has listened to **{artistname}**")

        content = discord.Embed(title=f"Who knows **{artistname}**?")
        image_url = await self.get_artist_image(artistname)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        content.colour = await self.cached_image_color(image_url)

        await util.send_as_pages(ctx, content, rows)
        if not old_king or old_king is None or old_king.id == new_king.id:
            return

        await ctx.send(
            f"> **{util.displayname(new_king)}** just stole the **{artistname}** crown from **{util.displayname(old_king)}**"
        )

    @commands.command(aliases=["wkt", "whomstknowstrack"], usage="<track> | <artist> 'np'")
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknowstrack(self, ctx: commands.Context, *, track):
        """
        Who has listened to a given song the most.

        Usage:
            >whoknowstrack <track name> | <artist name>
            >whoknowstrack np
        """
        track = remove_mentions(track)
        if track.lower() == "np":
            npd = await self.getnowplaying(ctx)
            trackname = npd["track"]
            artistname = npd["artist"]
            if None in [trackname, artistname]:
                raise exceptions.CommandWarning("Could not get currently playing track!")
        else:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if "" in (trackname, artistname):
                    raise ValueError
            except ValueError:
                raise exceptions.CommandWarning("Incorrect format! use `track | artist`")

        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_playcount_track(artistname, trackname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, metadata in data:
                artistname, trackname, image_url = metadata
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = discord.utils.escape_markdown(artistname)
        trackname = discord.utils.escape_markdown(trackname)

        rows = []
        total = 0
        for i, (playcount, user) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            rows.append(
                f"`#{i:2}` **{util.displayname(user)}** — **{playcount}** {format_plays(playcount)}"
            )
            total += playcount

        if not rows:
            return await ctx.send(
                f"Nobody on this server has listened to **{trackname}** by **{artistname}**"
            )

        if image_url is None:
            image_url = await self.get_artist_image(artistname)

        content = discord.Embed(title=f"Who knows **{trackname}**\n— by {artistname}")
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        content.colour = await self.cached_image_color(image_url)

        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=["wka", "whomstknowsalbum"], usage="<album> | <artist> 'np'")
    @commands.guild_only()
    @is_small_server()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknowsalbum(self, ctx: commands.Context, *, album):
        """
        Who has listened to a given album the most.

        Usage:
            >whoknowsalbum <album name> | <artist name>
            >whoknowsalbum np
        """
        album = remove_mentions(album)
        if album.lower() == "np":
            npd = await self.getnowplaying(ctx)
            albumname = npd["album"]
            artistname = npd["artist"]
            if None in [albumname, artistname]:
                raise exceptions.CommandWarning("Could not get currently playing album!")
        else:
            try:
                albumname, artistname = [x.strip() for x in album.split("|")]
                if "" in (albumname, artistname):
                    raise ValueError
            except ValueError:
                raise exceptions.CommandWarning("Incorrect format! use `album | artist`")

        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_blacklisted=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_playcount_album(artistname, albumname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, metadata in data:
                artistname, albumname, image_url = metadata
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = discord.utils.escape_markdown(artistname)
        albumname = discord.utils.escape_markdown(albumname)

        rows = []
        total = 0
        for i, (playcount, user) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            rows.append(
                f"`#{i:2}` **{util.displayname(user)}** — **{playcount}** {format_plays(playcount)}"
            )
            total += playcount

        if not rows:
            return await ctx.send(
                f"Nobody on this server has listened to **{albumname}** by **{artistname}**"
            )

        if image_url is None:
            image_url = await self.get_artist_image(artistname)

        content = discord.Embed(title=f"Who knows **{albumname}**\n— by {artistname}")
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        content.colour = await self.cached_image_color(image_url)

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    @is_small_server()
    @commands.guild_only()
    async def crowns(self, ctx: commands.Context, *, user: discord.Member = None):
        """See your current artist crowns on this server"""
        if user is None:
            user = ctx.author

        crownartists = await self.bot.db.fetch(
            """
            SELECT artist_name, cached_playcount FROM artist_crown
            WHERE guild_id = %s AND user_id = %s ORDER BY cached_playcount DESC
            """,
            ctx.guild.id,
            user.id,
        )
        if not crownartists:
            return await ctx.send(
                "You haven't acquired any crowns yet! "
                "Use the `>whoknows` command to claim crowns of your favourite artists :crown:"
            )

        rows = []
        for artist, playcount in crownartists:
            rows.append(
                f"**{discord.utils.escape_markdown(str(artist))}** with **{playcount}** {format_plays(playcount)}"
            )

        content = discord.Embed(color=discord.Color.gold())
        content.set_author(
            name=f"👑 {util.displayname(user, escape=False)} artist crowns",
            icon_url=user.display_avatar.url,
        )
        content.set_footer(text=f"Total {len(crownartists)} crowns")
        await util.send_as_pages(ctx, content, rows)

    @util.patrons_only()
    @commands.command(usage="<song> 'np'")
    async def lyrics(self, ctx: commands.Context, *, query):
        """Search for song lyrics"""
        if query.lower() == "np":
            npd = await self.getnowplaying(ctx)
            trackname = npd["track"]
            artistname = npd["artist"]
            if None in [trackname, artistname]:
                return await ctx.send(":warning: Could not get currently playing track!")
            query = artistname + " " + trackname

        genius = Genius(self.bot)
        results = await genius.search(query)
        if not results:
            raise exceptions.CommandWarning(f'Found no lyrics for "{query}"')

        if len(results) > 1:
            picker_content = discord.Embed(title=f"Search results for `{query}`")
            picker_content.set_author(name="Type number to choose result")
            found_titles = []
            for i, result in enumerate(results, start=1):
                found_titles.append(f"`{i}.` {result['full_title']}")

            picker_content.description = "\n".join(found_titles)
            bot_msg = await ctx.send(embed=picker_content)

            def check(message):
                if message.author == ctx.author and message.channel == ctx.channel:
                    try:
                        num = int(message.content)
                    except ValueError:
                        return False
                    else:
                        return num <= len(results) and num > 0
                else:
                    return False

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("number selection timed out")
            else:
                result = results[int(msg.content) - 1]
                await bot_msg.delete()
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass

        else:
            result = results[0]

        lyrics = await genius.scrape_lyrics(result["path"])
        rows = [f'[Lyrics by Genius]({result["url"]})\n']
        for page in lyrics:
            rows += page.strip().split("\n")
        image_color = await util.color_from_image_url(
            self.bot.session, result["song_art_image_thumbnail_url"]
        )
        content = discord.Embed(title=result["full_title"], color=int(image_color, 16))
        content.set_footer(text=f"Released {result['release_date_for_display']}")
        content.set_thumbnail(url=result["song_art_image_url"])
        await util.send_as_pages(ctx, content, rows, maxrows=20)

    async def cached_image_color(self, image_url):
        """Get image color, cache if new"""
        image_hash = image_url.split("/")[-1].split(".")[0]
        cached_color = await self.bot.db.fetch_value(
            "SELECT hex FROM image_color_cache WHERE image_hash = %s",
            image_hash,
        )
        if cached_color:
            return int(cached_color, 16)
        color = await util.rgb_from_image_url(self.bot.session, image_url)
        if color is None:
            return int(self.lastfm_red, 16)

        hex_color = util.rgb_to_hex(color)
        await self.bot.db.execute(
            "INSERT IGNORE image_color_cache (image_hash, r, g, b, hex) VALUES (%s, %s, %s, %s, %s)",
            image_hash,
            color.r,
            color.g,
            color.b,
            hex_color,
        )

        return int(hex_color, 16)

    async def get_userinfo_embed(self, username):
        data = await self.api_request(
            {"user": username, "method": "user.getinfo"}, ignore_errors=True
        )
        if data is None:
            return None

        username = data["user"]["name"]
        blacklisted = await self.bot.db.fetch(
            "SELECT * from lastfm_cheater WHERE lastfm_username = %s", username.lower()
        )
        playcount = data["user"]["playcount"]
        profile_url = data["user"]["url"]
        profile_pic_url = data["user"]["image"][3]["#text"]
        timestamp = arrow.get(int(data["user"]["registered"]["unixtime"]))

        content = discord.Embed(
            title=f"{emojis.LASTFM} {username}"
            + (" `LAST.FM PRO`" if int(data["user"]["subscriber"]) == 1 else "")
        )
        content.add_field(name="Profile", value=f"[Link]({profile_url})", inline=True)
        content.add_field(
            name="Registered",
            value=f"{timestamp.humanize()}\n{timestamp.format('DD/MM/YYYY')}",
            inline=True,
        )
        content.add_field(name="Country", value=data["user"]["country"])
        if profile_pic_url:
            content.set_thumbnail(url=profile_pic_url)
        content.set_footer(text=f"Total plays: {playcount}")
        content.colour = int(self.lastfm_red, 16)
        if blacklisted:
            content.description = ":warning: `This account is flagged as a cheater`"

        return content

    async def listening_report(self, ctx: commands.Context, timeframe):
        current_day_floor = arrow.utcnow().floor("day")
        week = []
        # for i in range(7, 0, -1):
        for i in range(1, 8):
            dt = current_day_floor.shift(days=-i)
            week.append(
                {
                    "dt": dt,
                    "ts": dt.int_timestamp,
                    "ts_to": dt.shift(days=+1, minutes=-1).int_timestamp,
                    "day": dt.format("ddd, MMM Do"),
                    "scrobbles": 0,
                }
            )

        params = {
            "method": "user.getrecenttracks",
            "user": ctx.username,
            "from": week[-1]["ts"],
            "to": current_day_floor.shift(minutes=-1).int_timestamp,
            "limit": 1000,
        }
        content = await self.api_request(params)
        tracks = content["recenttracks"]["track"]

        # get rid of nowplaying track if user is currently scrobbling.
        # for some reason even with from and to parameters it appears
        if tracks[0].get("@attr") is not None:
            tracks = tracks[1:]

        day_counter = 1
        for trackdata in reversed(tracks):
            scrobble_ts = int(trackdata["date"]["uts"])
            if scrobble_ts > week[-day_counter]["ts_to"]:
                day_counter += 1

            week[day_counter - 1]["scrobbles"] += 1

        scrobbles_total = sum(day["scrobbles"] for day in week)
        scrobbles_average = round(scrobbles_total / len(week))

        rows = []
        for day in week:
            rows.append(f"`{day['day']}`: **{day['scrobbles']}** Scrobbles")

        content = discord.Embed(color=int(self.lastfm_red, 16))
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} | LAST.{timeframe.upper()}",
            icon_url=ctx.usertarget.display_avatar.url,
        )
        content.description = "\n".join(rows)
        content.add_field(
            name="Total scrobbles", value=f"{scrobbles_total} Scrobbles", inline=False
        )
        content.add_field(
            name="Avg. daily scrobbles",
            value=f"{scrobbles_average} Scrobbles",
            inline=False,
        )
        # content.add_field(name="Listening time", value=listening_time)
        await ctx.send(embed=content)

    async def get_artist_image(self, artist):
        image_life = 604800  # 1 week
        cached = await self.bot.db.fetch_row(
            "SELECT image_hash, scrape_date FROM artist_image_cache WHERE artist_name = %s",
            artist,
        )

        if cached:
            lifetime = arrow.utcnow().timestamp() - cached[1].timestamp()
            if (lifetime) < image_life:
                return self.cover_base_urls[3].format(cached[0])

        image = await self.scrape_artist_image(artist)
        if image is None:
            return ""
        image_hash = image["src"].split("/")[-1].split(".")[0]
        if image_hash == MISSING_IMAGE_HASH:
            # basic star image, dont save it
            return ""

        await self.bot.db.execute(
            """
            INSERT INTO artist_image_cache (artist_name, image_hash, scrape_date)
                VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                image_hash = VALUES(image_hash),
                scrape_date = VALUES(scrape_date)
            """,
            artist,
            image_hash,
            arrow.now().datetime,
        )
        return self.cover_base_urls[3].format(image_hash)

    async def api_request(self, params, ignore_errors=False):
        """Get json data from the lastfm api"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params["api_key"] = self.bot.keychain.LASTFM_API_KEY
        params["format"] = "json"
        tries = 0
        max_tries = 2
        while True:
            async with self.bot.session.get(url, params=params) as response:
                try:
                    content = await response.json(loads=orjson.loads)
                except aiohttp.ContentTypeError:
                    if ignore_errors:
                        return None
                    text = await response.text()
                    raise exceptions.LastFMError(error_code=response.status, message=text)

                if content is None:
                    raise exceptions.LastFMError(
                        error_code=408,
                        message="Could not connect to LastFM",
                    )
                if response.status == 200 and content.get("error") is None:
                    return content
                if int(content.get("error")) == 8:
                    tries += 1
                    if tries < max_tries:
                        continue

                if ignore_errors:
                    return None
                raise exceptions.LastFMError(
                    error_code=content.get("error"),
                    message=content.get("message"),
                )

    async def custom_period(self, user, group_by, shift_hours=24):
        """Parse recent tracks to get custom duration data (24 hour)"""
        limit_timestamp = arrow.utcnow().shift(hours=-shift_hours)
        data = await self.api_request(
            {
                "user": user,
                "method": "user.getrecenttracks",
                "from": limit_timestamp.int_timestamp,
                "limit": 200,
            }
        )
        loops = int(data["recenttracks"]["@attr"]["totalPages"])
        if loops > 1:
            for i in range(2, loops + 1):
                newdata = await self.api_request(
                    {
                        "user": user,
                        "method": "user.getrecenttracks",
                        "from": limit_timestamp.int_timestamp,
                        "limit": 200,
                        "page": i,
                    }
                )
                data["recenttracks"]["track"] += newdata["recenttracks"]["track"]

        formatted_data = {}
        if group_by in ["album", "user.gettopalbums"]:
            for track in data["recenttracks"]["track"]:
                album_name = track["album"]["#text"]
                artist_name = track["artist"]["#text"]
                if (artist_name, album_name) in formatted_data:
                    formatted_data[(artist_name, album_name)]["playcount"] += 1
                else:
                    formatted_data[(artist_name, album_name)] = {
                        "playcount": 1,
                        "artist": {"name": artist_name},
                        "name": album_name,
                        "image": track["image"],
                    }

            albumsdata = sorted(formatted_data.values(), key=lambda x: x["playcount"], reverse=True)
            return {
                "topalbums": {
                    "album": albumsdata,
                    "@attr": {
                        "user": data["recenttracks"]["@attr"]["user"],
                        "total": len(formatted_data.values()),
                    },
                }
            }

        if group_by in ["track", "user.gettoptracks"]:
            for track in data["recenttracks"]["track"]:
                track_name = track["name"]
                artist_name = track["artist"]["#text"]
                if (track_name, artist_name) in formatted_data:
                    formatted_data[(track_name, artist_name)]["playcount"] += 1
                else:
                    formatted_data[(track_name, artist_name)] = {
                        "playcount": 1,
                        "artist": {"name": artist_name},
                        "name": track_name,
                        "image": track["image"],
                    }

            tracksdata = sorted(formatted_data.values(), key=lambda x: x["playcount"], reverse=True)
            return {
                "toptracks": {
                    "track": tracksdata,
                    "@attr": {
                        "user": data["recenttracks"]["@attr"]["user"],
                        "total": len(formatted_data.values()),
                    },
                }
            }

        if group_by in ["artist", "user.gettopartists"]:
            for track in data["recenttracks"]["track"]:
                artist_name = track["artist"]["#text"]
                if artist_name in formatted_data:
                    formatted_data[artist_name]["playcount"] += 1
                else:
                    formatted_data[artist_name] = {
                        "playcount": 1,
                        "name": artist_name,
                        "image": track["image"],
                    }

            artistdata = sorted(formatted_data.values(), key=lambda x: x["playcount"], reverse=True)
            return {
                "topartists": {
                    "artist": artistdata,
                    "@attr": {
                        "user": data["recenttracks"]["@attr"]["user"],
                        "total": len(formatted_data.values()),
                    },
                }
            }

    async def get_np(self, username, ref):
        data = await self.api_request(
            {"method": "user.getrecenttracks", "user": username, "limit": 1},
            ignore_errors=True,
        )
        song = None
        if data is not None:
            try:
                tracks = data["recenttracks"]["track"]
                if tracks and "@attr" in tracks[0] and "nowplaying" in tracks[0]["@attr"]:
                    song = {
                        "artist": tracks[0]["artist"]["#text"],
                        "name": tracks[0]["name"],
                    }
            except KeyError:
                pass

        return song, ref

    async def get_lastplayed(self, username, ref):
        data = await self.api_request(
            {"method": "user.getrecenttracks", "user": username, "limit": 1},
            ignore_errors=True,
        )
        song = None
        if data is not None:
            try:
                tracks = data["recenttracks"]["track"]
                if tracks:
                    nowplaying = False
                    if tracks[0].get("@attr") and tracks[0]["@attr"].get("nowplaying"):
                        nowplaying = True

                    if tracks[0].get("date"):
                        date = tracks[0]["date"]["uts"]
                    else:
                        date = arrow.utcnow().int_timestamp

                    song = {
                        "artist": tracks[0]["artist"]["#text"],
                        "name": tracks[0]["name"],
                        "nowplaying": nowplaying,
                        "date": int(date),
                    }
            except KeyError:
                pass

        return song, ref

    async def getnowplaying(self, ctx: commands.Context):
        await username_to_ctx(ctx)
        playing = {"artist": None, "album": None, "track": None}

        data = await self.api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}
        )

        try:
            tracks = data["recenttracks"]["track"]
            if tracks:
                playing["artist"] = tracks[0]["artist"]["#text"]
                playing["album"] = tracks[0]["album"]["#text"]
                playing["track"] = tracks[0]["name"]
        except KeyError:
            pass

        return playing

    async def get_playcount_track(self, artist, track, username, reference=None):
        data = await self.api_request(
            {
                "method": "track.getinfo",
                "user": username,
                "track": track,
                "artist": artist,
                "autocorrect": 1,
            }
        )
        try:
            count = int(data["track"]["userplaycount"])
        except (KeyError, TypeError):
            count = 0

        artistname = data["track"]["artist"]["name"]
        trackname = data["track"]["name"]

        try:
            image_url = data["track"]["album"]["image"][-1]["#text"]
        except KeyError:
            image_url = None

        if reference is None:
            return count
        return count, reference, (artistname, trackname, image_url)

    async def get_playcount_album(self, artist, album, username, reference=None):
        data = await self.api_request(
            {
                "method": "album.getinfo",
                "user": username,
                "album": album,
                "artist": artist,
                "autocorrect": 1,
            }
        )
        try:
            count = int(data["album"]["userplaycount"])
        except (KeyError, TypeError):
            count = 0

        artistname = data["album"]["artist"]
        albumname = data["album"]["name"]

        try:
            image_url = data["album"]["image"][-1]["#text"]
        except KeyError:
            image_url = None

        if reference is None:
            return count
        return count, reference, (artistname, albumname, image_url)

    async def get_playcount(self, artist, username, reference=None):
        data = await self.api_request(
            {
                "method": "artist.getinfo",
                "user": username,
                "artist": artist,
                "autocorrect": 1,
            }
        )
        try:
            count = int(data["artist"]["stats"]["userplaycount"])
        except (KeyError, TypeError):
            count = 0

        name = data["artist"]["name"]

        if reference is None:
            return count
        return count, reference, name

    async def scrape_artist_image(self, artist):
        url = f"https://www.last.fm/music/{urllib.parse.quote_plus(str(artist))}/+images"
        data, error = await fetch_html(self.bot, url)
        if error:
            return None

        soup = BeautifulSoup(data, "lxml")
        image = soup.find("img", {"class": "image-list-image"})
        if image is None:
            try:
                image = soup.find("li", {"class": "image-list-item-wrapper"}).find("a").find("img")  # type: ignore
            except AttributeError:
                image = None

        return image

    async def scrape_artists_for_chart(self, username, period, amount):
        tasks = []
        url = f"https://www.last.fm/user/{username}/library/artists"
        for i in range(1, math.ceil(amount / 50) + 1):
            params = {"date_preset": period_http_format(period), "page": i}
            task = asyncio.ensure_future(fetch_html(self.bot, url, params))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        images = []
        for data, error in responses:
            if len(images) >= amount:
                break

            if error:
                raise exceptions.LastFMError(0, error)

            soup = BeautifulSoup(data, "lxml")
            imagedivs = soup.findAll("td", {"class": "chartlist-image"})
            images += [
                div.find("img")["src"].replace("/avatar70s/", "/300x300/") for div in imagedivs
            ]

        return images


# class ends here


async def setup(bot):
    await bot.add_cog(LastFm(bot))


def format_plays(amount):
    if amount == 1:
        return "play"
    return "plays"


def get_period(timeframe, allow_custom=True):
    if timeframe in ["day", "today", "1day", "24h"] and allow_custom:
        period = "today"
    elif timeframe in ["7day", "7days", "weekly", "week", "1week"]:
        period = "7day"
    elif timeframe in ["30day", "30days", "monthly", "month", "1month"]:
        period = "1month"
    elif timeframe in ["90day", "90days", "3months", "3month"]:
        period = "3month"
    elif timeframe in ["180day", "180days", "6months", "6month", "halfyear"]:
        period = "6month"
    elif timeframe in ["365day", "365days", "1year", "year", "12months", "12month"]:
        period = "12month"
    elif timeframe in ["at", "alltime", "overall"]:
        period = "overall"
    else:
        period = None

    return period


def humanized_period(period):
    if period == "today":
        humanized = "daily"
    elif period == "7day":
        humanized = "weekly"
    elif period == "1month":
        humanized = "monthly"
    elif period == "3month":
        humanized = "past 3 months"
    elif period == "6month":
        humanized = "past 6 months"
    elif period == "12month":
        humanized = "yearly"
    else:
        humanized = "alltime"

    return humanized


def parse_arguments(args):
    parsed = {"period": None, "amount": None}
    for a in args:
        if parsed["amount"] is None:
            try:
                parsed["amount"] = int(a)
                continue
            except ValueError:
                pass
        if parsed["period"] is None:
            parsed["period"] = get_period(a)

    if parsed["period"] is None:
        parsed["period"] = "overall"
    if parsed["amount"] is None:
        parsed["amount"] = 15
    return parsed


def parse_chart_arguments(args, server_version=False):
    parsed = {
        "period": None,
        "amount": None,
        "width": None,
        "height": None,
        "method": None,
        "path": None,
        "showtitles": None,
    }
    for a in args:
        a = a.lower()
        if parsed["amount"] is None:
            try:
                size = a.split("x")
                parsed["width"] = abs(int(size[0]))
                if len(size) > 1:
                    parsed["height"] = abs(int(size[1]))
                else:
                    parsed["height"] = abs(int(size[0]))
                continue
            except ValueError:
                pass

        if parsed["method"] is None:
            if a in ["talb", "topalbums", "albums", "album"]:
                parsed["method"] = "user.gettopalbums"
                continue

            if a in ["ta", "topartists", "artists", "artist"]:
                parsed["method"] = "user.gettopartists"
                continue

            if a in ["re", "recent", "recents"] and not server_version:
                parsed["method"] = "user.getrecenttracks"
                continue

        if parsed["period"] is None:
            parsed["period"] = get_period(a, allow_custom=not server_version)

        if parsed["showtitles"] is None and a == "notitle":
            parsed["showtitles"] = False

    if parsed["period"] is None:
        parsed["period"] = "7day"
    if parsed["width"] is None:
        parsed["width"] = 3
        parsed["height"] = 3
    if parsed["method"] is None:
        parsed["method"] = "user.gettopalbums"
    if parsed["showtitles"] is None:
        parsed["showtitles"] = True
    parsed["amount"] = parsed["width"] * parsed["height"]
    return parsed


async def fetch_html(bot: MisoBot, url: str, params: Optional[dict] = None):
    """Returns tuple of (data, error)"""
    headers = headers = {
        "Host": "www.last.fm",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:106.0) Gecko/20100101 Firefox/106.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fi,en;q=0.7,en-US;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Cookie": bot.keychain.LASTFM_LOGIN_COOKIE,
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }
    async with bot.session.get(url, params=params, headers=headers) as response:
        data: str = await response.text()
        if not response.ok:
            logger.error(f"Lastfm error {response.status}")
            return "", data
        return data, None


def period_http_format(period):
    period_format_map = {
        "7day": "LAST_7_DAYS",
        "1month": "LAST_30_DAYS",
        "3month": "LAST_90_DAYS",
        "6month": "LAST_180_DAYS",
        "12month": "LAST_365_DAYS",
        "overall": "ALL",
    }
    return period_format_map.get(period)


async def username_to_ctx(ctx: commands.Context):
    if ctx.message.mentions:
        ctx.foreign_target = True
        ctx.usertarget = ctx.message.mentions[0]
    else:
        ctx.foreign_target = False
        ctx.usertarget = ctx.author

    bot: MisoBot = ctx.bot
    ctx.username = await bot.db.fetch_value(
        "SELECT lastfm_username FROM user_settings WHERE user_id = %s",
        ctx.usertarget.id,
    )
    if not ctx.username and (
        not ctx.invoked_subcommand or ctx.invoked_subcommand.name not in ["set", "blacklist"]
    ):
        if not ctx.foreign_target:
            msg = f"No last.fm username saved! Please use `{ctx.prefix}fm set` to save your username (last.fm account required)"
        else:
            msg = f"{ctx.usertarget.mention} has not saved their lastfm username!"

        raise exceptions.CommandWarning(msg)


def remove_mentions(text):
    """Remove mentions from string"""
    return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()


def get_list_contents(soup):
    """Scrape lastfm for listing pages"""
    try:
        chartlist = soup.find("tbody", {"data-playlisting-add-entries": ""})
    except ValueError:
        return []

    results = []
    items = chartlist.findAll("tr", {"class": "chartlist-row"})
    for item in items:
        name = item.find("td", {"class": "chartlist-name"}).find("a").get("title")
        playcount = (
            item.find("span", {"class": "chartlist-count-bar-value"})
            .text.replace("scrobbles", "")
            .replace("scrobble", "")
            .strip()
        )
        results.append((name, int(playcount.replace(",", ""))))

    return results


async def get_additional_pages(bot, soup, url):
    """Check for pagination on listing page and asynchronously fetch all the remaining pages"""
    pagination = soup.find("ul", {"class": "pagination-list"})

    if pagination is None:
        return []

    page_count = len(pagination.findAll("li", {"class": "pagination-page"}))

    async def get_additional_page(n):
        new_url = url + f"&page={n}"
        data, error = await fetch_html(bot, new_url)
        if error:
            raise exceptions.LastFMError(error_code=0, message=error)
        soup = BeautifulSoup(data, "lxml")
        return get_list_contents(soup)

    tasks = []
    if page_count > 1:
        for i in range(2, page_count + 1):
            tasks.append(get_additional_page(i))

    results = []
    for result in await asyncio.gather(*tasks):
        results += result

    return results
