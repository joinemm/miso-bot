import discord
import asyncio
import googlesearch
import json
import random
import re
import wikipedia
import tweepy
import os
import copy
import aiohttp
import regex
import arrow
from discord.ext import commands, flags
from tweepy import OAuthHandler
from bs4 import BeautifulSoup
from helpers import utilityfunctions as util

TWITTER_CKEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CSECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
IG_COOKIE = os.environ.get("IG_COOKIE")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")


class Media(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitter_api = tweepy.API(OAuthHandler(TWITTER_CKEY, TWITTER_CSECRET))
        self.ig_colors = [
            int("405de6", 16),
            int("5851db", 16),
            int("833ab4", 16),
            int("c13584", 16),
            int("e1306c", 16),
            int("fd1d1d", 16),
            int("f56040", 16),
            int("f77737", 16),
            int("fcaf45", 16),
        ]

    @commands.command(aliases=["colour"])
    async def color(self, ctx, *sources):
        """
        Get colors.

        Different color sources can be chained together to create patterns.

        Usage:
            >color <hex>
            >color <@member>
            >color <@role>
            >color random [amount]
            >color <image url>
        """
        if not sources:
            return await util.send_command_help(ctx)

        colors = []
        i = 0
        while i < len(sources):
            source = sources[i]
            i += 1
            if source.lower() == "random":
                try:
                    amount = int(sources[i])
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

            if source.startswith("http") or source.startswith("https"):
                url_color = await util.color_from_image_url(source)
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
        url = "https://api.color.pizza/v1/" + ",".join(colors)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                colordata = (await response.json()).get("colors")

        if len(colors) == 1:
            discord_color = await util.get_color(ctx, colors[0])
            hexvalue = colordata[0]["requestedHex"]
            rgbvalue = discord_color.to_rgb()
            name = colordata[0]["name"]
            luminance = colordata[0]["luminance"]
            image_url = f"http://www.colourlovers.com/img/{colors[0]}/200/200/color.png"
            content.title = name
            content.description = (
                f"**HEX:** `{hexvalue}`\n"
                f"**RGB:** {rgbvalue}\n"
                f"**Luminance:** {luminance:.4f}"
            )
        else:
            content.description = ""
            palette = ""
            for i, color in enumerate(colors):
                hexvalue = colordata[i]["requestedHex"]
                name = colordata[i]["name"]
                content.description += f"`{hexvalue}` **| {name}**\n"
                palette += color.strip("#") + "/"

            image_url = f"https://www.colourlovers.com/paletteImg/{palette}palette.png"

        content.set_image(url=image_url)
        await ctx.send(embed=content)

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx, *, query):
        """
        Search videos from youtube.

        Usage:
            >youtube <search term>
        """
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": GOOGLE_API_KEY,
            "part": "snippet",
            "type": "video",
            "maxResults": 25,
            "q": query,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 403:
                    return await ctx.send("```Error: Daily quota reached.```")
                else:
                    data = await response.json()

        urls = []
        for item in data.get("items"):
            urls.append(f"https://youtube.com/watch?v={item['id']['videoId']}")

        if not urls:
            return await ctx.send("No results found!")

        videos = util.TwoWayIterator(urls)
        msg = await ctx.send(f"`#1` {videos.current()}")

        async def next_link():
            link = videos.next()
            if link is not None:
                await msg.edit(content=f"`#{videos.index+1}` {link}", embed=None)

        async def prev_link():
            link = videos.previous()
            if link is not None:
                await msg.edit(content=f"`#{videos.index+1}` {link}", embed=None)

        async def done():
            return True

        functions = {"⬅": prev_link, "➡": next_link, "✅": done}

        asyncio.ensure_future(util.reaction_buttons(ctx, msg, functions, only_author=True))

    @flags.add_flag("urls", nargs="+")
    @flags.add_flag("-d", "--download", action="store_true")
    @flags.command(aliases=["ig", "insta"])
    async def instagram(self, ctx, **flags):
        """Get all the images from one or more instagram posts."""
        try:
            # delete discord automatic embed
            await ctx.message.edit(suppress=True)
        except discord.Forbidden:
            pass

        for url in flags["urls"]:

            result = regex.findall("/p/(.*?)(/|\\Z)", url)
            if result:
                url = f"https://www.instagram.com/p/{result[0][0]}"
            else:
                url = f"https://www.instagram.com/p/{url.strip('/').split('/')[0]}"

            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0",
            }
            post_id = url.split("/")[-1]
            newurl = "https://www.instagram.com/graphql/query/"
            params = {
                "query_hash": "505f2f2dfcfce5b99cb7ac4155cbf299",
                "variables": '{"shortcode":"' + post_id + '"}',
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(newurl, params=params, headers=headers) as response:
                    data = await response.json()
                    data = data["data"]["shortcode_media"]

            if data is None:
                await ctx.send(f":warning: Invalid instagram URL `{url}`")
                continue

            medias = []
            try:
                for x in data["edge_sidecar_to_children"]["edges"]:
                    medias.append(x["node"])
            except KeyError:
                medias.append(data)

            avatar_url = data["owner"]["profile_pic_url"]
            username = data["owner"]["username"]
            content = discord.Embed(color=random.choice(self.ig_colors))
            content.set_author(name=f"@{username}", icon_url=avatar_url, url=url)

            if not medias:
                await ctx.send(f":warning: Could not find any media from `{url}`")
                continue

            if flags["download"]:
                # send as files
                async with aiohttp.ClientSession() as session:
                    await ctx.send(f"<{url}>")
                    timestamp = arrow.get(data["taken_at_timestamp"]).format("YYMMDD")
                    for n, file in enumerate(medias, start=1):
                        if file.get("is_video"):
                            media_url = file.get("video_url")
                            extension = "mp4"
                        else:
                            media_url = file.get("display_url")
                            extension = "jpg"

                        filename = f"{timestamp}-@{username}-{post_id}-{n}.{extension}"
                        async with session.get(media_url) as response:
                            with open(filename, "wb") as f:
                                while True:
                                    block = await response.content.read(1024)
                                    if not block:
                                        break
                                    f.write(block)

                        with open(filename, "rb") as f:
                            await ctx.send(file=discord.File(f))

                        os.remove(filename)
            else:
                # send as embeds
                for medianode in medias:
                    if medianode.get("is_video"):
                        await ctx.send(embed=content)
                        await ctx.send(medianode.get("video_url"))
                    else:
                        content.set_image(url=medianode.get("display_url"))
                        await ctx.send(embed=content)
                    content.description = None
                    content._author = None

    @flags.add_flag("urls", nargs="+")
    @flags.add_flag("-d", "--download", action="store_true")
    @flags.command(aliases=["twt"])
    async def twitter(self, ctx, **flags):
        """Get all the images from one or more tweets."""
        try:
            # delete discord automatic embed
            await ctx.message.edit(suppress=True)
        except discord.Forbidden:
            pass

        for tweet_url in flags["urls"]:

            if "status" in tweet_url:
                tweet_id = re.search(r"status/(\d+)", tweet_url).group(1)
            else:
                tweet_id = tweet_url

            try:
                tweet = await ctx.bot.loop.run_in_executor(
                    None, lambda: self.twitter_api.get_status(tweet_id, tweet_mode="extended")
                )

            except Exception:
                await ctx.send(f":warning: Could not get tweet `{tweet_url}`")
                continue

            media_files = []
            try:
                media = tweet.extended_entities.get("media", [])
            except AttributeError:
                media = []

            if not media:
                await ctx.send(f":warning: Could not find any images from tweet id `{tweet_id}`")
                continue

            hashtags = []
            for hashtag in tweet.entities.get("hashtags", []):
                hashtags.append(f"#{hashtag['text']}")

            for i in range(len(media)):
                media_url = media[i]["media_url"]
                video_url = None
                if not media[i]["type"] == "photo":
                    video_urls = media[i]["video_info"]["variants"]
                    largest_rate = -1
                    for x in range(len(video_urls)):
                        if video_urls[x]["content_type"] == "video/mp4":
                            if video_urls[x]["bitrate"] > largest_rate:
                                largest_rate = video_urls[x]["bitrate"]
                                video_url = video_urls[x]["url"]
                                media_url = video_urls[x]["url"]
                media_files.append((" ".join(hashtags), media_url, video_url))

            content = discord.Embed(colour=int(tweet.user.profile_link_color, 16))
            content.set_author(
                icon_url=tweet.user.profile_image_url,
                name=f"@{tweet.user.screen_name}\n{media_files[0][0]}",
                url=f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}",
            )

            if flags["download"]:
                # download file and rename, upload to discord
                async with aiohttp.ClientSession() as session:
                    await ctx.send(f"<{tweet.full_text.split(' ')[-1]}>")
                    timestamp = arrow.get(tweet.created_at).format("YYMMDD")
                    for n, file in enumerate(media_files, start=1):
                        # is image not video
                        if file[2] is None:
                            extension = "jpeg"
                        else:
                            extension = "mp4"

                        filename = (
                            f"{timestamp}-@{tweet.user.screen_name}-{tweet.id}-{n}.{extension}"
                        )
                        url = file[1].replace(".jpg", "?format=jpg&name=orig")
                        async with session.get(url) as response:
                            with open(filename, "wb") as f:
                                while True:
                                    block = await response.content.read(1024)
                                    if not block:
                                        break
                                    f.write(block)

                        with open(filename, "rb") as f:
                            await ctx.send(file=discord.File(f))

                        os.remove(filename)

            else:
                # just send link in embed
                for file in media_files:
                    url = file[1].replace(".jpg", "?format=jpg&name=orig")
                    content.set_image(url=url)
                    await ctx.send(embed=content)

                    if file[2] is not None:
                        # contains a video/gif, send it separately
                        await ctx.send(file[2])

                    content._author = None

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx, *, query):
        """Search for a random gif"""

        async def extract_scripts(session, url):
            async with session.get(url) as response:
                data = await response.text()
                soup = BeautifulSoup(data, "html.parser")
                return soup.find_all("script", {"type": "application/ld+json"})

        scripts = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            if len(query.split(" ")) == 1:
                tasks.append(extract_scripts(session, f"https://gfycat.com/gifs/tag/{query}"))

            tasks.append(extract_scripts(session, f"https://gfycat.com/gifs/search/{query}"))
            scripts = sum(await asyncio.gather(*tasks), [])

        urls = []
        for script in scripts:
            try:
                data = json.loads(script.contents[0], encoding="utf-8")
                for x in data["itemListElement"]:
                    if "url" in x:
                        urls.append(x["url"])
            except json.JSONDecodeError:
                continue

        if not urls:
            return await ctx.send("Found nothing!")

        msg = await ctx.send(f"**{query}** {random.choice(urls)}")

        async def randomize():
            await msg.edit(content=f"**{query}** {random.choice(urls)}")

        buttons = {"❌": msg.delete, "🔁": randomize}
        asyncio.ensure_future(util.reaction_buttons(ctx, msg, buttons, only_author=True))

    @commands.command()
    async def melon(self, ctx, timeframe=None):
        """
        Melon music charts.

        Usage:
            >melon [realtime | day | month | rising]
        """
        if timeframe not in ["day", "month"]:
            if timeframe == "realtime":
                timeframe = ""
            elif timeframe == "rising":
                timeframe = "rise"
            else:
                return await util.send_command_help(ctx)

        url = f"https://www.melon.com/chart/{timeframe}/index.htm"
        async with aiohttp.ClientSession() as session:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
            }
            async with session.get(url, headers=headers) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")

        song_titles = [
            util.escape_md(x.find("span").find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank01"})
        ]
        artists = [
            util.escape_md(x.find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank02"})
        ]
        albums = [
            util.escape_md(x.find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank03"})
        ]
        image = soup.find("img", {"onerror": "WEBPOCIMG.defaultAlbumImg(this);"}).get("src")

        content = discord.Embed(color=discord.Color.from_rgb(0, 205, 60))
        content.set_author(
            name=f"Melon top {len(song_titles)}"
            + ("" if timeframe == "" else f" - {timeframe.capitalize()}"),
            url=url,
        )
        content.set_thumbnail(url=image)
        content.timestamp = ctx.message.created_at

        pages = []
        for i, (song, album, artist) in enumerate(zip(song_titles, albums, artists)):
            if i != 0 and i % 10 == 0:
                pages.append(content)
                content = copy.deepcopy(content)
                content.clear_fields()

            content.add_field(
                name=f"`#{i+1}` {song}", value=f"*by* **{artist}** *on* **{album}**", inline=False,
            )

        if content._fields:
            pages.append(content)

        await util.page_switcher(ctx, pages)

    @commands.command()
    async def xkcd(self, ctx, comic_id=None):
        """Get a random xkcd comic"""
        if comic_id is None:
            async with aiohttp.ClientSession() as session:
                url = "https://c.xkcd.com/random/comic"
                headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "keep-alive",
                    "Referer": "https://xkcd.com/",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0",
                }
                async with session.get(url, headers=headers) as response:
                    location = response.url
        else:
            location = f"https://xkcd.com/{comic_id}/"
        await ctx.send(location)

    @commands.command()
    async def wikipedia(self, ctx, *, query):
        """
        Search from wikipedia, or get random page.

        Usage:
            >wikipedia <query>
            >wikipedia random
        """
        if query == "random":
            query = await self.bot.loop.run_in_executor(None, wikipedia.random)

        try:
            page = await self.bot.loop.run_in_executor(None, lambda: wikipedia.page(query))
            await ctx.send(page.url)
        except wikipedia.exceptions.DisambiguationError as disabiguation_page:
            await ctx.send(f"```{str(disabiguation_page)}```")

    @commands.command()
    async def google(self, ctx, *, query):
        """Search from google."""
        results = await self.bot.loop.run_in_executor(
            None, lambda: googlesearch.search(query, stop=10, pause=1.0)
        )
        pages = util.TwoWayIterator([f"`#{i+1}` {x}" for i, x in enumerate(list(results))])
        msg = await ctx.send(pages.current())

        async def next_result():
            new_content = pages.next()
            if new_content is None:
                return
            await msg.edit(content=new_content, embed=None)

        async def previous_result():
            new_content = pages.previous()
            if new_content is None:
                return
            await msg.edit(content=new_content, embed=None)

        functions = {"⬅": previous_result, "➡": next_result}
        asyncio.ensure_future(util.reaction_buttons(ctx, msg, functions, only_author=True))


def setup(bot):
    bot.add_cog(Media(bot))
