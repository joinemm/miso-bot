import discord
from discord.ext import commands
import requests
import googlesearch
from bs4 import BeautifulSoup
import json
import asyncio
import random
import re
import wikipedia
import tweepy
from tweepy import OAuthHandler
import os
# import arrow
from helpers import utilityfunctions as util
import copy
import spotipy
from spotipy import util as spotipyutil

TWITTER_CKEY = os.environ.get('TWITTER_CONSUMER_KEY')
TWITTER_CSECRET = os.environ.get('TWITTER_CONSUMER_SECRET')
IG_COOKIE = os.environ.get('IG_COOKIE')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')


class Media(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.twt = tweepy.API(OAuthHandler(TWITTER_CKEY, TWITTER_CSECRET))

    @commands.command(aliases=["colour"])
    async def color(self, ctx, *sources):
        """Get a hex color, the color of discord user, or a random color."""
        if not sources:
            return await ctx.send("Missing color source. Valid color sources are:\n"
                                  "`[@mention | @rolemention | hex | image_url | random]`\n"
                                  "These can be chained together to create patterns")

        colors = []
        i = 0
        while i < len(sources):
            source = sources[i]
            if source.lower() == "random":
                try:
                    amount = int(sources[i+1])
                    i += 1
                except (IndexError, ValueError):
                    amount = 1
                for x in range(amount):
                    colors.append("{:06x}".format(random.randint(0, 0xFFFFFF)))
                i += 1
                continue

            role_or_user = await util.get_member(ctx, source) or await util.get_role(ctx, source)
            if role_or_user is not None:
                colors.append(str(role_or_user.color).strip("#"))
                i += 1
                continue

            if 'http' in source or 'https' in source:
                url_color = util.color_from_image_url(source)
                if url_color is not None:
                    colors.append(url_color)
                    i += 1
                    continue

            color = await util.get_color(ctx, source)
            if color is not None:
                colors.append(str(color))
                i += 1
                continue

            await ctx.send(f"Could not parse input [{source}]")
            i += 1

        content = discord.Embed(colour=await util.get_color(ctx, colors[0]))
        if len(colors) == 1:
            color = colors[0]
            url = f"http://thecolorapi.com/id?hex={color}&format=json"
            response = requests.get(url=url)
            response.raise_for_status()
            data = json.loads(response.content.decode('utf-8'))
            hexvalue = data['hex']['value']
            rgbvalue = data['rgb']['value']
            name = data['name']['value']
            image_url = f"http://www.colourlovers.com/img/{color}/200/200/color.png"
            content.title = name
            content.description = f"{hexvalue} - {rgbvalue}"
        else:
            if len(colors) > 12:
                await ctx.send("Maximum amount of colors is 12, ignoring rest...")
                await ctx.trigger_typing()
                colors = colors[:12]
            palette = ""
            for color in colors:
                try:
                    url = f"http://thecolorapi.com/id?hex={color}&format=json"
                    response = requests.get(url=url)
                    response.raise_for_status()
                    data = json.loads(response.content.decode('utf-8'))
                    hexvalue = data['hex']['value']
                    # rgbvalue = data['rgb']['value']
                    name = data['name']['value']
                    content.add_field(name=name, value=f"{hexvalue}")
                    palette += color + "/"
                except Exception as e:
                    print(e)
                    await ctx.send(f"Skipping color {color} because of error `{e}`")
            image_url = f"https://www.colourlovers.com/paletteImg/{palette}palette.png"

        content.set_image(url=image_url)
        await ctx.send(embed=content)

    @commands.command()
    async def spotify(self, ctx, url, amount=15):
        """Analyze a spotify playlist"""
        try:
            if url.startswith("https://open."):
                # its playlist link
                user_id = re.search(r'user/(.*?)/playlist', url).group(1)
                playlist_id = re.search(r'playlist/(.*?)\?', url).group(1)
            else:
                # its URI (probably)
                data = url.split(":")
                playlist_id = data[4]
                user_id = data[2]
        except IndexError:
            return await ctx.send("**ERROR:** Invalid playlist url/URI.\n"
                                  "How to get Spotify URI? Right click playlist -> `Share` -> `Copy Spotify URI`")

        if amount > 50:
            amount = 50

        token = spotipyutil.oauth2.SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID,
                                                            client_secret=SPOTIFY_CLIENT_SECRET)
        cache_token = token.get_access_token()
        spotify = spotipy.Spotify(cache_token)
        tracks_per_request = 100
        results = []

        playlist_data = spotify.user_playlist(user_id, playlist_id)
        playlist_name = playlist_data['name']
        playlist_owner = playlist_data['owner']['display_name']
        playlist_image = playlist_data['images'][0]['url']

        this_request_results = spotify.user_playlist_tracks(user_id, playlist_id, limit=tracks_per_request,
                                                            offset=0)["items"]
        for i in range(len(this_request_results)):
            results.append(this_request_results[i])
        while len(this_request_results) >= tracks_per_request:
            this_request_results = spotify.user_playlist_tracks(user_id, playlist_id, limit=tracks_per_request,
                                                                offset=len(results))["items"]
            for i in range(len(this_request_results)):
                results.append(this_request_results[i])

        artists_dict = {}
        total = 0
        for i in range(len(results)):
            artist = results[i]["track"]["artists"][0]["name"]
            if artist in artists_dict:
                artists_dict[artist] += 1
            else:
                artists_dict[artist] = 1
            total += 1

        count = 0
        description = ""
        for item in sorted(artists_dict.items(), key=lambda v: v[1], reverse=True):
            if count < amount:
                percentage = (item[1] / total) * 100
                description += f"**{item[1]}** tracks ({percentage:.2f}%) — **{item[0]}**\n"
                count += 1
            else:
                break

        message = discord.Embed(colour=discord.Colour.green())
        message.set_author(name=f"{playlist_name} · by {playlist_owner}",
                           icon_url="https://i.imgur.com/tN20ywg.png")
        message.set_thumbnail(url=playlist_image)
        message.title = "Artist distribution:"
        message.set_footer(text=f"Total: {total} tracks from {len(artists_dict)} different artists")
        message.description = description

        await ctx.send(embed=message)

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx, *, query):
        """Search youtube for the given search query and return first result"""
        response = requests.get(f"http://www.youtube.com/results?search_query={query}")
        video_ids = set(re.findall('watch\\?v=(.{11})', response.content.decode('utf-8')))
        results = util.TwoWayIterator([f'http://www.youtube.com/watch?v={x}' for x in video_ids])

        msg = await ctx.send(f"**#1:** {results.current()}")

        async def next_link():
            link = results.next()
            await msg.edit(content=f"**#{results.index+1}:** {link}", embed=None)

        async def prev_link():
            link = results.previous()
            await msg.edit(content=f"**#{results.index+1}:** {link}", embed=None)

        async def done():
            return True

        functions = {"⬅": prev_link,
                     "➡": next_link,
                     "✅": done}

        await util.reaction_buttons(ctx, msg, functions, only_author=True)

    @commands.command()
    async def ig(self, ctx, url):
        """Get the source images from an instagram post"""
        if "/" not in url:
            url = f"https://www.instagram.com/p/{url}"

        headers = {"Accept": "*/*",
                   "Host": "www.instagram.com",
                   "Accept-Encoding": "gzip, deflate, br",
                   "Accept-Language": "en,en-US;q=0.5",
                   "Connection": "keep-alive",
                   "DNT": "1",
                   "Upgrade-Insecure-Requests": "1",
                   "Cookie": IG_COOKIE,
                   "User-Agent": 'Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0'}

        response = requests.get(url + "/?__a=1", headers=headers)
        response.raise_for_status()
        data = json.loads(response.content.decode('utf-8'))['graphql']['shortcode_media']
        medias = []
        try:
            for x in data['edge_sidecar_to_children']['edges']:
                medias.append(x['node'])
        except KeyError:
            medias.append(data)

        avatar_url = data['owner']['profile_pic_url']
        username = data['owner']['username']
        content = discord.Embed(color=discord.Color.magenta())
        content.set_author(name='@' + username, url=url, icon_url=avatar_url)

        if medias:
            # there are images
            for medianode in medias:
                if medianode.get('is_video'):
                    await ctx.send(embed=content)
                    await ctx.send(medianode.get('video_url'))
                else:
                    content.set_image(url=medianode.get('display_url'))
                    await ctx.send(embed=content)
                content.description = None
                content._author = None

        else:
            await ctx.send("No media found")

    @commands.command()
    async def twitter(self, ctx, tweet_url, delete=None):
        """Get all the images from a tweet"""
        if "status" in tweet_url:
            tweet_url = re.search(r'status/(\d+)', tweet_url).group(1)
        tweet = self.twt.get_status(tweet_url, tweet_mode='extended')

        media_files = []
        try:
            media = tweet.extended_entities.get('media', [])
        except AttributeError:
            await ctx.send("This tweet appears to contain no media!")
            return
        hashtags = []
        for hashtag in tweet.entities.get('hashtags', []):
            hashtags.append(f"#{hashtag['text']}")
        for i in range(len(media)):
            media_url = media[i]['media_url']
            video_url = None
            if not media[i]['type'] == "photo":
                video_urls = media[i]['video_info']['variants']
                largest_rate = 0
                for x in range(len(video_urls)):
                    if video_urls[x]['content_type'] == "video/mp4":
                        if video_urls[x]['bitrate'] > largest_rate:
                            largest_rate = video_urls[x]['bitrate']
                            video_url = video_urls[x]['url']
                            media_url = video_urls[x]['url']
            media_files.append((" ".join(hashtags), media_url, video_url))

        content = discord.Embed(colour=int(tweet.user.profile_link_color, 16))
        content.set_author(icon_url=tweet.user.profile_image_url,
                           name=f"@{tweet.user.screen_name}\n{media_files[0][0]}",
                           url=f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}")

        for file in media_files:
            content.set_image(url=file[1] + ":orig")
            await ctx.send(embed=content)

            if file[2] is not None:
                # contains a video/gif, send it separately
                await ctx.send(file[2])

            content._author = None

        if delete == "delete":
            await ctx.message.delete()

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx, *, query):
        """Search for a random gif"""
        if not query:
            return await ctx.send("Give me something to search!")

        scripts = []
        if len(query.split(" ")) == 1:
            url = f"https://gfycat.com/gifs/tag/{query}"
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            scripts += soup.find_all('script')

        url = f"https://gfycat.com/gifs/search/{query}"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        scripts += soup.find_all('script')
        urls = []
        for i in range(len(scripts)):
            try:
                data = json.loads(scripts[i].text, encoding='utf-8')
                for x in data["itemListElement"]:
                    if "url" in x:
                        urls.append(x['url'])
            except json.JSONDecodeError:
                continue

        if not urls:
            return await ctx.send("Found nothing!")

        msg = await ctx.send(f"**{query}**: {random.choice(urls)}")

        async def randomize():
            await msg.edit(content=f"**{query}**: {random.choice(urls)}")

        await util.reaction_buttons(ctx, msg, {"❌": msg.delete, "🔁": randomize})

    @commands.command()
    async def melon(self, ctx, timeframe=None):
        """Get realtime / daily / monthly chart from Melon"""
        if timeframe not in ["day", "month", "rise", None]:
            if timeframe == "realtime":
                timeframe = None
            else:
                return await ctx.send(f"ERROR: Invalid timeframe `{timeframe}`\ntry `[realtime | day | month | rise]`")

        url = f"https://www.melon.com/chart/{timeframe or ''}/index.htm"

        response = requests.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0"})

        soup = BeautifulSoup(response.text, 'html.parser')
        song_titles = [util.escape_md(x.find('span').find('a').text)
                       for x in soup.find_all('div', {'class': 'ellipsis rank01'})]
        artists = [util.escape_md(x.find('a').text)
                   for x in soup.find_all('div', {'class': 'ellipsis rank02'})]
        albums = [util.escape_md(x.find('a').text)
                  for x in soup.find_all('div', {'class': 'ellipsis rank03'})]
        image = soup.find('img', {'onerror': 'WEBPOCIMG.defaultAlbumImg(this);'}).get('src')

        content = discord.Embed(title=f"Melon top {len(song_titles)}" +
                                      ("" if timeframe is None else f" - {timeframe.capitalize()}"),
                                colour=discord.Colour.green())
        content.set_thumbnail(url=image)
        content.timestamp = ctx.message.created_at

        pages = []
        x = 0
        for i in range(len(song_titles)):
            if x == 10:
                pages.append(content)
                content = copy.deepcopy(content)
                content.clear_fields()
                x = 0
            content.add_field(name=f"**{i + 1}.** {song_titles[i]}",
                              value=f"**{artists[i]}** — {albums[i]}",
                              inline=False)
            x += 1

        pages.append(content)
        await util.page_switcher(ctx, pages)

    @commands.command()
    async def xkcd(self, ctx, comic_id=None):
        """Get a random xkcd comic"""
        if comic_id is None:
            url = "https://c.xkcd.com/random/comic/"
            response = requests.get(url, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Connection": "keep-alive",
                "Referer": "https://xkcd.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"})
            location = response.url
        else:
            location = f"https://xkcd.com/{comic_id}/"
        await ctx.send(location)

    @commands.command()
    async def wikipedia(self, ctx, *query):
        """Search for a wikipedia page"""
        if query[0] == 'random':
            search_string = wikipedia.random()
        else:
            search_string = " ".join(query)
        try:
            page = wikipedia.page(search_string)
            await ctx.send(page.url)
        except wikipedia.exceptions.DisambiguationError as disabiguation_page:
            await ctx.send(f"```{str(disabiguation_page)}```")

    @commands.command()
    async def google(self, ctx, *, query):
        """Search anything from google.com"""
        results = list(googlesearch.search(query, stop=10, pause=1.0, only_standard=True))
        msg = await ctx.send(f"**#{1}: **{results[0]}")

        await msg.add_reaction("⬅")
        await msg.add_reaction("➡")

        def check(_reaction, _user):
            return _reaction.message.id == msg.id and _reaction.emoji in ["⬅", "➡"] and _user == ctx.author

        i = 0
        while True:
            try:
                reaction, user = await self.client.wait_for('reaction_add', timeout=300.0, check=check)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                return
            else:
                if reaction.emoji == "⬅" and i > 0:
                    i -= 1
                    await msg.remove_reaction("⬅", user)
                elif reaction.emoji == "➡" and i < len(results) - 1:
                    i += 1
                    await msg.remove_reaction("➡", user)
                await msg.edit(content=f"**#{i + 1}: **{results[i]}", embed=None)


def setup(client):
    client.add_cog(Media(client))
