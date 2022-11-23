import asyncio
import io
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
from tweepy.asynchronous import AsyncClient as TweepyClient

from modules import exceptions, instagram, log, util
from modules.misobot import MisoBot
from modules.views import LinkButton

logger = log.get_logger(__name__)


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🌐"
        self.tweepy: TweepyClient = TweepyClient(
            self.bot.keychain.TWITTER_BEARER_TOKEN,
            wait_on_rate_limit=True,
        )
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
                if response.headers.get("Content-Type") == "text/plain":
                    content = await response.text()
                    error_message = f"{response.status} {response.reason} | {content}"
                else:
                    error_message = f"{response.status} {response.reason}"

                logger.error(error_message)
                return f"`[{error_message}]`"

            content_length = response.headers.get("Content-Length") or response.headers.get(
                "x-full-image-content-length"
            )
            if content_length:
                if int(content_length) < max_filesize:
                    buffer = io.BytesIO(await response.read())
                    return discord.File(fp=buffer, filename=filename)
                elif int(content_length) >= max_filesize:
                    return media_url
            else:
                logger.warning(f"No content length header for {media_url}")
                # there is no Content-Length header
                # try to stream until we hit our limit
                try:
                    buffer = b""
                    async for chunk in response.content.iter_chunked(1024):
                        buffer += chunk
                        if len(buffer) > max_filesize:
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
                    post = await instagram.Datalama(self.bot).get_post_v1(shortcode)
                elif story_pk:
                    post_url = f"https://www.instagram.com/stories/{username}/{story_pk}"
                    post = await instagram.Datalama(self.bot).get_story_v1(story_pk)
                else:
                    raise exceptions.CommandError("Could not find anything to show")

            except instagram.ExpiredCookie as exc:
                raise exceptions.CommandError(
                    "The Instagram login session has expired, please ask my developer to reauthenticate!"
                ) from exc
            except instagram.ExpiredStory as exc:
                raise exceptions.CommandError("This story is no longer available.") from exc
            except instagram.InstagramError as exc:
                raise exceptions.CommandError(exc.message)

            if use_embeds:
                # send as embeds
                content = discord.Embed(color=self.ig.color)
                embeds = []
                videos = []
                for n, media in enumerate(post.media, start=1):
                    if media.media_type == instagram.MediaType.VIDEO:
                        videos.append(media.url)
                    else:
                        content.set_image(url=media.url)
                        embeds.append(content.copy())

                if embeds:
                    embeds[0].set_author(
                        name=f"@{post.user.username}",
                        icon_url=post.user.avatar_url,
                        url=post_url,
                    )
                    embeds[-1].timestamp = arrow.get(post.timestamp).datetime
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
                        caption += "\n" + result

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
            tweet_id = tweet_url
            if "status" in tweet_url:
                match = re.search(r"status/(\d+)", tweet_url)
                if match:
                    tweet_id = match.group(1)

            try:
                tweet_id = int(tweet_id)
            except ValueError:
                raise exceptions.CommandError(f"Tweet ID must be a number, not `{tweet_id}`")

            response = await self.tweepy.get_tweet(
                tweet_id,
                tweet_fields=["attachments", "created_at"],
                expansions=["attachments.media_keys", "author_id"],
                media_fields=["variants", "url", "alt_text"],
                user_fields=["profile_image_url"],
            )

            tweet: tweepy.Tweet = response.data  # type: ignore

            media_urls = []

            media: tweepy.Media
            for media in response.includes.get("media", []):  # type: ignore
                if media.type == "photo":
                    base, extension = media.url.rsplit(".", 1)
                    media_urls.append(("jpg", base + "?format=" + extension + "&name=orig"))
                else:
                    variants = sorted(
                        filter(lambda x: x["content_type"] == "video/mp4", media.data["variants"]),
                        key=lambda y: y["bit_rate"],
                        reverse=True,
                    )
                    media_urls.append(("mp4", variants[0]["url"]))

            if not media_urls:
                raise exceptions.CommandWarning(
                    f"Could not find any media from tweet ID `{tweet_id}`"
                )

            user = response.includes["users"][0]  # type: ignore
            screen_name = user.username
            tweet_url = f"https://twitter.com/{screen_name}/status/{tweet.id}"
            timestamp = arrow.get(tweet.created_at)

            if use_embeds:
                content = discord.Embed(colour=int("1d9bf0", 16))
                # just send link in embed
                embeds = []
                videos = []
                for n, (extension, media_url) in enumerate(media_urls, start=1):
                    if extension == "mp4":
                        videos.append(media_url)
                    else:
                        content.set_image(url=media_url)
                        embeds.append(content.copy())

                if embeds:
                    embeds[-1].timestamp = timestamp.datetime
                    embeds[0].set_author(
                        icon_url=user.profile_image_url,
                        name=f"@{screen_name}",
                        url=tweet_url,
                    )
                    await ctx.send(embeds=embeds)
                if videos:
                    await ctx.send("\n".join(videos))
            else:
                tasks = []
                max_filesize = getattr(ctx.guild, "filesize_limit", 8388608)
                for n, (extension, media_url) in enumerate(media_urls, start=1):
                    filename = (
                        f"{timestamp.format('YYMMDD')}-@{screen_name}-{tweet.id}-{n}.{extension}"
                    )
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
            text = await response.text()
            soup = BeautifulSoup(text, "lxml")

        rows = []
        image = None
        for i, chart_row in enumerate(soup.select(".lst50, .lst100"), start=1):
            if not image:
                image = chart_row.select_one("img")
            title = chart_row.select_one(".wrap_song_info .rank01 span a")
            artist = chart_row.select_one(".wrap_song_info .rank02 a")
            if not title or not artist:
                raise exceptions.CommandError("Failure parsing Melon page")

            rows.append(f"`#{i:2}` **{artist.attrs['title']}** — ***{title.attrs['title']}***")

        content = discord.Embed(color=discord.Color.from_rgb(0, 205, 60))
        content.set_author(
            name=f"Melon top {len(rows)}"
            + ("" if timeframe == "" else f" - {timeframe.capitalize()}"),
            url=url,
            icon_url="https://i.imgur.com/hm9xzPz.png",
        )
        if image:
            content.set_thumbnail(url=image.attrs["src"])
        content.timestamp = ctx.message.created_at
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
                location = str(response.url)
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
