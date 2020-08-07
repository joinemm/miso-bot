import discord
import kdtree
import os
import asyncio
import arrow
import aiohttp
import re
import math
import urllib.parse
from bs4 import BeautifulSoup
from operator import itemgetter
from discord.ext import commands
from helpers import utilityfunctions as util
from data import database as db
from helpers.exceptions import LastFMError
from PIL import Image
import io
import colorgram


LASTFM_APPID = os.environ.get("LASTFM_APIKEY")
LASTFM_TOKEN = os.environ.get("LASTFM_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")


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
        return f"AlbumColorNode({self.rgb}, {self.image_url})"


class LastFm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cover_base_urls = [
            "https://lastfm.freetls.fastly.net/i/u/34s/{0}.png",
            "https://lastfm.freetls.fastly.net/i/u/64s/{0}.png",
            "https://lastfm.freetls.fastly.net/i/u/174s/{0}.png",
            "https://lastfm.freetls.fastly.net/i/u/300x300/{0}.png",
        ]
        with open("html/fm_chart_flex.html", "r", encoding="utf-8") as file:
            self.chart_html_flex = file.read().replace("\n", "")

    @commands.group(case_insensitive=True)
    async def fm(self, ctx):
        """Last.fm commands."""
        await username_to_ctx(ctx)

        if ctx.invoked_subcommand is None:
            await util.command_group_help(ctx)

    @fm.command()
    async def set(self, ctx, username):
        """Save your last.fm username."""
        if ctx.foreign_target:
            return await ctx.send(":warning: You cannot set lastfm username for someone else!")

        content = await get_userinfo_embed(username)
        if content is None:
            return await ctx.send(f":warning: Invalid Last.fm username `{username}`")

        db.update_user(ctx.author.id, "lastfm_username", username)
        await ctx.send(f"{ctx.author.mention} Username saved as `{username}`", embed=content)

    @fm.command()
    async def unset(self, ctx):
        """Unlink your last.fm."""
        if ctx.foreign_target:
            return await ctx.send(":warning: You cannot unset someone else's lastfm username!")

        db.update_user(ctx.author.id, "lastfm_username", None)
        await ctx.send(":broken_heart: Removed your last.fm username from the database")

    @fm.command()
    async def profile(self, ctx):
        """Last.fm profile."""
        await ctx.send(embed=await get_userinfo_embed(ctx.username))

    @fm.command(aliases=["yt"])
    async def youtube(self, ctx):
        """Search for your currently playing song on youtube."""
        data = await api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}
        )

        tracks = data["recenttracks"]["track"]

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

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

    @fm.command(aliases=["np"])
    async def nowplaying(self, ctx):
        """Show your currently playing song."""
        data = await api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": 1}
        )

        tracks = data["recenttracks"]["track"]

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

        username = data["recenttracks"]["@attr"]["user"]
        artist = tracks[0]["artist"]["#text"]
        album = tracks[0]["album"]["#text"]
        track = tracks[0]["name"]
        image_url = tracks[0]["image"][-1]["#text"]
        image_url_small = tracks[0]["image"][1]["#text"]
        image_colour = await util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.description = f"**{util.escape_md(album)}**"
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
        state = "— Most recent track"
        if "@attr" in tracks[0]:
            if "nowplaying" in tracks[0]["@attr"]:
                state = "— Now Playing"

        content.set_author(name=f"{username} {state}", icon_url=ctx.usertarget.avatar_url)

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
            return await ctx.send("You have not listened to any artists yet!")

        rows = []
        for i, artist in enumerate(artists, start=1):
            name = util.escape_md(artist["name"])
            plays = artist["playcount"]
            rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} : **{name}**")

        image_url = await scrape_artist_image(artists[0]["name"])
        image_colour = await util.color_from_image_url(image_url)
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique artists: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {formatted_timeframe} top artists",
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
            return await ctx.send("You have not listened to any albums yet!")

        rows = []
        for i, album in enumerate(albums, start=1):
            name = util.escape_md(album["name"])
            artist_name = util.escape_md(album["artist"]["name"])
            plays = album["playcount"]
            rows.append(
                f"`#{i:2}` **{plays}** {format_plays(plays)} : **{artist_name}** — ***{name}***"
            )

        image_url = albums[0]["image"][-1]["#text"]
        image_url_small = albums[0]["image"][1]["#text"]
        image_colour = await util.color_from_image_url(image_url_small)
        formatted_timeframe = humanized_period(arguments["period"]).capitalize()

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {formatted_timeframe} top albums",
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
            return await ctx.send("You have not listened to anything yet!")

        rows = []
        for i, track in enumerate(tracks, start=1):
            name = util.escape_md(track["name"])
            artist_name = util.escape_md(track["artist"]["name"])
            plays = track["playcount"]
            rows.append(
                f"`#{i:2}` **{plays}** {format_plays(plays)} : **{artist_name}** — ***{name}***"
            )

        trackdata = await api_request(
            {
                "user": ctx.username,
                "method": "track.getInfo",
                "artist": tracks[0]["artist"]["name"],
                "track": tracks[0]["name"],
            },
            ignore_errors=True,
        )
        content = discord.Embed()
        try:
            if trackdata is None:
                raise KeyError
            image_url = trackdata["track"]["album"]["image"][-1]["#text"]
            image_url_small = trackdata["track"]["album"]["image"][1]["#text"]
            image_colour = await util.color_from_image_url(image_url_small)
        except KeyError:
            image_url = await scrape_artist_image(tracks[0]["artist"]["name"])
            image_colour = await util.color_from_image_url(image_url)

        formatted_timeframe = humanized_period(arguments["period"]).capitalize()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)

        content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {formatted_timeframe} top tracks",
            icon_url=ctx.usertarget.avatar_url,
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=["recents", "re"])
    async def recent(self, ctx, size="15"):
        """
        Recently listened tracks.

        Usage:
            >fm recent [amount]
        """
        try:
            size = abs(int(size))
        except ValueError:
            size = 15

        data = await api_request(
            {"user": ctx.username, "method": "user.getrecenttracks", "limit": size}
        )
        user_attr = data["recenttracks"]["@attr"]
        tracks = data["recenttracks"]["track"]

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

        rows = []
        for i, track in enumerate(tracks):
            if i >= size:
                break
            name = util.escape_md(track["name"])
            artist_name = util.escape_md(track["artist"]["#text"])
            rows.append(f"**{artist_name}** — ***{name}***")

        image_url = tracks[0]["image"][-1]["#text"]
        image_url_small = tracks[0]["image"][1]["#text"]
        image_colour = await util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — Recent tracks", icon_url=ctx.usertarget.avatar_url,
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
            return await ctx.send(f":warning: Invalid timeframe `{timeframe}`")

        await listening_overview(ctx, timeframe)

    @fm.command()
    async def artist(self, ctx, timeframe, datatype, *, artistname=""):
        """
        Artist specific playcounts and info.

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
                return await ctx.send(":warning: Could not get currently playing artist!")

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

        image_colour = await util.color_from_image_url(artist["image_url"])

        rows = []
        for i, (name, playcount) in enumerate(data, start=1):
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{name}**")

        artistname = urllib.parse.quote_plus(artistname)
        content = discord.Embed()
        content.set_thumbnail(url=artist["image_url"])
        content.colour = int(image_colour, 16)
        content.set_author(
            name=f"{ctx.usertarget.name} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + f"Top 50 {datatype} for {artist['formatted_name']}",
            icon_url=ctx.usertarget.avatar_url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
            f"+{datatype}?date_preset={period_http_format(period)}",
        )

        await util.send_as_pages(ctx, content, rows)

    async def artist_top(self, ctx, period, artistname, datatype):
        """Scrape either top tracks or top albums from lastfm library page."""
        artistname = urllib.parse.quote_plus(artistname)
        async with aiohttp.ClientSession() as session:
            url = (
                f"https://last.fm/user/{ctx.username}/library/music/{artistname}/"
                f"+{datatype}?date_preset={period_http_format(period)}"
            )
            data = await fetch(session, url, handling="text")
            soup = BeautifulSoup(data, "html.parser")
            data = []
            try:
                chartlist = soup.find("tbody", {"data-playlisting-add-entries": ""})
            except ValueError:
                return None, []

            artist = {
                "image_url": soup.find("span", {"class": "library-header-image"})
                .find("img")
                .get("src")
                .replace("avatar70s", "avatar300s"),
                "formatted_name": soup.find("a", {"class": "library-header-crumb"}).text.strip(),
            }

            items = chartlist.findAll("tr", {"class": "chartlist-row"})
            for item in items:
                name = item.find("td", {"class": "chartlist-name"}).find("a").get("title")
                playcount = (
                    item.find("span", {"class": "chartlist-count-bar-value"})
                    .text.replace("scrobbles", "")
                    .replace("scrobble", "")
                    .strip()
                )
                data.append((name, int(playcount.replace(",", ""))))

            return artist, data

    async def artist_overview(self, ctx, period, artistname):
        """Overall artist view."""
        albums = []
        tracks = []
        metadata = [None, None, None]
        async with aiohttp.ClientSession() as session:
            url = (
                f"https://last.fm/user/{ctx.username}/library/music/"
                f"{urllib.parse.quote_plus(artistname)}"
                f"?date_preset={period_http_format(period)}"
            )
            data = await fetch(session, url, handling="text")
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

        image_colour = await util.color_from_image_url(artist["image_url"])
        similar, listeners = await get_similar_artists(artist["formatted_name"])
        artistname = urllib.parse.quote_plus(artistname)

        content = discord.Embed()
        content.set_thumbnail(url=artist["image_url"])
        content.colour = int(image_colour, 16)
        content.set_author(
            name=f"{ctx.usertarget.name} — {artist['formatted_name']} "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + "Overview",
            icon_url=ctx.usertarget.avatar_url,
            url=f"https://last.fm/user/{ctx.username}/library/music/{artistname}"
            f"?date_preset={period_http_format(period)}",
        )

        content.set_footer(text=f"{listeners} Listeners | Similar to: {', '.join(similar)}")

        crown_holder = db.query(
            """
            SELECT user_id FROM crowns WHERE guild_id = ? AND artist = ?
            """,
            (ctx.guild.id, artist["formatted_name"]),
        )

        if crown_holder is None or crown_holder[0][0] != ctx.usertarget.id:
            crownstate = ""
        else:
            crownstate = ":crown: "

        content.add_field(
            name="Scrobbles | Albums | Tracks",
            value=f"{crownstate}**{metadata[0]}** | **{metadata[1]}** | **{metadata[2]}**",
            inline=False,
        )

        content.add_field(
            name="Top albums",
            value="\n".join(
                f"`#{i:2}` **{item}** ({playcount})"
                for i, (item, playcount) in enumerate(albums, start=1)
            ),
            inline=True,
        )
        content.add_field(
            name="Top tracks",
            value="\n".join(
                f"`#{i:2}` **{item}** ({playcount})"
                for i, (item, playcount) in enumerate(tracks, start=1)
            ),
            inline=True,
        )
        await ctx.send(embed=content)

    async def fetch_color(self, session, album_art_id):
        async def get_image(url):
            async with session.get(url) as response:
                try:
                    return Image.open(io.BytesIO(await response.read()))
                except Exception:
                    return None

        image = None
        imagesize = 0
        while image is None or imagesize >= 3:
            image = await get_image(self.cover_base_urls[imagesize].format(album_art_id))
            imagesize += 1

        if image is None:
            return None

        colors = colorgram.extract(image, 1)
        dominant_color = colors[0]

        colorspace = dominant_color.rgb
        return (colorspace.r, colorspace.g, colorspace.b)

    async def get_all_albums(self, username):
        params = {
            "user": username,
            "method": "user.gettopalbums",
            "period": "overall",
            "limit": 500,
        }
        data = await api_request(dict(params, **{"page": 1}))
        topalbums = data["topalbums"]["album"]
        total_pages = int(data["topalbums"]["@attr"]["totalPages"])
        if total_pages > 1:
            tasks = []
            for i in range(2, total_pages + 1):
                tasks.append(api_request(dict(params, **{"page": i})))

            data = await asyncio.gather(*tasks)
            for page in data:
                topalbums += page["topalbums"]["album"]

        return topalbums

    @fm.command(aliases=["colourchart"])
    async def colorchart(self, ctx, colour: discord.Colour, size="3x3"):
        """
        Color based album chart.

        Usage:
            >fm colorchart #<hex color>
        """
        dim = size.split("x")
        width = int(dim[0])
        if len(dim) > 1:
            height = abs(int(dim[1]))
        else:
            height = abs(int(dim[0]))

        if width + height > 30:
            return await ctx.send(
                "Size is too big! Chart `width` + `height` total must not exceed `30`"
            )

        query_color = colour.to_rgb()

        topalbums = await self.get_all_albums(ctx.username)

        def string_to_rgb(rgbstring):
            values = [int(x) for x in rgbstring.strip("()").split(", ")]
            return tuple(values)

        albums = set()
        album_color_nodes = []
        for album in topalbums:
            album_art_id = album["image"][0]["#text"].split("/")[-1].split(".")[0]
            if album_art_id.strip() == "":
                continue

            albums.add(album_art_id)

        to_fetch = []
        albumcolors = db.album_colors_from_cache(list(albums))
        warn = None

        async with aiohttp.ClientSession() as session:
            for image_id, color in albumcolors:
                if color is None:
                    to_fetch.append(image_id)
                else:
                    color = string_to_rgb(color)
                    album_color_nodes.append(AlbumColorNode(color, image_id))

            if to_fetch:
                to_cache = []
                tasks = []
                for image_id in to_fetch:
                    tasks.append(self.fetch_color(session, image_id))

                if len(tasks) > 500:
                    warn = await ctx.send(
                        ":exclamation:Your library includes over 500 uncached album colours, "
                        "this might take a while <a:loading:643419324941336587>"
                    )

                colordata = await asyncio.gather(*tasks)
                for i, color in enumerate(colordata):
                    if color is not None:
                        to_cache.append((to_fetch[i], str(color)))
                        album_color_nodes.append(AlbumColorNode(color, to_fetch[i]))

                db.executemany("INSERT INTO album_color_cache VALUES(?, ?)", to_cache)

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

        await ctx.send(
            f"`{ctx.username} album color chart for {colour}`"
            + (
                f"\n`{len(to_fetch)} fetched, {len(albumcolors)-len(to_fetch)} from cache`"
                if to_fetch
                else ""
            ),
            file=discord.File(
                fp=buffer, filename=f"fmcolorchart_{ctx.username}_{str(colour).strip('#')}.jpeg"
            ),
        )

        if warn is not None:
            await warn.delete()

    @fm.command()
    async def chart(self, ctx, *args):
        """
        Visual chart of your top albums or artists.

        Usage:
            >fm chart [album | artist] [timeframe] [width]x[height]
        """
        arguments = parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 30:
            return await ctx.send(
                "Size is too big! Chart `width` + `height` total must not exceed `30`"
            )

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
                        f"{plays} {format_plays(plays)}<br>" f"{name} - {artist}",
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
                chart.append((track["image"][3]["#text"], f"{name} - {artist}"))

        buffer = await self.chart_factory(chart, arguments["width"], arguments["height"])

        await ctx.send(
            f"`{ctx.username} {humanized_period(arguments['period'])} "
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

        dimensions = (300 * width, 300 * height)
        replacements = {
            "WIDTH": dimensions[0],
            "HEIGHT": dimensions[1],
            "ARTS": img_divs,
        }

        def dictsub(m):
            return str(replacements[m.group().strip("%")])

        formatted_html = re.sub(r"%%(\S*)%%", dictsub, self.chart_html_flex)

        payload = {
            "html": formatted_html,
            "width": dimensions[0],
            "height": dimensions[1],
            "imageFormat": "jpeg",
            "quality": 70,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:3000/html", data=payload) as response:
                buffer = io.BytesIO(await response.read())

        return buffer

    @fm.command(aliases=["snp"])
    async def servernp(self, ctx):
        """What people on this server are listening to at the moment."""
        listeners = []
        tasks = []
        userslist = db.query(
            "SELECT user_id, lastfm_username FROM users where lastfm_username is not null"
        )
        for user in userslist if userslist is not None else []:
            lastfm_username = user[1]
            member = ctx.guild.get_member(user[0])
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
        for song, member in listeners:
            rows.append(f"{member.mention} **{util.escape_md(song.get('artist'))}** — ***{util.escape_md(song.get('name'))}***")

        content = discord.Embed()
        content.set_author(
            name=f"What is {ctx.guild.name} listening to?",
            icon_url=ctx.guild.icon_url_as(size=64),
        )
        content.colour = int(
            await util.color_from_image_url(str(ctx.guild.icon_url_as(size=64))), 16
        )
        content.set_footer(text=f"{total_listening} / {total_linked} Members")
        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=["wk"])
    @commands.guild_only()
    @commands.cooldown(2, 15, type=commands.BucketType.user)
    async def whoknows(self, ctx, *, artistname=None):
        """
        Check who has listened to a given artist the most.

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
                return await ctx.send(":warning: Could not get currently playing artist!")

        listeners = []
        tasks = []
        userslist = db.query(
            "SELECT user_id, lastfm_username FROM users where lastfm_username is not null"
            " AND LOWER(lastfm_username) not in (select username from lastfm_blacklist)"
        )
        for user in userslist if userslist is not None else []:
            lastfm_username = user[1]
            member = ctx.guild.get_member(user[0])
            if member is None:
                continue

            tasks.append(get_playcount(artistname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, name in data:
                artistname = name
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        artistname = util.escape_md(artistname)

        rows = []
        old_king = None
        new_king = None
        total = 0
        for i, (playcount, user) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            if i == 1:
                rank = ":crown:"
                old_king = db.add_crown(artistname, ctx.guild.id, user.id, playcount)
                if old_king is not None:
                    old_king = ctx.guild.get_member(old_king)
                new_king = user
            else:
                rank = f"`#{i:2}`"
            rows.append(f"{rank} **{user.name}** — **{playcount}** {format_plays(playcount)}")
            total += playcount

        if not rows:
            return await ctx.send(f"Nobody on this server has listened to **{artistname}**")

        content = discord.Embed(title=f"Who knows **{artistname}**?")
        image_url = await scrape_artist_image(artistname)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        image_colour = await util.color_from_image_url(image_url)
        content.colour = int(image_colour, 16)

        await util.send_as_pages(ctx, content, rows)
        if old_king is None or old_king.id == new_king.id:
            return

        await ctx.send(
            f"> **{new_king.name}** just stole the **{artistname}** crown from **{old_king.name}**"
        )

    @commands.command(aliases=["wkt", "whoknowst"])
    @commands.guild_only()
    @commands.cooldown(2, 15, type=commands.BucketType.user)
    async def whoknowstrack(self, ctx, *, track=None):
        """
        Check who has listened to a given song the most.

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
                return await ctx.send(":warning: Could not get currently playing track!")
        else:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send(":warning: Incorrect format! use `track | artist`")

        listeners = []
        tasks = []
        userslist = db.query(
            "SELECT user_id, lastfm_username FROM users where lastfm_username is not null"
            " AND LOWER(lastfm_username) not in (select username from lastfm_blacklist)"
        )
        for user in userslist if userslist is not None else []:
            lastfm_username = user[1]
            member = ctx.guild.get_member(user[0])
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
            rows.append(f"`#{i:2}` **{user.name}** — **{playcount}** {format_plays(playcount)}")
            total += playcount

        if not rows:
            return await ctx.send(
                f"Nobody on this server has listened to **{trackname}** by **{artistname}**"
            )

        if image_url is None:
            image_url = await scrape_artist_image(artistname)

        content = discord.Embed(title=f"Who knows **{trackname}**\n— by {artistname}")
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        image_colour = await util.color_from_image_url(image_url)
        content.colour = int(image_colour, 16)

        await util.send_as_pages(ctx, content, rows)

    @commands.command(aliases=["wka", "whoknowsa"])
    @commands.guild_only()
    @commands.cooldown(2, 15, type=commands.BucketType.user)
    async def whoknowsalbum(self, ctx, *, album):
        """
        Check who has listened to a given album the most.

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
                return await ctx.send(":warning: Could not get currently playing album!")
        else:
            try:
                albumname, artistname = [x.strip() for x in album.split("|")]
                if albumname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send(":warning: Incorrect format! use `album | artist`")

        listeners = []
        tasks = []
        userslist = db.query(
            "SELECT user_id, lastfm_username FROM users where lastfm_username is not null"
            " AND LOWER(lastfm_username) not in (select username from lastfm_blacklist)"
        )
        for user in userslist if userslist is not None else []:
            lastfm_username = user[1]
            member = ctx.guild.get_member(user[0])
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
            rows.append(f"`#{i:2}` **{user.name}** — **{playcount}** {format_plays(playcount)}")
            total += playcount

        if not rows:
            return await ctx.send(
                f"Nobody on this server has listened to **{albumname}** by **{artistname}**"
            )

        if image_url is None:
            image_url = await scrape_artist_image(artistname)

        content = discord.Embed(title=f"Who knows **{albumname}**\n— by {artistname}")
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        image_colour = await util.color_from_image_url(image_url)
        content.colour = int(image_colour, 16)

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    @commands.guild_only()
    async def crowns(self, ctx, *, user: discord.Member = None):
        """Check your artist crowns."""
        if user is None:
            user = ctx.author

        crownartists = db.query(
            """SELECT artist, playcount FROM crowns
            WHERE guild_id = ? AND user_id = ?""",
            (ctx.guild.id, user.id),
        )
        if crownartists is None:
            return await ctx.send(
                "You haven't acquired any crowns yet! "
                "Use the `>whoknows` command to claim crowns :crown:"
            )

        rows = []
        for artist, playcount in sorted(crownartists, key=itemgetter(1), reverse=True):
            rows.append(f"**{util.escape_md(artist)}** with **{playcount}** {format_plays(playcount)}")

        content = discord.Embed(
            title=f"Artist crowns for {user.name} — Total {len(crownartists)} crowns",
            color=discord.Color.gold(),
        )
        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def report(self, ctx, lastfm_username, *, reason):
        """Report someone who is botting plays."""
        lastfm_username = lastfm_username.strip("/").split("/")[-1]
        url = f"https://www.last.fm/user/{lastfm_username}"
        data = await api_request(
            {"user": lastfm_username, "method": "user.getinfo"}, ignore_errors=True
        )
        if data is None:
            return await ctx.send(f":warning: `{url}` is not a valid last.fm profile.")

        content = discord.Embed(title="New Last.fm user report")
        content.add_field(name="Profile", value=url)
        content.add_field(name="Reason", value=reason)

        content.description = (
            "Are you sure you want to report this lastfm account?"
            " Please note sending false reports **will get you blacklisted**."
        )

        # send confirmation message
        msg = await ctx.send(embed=content)

        async def confirm_ban():
            content.add_field(
                name="Reported by", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False
            )
            data = db.query(
                "select user_id from users where LOWER(lastfm_username) = ?",
                (lastfm_username.lower(),),
            )
            if data is not None:
                connected_accounts = []
                for x in data:
                    user = self.bot.get_user(x[0])
                    connected_accounts.append(f"{user} (`{user.id}`)")

                content.add_field(
                    name="Connected by", value=", ".join(connected_accounts), inline=False
                )
            content.set_footer(text=f">fmban {lastfm_username}")
            content.description = ""

            await self.send_report(ctx, content, lastfm_username)
            await msg.edit(content="📨 Report sent!", embed=None)

        async def cancel_ban():
            await msg.edit(content="❌ Report cancelled.", embed=None)

        functions = {"✅": confirm_ban, "❌": cancel_ban}

        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )

    async def send_report(self, ctx, content, lastfm_username):
        reports_channel = self.bot.get_channel(648153195356356619)  # 729736304677486723)
        if reports_channel is None:
            return await ctx.send(":warning: Something went wrong.")

        msg = await reports_channel.send(embed=content)

        async def confirm_ban():
            db.execute("INSERT INTO lastfm_blacklist VALUES(?)", (lastfm_username.lower(),))
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

    tracks = data["recenttracks"]["track"]
    if tracks:
        playing["artist"] = tracks[0]["artist"]["#text"]
        playing["album"] = tracks[0]["album"]["#text"]
        playing["track"] = tracks[0]["name"]

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
    except KeyError:
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
    except KeyError:
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
    except KeyError:
        count = 0

    name = data["artist"]["name"]

    if reference is None:
        return count
    else:
        return count, reference, name


async def get_np(username, ref):
    data = await api_request(
        {"method": "user.getrecenttracks", "user": username, "limit": 1}, ignore_errors=True,
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


async def get_similar_artists(artistname):
    similar = []
    url = f"https://last.fm/music/{artistname}"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        for artist in soup.findAll("h3", {"class": "artist-similar-artists-sidebar-item-name"}):
            similar.append(artist.find("a").text)
        listeners = (
            soup.find("li", {"class": "header-metadata-tnew-item--listeners"}).find("abbr").text
        )
    return similar, listeners


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
            elif a in ["ta", "topartists", "artists", "artist"]:
                parsed["method"] = "user.gettopartists"
                continue
            elif a in ["re", "recent", "recents"]:
                parsed["method"] = "user.getrecenttracks"
                continue

        if parsed["period"] is None:
            parsed["period"] = get_period(a, allow_custom=False)

    if parsed["period"] is None:
        parsed["period"] = "7day"
    if parsed["width"] is None:
        parsed["width"] = 3
        parsed["height"] = 3
    if parsed["method"] is None:
        parsed["method"] = "user.gettopalbums"
    parsed["amount"] = parsed["width"] * parsed["height"]
    return parsed


async def api_request(params, ignore_errors=False):
    """Get json data from the lastfm api."""
    url = "http://ws.audioscrobbler.com/2.0/"
    params["api_key"] = LASTFM_APPID
    params["format"] = "json"
    tries = 0
    max_tries = 3
    while True:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                try:
                    content = await response.json()
                    if response.status == 200 and content.get("error") is None:
                        return content
                    else:
                        if int(content.get("error")) in [6, 8]:
                            tries += 1
                            if tries < max_tries:
                                continue

                        if ignore_errors:
                            return None
                        else:
                            raise LastFMError(
                                f"Error {content.get('error')} : {content.get('message')}"
                            )

                except aiohttp.client_exceptions.ContentTypeError:
                    return None


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
    if group_by == "album":
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

    elif group_by == "track":
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

    elif group_by == "artist":
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


async def get_userinfo_embed(username):
    data = await api_request({"user": username, "method": "user.getinfo"}, ignore_errors=True)
    if data is None:
        return None

    username = data["user"]["name"]
    blacklisted = db.query(
        "select * from lastfm_blacklist where username = ?", (username.lower(),)
    )
    playcount = data["user"]["playcount"]
    profile_url = data["user"]["url"]
    profile_pic_url = data["user"]["image"][3]["#text"]
    timestamp = arrow.get(int(data["user"]["registered"]["unixtime"]))
    image_colour = await util.color_from_image_url(profile_pic_url)

    content = discord.Embed(title=f":cd: {username}")
    content.add_field(name="Last.fm profile", value=f"[Link]({profile_url})", inline=True)
    content.add_field(
        name="Registered",
        value=f"{timestamp.humanize()}\n{timestamp.format('DD/MM/YYYY')}",
        inline=True,
    )
    content.set_thumbnail(url=profile_pic_url)
    content.set_footer(text=f"Total plays: {playcount}")
    content.colour = int(image_colour, 16)
    if blacklisted is not None:
        content.description = ":warning: `This account is flagged as a cheater`"

    return content


async def scrape_artist_image(artist):
    url = f"https://www.last.fm/music/{urllib.parse.quote_plus(str(artist))}/+images"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url, handling="text")

    soup = BeautifulSoup(data, "html.parser")
    if soup is None:
        return ""

    image = soup.find("img", {"class": "image-list-image"})
    if image is None:
        try:
            image = soup.find("li", {"class": "image-list-item-wrapper"}).find("a").find("img")
        except AttributeError:
            return ""

    return image["src"].replace("/avatar170s/", "/300x300/") if image else ""


async def fetch(session, url, params=None, handling="json"):
    async with session.get(url, params=params) as response:
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
        else:
            soup = BeautifulSoup(data, "html.parser")
            imagedivs = soup.findAll("td", {"class": "chartlist-image"})
            images += [
                div.find("img")["src"].replace("/avatar70s/", "/300x300/") for div in imagedivs
            ]

    return images


async def username_to_ctx(ctx):
    if ctx.message.mentions:
        ctx.foreign_target = True
        ctx.usertarget = ctx.message.mentions[0]
    else:
        ctx.foreign_target = False
        ctx.usertarget = ctx.author

    userdata = db.userdata(ctx.usertarget.id)
    ctx.username = userdata.lastfm_username if userdata is not None else None
    if ctx.username is None and str(ctx.invoked_subcommand) not in ["fm set"]:
        if not ctx.foreign_target:
            raise util.ErrorMessage(
                f":warning: No last.fm username saved. "
                f"Please use `{ctx.prefix}fm set <lastfm username>`"
            )
        else:
            raise util.ErrorMessage(
                f":warning: **{ctx.usertarget.name}** has not saved their lastfm username."
            )


async def listening_overview(ctx, timeframe):
    rows = []
    async with aiohttp.ClientSession() as session:
        url = f"https://last.fm/user/{ctx.username}/listening-report/{timeframe}"
        data = await fetch(session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")

        if soup.find("a", {"class": "btn-subscribe"}) is not None:
            return await ctx.send(
                f":warning: Sorry, you can‘t see this because `{ctx.username}` doesn't have Last.fm Pro!"
            )

        if soup.find("section", {"class": "user-dashboard-nodata"}) is not None:
            return await ctx.send(
                f"`{ctx.username}` didn't listen to any music :("
            )

        # profile quick numbers
        scrobbles = (
            soup.find("div", {"class": "user-dashboard-data-point-scrobbles"})
            .find("a")
            .find("span", {"class": "js-ticker"})
            .get("data-value")
        )
        per_day = (
            soup.find("div", {"class": "user-dashboard-data-point-scrobbles-per-day"})
            .find("span", {"class": "js-ticker"})
            .get("data-value")
        )
        timetotal = (
            soup.find("div", {"class": "user-dashboard-data-point-total-listening"})
            .find("span", {"class": "duration-data"})
            .text.strip()
            .split()
        )
        if len(timetotal) > 3:
            timetotal = " ".join([timetotal[0], timetotal[2], timetotal[3], timetotal[5]])
        else:
            timetotal = " ".join([timetotal[0], timetotal[2]])

        # day/month chart
        barchart_tbody = soup.find("table", {"class": "js-scrobble-stats-history-data"}).find(
            "tbody"
        )
        if timeframe == "week":
            datefmt = "ddd, MMM Do"
        elif timeframe == "month":
            datefmt = "ddd, MMM Do"
        elif timeframe == "year":
            datefmt = "MMM"

        for tr in barchart_tbody.findAll("tr"):
            scrobble_td = tr.find("td", {"data-scrobble-count-tooltip": True})
            timestamp = int(scrobble_td.get("data-library-url").split("?from=")[1].split("&")[0])
            date = arrow.get(timestamp).format(fmt=datefmt)
            scrobble_count = scrobble_td.text.strip()
            rows.append(
                f"`{date}`: **{scrobble_count}** Scrobbles"
            )

        # top tags for the week
        top_tags = []
        piechart = False
        tags = soup.find("table", {"class": "js-tube-tags-table"})
        if tags is None:
            tags = soup.find("table", {"class": "js-top-tags-table"})
            piechart = True

        for tr in tags.find("tbody").findAll("tr"):
            td = tr.find("td", {"data-value": False}) if piechart else tr.findAll("td")[-1]
            tag = td.find("a").text.strip()
            top_tags.append(tag)

    content = discord.Embed(color=discord.Color.red())
    content.set_author(
        name=f"{ctx.username} | LAST.{timeframe.upper()}", icon_url=ctx.usertarget.avatar_url, url=url
    )
    content.description = "\n".join(rows)
    content.add_field(name="Top tags", value=", ".join(top_tags), inline=False)
    content.add_field(name="Scrobbles", value=scrobbles)
    content.add_field(name="Per day", value=per_day)
    content.add_field(name="Listening time", value=timetotal)
    if timeframe == "year":
        streak = (
            soup.find("section", {"class": "user-dashboard-longest-streak"})
            .find("span", {"class": "js-ticker"})
            .get("data-value")
        )
        content.add_field(name="Longest streak", value=f"{streak} days")
    await ctx.send(embed=content)


def remove_mentions(text):
    """Remove mentions from string."""
    return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()
