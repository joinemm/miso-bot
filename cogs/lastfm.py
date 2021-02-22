import discord
import random
import kdtree
import os
import asyncio
import arrow
import aiohttp
import re
import html
import math
import io
import colorgram
import urllib.parse
from bs4 import BeautifulSoup
from discord.ext import commands
from PIL import Image
from modules import exceptions, emojis, util


LASTFM_APPID = os.environ.get("LASTFM_APIKEY")
LASTFM_TOKEN = os.environ.get("LASTFM_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
AUDDIO_TOKEN = os.environ.get("AUDDIO_TOKEN")

MISSING_IMAGE_HASH = "2a96cbd8b46e442fc41c2b86b821562f"


class AlbumColorNode(object):
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
        self.bot = bot
        self.icon = "🎵"
        self.lastfm_red = "b90000"
        self.cover_base_urls = [
            "https://lastfm.freetls.fastly.net/i/u/34s/{0}.png",
            "https://lastfm.freetls.fastly.net/i/u/64s/{0}.png",
            "https://lastfm.freetls.fastly.net/i/u/174s/{0}.png",
            "https://lastfm.freetls.fastly.net/i/u/300x300/{0}.png",
        ]
        with open("html/fm_chart.min.html", "r", encoding="utf-8") as file:
            self.chart_html = file.read().replace("\n", "")

    @commands.group(case_insensitive=True)
    async def fm(self, ctx):
        await username_to_ctx(ctx)

        if ctx.invoked_subcommand is None:
            await util.command_group_help(ctx)

    @fm.command()
    async def set(self, ctx, username):
        """Save your Last.fm username."""
        if ctx.foreign_target:
            raise exceptions.Warning("You cannot set Last.fm username for someone else!")

        content = await self.get_userinfo_embed(username)
        if content is None:
            raise exceptions.Warning(f"Last.fm profile `{username}` was not found")

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
            f"{ctx.author.mention} Last.fm username saved as `{username}`", embed=content
        )

    @fm.command()
    async def unset(self, ctx):
        """Unlink your Last.fm."""
        if ctx.foreign_target:
            raise exceptions.Warning("You cannot unset someone else's Last.fm username!")

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
    async def profile(self, ctx):
        """Last.fm profile."""
        await ctx.send(embed=await self.get_userinfo_embed(ctx.username))

    @fm.command(aliases=["yt"])
    async def youtube(self, ctx):
        """See your current song on youtube."""
        data = await api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}
        )

        tracks = data["recenttracks"]["track"]

        if not tracks:
            raise exceptions.Info("You have not listened to anything yet!")

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
            "key": GOOGLE_API_KEY,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

        video_id = data["items"][0]["id"]["videoId"]
        video_url = f"https://youtube.com/watch?v={video_id}"

        await ctx.send(f"**{username} — {state}** :cd:\n{video_url}")

    @fm.command(aliases=["np", "no"])
    async def nowplaying(self, ctx):
        """Show your currently playing song."""
        data = await api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}
        )

        tracks = data["recenttracks"]["track"]

        if not tracks:
            raise exceptions.Info("You have not listened to anything yet!")

        artist = tracks[0]["artist"]["#text"]
        album = tracks[0]["album"]["#text"]
        track = tracks[0]["name"]
        image_url = tracks[0]["image"][-1]["#text"]

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.description = f":cd: **{util.escape_md(album)}**"
        content.title = f"**{util.escape_md(artist)} — *{util.escape_md(track)}* **"
        content.set_thumbnail(url=image_url)

        # tags and playcount
        trackdata = await api_request(
            {"user": ctx.username, "method": "track.getInfo", "artist": artist, "track": track},
            ignore_errors=True,
        )
        if trackdata is not None:
            tags = []
            try:
                trackdata = trackdata["track"]
                playcount = int(trackdata["userplaycount"])
                if playcount > 0:
                    content.description += f"\n> {playcount} {format_plays(playcount)}"
                for tag in trackdata["toptags"]["tag"]:
                    tags.append(tag["name"])
                content.set_footer(text=", ".join(tags))
            except KeyError:
                pass

        # play state
        np = "@attr" in tracks[0] and "nowplaying" in tracks[0]["@attr"]
        state = "> Now Playing" if np else "II Last track"
        if not np:
            content.timestamp = arrow.get(int(tracks[0]["date"]["uts"])).datetime

        content.set_author(
            name=f"{util.displayname(ctx.usertarget)} {state}",
            icon_url=ctx.usertarget.avatar_url,
        )

        await ctx.send(embed=content)

    @fm.command(aliases=["ta"])
    async def topartists(self, ctx, *args):
        """
        Most listened artists.

        Usage:
            >fm topartists [timeframe] [amount]
        """
        arguments = parse_arguments(args)
        if arguments["period"] == "today":
            data = await custom_period(ctx.username, "artist")
        else:
            data = await api_request(
                {
                    "user": ctx.username,
                    "method": "user.gettopartists",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                }
            )
        user_attr = data["topartists"]["@attr"]
        artists = data["topartists"]["artist"][: arguments["amount"]]

        if not artists:
            raise exceptions.Info("You have not listened to anything yet!")

        rows = []
        for i, artist in enumerate(artists, start=1):
            name = util.escape_md(artist["name"])
            plays = artist["playcount"]
            rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} : **{name}**")

        image_url = await self.get_artist_image(artists[0]["name"])
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique artists: {user_attr['total']}")
        content.set_author(
            name=f"{util.displayname(ctx.usertarget)} — {formatted_timeframe} top artists",
            icon_url=ctx.usertarget.avatar_url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["talb"])
    async def topalbums(self, ctx, *args):
        """
        Most listened albums.

        Usage:
            >fm topalbums [timeframe] [amount]
        """
        arguments = parse_arguments(args)
        if arguments["period"] == "today":
            data = await custom_period(ctx.username, "album")
        else:
            data = await api_request(
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
            raise exceptions.Info("You have not listened to anything yet!")

        rows = []
        for i, album in enumerate(albums, start=1):
            name = util.escape_md(album["name"])
            artist_name = util.escape_md(album["artist"]["name"])
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
            name=f"{util.displayname(ctx.usertarget)} — {formatted_timeframe} top albums",
            icon_url=ctx.usertarget.avatar_url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["tt"])
    async def toptracks(self, ctx, *args):
        """
        Most listened tracks.

        Usage:
            >fm toptracks [timeframe] [amount]
        """
        arguments = parse_arguments(args)
        if arguments["period"] == "today":
            data = await custom_period(ctx.username, "track")
        else:
            data = await api_request(
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
            raise exceptions.Info("You have not listened to anything yet!")

        rows = []
        for i, track in enumerate(tracks, start=1):
            if i == 1:
                image_url = await self.get_artist_image(tracks[0]["artist"]["name"])

            name = util.escape_md(track["name"])
            artist_name = util.escape_md(track["artist"]["name"])
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
            name=f"{util.displayname(ctx.usertarget)} — {formatted_timeframe} top tracks",
            icon_url=ctx.usertarget.avatar_url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["recents", "re"])
    async def recent(self, ctx, size="15"):
        """Recently listened to tracks."""
        try:
            size = abs(int(size))
        except ValueError:
            size = 15

        data = await api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": size}
        )
        user_attr = data["recenttracks"]["@attr"]
        tracks = data["recenttracks"]["track"][:size]

        if not tracks:
            raise exceptions.Info("You have not listened to anything yet!")

        rows = []
        for track in tracks:
            name = util.escape_md(track["name"])
            artist_name = util.escape_md(track["artist"]["#text"])
            rows.append(f"**{artist_name}** — ***{name}***")

        image_url = tracks[0]["image"][-1]["#text"]

        content = discord.Embed()
        content.colour = await self.cached_image_color(image_url)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
        content.set_author(
            name=f"{util.displayname(ctx.usertarget, escape=False)} — Recent tracks",
            icon_url=ctx.usertarget.avatar_url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command()
    async def last(self, ctx, timeframe):
        """
        Your week/month/year listening overview.

        Usage:
            >fm last week
            >fm last month (requires lastfm pro)
            >fm last year
        """
        timeframe = timeframe.lower()
        if timeframe not in ["week", "month", "year"]:
            raise exceptions.Info("Available timeframes: `[ week | month | year ]`")

        if timeframe != "week":
            raise exceptions.Warning(
                "Only the weekly listening report is currently available due to a Last.fm change, sorry for the inconvenience!"
            )

        await self.listening_report(ctx, timeframe)

    @fm.command()
    async def artist(self, ctx, timeframe, datatype, *, artistname=""):
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
            artistname = (await getnowplaying(ctx))["artist"]
            if artistname is None:
                raise exceptions.Warning("Could not get currently playing artist!")

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
            artistname = util.escape_md(artistname)
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            else:
                return await ctx.send(
                    f"You have not listened to **{artistname}** in the past {period}s!"
                )

        total = 0
        rows = []
        for i, (name, playcount) in enumerate(data, start=1):
            rows.append(
                f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{util.escape_md(name)}**"
            )
            total += playcount

        artistname = urllib.parse.quote_plus(artistname)
        content = discord.Embed()
        content.set_thumbnail(url=artist["image_url"])
        content.colour = await self.cached_image_color(artist["image_url"])
        content.set_author(
            name=f"{util.displayname(ctx.usertarget)} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + f"Top {datatype} by {artist['formatted_name']}",
            icon_url=ctx.usertarget.avatar_url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"+{datatype}?date_preset={period_http_format(period)}",
        )
        content.set_footer(
            text=f"Total {total} {format_plays(total)} across {len(rows)} {datatype}"
        )

        await util.send_as_pages(ctx, content, rows)

    @fm.command(name="album")
    async def album(self, ctx, *, album):
        """Get your top tracks from a given album."""
        period = "overall"
        if album is None:
            return await util.send_command_help(ctx)

        album = remove_mentions(album)
        if album.lower() == "np":
            npd = await getnowplaying(ctx)
            albumname = npd["album"]
            artistname = npd["artist"]
            if None in [albumname, artistname]:
                raise exceptions.Warning("Could not get currently playing album!")
        else:
            try:
                albumname, artistname = [x.strip() for x in album.split("|")]
                if albumname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                raise exceptions.Warning("Incorrect format! use `album | artist`")

        album, data = await self.album_top_tracks(ctx, period, artistname, albumname)
        if album is None or not data:
            if period == "overall":
                return await ctx.send(
                    f"You have never listened to **{albumname}** by **{artistname}**!"
                )
            else:
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
                f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{util.escape_md(name)}**"
            )

        titlestring = f"top tracks from {albumname}\n— by {artistname}"
        artistname = urllib.parse.quote_plus(artistname)
        albumname = urllib.parse.quote_plus(albumname)
        content = discord.Embed()
        content.set_thumbnail(url=album["image_url"])
        content.set_footer(text=f"Total album plays: {total_plays}")
        content.colour = await self.cached_image_color(album["image_url"])
        content.set_author(
            name=f"{util.displayname(ctx.usertarget)} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + titlestring,
            icon_url=ctx.usertarget.avatar_url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"{albumname}?date_preset={period_http_format(period)}",
        )

        await util.send_as_pages(ctx, content, rows)

    async def album_top_tracks(self, ctx, period, artistname, albumname):
        """Scrape the top tracks of given album from lastfm library page."""
        artistname = urllib.parse.quote_plus(artistname)
        albumname = urllib.parse.quote_plus(albumname)
        async with aiohttp.ClientSession() as session:
            url = (
                f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
                f"{albumname}?date_preset={period_http_format(period)}"
            )
            data = await fetch(session, url, handling="text")
            if data is None:
                raise exceptions.LastFMError(404, "Album page not found")

            soup = BeautifulSoup(data, "html.parser")

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
            all_results += await get_additional_pages(session, soup, url)

            return album, all_results

    async def artist_top(self, ctx, period, artistname, datatype):
        """Scrape either top tracks or top albums from lastfm library page."""
        artistname = urllib.parse.quote_plus(artistname)
        async with aiohttp.ClientSession() as session:
            url = (
                f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
                f"+{datatype}?date_preset={period_http_format(period)}"
            )
            data = await fetch(session, url, handling="text")
            if data is None:
                raise exceptions.LastFMError(404, "Artist page not found")

            soup = BeautifulSoup(data, "html.parser")

            artist = {
                "image_url": soup.find("span", {"class": "library-header-image"})
                .find("img")
                .get("src")
                .replace("avatar70s", "avatar300s"),
                "formatted_name": soup.find("a", {"class": "library-header-crumb"}).text.strip(),
            }

            all_results = get_list_contents(soup)
            all_results += await get_additional_pages(session, soup, url)

            return artist, all_results

    async def artist_overview(self, ctx, period, artistname):
        """Overall artist view."""
        albums = []
        tracks = []
        metadata = [None, None, None]
        artistinfo = await api_request({"method": "artist.getInfo", "artist": artistname})
        async with aiohttp.ClientSession() as session:
            url = (
                f"https://last.fm/user/{ctx.username}/library/music/"
                f"{urllib.parse.quote_plus(artistname)}"
                f"?date_preset={period_http_format(period)}"
            )
            data = await fetch(session, url, handling="text")
            if data is None:
                raise exceptions.LastFMError(404, "Artist page not found")

            soup = BeautifulSoup(data, "html.parser")
            try:
                albumsdiv, tracksdiv, _ = soup.findAll(
                    "tbody", {"data-playlisting-add-entries": ""}
                )

            except ValueError:
                artistname = util.escape_md(artistname)
                if period == "overall":
                    return await ctx.send(f"You have never listened to **{artistname}**!")
                else:
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
            name=f"{util.displayname(ctx.usertarget)} — {artist['formatted_name']} "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + "Overview",
            icon_url=ctx.usertarget.avatar_url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}"
            f"?date_preset={period_http_format(period)}",
        )

        content.set_footer(text=f"{', '.join(tags)}")

        crown_holder = await self.bot.db.execute(
            """
            SELECT user_id FROM artist_crown WHERE guild_id = %s AND artist_name = %s
            """,
            ctx.guild.id,
            artist["formatted_name"],
            one_value=True,
        )

        if crown_holder == ctx.usertarget.id:
            crownstate = " :crown:"
        else:
            crownstate = ""

        scrobbles, albums_count, tracks_count = metadata
        content.add_field(name="Listeners", value=f"**{listeners}**")
        content.add_field(name="Scrobbles", value=f"**{globalscrobbles}**")
        content.add_field(name="Your scrobbles", value=f"**{scrobbles}**{crownstate}")

        content.add_field(
            name=f":cd: {albums_count} Albums",
            value="\n".join(
                f"`#{i:2}` **{util.escape_md(item)}** ({playcount})"
                for i, (item, playcount) in enumerate(albums, start=1)
            ),
            inline=True,
        )
        content.add_field(
            name=f":musical_note: {tracks_count} Tracks",
            value="\n".join(
                f"`#{i:2}` **{util.escape_md(item)}** ({playcount})"
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

        colors = colorgram.extract(image, 1)
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
            "limit": 1000,
        }
        data = await api_request(dict(params, **{"page": 1}))
        topalbums = data["topalbums"]["album"]
        # total_pages = int(data["topalbums"]["@attr"]["totalPages"])
        # if total_pages > 1:
        #     tasks = []
        #     for i in range(2, total_pages + 1):
        #         tasks.append(api_request(dict(params, **{"page": i})))

        #     data = await asyncio.gather(*tasks)
        #     for page in data:
        #         topalbums += page["topalbums"]["album"]

        return topalbums

    @fm.command(aliases=["colourchart"])
    async def colorchart(self, ctx, colour, size="3x3"):
        """
        Color based album chart.

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
                raise exceptions.Warning(f"`{colour}` is not a valid hex colour")

            dim = size.split("x")
            width = int(dim[0])
            if len(dim) > 1:
                height = abs(int(dim[1]))
            else:
                height = abs(int(dim[0]))

            if width + height > max_size:
                raise exceptions.Info(
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
            raise exceptions.Error("There was an unknown error while getting your albums!")

        to_fetch = []
        albumcolors = await self.bot.db.execute(
            """
            SELECT image_hash, r, g, b FROM image_color_cache WHERE image_hash IN %s
            """,
            tuple(albums),
        )
        albumcolors_dict = {}
        for image_hash, r, g, b in albumcolors:
            albumcolors_dict[image_hash] = (r, g, b)
        warn = None

        async with aiohttp.ClientSession() as session:
            for image_id in albums:
                color = albumcolors_dict.get(image_id)
                if color is None:
                    to_fetch.append(image_id)
                else:
                    album_color_nodes.append(AlbumColorNode(color, image_id))

            if to_fetch:
                to_cache = []
                tasks = []
                for image_id in to_fetch:
                    tasks.append(self.fetch_color(session, image_id))

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

            if rainbow:
                if diagonal:
                    rainbow_colors = [
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
                else:
                    rainbow_colors = [
                        (255, 0, 0),  # red
                        (255, 127, 0),  # orange
                        (255, 255, 0),  # yellow
                        (0, 255, 0),  # green
                        (0, 0, 255),  # blue
                        (75, 0, 130),  # purple
                        (148, 0, 211),  # violet
                    ]

                chunks = []
                tree = kdtree.create(album_color_nodes)
                for rgb in rainbow_colors:
                    chunks.append(list(tree.search_knn(rgb, width + height)))

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
                tree = kdtree.create(album_color_nodes)
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

    @fm.command()
    async def chart(self, ctx, *args):
        """
        Visual chart of your top albums or artists.

        Usage:
            >fm chart [album | artist] [timeframe] [width]x[height] [notitle]
        """
        arguments = parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 30:
            raise exceptions.Info(
                "Size is too big! Chart `width` + `height` total must not exceed `30`"
            )

        if arguments["period"] == "today":
            data = await custom_period(ctx.username, arguments["method"])
        else:
            data = await api_request(
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
            scraped_images = await scrape_artists_for_chart(
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
            chart, arguments["width"], arguments["height"], show_labels=arguments["showtitles"]
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

        return await util.render_html(payload)

    async def server_lastfm_usernames(self, ctx, filter_cheaters=False):
        guild_user_ids = [user.id for user in ctx.guild.members]
        data = await self.bot.db.execute(
            """
            SELECT user_id, lastfm_username FROM user_settings WHERE user_id IN %s
            AND lastfm_username IS NOT NULL
            """
            + (
                " AND lastfm_username not in (SELECT lastfm_username FROM lastfm_cheater)"
                if filter_cheaters
                else ""
            ),
            guild_user_ids,
        )
        return data

    @fm.group(aliases=["s", "guild"])
    @commands.guild_only()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def server(self, ctx):
        """Server wide statistics."""
        await util.command_group_help(ctx)

    @server.command(name="nowplaying", aliases=["np"])
    async def server_nowplaying(self, ctx):
        """What people on this server are listening to."""
        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(ctx):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(get_np(lastfm_username, member))

        total_linked = len(tasks)
        if tasks:
            data = await asyncio.gather(*tasks)
            for song, member_ref in data:
                if song is not None:
                    listeners.append((song, member_ref))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        if not listeners:
            return await ctx.send("Nobody on this server is listening to anything at the moment!")

        total_listening = len(listeners)
        rows = []
        maxlen = 0
        for song, member in listeners:
            dn = util.displayname(member)
            if len(dn) > maxlen:
                maxlen = len(dn)

        for song, member in listeners:
            rows.append(
                f"{util.displayname(member)} | **{util.escape_md(song.get('artist'))}** — ***{util.escape_md(song.get('name'))}***"
            )

        content = discord.Embed()
        content.set_author(
            name=f"What is {ctx.guild.name} listening to?",
            icon_url=ctx.guild.icon_url_as(size=64),
        )
        content.colour = int(
            await util.color_from_image_url(str(ctx.guild.icon_url_as(size=64))), 16
        )
        content.set_footer(
            text=f"{total_listening} / {total_linked} Members are listening to music"
        )
        await util.send_as_pages(ctx, content, rows)

    @server.command(name="recent", aliases=["re"])
    async def server_recent(self, ctx):
        """What people on this server have recently listened."""
        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(ctx):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(get_lastplayed(lastfm_username, member))

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

        listeners = sorted(listeners, key=lambda l: l[0].get("date"), reverse=True)
        rows = []
        for song, member in listeners:
            suffix = ""
            if song.get("nowplaying"):
                suffix = ":musical_note: "
            else:
                suffix = f"({arrow.get(song.get('date')).humanize()})"

            rows.append(
                f"{util.displayname(member)} | **{util.escape_md(song.get('artist'))}** — ***{util.escape_md(song.get('name'))}*** {suffix}"
            )

        content = discord.Embed()
        content.set_author(
            name=f"What has {ctx.guild.name} been listening to?",
            icon_url=ctx.guild.icon_url_as(size=64),
        )
        content.colour = int(
            await util.color_from_image_url(str(ctx.guild.icon_url_as(size=64))), 16
        )
        content.set_footer(
            text=f"{total_listening} / {total_linked} Members are listening to music right now"
        )
        await util.send_as_pages(ctx, content, rows)

    @server.command(name="topartists", aliases=["ta"])
    async def server_topartists(self, ctx):
        """Combined top artists of this server's members."""
        artist_map = {}
        tasks = []
        total_users = 0
        total_plays = 0
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_cheaters=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_server_top(lastfm_username, "artist"))

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
        content = discord.Embed(title=f"Most listened to artists in {ctx.guild}")
        content.set_footer(text=f"Taking into account top 100 artists of {total_users} members")
        for i, (artistname, playcount) in enumerate(
            sorted(artist_map.items(), key=lambda x: x[1], reverse=True), start=1
        ):
            if i == 1:
                image_url = await self.get_artist_image(artistname)
                content.colour = await self.cached_image_color(image_url)
                content.set_thumbnail(url=image_url)

            rows.append(
                f"`#{i:2}` **{playcount}** {format_plays(playcount)} : **{util.escape_md(artistname)}**"
            )

        await util.send_as_pages(ctx, content, rows, 15)

    @server.command(name="topalbums", aliases=["talb"])
    async def server_topalbums(self, ctx):
        """Combined top albums of this server's members."""
        album_map = {}
        tasks = []
        total_users = 0
        total_plays = 0
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_cheaters=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_server_top(lastfm_username, "album"))

        if tasks:
            data = await asyncio.gather(*tasks)
            for user_data in data:
                if user_data is None:
                    continue
                total_users += 1
                for data_block in user_data:
                    name = f'{util.escape_md(data_block["artist"]["name"])} — *{util.escape_md(data_block["name"])}*'
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
        content = discord.Embed(title=f"Most listened to albums in {ctx.guild}")
        content.set_footer(text=f"Taking into account top 100 albums of {total_users} members")
        for i, (albumname, albumdata) in enumerate(
            sorted(album_map.items(), key=lambda x: x[1]["plays"], reverse=True), start=1
        ):
            if i == 1:
                image_url = albumdata["image"]
                content.colour = await self.cached_image_color(image_url)
                content.set_thumbnail(url=image_url)

            playcount = albumdata["plays"]
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} : **{albumname}**")

        await util.send_as_pages(ctx, content, rows, 15)

    @server.command(name="toptracks", aliases=["tt"])
    async def server_toptracks(self, ctx):
        """Combined top tracks of this server's members."""
        track_map = {}
        tasks = []
        total_users = 0
        total_plays = 0
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_cheaters=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(self.get_server_top(lastfm_username, "track"))

        if tasks:
            data = await asyncio.gather(*tasks)
            for user_data in data:
                if user_data is None:
                    continue
                total_users += 1
                for data_block in user_data:
                    name = f'{util.escape_md(data_block["artist"]["name"])} — *{util.escape_md(data_block["name"])}*'
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
        content = discord.Embed(title=f"Most listened to tracks in {ctx.guild}")
        content.set_footer(text=f"Taking into account top 100 tracks of {total_users} members")
        for i, (trackname, trackdata) in enumerate(
            sorted(track_map.items(), key=lambda x: x[1]["plays"], reverse=True), start=1
        ):
            if i == 1:
                image_url = await self.get_artist_image(trackdata["artist"])
                content.colour = await self.cached_image_color(image_url)
                content.set_thumbnail(url=image_url)

            playcount = trackdata["plays"]
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} : **{trackname}**")

        await util.send_as_pages(ctx, content, rows, 15)

    async def get_server_top(self, username, datatype):
        limit = 100
        if datatype == "artist":
            data = await api_request(
                {
                    "user": username,
                    "method": "user.gettopartists",
                    "limit": limit,
                },
                ignore_errors=True,
            )
            return data["topartists"]["artist"] if data is not None else None
        elif datatype == "album":
            data = await api_request(
                {
                    "user": username,
                    "method": "user.gettopalbums",
                    "limit": limit,
                },
                ignore_errors=True,
            )
            return data["topalbums"]["album"] if data is not None else None
        elif datatype == "track":
            data = await api_request(
                {
                    "user": username,
                    "method": "user.gettoptracks",
                    "limit": limit,
                },
                ignore_errors=True,
            )
            return data["toptracks"]["track"] if data is not None else None

    @commands.command(aliases=["wk", "whomstknows"])
    @commands.guild_only()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknows(self, ctx, *, artistname=None):
        """
        Who has listened to a given artist the most.

        Usage:
            >whoknows <artist name>
            >whoknows np
        """
        if artistname is None:
            return await util.send_command_help(ctx)

        artistname = remove_mentions(artistname)
        if artistname.lower() == "np":
            artistname = (await getnowplaying(ctx))["artist"]
            if artistname is None:
                raise exceptions.Warning("Could not get currently playing artist!")

        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_cheaters=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(get_playcount(artistname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, member, name in data:
                artistname = name
                if playcount > 0:
                    listeners.append((playcount, member))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = util.escape_md(artistname)

        rows = []
        old_king = None
        new_king = None
        total = 0
        for i, (playcount, member) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            if i == 1:
                rank = ":crown:"
                old_king = await self.bot.db.execute(
                    "SELECT user_id FROM artist_crown WHERE artist_name = %s AND guild_id = %s",
                    artistname,
                    ctx.guild.id,
                    one_value=True,
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

    @commands.command(aliases=["wkt", "whomstknowstrack"])
    @commands.guild_only()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknowstrack(self, ctx, *, track=None):
        """
        Who has listened to a given song the most.

        Usage:
            >whoknowstrack <track name> | <artist name>
            >whoknowstrack np
        """
        if track is None:
            return await util.send_command_help(ctx)

        track = remove_mentions(track)
        if track.lower() == "np":
            npd = await getnowplaying(ctx)
            trackname = npd["track"]
            artistname = npd["artist"]
            if None in [trackname, artistname]:
                raise exceptions.Warning("Could not get currently playing track!")
        else:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                raise exceptions.Warning("Incorrect format! use `track | artist`")

        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_cheaters=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(get_playcount_track(artistname, trackname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, metadata in data:
                artistname, trackname, image_url = metadata
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = util.escape_md(artistname)
        trackname = util.escape_md(trackname)

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

    @commands.command(aliases=["wka", "whomstknowsalbum"])
    @commands.guild_only()
    @commands.cooldown(2, 60, type=commands.BucketType.user)
    async def whoknowsalbum(self, ctx, *, album):
        """
        Who has listened to a given album the most.

        Usage:
            >whoknowsalbum <album name> | <artist name>
            >whoknowsalbum np
        """
        if album is None:
            return await util.send_command_help(ctx)

        album = remove_mentions(album)
        if album.lower() == "np":
            npd = await getnowplaying(ctx)
            albumname = npd["album"]
            artistname = npd["artist"]
            if None in [albumname, artistname]:
                raise exceptions.Warning("Could not get currently playing album!")
        else:
            try:
                albumname, artistname = [x.strip() for x in album.split("|")]
                if albumname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                raise exceptions.Warning("Incorrect format! use `album | artist`")

        listeners = []
        tasks = []
        for user_id, lastfm_username in await self.server_lastfm_usernames(
            ctx, filter_cheaters=True
        ):
            member = ctx.guild.get_member(user_id)
            if member is None:
                continue

            tasks.append(get_playcount_album(artistname, albumname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, metadata in data:
                artistname, albumname, image_url = metadata
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = util.escape_md(artistname)
        albumname = util.escape_md(albumname)

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
    @commands.guild_only()
    async def crowns(self, ctx, *, user: discord.Member = None):
        """Check your artist crowns."""
        if user is None:
            user = ctx.author

        crownartists = await self.bot.db.execute(
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
                f"**{util.escape_md(str(artist))}** with **{playcount}** {format_plays(playcount)}"
            )

        content = discord.Embed(color=discord.Color.gold())
        content.set_author(
            name=f"👑 {util.displayname(user)} artist crowns",
            icon_url=user.avatar_url,
        )
        content.set_footer(text=f"Total {len(crownartists)} crowns")
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def report(self, ctx, lastfm_username, *, reason):
        """Report lastfm account."""
        lastfm_username = lastfm_username.strip("/").split("/")[-1].lower()
        url = f"https://www.last.fm/user/{lastfm_username}"
        data = await api_request(
            {"user": lastfm_username, "method": "user.getinfo"}, ignore_errors=True
        )
        if data is None:
            raise exceptions.Warning(f"`{url}` is not a valid Last.fm profile.")

        content = discord.Embed(title="New Last.fm user report")
        content.add_field(name="Profile", value=url)
        content.add_field(name="Reason", value=reason)

        content.description = (
            "Are you sure you want to report this lastfm account?"
            " Please note sending false reports or spamming **will get you blacklisted**."
        )

        # send confirmation message
        msg = await ctx.send(embed=content)

        async def confirm_ban():
            content.add_field(
                name="Reported by",
                value=f"{ctx.author} (`{ctx.author.id}`)",
                inline=False,
            )
            user_ids = await self.bot.db.execute(
                "SELECT user_id FROM user_settings WHERE lastfm_username = %s", lastfm_username
            )
            if user_ids:
                connected_accounts = []
                for x in user_ids:
                    user = self.bot.get_user(x[0])
                    connected_accounts.append(f"{user} (`{user.id}`)")

                content.add_field(
                    name="Connected by",
                    value=", ".join(connected_accounts),
                    inline=False,
                )
            content.set_footer(text=f">fmban {lastfm_username}")
            content.description = ""

            await self.send_report(ctx, content, lastfm_username, reason)
            await msg.edit(content="📨 Report sent!", embed=None)

        async def cancel_ban():
            await msg.edit(content="❌ Report cancelled.", embed=None)

        functions = {"✅": confirm_ban, "❌": cancel_ban}

        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )

    async def send_report(self, ctx, content, lastfm_username, reason=None):
        reports_channel = self.bot.get_channel(729736304677486723)
        if reports_channel is None:
            raise exceptions.Warning("Something went wrong.")

        msg = await reports_channel.send(embed=content)

        async def confirm_ban():
            await self.bot.db.execute(
                """
                INSERT IGNORE lastfm_cheater (lastfm_username, flagged_on, reason)
                """,
                lastfm_username.lower(),
                arrow.now().datetime,
                reason,
            )
            content.description = "Account flagged"
            content.color = discord.Color.green()
            await msg.edit(embed=content)

        async def cancel_ban():
            content.description = "Report ignored"
            content.color = discord.Color.red()
            await msg.edit(embed=content)

        functions = {"✅": confirm_ban, "❌": cancel_ban}

        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, single_use=True, only_owner=True)
        )

    @util.patrons_only()
    @commands.command()
    async def lyrics(self, ctx, *, query):
        """Search for song lyrics."""
        if query.lower() == "np":
            npd = await getnowplaying(ctx)
            trackname = npd["track"]
            artistname = npd["artist"]
            if None in [trackname, artistname]:
                return await ctx.send(":warning: Could not get currently playing track!")
            query = artistname + " " + trackname

        url = "https://api.audd.io/findLyrics/"
        request_data = {
            "api_token": AUDDIO_TOKEN,
            "q": query,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url=url, data=request_data) as response:
                data = await response.json()

        if data["status"] != "success":
            raise exceptions.Warning(
                f"Something went wrong! `error {data['error']['error_code']}: {data['error']['error_message']}`"
            )

        results = data["result"]
        if not results:
            return await ctx.send("Found nothing!")

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

        else:
            result = results[0]

        rows = html.unescape(result["lyrics"]).split("\n")
        content = discord.Embed(title=result["full_title"])
        await util.send_as_pages(ctx, content, rows, maxrows=20)

    async def cached_image_color(self, image_url):
        """Get image color, cache if new."""
        image_hash = image_url.split("/")[-1].split(".")[0]
        cached_color = await self.bot.db.execute(
            "SELECT hex FROM image_color_cache WHERE image_hash = %s",
            image_hash,
            one_value=True,
        )
        if cached_color:
            return int(cached_color, 16)
        else:
            color = await util.color_from_image_url(
                image_url, fallback=None, return_color_object=True
            )
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
        data = await api_request({"user": username, "method": "user.getinfo"}, ignore_errors=True)
        if data is None:
            return None

        username = data["user"]["name"]
        blacklisted = await self.bot.db.execute(
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
        content.set_thumbnail(url=profile_pic_url)
        content.set_footer(text=f"Total plays: {playcount}")
        content.colour = int(self.lastfm_red, 16)
        if blacklisted:
            content.description = ":warning: `This account is flagged as a cheater`"

        return content

    async def listening_report(self, ctx, timeframe):
        current_day_floor = arrow.utcnow().floor("day")
        week = []
        # for i in range(7, 0, -1):
        for i in range(1, 8):
            dt = current_day_floor.shift(days=-i)
            week.append(
                {
                    "dt": dt,
                    "ts": dt.timestamp,
                    "ts_to": dt.shift(days=+1, minutes=-1).timestamp,
                    "day": dt.format("ddd, MMM Do"),
                    "scrobbles": 0,
                }
            )

        params = {
            "method": "user.getrecenttracks",
            "user": ctx.username,
            "from": week[-1]["ts"],
            "to": current_day_floor.shift(minutes=-1).timestamp,
            "limit": 1000,
        }
        content = await api_request(params)
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
            name=f"{ctx.username} | LAST.{timeframe.upper()}",
            icon_url=ctx.usertarget.avatar_url,
        )
        content.description = "\n".join(rows)
        content.add_field(
            name="Total scrobbles", value=f"{scrobbles_total} Scrobbles", inline=False
        )
        content.add_field(
            name="Avg. daily scrobbles", value=f"{scrobbles_average} Scrobbles", inline=False
        )
        # content.add_field(name="Listening time", value=listening_time)
        await ctx.send(embed=content)

    async def get_artist_image(self, artist):
        image_life = 604800  # 1 week
        cached = await self.bot.db.execute(
            "SELECT image_hash, scrape_date FROM artist_image_cache WHERE artist_name = %s",
            artist,
            one_row=True,
        )

        if cached:
            lifetime = arrow.utcnow().timestamp - cached[1].timestamp()
            if (lifetime) < image_life:
                return self.cover_base_urls[-1].format(cached[0])

        image = await scrape_artist_image(artist)
        if image is None:
            return ""
        else:
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
            return self.cover_base_urls[-1].format(image_hash)


# class ends here


async def scrape_artist_image(artist):
    url = f"https://www.last.fm/music/{urllib.parse.quote_plus(str(artist))}/+images"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url, handling="text")
    if data is None:
        return None

    soup = BeautifulSoup(data, "html.parser")
    image = soup.find("img", {"class": "image-list-image"})
    if image is None:
        try:
            image = soup.find("li", {"class": "image-list-item-wrapper"}).find("a").find("img")
        except AttributeError:
            image = None

    return image


def setup(bot):
    bot.add_cog(LastFm(bot))


def format_plays(amount):
    if amount == 1:
        return "play"
    else:
        return "plays"


async def getnowplaying(ctx):
    await username_to_ctx(ctx)
    playing = {"artist": None, "album": None, "track": None}

    data = await api_request({"user": ctx.username, "method": "user.getrecenttracks", "limit": 1})

    try:
        tracks = data["recenttracks"]["track"]
        if tracks:
            playing["artist"] = tracks[0]["artist"]["#text"]
            playing["album"] = tracks[0]["album"]["#text"]
            playing["track"] = tracks[0]["name"]
    except KeyError:
        pass

    return playing


async def get_playcount_track(artist, track, username, reference=None):
    data = await api_request(
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
    else:
        return count, reference, (artistname, trackname, image_url)


async def get_playcount_album(artist, album, username, reference=None):
    data = await api_request(
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
    else:
        return count, reference, (artistname, albumname, image_url)


async def get_playcount(artist, username, reference=None):
    data = await api_request(
        {"method": "artist.getinfo", "user": username, "artist": artist, "autocorrect": 1}
    )
    try:
        count = int(data["artist"]["stats"]["userplaycount"])
    except (KeyError, TypeError):
        count = 0

    name = data["artist"]["name"]

    if reference is None:
        return count
    else:
        return count, reference, name


async def get_np(username, ref):
    data = await api_request(
        {"method": "user.getrecenttracks", "user": username, "limit": 1},
        ignore_errors=True,
    )
    song = None
    if data is not None:
        try:
            tracks = data["recenttracks"]["track"]
            if tracks:
                if "@attr" in tracks[0]:
                    if "nowplaying" in tracks[0]["@attr"]:
                        song = {
                            "artist": tracks[0]["artist"]["#text"],
                            "name": tracks[0]["name"],
                        }
        except KeyError:
            pass

    return song, ref


async def get_lastplayed(username, ref):
    data = await api_request(
        {"method": "user.getrecenttracks", "user": username, "limit": 1},
        ignore_errors=True,
    )
    song = None
    if data is not None:
        try:
            tracks = data["recenttracks"]["track"]
            if tracks:
                nowplaying = False
                if tracks[0].get("@attr"):
                    if tracks[0]["@attr"].get("nowplaying"):
                        nowplaying = True

                if tracks[0].get("date"):
                    date = tracks[0]["date"]["uts"]
                else:
                    date = arrow.now().timestamp

                song = {
                    "artist": tracks[0]["artist"]["#text"],
                    "name": tracks[0]["name"],
                    "nowplaying": nowplaying,
                    "date": int(date),
                }
        except KeyError:
            pass

    return song, ref


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


def parse_chart_arguments(args):
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

            if a in ["re", "recent", "recents"]:
                parsed["method"] = "user.getrecenttracks"
                continue

        if parsed["period"] is None:
            parsed["period"] = get_period(a, allow_custom=False)

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


async def api_request(params, ignore_errors=False):
    """Get json data from the lastfm api."""
    url = "http://ws.audioscrobbler.com/2.0/"
    params["api_key"] = LASTFM_APPID
    params["format"] = "json"
    tries = 0
    max_tries = 2
    while True:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                try:
                    content = await response.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    if ignore_errors:
                        return None
                    else:
                        text = await response.text()
                        raise exceptions.LastFMError(error_code=response.status, message=text)

                if content is None:
                    raise exceptions.LastFMError(
                        error_code=408,
                        message="Could not connect to LastFM",
                    )
                if response.status == 200 and content.get("error") is None:
                    return content
                else:
                    if int(content.get("error")) == 8:
                        tries += 1
                        if tries < max_tries:
                            continue

                    if ignore_errors:
                        return None
                    else:
                        raise exceptions.LastFMError(
                            error_code=content.get("error"),
                            message=content.get("message"),
                        )


async def custom_period(user, group_by, shift_hours=24):
    """Parse recent tracks to get custom duration data (24 hour)."""
    limit_timestamp = arrow.utcnow().shift(hours=-shift_hours)
    data = await api_request(
        {
            "user": user,
            "method": "user.getrecenttracks",
            "from": limit_timestamp.timestamp,
            "limit": 200,
        }
    )
    loops = int(data["recenttracks"]["@attr"]["totalPages"])
    if loops > 1:
        for i in range(2, loops + 1):
            newdata = await api_request(
                {
                    "user": user,
                    "method": "user.getrecenttracks",
                    "from": limit_timestamp.timestamp,
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

    elif group_by in ["track", "user.gettoptracks"]:
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

    elif group_by in ["artist", "user.gettopartists"]:
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


async def fetch(session, url, params=None, handling="json"):
    async with session.get(url, params=params) as response:
        if response.status != 200:
            return None
        if handling == "json":
            return await response.json()
        elif handling == "text":
            return await response.text()
        else:
            return await response


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


async def scrape_artists_for_chart(username, period, amount):
    tasks = []
    url = f"https://www.last.fm/user/{username}/library/artists"
    async with aiohttp.ClientSession() as session:
        for i in range(1, math.ceil(amount / 50) + 1):
            params = {"date_preset": period_http_format(period), "page": i}
            task = asyncio.ensure_future(fetch(session, url, params, handling="text"))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

    images = []
    for data in responses:
        if len(images) >= amount:
            break

        soup = BeautifulSoup(data, "html.parser")
        imagedivs = soup.findAll("td", {"class": "chartlist-image"})
        images += [div.find("img")["src"].replace("/avatar70s/", "/300x300/") for div in imagedivs]

    return images


async def username_to_ctx(ctx):
    if ctx.message.mentions:
        ctx.foreign_target = True
        ctx.usertarget = ctx.message.mentions[0]
    else:
        ctx.foreign_target = False
        ctx.usertarget = ctx.author

    ctx.username = await ctx.bot.db.execute(
        "SELECT lastfm_username FROM user_settings WHERE user_id = %s",
        ctx.usertarget.id,
        one_value=True,
    )
    if not ctx.username and str(ctx.invoked_subcommand) not in ["fm set"]:
        if not ctx.foreign_target:
            msg = f"No last.fm username saved! Please use `{ctx.prefix}fm set <lastfm username>`"
        else:
            msg = f"{ctx.usertarget.mention} has not saved their lastfm username!"

        raise exceptions.Warning(msg)


def remove_mentions(text):
    """Remove mentions from string."""
    return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()


def get_list_contents(soup):
    """Scrape lastfm for listing pages"""
    try:
        chartlist = soup.find("tbody", {"data-playlisting-add-entries": ""})
    except ValueError:
        []

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


async def get_additional_pages(session, soup, url):
    """Check for pagination on listing page and asynchronously fetch all the remaining pages"""
    pagination = soup.find("ul", {"class": "pagination-list"})

    if pagination is None:
        return []

    page_count = len(pagination.findAll("li", {"class": "pagination-page"}))

    async def get_additional_page(n):
        new_url = url + f"&page={n}"
        data = await fetch(session, new_url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        return get_list_contents(soup)

    tasks = []
    if page_count > 1:
        for i in range(2, page_count + 1):
            tasks.append(get_additional_page(i))

    results = []
    for result in await asyncio.gather(*tasks):
        results += result

    return results
