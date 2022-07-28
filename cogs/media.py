import asyncio
import io
import os
import random
import re

import arrow
import discord
import orjson
import regex
import tweepy
import yarl
from bs4 import BeautifulSoup
from discord.ext import commands
from tweepy import OAuthHandler

from modules import exceptions, instagram, log, util
from modules.views import LinkButton

logger = log.get_logger(__name__)

TWITTER_CKEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CSECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
IG_SESSION_ID = os.environ.get("IG_SESSION_ID")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
PROXY_URL = os.environ.get("PROXY_URL")
PROXY_USER = os.environ.get("PROXY_USER")
PROXY_PASS = os.environ.get("PROXY_PASS")
IG_COOKIE = os.environ.get("IG_COOKIE")


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🌐"
        self.twitter_api = tweepy.API(OAuthHandler(TWITTER_CKEY, TWITTER_CSECRET))
        self.ig = instagram.Instagram(
            self.bot.session,
            IG_SESSION_ID,
            use_proxy=True,
            proxy_url=PROXY_URL,
            proxy_user=PROXY_USER,
            proxy_pass=PROXY_PASS,
        )

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx: commands.Context, *, query):
        """Search for videos from youtube"""
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": GOOGLE_API_KEY,
            "part": "snippet",
            "type": "video",
            "maxResults": 25,
            "q": query,
        }
        async with self.bot.session.get(url, params=params) as response:
            if response.status == 403:
                raise exceptions.CommandError("Daily youtube api quota reached.")

            data = await response.json(loads=orjson.loads)

        if not data.get("items"):
            return await ctx.send("No results found!")

        await util.paginate_list(
            ctx,
            [f"https://youtube.com/watch?v={item['id']['videoId']}" for item in data.get("items")],
            use_locking=True,
            only_author=True,
            index_entries=True,
        )

    async def download_media(self, media_url: str, filename: str, max_filesize: int):
        # The url params are unescaped by aiohttp's built-in yarl
        # This causes problems with the hash-based request signing that instagram uses
        # Thankfully you can plug your own yarl.URL with encoded=True so it wont get encoded twice
        async with self.bot.session.get(yarl.URL(media_url, encoded=True)) as response:
            if int(response.headers.get("content-length", max_filesize)) > max_filesize:
                return f"\n{media_url}"
            else:
                buffer = io.BytesIO(await response.read())
                return discord.File(fp=buffer, filename=filename)

    @commands.command(aliases=["ig", "insta"], usage="<links...> '-e'")
    async def instagram(self, ctx: commands.Context, *links):
        """Retrieve images from one or more instagram posts"""
        urls = []
        use_embeds = False

        for link in links:
            if link.lower() in ["-e", "--embed"]:
                use_embeds = True
            elif link.lower() in ["-d", "--download"]:
                await ctx.send(
                    ":information_source: `-d` is deprecated and is now the default option. pass `-e` to use embeds"
                )
                await ctx.typing()
            else:
                urls.append(link)

        if len(urls) > 5:
            raise exceptions.CommandWarning("Only 5 links at a time please!")

        for post_url in urls:
            shortcode = None
            story_pk = None
            username = None
            result = regex.search(r"/(p|reel|tv)/(.*?)(/|\Z)", post_url)
            if result is not None:
                shortcode = result.group(2)
            else:
                story_result = regex.search(r"/stories/(.*?)/(\d*)(/|\Z)", post_url)
                if story_result is not None:
                    username = story_result.group(1)
                    story_pk = story_result.group(2)
                else:
                    shortcode = post_url.strip("/").split("/")[0]

            try:
                if shortcode:
                    post_url = f"https://www.instagram.com/p/{shortcode}"
                    post = await self.ig.get_post(shortcode)
                else:
                    post_url = f"https://www.instagram.com/stories/{username}/{story_pk}"
                    post = await self.ig.get_story(username, story_pk)
            except instagram.ExpiredCookie:
                raise exceptions.CommandError(
                    "The Instagram login session has expired, please ask my developer to reauthenticate!"
                )
            except instagram.ExpiredStory:
                raise exceptions.CommandError("This story is no longer available.")
            except instagram.InstagramError as e:
                raise exceptions.CommandError(e.message)

            if use_embeds:
                # send as embeds
                content = discord.Embed(color=self.ig.color)
                content.set_author(
                    name=f"@{post.user.username}",
                    icon_url=post.user.avatar_url,
                    url=post_url,
                )
                embeds = []
                videos = []
                for n, media in enumerate(post.media, start=1):
                    if n == len(post.media):
                        content.timestamp = arrow.get(post.timestamp).datetime
                    if media.media_type == instagram.MediaType.VIDEO:
                        videos.append(media.url)
                    else:
                        content.set_image(url=media.url)
                        embeds.append(content.copy())
                    content._author = None
                if embeds:
                    await ctx.send(embeds=embeds)
                if videos:
                    await ctx.send("\n".join(videos))
            else:
                # send as files
                caption = f"{self.ig.emoji} **@{post.user.username}** <t:{post.timestamp}:R>"
                tasks = []
                # discord normally has 8MB file size limit, but it can be increased in some guilds
                max_filesize = getattr(ctx.guild, "filesize_limit", 8388608)
                for n, media in enumerate(post.media, start=1):
                    ext = "mp4" if media.media_type == instagram.MediaType.VIDEO else "jpg"
                    dateformat = arrow.get(post.timestamp).format("YYMMDD")
                    filename = f"{dateformat}-@{post.user.username}-{shortcode}-{n}.{ext}"
                    tasks.append(self.download_media(media.url, filename, max_filesize))

                files = []
                results = await asyncio.gather(*tasks)
                for result in results:
                    if isinstance(result, discord.File):
                        files.append(result)
                    else:
                        caption += result

                # send files to discord
                await ctx.send(
                    caption,
                    files=files,
                    view=LinkButton("View on Instagram", post_url),
                )

        # finally delete discord automatic embed
        try:
            await ctx.message.edit(suppress=True)
        except (discord.Forbidden, discord.NotFound):
            pass

    @commands.command(aliases=["twt"], usage="<links...> '-e'")
    async def twitter(self, ctx: commands.Context, *links):
        """Retrieve images from one or more tweets"""
        urls = []
        use_embeds = False
        for link in links:
            if link.lower() in ["-e", "--embed"]:
                use_embeds = True
            elif link.lower() in ["-d", "--download"]:
                await ctx.send(
                    ":information_source: `-d` is deprecated and is now the default option. pass `-e` to use embeds"
                )
                await ctx.typing()
            else:
                urls.append(link)

        if len(urls) > 5:
            raise exceptions.CommandWarning("Only 5 links at a time please!")

        for tweet_url in urls:
            if "status" in tweet_url:
                tweet_id = re.search(r"status/(\d+)", tweet_url).group(1)
            else:
                tweet_id = tweet_url

            try:
                tweet = await ctx.bot.loop.run_in_executor(
                    None,
                    lambda: self.twitter_api.get_status(str(tweet_id), tweet_mode="extended"),
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

            for resource in media:
                media_url = resource["media_url"]
                video_url = None
                if not resource["type"] == "photo":
                    video_variants = resource["video_info"]["variants"]
                    largest_rate = -1
                    for video in video_variants:
                        if (
                            video["content_type"] == "video/mp4"
                            and video["bitrate"] > largest_rate
                        ):
                            largest_rate = video["bitrate"]
                            video_url = video["url"]
                            media_url = video["url"]

                media_files.append((media_url, video_url))

            content = discord.Embed(colour=int(tweet.user.profile_link_color, 16))
            content.set_author(
                icon_url=tweet.user.profile_image_url,
                name=f"@{tweet.user.screen_name}",
                url=f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}",
            )

            if use_embeds:
                # just send link in embed
                embeds = []
                videos = []
                for n, (media_url, video_url) in enumerate(media_files, start=1):
                    url = media_url.replace(".jpg", "?format=jpg&name=orig")
                    content.set_image(url=url)
                    if n == len(media_files):
                        content.timestamp = tweet.created_at
                    embeds.append(content.copy())
                    if video_url is not None:
                        # contains a video/gif, send it separately
                        videos.append(video_url)
                    content._author = None

                if embeds:
                    await ctx.send(embeds=embeds)
                if videos:
                    await ctx.send("\n".join(videos))
            else:
                # download file and rename, upload to discord
                tweet_link = "https://" + tweet.full_text.split(" ")[-1].split("https://")[-1]
                timestamp = arrow.get(tweet.created_at).timestamp()
                caption = f"<:twitter:937425165241946162> **@{tweet.user.screen_name}** <t:{int(timestamp)}:R>"
                tasks = []
                for n, (media_url, video_url) in enumerate(media_files, start=1):
                    # is image not video
                    if video_url is None:
                        extension = "jpg"
                    else:
                        extension = "mp4"

                    filename = f"{timestamp}-@{tweet.user.screen_name}-{tweet.id}-{n}.{extension}"
                    # discord normally has 8MB file size limit, but it can be increased in some guilds
                    max_filesize = getattr(ctx.guild, "filesize_limit", 8388608)
                    url = media_url.replace(".jpg", "?format=jpg&name=orig")
                    tasks.append(self.download_media(url, filename, max_filesize))

                files = []
                results = await asyncio.gather(*tasks)
                for result in results:
                    if isinstance(result, discord.File):
                        files.append(result)
                    else:
                        caption += result

                await ctx.send(
                    caption, files=files, view=LinkButton("View on twitter", tweet_link)
                )

        try:
            # delete discord automatic embed
            await ctx.message.edit(suppress=True)
        except (discord.Forbidden, discord.NotFound):
            pass

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx: commands.Context, *, query):
        """Search for a gfycat gif"""
        scripts = []
        tasks = []
        if len(query.split(" ")) == 1:
            tasks.append(extract_scripts(self.bot.session, f"https://gfycat.com/gifs/tag/{query}"))

        tasks.append(extract_scripts(self.bot.session, f"https://gfycat.com/gifs/search/{query}"))
        scripts = sum(await asyncio.gather(*tasks), [])

        urls = []
        for script in scripts:
            try:
                data = orjson.loads(str(script.contents[0]))
                for x in data["itemListElement"]:
                    if "url" in x:
                        urls.append(x["url"])
            except orjson.JSONDecodeError:
                continue

        if not urls:
            return await ctx.send("Found nothing!")

        msg = await ctx.send(f"**{query}** {random.choice(urls)}")

        async def randomize():
            await msg.edit(content=f"**{query}** {random.choice(urls)}")

        async def done():
            return True

        buttons = {"❌": msg.delete, "🔁": randomize, "🔒": done}
        asyncio.ensure_future(util.reaction_buttons(ctx, msg, buttons, only_author=True))

    @commands.command(usage="<day | month | realtime | rising>")
    async def melon(self, ctx: commands.Context, timeframe):
        """Melon music charts"""
        if timeframe not in ["day", "month"]:
            if timeframe == "realtime":
                timeframe = ""
            elif timeframe == "rising":
                timeframe = "rise"
            else:
                raise exceptions.CommandInfo(
                    "Available timeframes: `[ day | month | realtime | rising ]`"
                )

        url = f"https://www.melon.com/chart/{timeframe}/index.htm"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
        }
        async with self.bot.session.get(url, headers=headers) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        song_titles = [
            util.escape_md(x.find("span").find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank01"})
        ]
        artists = [
            util.escape_md(x.find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank02"})
        ]
        # albums = [
        #     util.escape_md(x.find("a").text)
        #     for x in soup.find_all("div", {"class": "ellipsis rank03"})
        # ]
        image = soup.find("img", {"onerror": "WEBPOCIMG.defaultAlbumImg(this);"}).get("src")

        content = discord.Embed(color=discord.Color.from_rgb(0, 205, 60))
        content.set_author(
            name=f"Melon top {len(song_titles)}"
            + ("" if timeframe == "" else f" - {timeframe.capitalize()}"),
            url=url,
            icon_url="https://i.imgur.com/hm9xzPz.png",
        )
        content.set_thumbnail(url=image)
        content.timestamp = ctx.message.created_at

        rows = []
        for i, (song, artist) in enumerate(zip(song_titles, artists), start=1):
            rows.append(f"`#{i:2}` **{artist}** — ***{song}***")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def xkcd(self, ctx: commands.Context, comic_id=None):
        """Get a random xkcd comic"""
        if comic_id is None:
            url = "https://c.xkcd.com/random/comic"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Connection": "keep-alive",
                "Referer": "https://xkcd.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0",
            }
            async with self.bot.session.get(url, headers=headers) as response:
                location = response.url
        else:
            location = f"https://xkcd.com/{comic_id}/"
        await ctx.send(location)


async def setup(bot):
    await bot.add_cog(Media(bot))


async def extract_scripts(session, url):
    async with session.get(url) as response:
        data = await response.text()
        soup = BeautifulSoup(data, "html.parser")
        return soup.find_all("script", {"type": "application/ld+json"})


class GGSoup:
    def __init__(self):
        self.soup = None

    async def create(self, region, summoner_name, sub_url=""):
        async with self.bot.session.get(
            f"https://{region}.op.gg/summoner/{sub_url}userName={summoner_name}"
        ) as response:
            data = await response.text()
            self.soup = BeautifulSoup(data, "html.parser")

    def text(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        a = source.find(obj, {"class": classname})
        return a.text.strip() if a else a

    def src(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        a = source.find(obj, {"class": classname})
        return "https:" + a.get("src") if a else a


class InstagramIdCodec:
    ENCODING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

    @staticmethod
    def encode(num, alphabet=ENCODING_CHARS):
        """Covert a numeric value to a shortcode."""
        num = int(num)
        if num == 0:
            return alphabet[0]
        arr = []
        base = len(alphabet)
        while num:
            rem = num % base
            num //= base
            arr.append(alphabet[rem])
        arr.reverse()
        return "".join(arr)

    @staticmethod
    def decode(shortcode, alphabet=ENCODING_CHARS):
        """Covert a shortcode to a numeric value."""
        base = len(alphabet)
        strlen = len(shortcode)
        num = 0
        idx = 0
        for char in shortcode:
            power = strlen - (idx + 1)
            num += alphabet.index(char) * (base**power)
            idx += 1
        return num
