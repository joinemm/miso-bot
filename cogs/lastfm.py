import discord
import os
import asyncio
import json
import arrow
import aiohttp
import re
import math
import urllib.parse
from bs4 import BeautifulSoup
from operator import itemgetter
from discord.ext import commands
from concurrent.futures import ThreadPoolExecutor
from helpers import utilityfunctions as util
from data import database as db


LASTFM_APPID = os.environ.get('LASTFM_APIKEY')
LASTFM_TOKEN = os.environ.get('LASTFM_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_KEY')


class LastFMError(Exception):
    pass


class LastFm(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        with open("html/fm_chart_flex.html", "r", encoding="utf-8") as file:
            self.chart_html_flex = file.read().replace('\n', '')

    @commands.group(case_insensitive=True)
    async def fm(self, ctx):
        """Last.fm commands"""
        if ctx.message.mentions:
            ctx.foreign_target = True
            ctx.usertarget = ctx.message.mentions[0]
        else:
            ctx.foreign_target = False
            ctx.usertarget = ctx.author

        userdata = db.userdata(ctx.usertarget.id)
        ctx.username = userdata.lastfm_username if userdata is not None else None
        if ctx.username is None and str(ctx.invoked_subcommand) not in ['fm set']:
            if not ctx.foreign_target:
                return await ctx.send(f":warning: No last.fm username saved. Please use `{ctx.prefix}fm set <lastfm username>`")
            else:
                return await ctx.send(f":warning: **{ctx.usertarget.name}** has not saved their lastfm username.")

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
        """Lastfm profile."""
        await ctx.send(embed=await get_userinfo_embed(ctx.username))

    @fm.command(aliases=['yt'])
    async def youtube(self, ctx):
        """Search for currently playing song on youtube."""
        data = await api_request({
            "user": ctx.username,
            "method": "user.getrecenttracks",
            "limit": 1
        })

        tracks = data['recenttracks']['track']

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

        user_attr = data['recenttracks']['@attr']

        artist = tracks[0]['artist']['#text']
        track = tracks[0]['name']

        url = 'https://www.googleapis.com/youtube/v3/search'
        params = {
            'part': 'snippet',
            'type': 'video',
            'maxResults': 1,
            'q': f"{artist} {track}",
            'key': GOOGLE_API_KEY
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

        video_item = data.get('items')[0]
        video_url = f"https://youtube.com/watch?v={video_item['id']['videoId']}"

        state = "Most recent track"
        if '@attr' in tracks[0]:
            if "nowplaying" in tracks[0]['@attr']:
                state = "Now Playing"

        await ctx.send(f'**{user_attr["user"]} — {state}** :cd:\n{video_url}')

    @fm.command(aliases=['np'])
    async def nowplaying(self, ctx):
        """Currently playing song or most recent song."""
        data = await api_request({
            "user": ctx.username,
            "method": "user.getrecenttracks",
            "limit": 1
        })
        user_attr = data['recenttracks']['@attr']
        tracks = data['recenttracks']['track']

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

        artist = tracks[0]['artist']['#text']
        album = tracks[0]['album']['#text']
        track = tracks[0]['name']
        image_url = tracks[0]['image'][-1]['#text']
        image_url_small = tracks[0]['image'][1]['#text']
        image_colour = await util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.description = f"**{util.escape_md(album)}**"
        content.title = f"**{util.escape_md(artist)}** — ***{util.escape_md(track)} ***"
        content.set_thumbnail(url=image_url)

        # tags and playcount
        trackdata = await api_request({
            "user": ctx.username,
            "method": "track.getInfo",
            "artist": artist,
            "track": track
        })
        if trackdata is not None:
            tags = []
            try:
                trackdata = trackdata['track']
                playcount = int(trackdata['userplaycount'])
                if playcount > 0:
                    content.description += f"\n> {playcount} {format_plays(playcount)}"
                for tag in trackdata['toptags']['tag']:
                    tags.append(tag['name'])
                content.set_footer(text=", ".join(tags))
            except KeyError:
                pass

        # play state
        state = "— Most recent track"
        if '@attr' in tracks[0]:
            if "nowplaying" in tracks[0]['@attr']:
                state = "— Now Playing"

        content.set_author(
            name=f"{user_attr['user']} {state}",
            icon_url=ctx.usertarget.avatar_url
        )

        await ctx.send(embed=content)

    @fm.command(aliases=['ta'])
    async def topartists(self, ctx, *args):
        """Most listened artists.

        Usage:
            >fm topartists [timeframe] [amount]
        """
        arguments = parse_arguments(args)
        if arguments['period'] == 'today':
            data = await custom_period(ctx.username, 'artist')
        else:
            data = await api_request({
                "user": ctx.username,
                "method": "user.gettopartists",
                "period": arguments['period'],
                "limit": arguments['amount']
            })
        user_attr = data['topartists']['@attr']
        artists = data['topartists']['artist'][:arguments['amount']]

        if not artists:
            return await ctx.send("You have not listened to any artists yet!")

        rows = []
        for i, artist in enumerate(artists, start=1):
            name = util.escape_md(artist['name'])
            plays = artist['playcount']
            rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} : **{name}**")

        image_url = await scrape_artist_image(artists[0]['name'])
        image_colour = await util.color_from_image_url(image_url)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique artists: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top artists",
            icon_url=ctx.usertarget.avatar_url
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=['talb'])
    async def topalbums(self, ctx, *args):
        """Most listened albums.

        Usage:
            >fm topalbums [timeframe] [amount]
        """
        arguments = parse_arguments(args)
        if arguments['period'] == 'today':
            data = await custom_period(ctx.username, 'album')
        else:
            data = await api_request({
                "user": ctx.username,
                "method": "user.gettopalbums",
                "period": arguments['period'],
                "limit": arguments['amount']
            })
        user_attr = data['topalbums']['@attr']
        albums = data['topalbums']['album'][:arguments['amount']]

        if not albums:
            return await ctx.send("You have not listened to any albums yet!")

        rows = []
        for i, album in enumerate(albums, start=1):
            name = util.escape_md(album['name'])
            artist_name = util.escape_md(album['artist']['name'])
            plays = album['playcount']
            rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} : **{artist_name}** — ***{name}***")

        image_url = albums[0]['image'][-1]['#text']
        image_url_small = albums[0]['image'][1]['#text']
        image_colour = await util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top albums",
            icon_url=ctx.usertarget.avatar_url
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=['tt'])
    async def toptracks(self, ctx, *args):
        """Most listened tracks.

        Usage:
            >fm toptracks [timeframe] [amount]
        """
        arguments = parse_arguments(args)
        if arguments['period'] == 'today':
            data = await custom_period(ctx.username, 'track')
        else:
            data = await api_request({
                "user": ctx.username,
                "method": "user.gettoptracks",
                "period": arguments['period'],
                "limit": arguments['amount']
            })
        user_attr = data['toptracks']['@attr']
        tracks = data['toptracks']['track'][:arguments['amount']]

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

        rows = []
        for i, track in enumerate(tracks, start=1):
            name = util.escape_md(track['name'])
            artist_name = util.escape_md(track['artist']['name'])
            plays = track['playcount']
            rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} : **{artist_name}** — ***{name}***")

        trackdata = await api_request({
            "user": ctx.username,
            "method": "track.getInfo",
            "artist": tracks[0]['artist']['name'],
            "track": tracks[0]['name']
        })
        content = discord.Embed()
        try:
            image_url = trackdata['track']['album']['image'][-1]['#text']
            image_url_small = trackdata['track']['album']['image'][1]['#text']
            image_colour = await util.color_from_image_url(image_url_small)
        except KeyError:
            image_url = await scrape_artist_image(tracks[0]['artist']['name'])
            image_colour = await util.color_from_image_url(image_url)

        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)

        content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top tracks",
            icon_url=ctx.usertarget.avatar_url
        )

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=['recents', 're'])
    async def recent(self, ctx, size: int=15):
        """Recently listened tracks.

        Usage:
            >fm recent [amount]
        """
        data = await api_request({
            "user": ctx.username,
            "method": "user.getrecenttracks",
            "limit": size
        })
        user_attr = data['recenttracks']['@attr']
        tracks = data['recenttracks']['track']

        if not tracks:
            return await ctx.send("You have not listened to anything yet!")

        rows = []
        for i, track in enumerate(tracks):
            if i >= size:
                break
            name = util.escape_md(track['name'])
            artist_name = util.escape_md(track['artist']['#text'])
            rows.append(f"**{artist_name}** — ***{name}***")

        image_url = tracks[0]['image'][-1]['#text']
        image_url_small = tracks[0]['image'][1]['#text']
        image_colour = await util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
        content.set_author(name=f"{user_attr['user']} — Recent tracks", icon_url=ctx.usertarget.avatar_url)

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command()
    async def artist(self, ctx, timeframe, datatype, *, artistname=""):
        """Your top tracks or albums for specific artist.

        Usage:
            >fm artist [timeframe] toptracks <artist name>
            >fm artist [timeframe] topalbums <artist name>
        """
        period = get_period(timeframe)
        if period is None:
            artistname = " ".join([datatype, artistname]).strip()
            datatype = timeframe
            period = 'overall'
        if datatype in ["toptracks", "tt", "tracks", "track"]:
            method = "user.gettoptracks"
            path = ["toptracks", "track"]
        elif datatype in ["topalbums", "talb", "albums", "album"]:
            method = "user.gettopalbums"
            path = ["topalbums", "album"]
        else:
            return await util.send_command_help(ctx)

        if artistname == "":
            return await ctx.send("Missing artist name!")

        async def extract_songs(items):
            songs = []
            for item in items:
                item_artist = item['artist']['name']
                if item_artist.casefold() == artistname.casefold():
                    songs.append((item['name'], int(item['playcount'])))
            return songs

        data = await api_request({
            "method": method,
            "user": ctx.username,
            "limit": 200,
            "period": period
        })
        total_pages = int(data[path[0]]['@attr']['totalPages'])
        artist_data = await extract_songs(data[path[0]][path[1]])
        username = data[path[0]]["@attr"]['user']

        if total_pages > 1:
            tasks = []
            for i in range(2, total_pages+1):
                params = {
                    "method": method,
                    "user": ctx.username,
                    "limit": 200,
                    "period": period,
                    "page": i
                }
                tasks.append(api_request(params))

            data = await asyncio.gather(*tasks)
            extraction_tasks = []
            for datapage in data:
                extraction_tasks.append(extract_songs(datapage[path[0]][path[1]]))

            artist_data += sum(await asyncio.gather(*extraction_tasks), [])

        if not artist_data:
            if period == 'overall':
                return await ctx.send(f"You have never listened to **{artistname}**!")
            else:
                return await ctx.send(f"You have not listened to **{artistname}** in the past {period}s!")

        artist_info = await api_request({
            "method": "artist.getinfo",
            "artist": artistname
        })
        artist_info = artist_info.get('artist')
        image_url = await scrape_artist_image(artistname)
        formatted_name = artist_info['name']

        image_colour = await util.color_from_image_url(image_url)

        content = discord.Embed()
        content.set_thumbnail(url=image_url)
        content.colour = int(image_colour, 16)

        rows = []
        total_plays = 0
        for i, (name, playcount) in enumerate(artist_data, start=1):
            line = f"`#{i:2}` **{playcount}** {format_plays(total_plays)} — **{name}**"
            total_plays += playcount
            rows.append(line)

        content.set_footer(text=f"Total {total_plays} {format_plays(total_plays)}")
        content.set_author(name=f"{username} — " + (f"{humanized_period(period)} " if period != 'overall' else '') + \
                                f"top {'tracks' if method == 'user.gettoptracks' else 'albums'}" \
                                f" for {formatted_name}", icon_url=ctx.usertarget.avatar_url)

        await util.send_as_pages(ctx, content, rows)

    @fm.command()
    async def chart(self, ctx, *args):
        """Visual chart of your top albums or artists.

        Usage:
            >fm chart [album | artist] [timeframe] [width]x[height]
        """
        arguments = parse_chart_arguments(args)
        if arguments['width'] + arguments['height'] > 31:
            return await ctx.send("Size is too big! Chart `width` + `height` total must not exceed `31`")

        data = await api_request({
            "user": ctx.username,
            "method": arguments['method'],
            "period": arguments['period'],
            "limit": arguments['amount']
        })
        chart = []
        chart_type = "ERROR"
        if arguments['method'] == "user.gettopalbums":
            chart_type = "top album"
            albums = data['topalbums']['album']
            for album in albums:
                name = album['name']
                artist = album['artist']['name']
                plays = album['playcount']
                chart.append((f"{plays} {format_plays(plays)}<br>"
                              f"{name} - {artist}", album['image'][3]['#text']))

        elif arguments['method'] == "user.gettopartists":
            chart_type = "top artist"
            artists = data['topartists']['artist']
            scraped_images = await scrape_artists_for_chart(ctx.username, arguments['period'], arguments['amount'])
            for i, artist in enumerate(artists):
                name = artist['name']
                plays = artist['playcount']
                chart.append((f"{plays} {format_plays(plays)}<br>{name}", scraped_images[i]))

        elif arguments['method'] == "user.getrecenttracks":
            chart_type = "recent tracks"
            tracks = data['recenttracks']['track']
            for track in tracks:
                name = track['name']
                artist = track['artist']['#text']
                chart.append((f"{name} - {artist}", track['image'][3]['#text']))

        img_divs = ''.join(
            ['<div class="art"><img src="{' + str(i) + '[1]}"><p class="label">{'
            + str(i) + '[0]}</p></div>' for i in range(len(chart))]
        ).format(*chart)

        dimensions = (300*arguments['width'], 300*arguments['height'])
        replacements = {
            'WIDTH': dimensions[0],
            'HEIGHT': dimensions[1],
            'ARTS': img_divs
        }

        def dictsub(m):
            return str(replacements[m.group().strip('%')])

        formatted_html = re.sub(r'%%(\S*)%%', dictsub, self.chart_html_flex)

        payload = {
            'html': formatted_html,
            'width': dimensions[0],
            'height': dimensions[1],
            'imageFormat': 'jpeg',
            'quality': 70
        }
        async with aiohttp.ClientSession() as session:
            async with session.post('http://localhost:3000/html', data=payload) as response:
                with open("downloads/fmchart.jpeg", "wb") as f:
                    while True:
                        block = await response.content.read(1024)
                        if not block:
                            break
                        f.write(block)

        with open("downloads/fmchart.jpeg", "rb") as img:
            await ctx.send(
                f"`{ctx.username} {humanized_period(arguments['period'])} "
                f"{dimensions[0]//300}x{dimensions[1]//300} {chart_type} chart`",
                file=discord.File(img)
            )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(2, 10, type=commands.BucketType.user)
    async def whoknows(self, ctx, *, artistname):
        """Check who has listened to a given artist the most.

        Usage:
            >whoknows <artist name>
        """
        listeners = []
        tasks = []
        userslist = db.query("SELECT user_id, lastfm_username FROM users where lastfm_username is not null")
        for user in (userslist if userslist is not None else []):
            lastfm_username = user[1]
            member = ctx.guild.get_member(user[0])
            if member is None:
                continue

            tasks.append(get_playcount(artistname, lastfm_username, member))

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, name in data:
                if playcount > 0:
                    artistname = name
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        rows = []
        old_king = None
        new_king = None
        total = 0
        for i, (playcount, user) in enumerate(sorted(listeners, key=lambda p: p[0], reverse=True), start=1):
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
        if len(listeners) > 1:
            content.set_footer(text=f"Collective plays: {total}")

        image_colour = await util.color_from_image_url(image_url)
        content.colour = int(image_colour, 16)

        await util.send_as_pages(ctx, content, rows)
        if old_king is not None and not (old_king.id == new_king.id):
            await ctx.send(f"> **{new_king.name}** just stole the **{artistname}** crown from **{old_king.name}**")

    @commands.command()
    @commands.guild_only()
    async def crowns(self, ctx):
        """Check your artist crowns."""
        crownartists = db.query("""SELECT artist, playcount FROM crowns WHERE guild_id = ? AND user_id = ?""",
                                (ctx.guild.id, ctx.usertarget.id))
        if crownartists is None:
            return await ctx.send("You haven't acquired any crowns yet! Use the `>whoknows` command to claim crowns :crown:")

        rows = []
        for artist, playcount in sorted(crownartists, key=itemgetter(1), reverse=True):
            rows.append(f"**{artist}** with **{playcount}** {format_plays(playcount)}")

        content = discord.Embed(
            title=f"Artist crowns for {ctx.usertarget.name} — Total {len(crownartists)} crowns",
            color=discord.Color.gold()
        )
        await util.send_as_pages(ctx, content, rows)


def setup(bot):
    bot.add_cog(LastFm(bot))


def format_plays(amount):
    if amount == 1:
        return 'play'
    else:
        return 'plays'


async def get_playcount(artist, username, reference=None):
    data = await api_request({
        "method": "artist.getinfo",
        "user": username,
        "artist": artist,
        "autocorrect": 1
    })
    try:
        count = int(data['artist']['stats']['userplaycount'])
        name = data['artist']['name']
    except KeyError:
        count = 0
        name = None

    if reference is None:
        return count
    else:
        return count, reference, name


def get_period(timeframe):
    if timeframe in ['day', 'today', '1day', '24h']:
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
    parsed = {
        "period": None,
        "amount": None
    }
    for a in args:
        if parsed['amount'] is None:
            try:
                parsed['amount'] = int(a)
                continue
            except ValueError:
                pass
        if parsed['period'] is None:
            parsed['period'] = get_period(a)

    if parsed['period'] is None:
        parsed['period'] = 'overall'
    if parsed['amount'] is None:
        parsed['amount'] = 15
    return parsed


def parse_chart_arguments(args):
    parsed = {
        "period": None,
        "amount": None,
        "width": None,
        "height": None,
        "method": None,
        "path": None
    }
    for a in args:
        a = a.lower()
        if parsed['amount'] is None:
            try:
                size = a.split('x')
                parsed['width'] = int(size[0])
                if len(size) > 1:
                    parsed['height'] = int(size[1])
                else:
                    parsed['height'] = int(size[0])
                continue
            except ValueError:
                pass

        if parsed['method'] is None:
            if a in ['talb', 'topalbums', 'albums', 'album']:
                parsed['method'] = "user.gettopalbums"
                continue
            elif a in ['ta', 'topartists', 'artists', 'artist']:
                parsed['method'] = "user.gettopartists"
                continue
            elif a in ['re', 'recent', 'recents']:
                parsed['method'] = "user.getrecenttracks"
                continue

        if parsed['period'] is None:
            parsed['period'] = get_period(a)

    if parsed['period'] is None:
        parsed['period'] = '7day'
    if parsed['width'] is None:
        parsed['width'] = 3
        parsed['height'] = 3
    if parsed['method'] is None:
        parsed['method'] = "user.gettopalbums"
    parsed['amount'] = parsed['width'] * parsed['height']
    return parsed


async def api_request(params):
    """Get json data from the lastfm api"""
    url = "http://ws.audioscrobbler.com/2.0/"
    params['api_key'] = LASTFM_APPID
    params['format'] = 'json'
    tries = 0
    max_tries = 2
    trying = True
    while trying:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                try:
                    content = await response.json()
                    if response.status == 200:
                        trying = False
                        return content
                    else:
                        if int(content.get('error')) in [6, 8]:
                            tries += 1
                            if tries < max_tries:
                                print("Error occured. Trying again...")
                                continue
                            else:
                                trying = False

                        raise LastFMError(f"Error {content.get('error')} : {content.get('message')}")

                except aiohttp.client_exceptions.ContentTypeError:
                    return None


async def custom_period(user, group_by, shift_hours=24):
    """parse recent tracks to get custom duration data (24 hour)"""
    limit_timestamp = arrow.utcnow().shift(hours=-shift_hours)
    data = await api_request({
        "user": user,
        "method": "user.getrecenttracks",
        "from": limit_timestamp.timestamp,
        "limit": 200
    })
    loops = int(data['recenttracks']['@attr']['totalPages'])
    if loops > 1:
        for i in range(2, loops+1):
            newdata = await api_request({
                "user": user,
                "method": "user.getrecenttracks",
                "from": limit_timestamp.timestamp,
                "limit": 200,
                "page": i
            })
            data['recenttracks']['track'] += newdata['recenttracks']['track']

    formatted_data = {}
    if group_by == "album":
        for track in data['recenttracks']['track']:
            album_name = track['album']['#text']
            artist_name = track['artist']['#text']
            if (artist_name, album_name) in formatted_data:
                formatted_data[(artist_name, album_name)]['playcount'] += 1
            else:
                formatted_data[(artist_name, album_name)] = {
                    "playcount": 1,
                    "artist": {'name': artist_name},
                    "name": album_name,
                    "image": track['image']
                }

        albumsdata = sorted(formatted_data.values(), key=lambda x: x['playcount'], reverse=True)
        return {"topalbums": {
            "album": albumsdata,
            "@attr": {
                "user": data['recenttracks']['@attr']['user'],
                "total": len(formatted_data.values())
            }
        }}

    elif group_by == "track":
        for track in data['recenttracks']['track']:
            track_name = track['name']
            artist_name = track['artist']['#text']
            if (track_name, artist_name) in formatted_data:
                formatted_data[(track_name, artist_name)]['playcount'] += 1
            else:
                formatted_data[(track_name, artist_name)] = {
                    "playcount": 1,
                    "artist": {'name': artist_name},
                    "name": track_name,
                    "image": track['image']
                }

        tracksdata = sorted(formatted_data.values(), key=lambda x: x['playcount'], reverse=True)
        return {"toptracks": {
            "track": tracksdata,
            "@attr": {
                "user": data['recenttracks']['@attr']['user'],
                "total": len(formatted_data.values())
            }
        }}

    elif group_by == "artist":
        for track in data['recenttracks']['track']:
            artist_name = track['artist']['#text']
            if artist_name in formatted_data:
                formatted_data[artist_name]['playcount'] += 1
            else:
                formatted_data[artist_name] = {
                    "playcount": 1,
                    "name": artist_name,
                    "image": track['image']
                }

        artistdata = sorted(formatted_data.values(), key=lambda x: x['playcount'], reverse=True)
        return {"topartists": {
            "artist": artistdata,
            "@attr": {
                "user": data['recenttracks']['@attr']['user'],
                "total": len(formatted_data.values())
            }
        }}



async def get_userinfo_embed(username):
    data = await api_request({
        "user": username,
        "method": "user.getinfo"
    })
    if data is None:
        return None

    username = data['user']['name']
    playcount = data['user']['playcount']
    profile_url = data['user']['url']
    profile_pic_url = data['user']['image'][3]['#text']
    timestamp = arrow.get(int(data['user']['registered']['unixtime']))
    image_colour = await util.color_from_image_url(profile_pic_url)

    content = discord.Embed(title=f":cd: {username}")
    content.add_field(
        name="Last.fm profile",
        value=f"[Link]({profile_url})",
        inline=True
    )
    content.add_field(
        name="Registered",
        value=f"{timestamp.humanize()}\n{timestamp.format('DD/MM/YYYY')}",
        inline=True
    )
    content.set_thumbnail(url=profile_pic_url)
    content.set_footer(text=f"Total plays: {playcount}")
    return content


async def scrape_artist_image(artist):
    url = f"https://www.last.fm/music/{urllib.parse.quote_plus(artist)}/+images"
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, url, handling='text')

    soup = BeautifulSoup(data, 'html.parser')
    if soup is None:
        return ""
    image = soup.find("img", {"class": "image-list-image"})
    if image is None:
        try:
            image = soup.find("li", {"class": "image-list-item-wrapper"}).find("a").find("img")
        except AttributeError:
            return ""
    return image['src'].replace("/avatar170s/", "/300x300/") if image else ""


async def fetch(session, url, params={}, handling='json'):
    async with session.get(url, params=params) as response:
        if handling == 'json':
            return await response.json()
        elif handling == 'text':
            return await response.text()
        else:
            return await response


async def scrape_artists_for_chart(username, period, amount):
    period_format_map = {
        "7day": "LAST_7_DAYS",
        "1month": "LAST_30_DAYS",
        "3month": "LAST_90_DAYS",
        "6month": "LAST_180_DAYS",
        "12month": "LAST_365_DAYS",
        "overall": "ALL"
    }
    tasks = []
    url = f"https://www.last.fm/user/{username}/library/artists"
    async with aiohttp.ClientSession() as session:
        for i in range(1, math.ceil(amount/50)+1):
            params = {
                'date_preset': period_format_map[period],
                'page': i
            }
            task = asyncio.ensure_future(fetch(session, url, params, handling='text'))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

    images = []
    for data in responses:
        if len(images) >= amount:
            break
        else:
            soup = BeautifulSoup(data, 'html.parser')
            imagedivs = soup.findAll("td", {"class": "chartlist-image"})
            images += [div.find("img")['src'].replace("/avatar70s/", "/300x300/") for div in imagedivs]

    return images

