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
import helpers.utilityfunctions as util
import copy

TWITTER_CKEY = os.environ.get('TWITTER_CONSUMER_KEY')
TWITTER_CSECRET = os.environ.get('TWITTER_CONSUMER_SECRET')
IG_COOKIE = os.environ.get('IG_COOKIE')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_KEY')


class Media(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.twt = tweepy.API(OAuthHandler(TWITTER_CKEY, TWITTER_CSECRET))

    @commands.command(aliases=["colour"])
    async def color(self, ctx, *sources):
        """Get a hex color, the color of discord user, or a random color."""
        if not sources:
            return await ctx.send("Missing color source. Valid color sources are:\n"
                                  "`[@mention | @rolemention | hex | image_url | discord default color | random]`\n"
                                  "These can be chained together to create patterns")

        colors = []
        i = 0
        while i < len(sources):
            source = sources[i]
            i += 1
            try:
                result = getattr(discord.Color, source)
                hexcolor = str(result())
                print(hexcolor)
                colors.append(hexcolor)
                continue
            except AttributeError:
                pass

            if source.lower() == "random":
                try:
                    amount = int(sources[i+1])
                    i += 1
                except (IndexError, ValueError):
                    amount = 1
                for x in range(amount):
                    colors.append("{:06x}".format(random.randint(0, 0xFFFFFF)))
                continue

            role_or_user = await util.get_member(ctx, source) or await util.get_role(ctx, source)
            if role_or_user is not None:
                colors.append(str(role_or_user.color).strip("#"))
                continue

            if 'http' in source or 'https' in source:
                url_color = util.color_from_image_url(source)
                if url_color is not None:
                    colors.append(url_color)
                    continue

            color = await util.get_color(ctx, source)
            if color is not None:
                colors.append(str(color))
                continue

            await ctx.send(f"Error parsing `{source}`")
        
        if not colors:
            return await ctx.send("No valid colors to show")

        content = discord.Embed(colour=await util.get_color(ctx, colors[0]))

        if len(colors) > 50:
            await ctx.send("Maximum amount of colors is 50, ignoring rest...")
            colors = colors[:50]

        colors = [x.strip("#") for x in colors]
        colordata = requests.get(f"https://api.color.pizza/v1/{','.join(colors)}").json().get('colors')

        if len(colors) == 1:
            discord_color = await util.get_color(ctx, colors[0])
            hexvalue = colordata[0]['requestedHex']
            rgbvalue = discord_color.to_rgb()
            name = colordata[0]['name']
            luminance = colordata[0]['luminance']
            image_url = f"http://www.colourlovers.com/img/{colors[0]}/200/200/color.png"
            content.title = name
            content.description = f"**HEX:** `{hexvalue}`\n**RGB:** {rgbvalue}\n**Luminance:** {luminance:.4f}"
        else:
            content.description = ""
            palette = ""
            for i, color in enumerate(colors):
                hexvalue = colordata[i]['requestedHex']
                name = colordata[i]['name']
                content.description += f"`{hexvalue}` **| {name}**\n"
                palette += color.strip('#') + "/"

            image_url = f"https://www.colourlovers.com/paletteImg/{palette}palette.png"

        content.set_image(url=image_url)
        await ctx.send(embed=content)

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx, *, query):
        """Search youtube for the given search query and return first result"""

        response = requests.get(url='https://www.googleapis.com/youtube/v3/search',
                                params={'part': 'snippet',
                                        'type': 'video',
                                        'maxResults': 25,
                                        'q': query,
                                        'key': GOOGLE_API_KEY}).json()

        urls = []
        for item in response.get('items'):
            urls.append(f"https://youtube.com/watch?v={item['id']['videoId']}")

        videos = util.TwoWayIterator(urls)

        msg = await ctx.send(f"**#1:** {videos.current()}")

        async def next_link():
            link = videos.next()
            if link is not None:
                await msg.edit(content=f"**#{videos.index+1}:** {link}", embed=None)

        async def prev_link():
            link = videos.previous()
            if link is not None:
                await msg.edit(content=f"**#{videos.index+1}:** {link}", embed=None)

        async def done():
            return True

        functions = {"⬅": prev_link,
                     "➡": next_link,
                     "✅": done}

        await util.reaction_buttons(ctx, msg, functions, only_author=True)

    @commands.command(aliases=['ig'])
    async def instagram(self, ctx, url):
        """Get all the images from an instagram post"""
        result = re.findall('/p/(.*?)(/|\\Z)', url)
        if result:
            url = f"https://www.instagram.com/p/{result[0][0]}"
        else:
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

        response = requests.get(url.strip("/") + "/?__a=1", headers=headers)
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
            await ctx.send("No media found!")

    @commands.command(aliases=['twt'])
    async def twitter(self, ctx, tweet_url):
        """Get all the images from a tweet"""
        if "status" in tweet_url:
            tweet_url = re.search(r'status/(\d+)', tweet_url).group(1)
        tweet = self.twt.get_status(tweet_url, tweet_mode='extended')

        media_files = []
        try:
            media = tweet.extended_entities.get('media', [])
        except AttributeError:
            await ctx.send("No media found!")
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
            content.set_image(url=file[1].replace('.jpg', '?format=jpg&name=orig'))
            await ctx.send(embed=content)

            if file[2] is not None:
                # contains a video/gif, send it separately
                await ctx.send(file[2])

            content._author = None

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx, *, query):
        """Search for a random gif"""
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

        await util.reaction_buttons(ctx, msg, {"❌": msg.delete, "🔁": randomize}, only_author=True)

    @commands.command()
    async def melon(self, ctx, timeframe=None):
        """Melon music charts"""
        if timeframe not in ["day", "month"]:
            if timeframe == "realtime":
                timeframe = ""
            elif timeframe == "rising":
                timeframe = "rise"
            else:
                return await ctx.send(f"```{self.client.command_prefix}melon [ realtime | day | month | rising ]"
                                      "\n\nMelon music charts```")
        
        url = f"https://www.melon.com/chart/{timeframe}/index.htm"

        response = requests.get(url, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0"
        })

        soup = BeautifulSoup(response.text, 'html.parser')
        song_titles = [util.escape_md(x.find('span').find('a').text)
                       for x in soup.find_all('div', {'class': 'ellipsis rank01'})]
        artists = [util.escape_md(x.find('a').text)
                   for x in soup.find_all('div', {'class': 'ellipsis rank02'})]
        albums = [util.escape_md(x.find('a').text)
                  for x in soup.find_all('div', {'class': 'ellipsis rank03'})]
        image = soup.find('img', {'onerror': 'WEBPOCIMG.defaultAlbumImg(this);'}).get('src')

        content = discord.Embed(title=f"Melon top {len(song_titles)}" +
                                      ("" if timeframe == '' else f" - {timeframe.capitalize()}"),
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
                try:
                    await msg.clear_reactions()
                except discord.errors.NotFound:
                    pass
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
