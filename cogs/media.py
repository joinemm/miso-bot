import asyncio
import io
import random
import re

import arrow
import discord
import orjson
import regex
import yarl
from aiohttp import ClientResponseError
from bs4 import BeautifulSoup
from discord.ext import commands

from modules import exceptions, instagram, log, util
from modules.views import LinkButton

# from tweepy import OAuthHandler
# import tweepy

logger = log.get_logger(__name__)


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🌐"
        # self.twitter_api = tweepy.API(
        #     OAuthHandler(
        #         self.bot.keychain.TWITTER_CONSUMER_KEY,
        #         self.bot.keychain.TWITTER_CONSUMER_SECRET,
        #     )
        # )
        self.ig = instagram.Instagram(self.bot, use_proxy=True)

    async def cog_unload(self):
        await self.ig.close()

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx: commands.Context, *, query):
        """Search for videos from youtube"""
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": self.bot.keychain.GCS_DEVELOPER_KEY,
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
            if not response.ok:
                logger.error(await response.text())
                response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) < max_filesize:
                buffer = io.BytesIO(await response.read())
                return discord.File(fp=buffer, filename=filename)
            elif content_length and int(content_length) >= max_filesize:
                return media_url
            else:
                logger.warning(f"No content type header for {media_url}")
                # there is no Content-Length header
                # try to stream until we hit our limit
                try:
                    amount_read = 0
                    buffer = b""
                    async for chunk in response.content.iter_chunked(1024):
                        amount_read += len(chunk)
                        buffer += chunk
                        if amount_read > max_filesize:
                            raise ValueError
                    return discord.File(fp=io.BytesIO(buffer), filename=filename)
                except ValueError:
                    return media_url

    @commands.command(aliases=["ig", "insta"], usage="<links...> '-e'")
    async def instagram(self, ctx: commands.Context, *links: str):
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

        if not urls:
            return await util.send_command_help(ctx)

        if len(urls) > 5:
            raise exceptions.CommandWarning("Only 5 links at a time please!")

        for post_url in urls:
            shortcode = None
            story_pk = None
            username = None
            result = regex.search(r"/(p|reel|tv)/([a-zA-Z\-_\d]{,11})", post_url)
            if result is not None:
                shortcode = result.group(2)
            else:
                story_result = regex.search(r"/stories/(.*?)/(\d*)", post_url)
                if story_result is not None:
                    username, story_pk = story_result.groups()
                else:
                    shortcode_only = regex.search(r"[a-zA-Z\-_\d]{,11}", post_url)
                    if shortcode_only is None:
                        raise exceptions.CommandError(
                            f"Invalid Instagram link or shortcode `{post_url}`"
                        )
                    shortcode = shortcode_only.group(0)

            try:
                if shortcode:
                    post_url = f"https://www.instagram.com/p/{shortcode}"
                    post = await instagram.Datalama(self.bot).get_post(shortcode)
                else:
                    post_url = f"https://www.instagram.com/stories/{username}/{story_pk}"
                    post = await instagram.Datalama(self.bot).get_story(story_pk)
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
                for video in videos:
                    await ctx.send(video)
            else:
                # send as files
                username = discord.utils.escape_markdown(post.user.username)
                caption = f"{self.ig.emoji} **@{username}** <t:{post.timestamp}:d>"
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

    @staticmethod
    def sort_videos(video: dict) -> int:
        width, height = re.findall(r"[/](\d*)x(\d*)[/]", video["src"])[0]
        res = int(width) * int(height)
        return res

    @commands.command(aliases=["twt"], usage="<links...> '-e'")
    async def twitter(self, ctx: commands.Context, *links: str):
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

        if not urls:
            return await util.send_command_help(ctx)

        if len(urls) > 5:
            raise exceptions.CommandWarning("Only 5 links at a time please!")

        for tweet_url in urls:
            if "status" in tweet_url:
                tweet_id = re.search(r"status/(\d+)", tweet_url).group(1)
            else:
                tweet_id = tweet_url

            async with self.bot.session.get(
                f"https://cdn.syndication.twimg.com/tweet?id={tweet_id}"
            ) as response:
                try:
                    response.raise_for_status()
                except ClientResponseError as e:
                    raise exceptions.CommandError(
                        f'Error getting tweet id "{tweet_id}": {e.status} {e.message}'
                    )
                tweet = await response.json()

            media_urls = []
            if tweet.get("video"):
                videos = list(
                    filter(lambda x: x["type"] == "video/mp4", tweet["video"]["variants"])
                )
                if len(videos) > 1:
                    best_src = sorted(videos, key=self.sort_videos)[-1]["src"]
                else:
                    best_src = videos[0]["src"]
                media_urls.append(("mp4", best_src))

            for photo in tweet.get("photos", []):
                base, extension = photo["url"].rsplit(".", 1)
                media_urls.append(("jpg", base + "?format=" + extension + "&name=orig"))

            if not media_urls:
                raise exceptions.CommandWarning(
                    f"Could not find any media from tweet id `{tweet_id}`"
                )

            screen_name = tweet["user"]["screen_name"]
            tweet_url = f"https://twitter.com/{screen_name}/status/{tweet_id}"
            timestamp = arrow.get(tweet["created_at"])

            if use_embeds:
                content = discord.Embed(colour=int(tweet["user"]["profile_link_color"], 16))
                content.set_author(
                    icon_url=tweet["user"]["profile_image_url"],
                    name=f"@{screen_name}",
                    url=tweet_url,
                )
                # just send link in embed
                embeds = []
                videos = []
                for n, (extension, media_url) in enumerate(media_urls, start=1):
                    if extension == "mp4":
                        videos.append(media_url)
                    else:
                        content.set_image(url=media_url)
                        embeds.append(content.copy())
                        content._author = None

                content.timestamp = timestamp.timestamp()
                if embeds:
                    await ctx.send(embeds=embeds)
                if videos:
                    await ctx.send("\n".join(videos))
            else:
                tasks = []
                max_filesize = getattr(ctx.guild, "filesize_limit", 8388608)
                for n, (extension, media_url) in enumerate(media_urls, start=1):
                    filename = f"{timestamp.format('YYMMDD')}-@{screen_name}-{tweet['id_str']}-{n}.{extension}"
                    tasks.append(self.download_media(media_url, filename, max_filesize))

                username = discord.utils.escape_markdown(screen_name)
                caption = f"<:twitter:937425165241946162> **@{username}** <t:{int(timestamp.timestamp())}:d>"

                files = []
                too_big_files = []
                results = await asyncio.gather(*tasks)
                for result in results:
                    if isinstance(result, discord.File):
                        files.append(result)
                    else:
                        too_big_files.append(result)

                caption = "\n".join([caption] + too_big_files)
                await ctx.send(caption, files=files, view=LinkButton("View on Twitter", tweet_url))

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
            soup = BeautifulSoup(await response.text(), "lxml")

        song_titles = [
            discord.utils.escape_markdown(x.find("span").find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank01"})
        ]
        artists = [
            discord.utils.escape_markdown(x.find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank02"})
        ]
        # albums = [
        #     discord.utils.escape_markdown(x.find("a").text)
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
        soup = BeautifulSoup(data, "lxml")
        return soup.find_all("script", {"type": "application/ld+json"})


class GGSoup:
    def __init__(self):
        self.soup = None

    async def create(self, region, summoner_name, sub_url=""):
        async with self.bot.session.get(
            f"https://{region}.op.gg/summoner/{sub_url}userName={summoner_name}"
        ) as response:
            data = await response.text()
            self.soup = BeautifulSoup(data, "lxml")

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
