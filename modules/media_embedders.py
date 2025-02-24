# SPDX-FileCopyrightText: 2024 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import io
from typing import TYPE_CHECKING, Any

import arrow
import discord
import regex
import yarl
from aiohttp import ClientConnectorError
from attr import dataclass
from discord.ext import commands
from discord.ui import View
from loguru import logger

from modules import emojis, exceptions, instagram, util
from modules.instagram import EmbedEz, InstaFix, InstagramError
from modules.tiktok import TikTokNew

if TYPE_CHECKING:
    from modules.misobot import MisoBot


@dataclass
class InstagramPost:
    shortcode: str


@dataclass
class Options:
    captions: bool = False
    delete_after: bool = False
    spoiler: bool = False
    sanitized_string: str = ""


def filesize_limit(guild: discord.Guild | None):
    """discord normally has 8MB file size limit,
    but it can be increased in some guilds due to boosting
    and we want to take full advantage of that"""
    return (
        guild.filesize_limit
        if guild is not None
        else discord.utils.DEFAULT_FILE_SIZE_LIMIT_BYTES
    )


class DownloadError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class BaseEmbedder:
    NO_RESULTS_ERROR = "..."
    NAME = "..."
    EMOJI = "..."

    def __init__(self, bot) -> None:
        self.bot: "MisoBot" = bot

    @staticmethod
    def get_options(text: str) -> Options:
        options = Options()
        valid_options = []
        words = text.lower().split()

        if "-c" in words or "--caption" in words:
            options.captions = True
            valid_options.append("-c")

        if "-d" in words or "--delete" in words:
            options.delete_after = True
            valid_options.append("-d")

        if "-s" in words or "--spoiler" in words:
            options.spoiler = True
            valid_options.append("-s")

        options.sanitized_string = " ".join(valid_options)
        return options

    async def process(self, ctx: commands.Context, user_input: str):
        """Process user input and embed any links found"""
        results = self.extract_links(user_input)
        options = self.get_options(user_input)
        if not results:
            raise exceptions.CommandWarning(self.NO_RESULTS_ERROR)

        for result in results:
            await self.send(ctx, result, options=options)

        if options.delete_after:
            try:
                await ctx.message.delete()
            except discord.errors.NotFound:
                pass
        else:
            await util.suppress(ctx.message)

    async def create_message(
        self,
        channel: "discord.abc.MessageableChannel",
        media: Any,
        options: Options | None = None,
    ):
        """Create the message parameters for later sending"""
        raise NotImplementedError

    @staticmethod
    def extract_links(text: str):
        raise NotImplementedError

    async def download_media(
        self,
        media_url: str,
        filename: str,
        max_filesize: int,
        url_tags: list[str] | None = None,
        spoiler: bool = False,
    ) -> str | discord.File:
        """Downloads media content respecting discord's filesize limit for each guild"""
        # The url params are unescaped by aiohttp's built-in yarl
        # This causes problems with the hash-based request signing that instagram uses
        # Thankfully you can plug your own yarl.URL with encoded=True so it wont get encoded twice
        async with self.bot.session.get(
            yarl.URL(media_url, encoded=True),
            headers={
                "User-Agent": util.random_user_agent(),
            },
        ) as response:
            if not response.ok:
                if response.headers.get("Content-Type") == "text/plain":
                    content = await response.text()
                    error_message = f"{response.status} {response.reason} | {content}"
                else:
                    error_message = f"{response.status} {response.reason}"

                raise DownloadError(error_message)

            content_length = response.headers.get(
                "Content-Length"
            ) or response.headers.get("x-full-image-content-length")
            try:
                if content_length:
                    if int(content_length) < max_filesize:
                        try:
                            file = io.BytesIO(await response.read())
                            return discord.File(
                                fp=file, filename=filename, spoiler=spoiler
                            )
                        except asyncio.TimeoutError:
                            pass
                    else:
                        raise ValueError
                else:
                    # try to stream until we hit our limit
                    buffer: bytes = b""
                    async for chunk in response.content.iter_chunked(1024):
                        buffer += chunk
                        if len(buffer) > max_filesize:
                            raise ValueError
                    return discord.File(
                        fp=io.BytesIO(buffer), filename=filename, spoiler=spoiler
                    )
            except ValueError:
                pass

        try:
            media_url = await util.shorten_url(self.bot, media_url, tags=url_tags)
        except ClientConnectorError:
            pass

        if spoiler:
            return f"||{media_url}||"

        return media_url

    @staticmethod
    def msg_split(contents: dict) -> tuple[dict, dict]:
        extra_contents = {}
        if len(contents.get("files", [])) > 10:
            extra_contents["files"] = contents["files"][10:]
            contents["files"] = contents["files"][:10]
            extra_contents["view"] = contents["view"]
            contents["view"] = None
        contents["content"] = contents["content"][:2000]
        return contents, extra_contents

    async def send(
        self,
        ctx: commands.Context,
        media: Any,
        options: Options | None = None,
    ):
        """Send the media to given context"""
        message_contents = await self.create_message(
            ctx.channel, media, options=options
        )
        message_contents, extra_contents = self.msg_split(message_contents)
        msg = await ctx.send(**message_contents)
        msg_extra = None
        if extra_contents:
            msg_extra = await ctx.send(**extra_contents)
        await self.msg_post_process(
            msg, msg_extra, message_contents, extra_contents, ctx.author
        )

    async def send_contextless(
        self,
        channel: "discord.abc.MessageableChannel",
        author: discord.User,
        media: Any,
        options: Options | None = None,
    ):
        """Send the media without relying on command context, for example in a message event"""
        message_contents = await self.create_message(channel, media, options=options)
        message_contents, extra_contents = self.msg_split(message_contents)
        msg = await channel.send(**message_contents)
        msg_extra = None
        if extra_contents:
            msg_extra = await channel.send(**extra_contents)

        await self.msg_post_process(
            msg, msg_extra, message_contents, extra_contents, author
        )

    async def send_reply(
        self,
        message: discord.Message,
        media: Any,
        options: Options | None = None,
    ):
        """Send the media as a reply to another message"""
        message_contents = await self.create_message(
            message.channel, media, options=options
        )
        message_contents, extra_contents = self.msg_split(message_contents)
        try:
            msg = await message.reply(**message_contents, mention_author=False)
        except discord.errors.HTTPException:
            # the original message was deleted, so we can't reply
            msg = await message.channel.send(**message_contents)

        msg_extra = None
        if extra_contents:
            msg_extra = await message.channel.send(**extra_contents)

        await self.msg_post_process(
            msg, msg_extra, message_contents, extra_contents, message.author
        )

    @staticmethod
    async def msg_post_process(
        msg: discord.Message,
        msg_extra: discord.Message | None,
        msg_content: dict,
        msg_extra_content: dict,
        author: discord.User,
    ):
        if msg_extra:
            view = msg_extra_content["view"]
            view.message_ref = msg_extra
            view.delete_with.append(msg_extra)
        else:
            view = msg_content["view"]
            view.message_ref = msg

        view.delete_with.append(msg)
        view.approved_deletors.append(author)


class RedditEmbedder(BaseEmbedder):
    NAME = "reddit"
    EMOJI = "<:reddit:1184484866520264724>"
    NO_RESULTS_ERROR = "Found no Reddit links to embed!"

    @staticmethod
    def extract_links(text: str) -> list[str]:
        text = "\n".join(text.split())
        reddit_regex = r"(?:.+?)(?:reddit\.com/r)(?:/[\w\d]+){2}(?:/)([\w\d]*)"
        gallery_regex = r"(?:.+?)reddit\.com/gallery/([\w\d]*)"
        posts = regex.findall(reddit_regex, text)
        galleries = regex.findall(gallery_regex, text)
        return posts + galleries

    async def create_message(
        self,
        channel: "discord.abc.MessageableChannel",
        reddit_post_id: str,
        options: Options | None = None,
    ):
        post = await self.bot.reddit_client.get_post(reddit_post_id)
        videos = post.videos
        caption = post.caption

        dateformat = arrow.get(post.timestamp).format("YYMMDD")

        tasks = []
        for n, media in enumerate(post.media, start=1):
            extension = media.rsplit(".")[-1]
            filename = f"{dateformat}-{post.subreddit}-{reddit_post_id}-{n}.{extension}"
            tasks.append(
                self.download_media(
                    media,
                    filename,
                    filesize_limit(channel.guild),
                    url_tags=["reddit"],
                    spoiler=options.spoiler if options else False,
                )
            )

        files = []
        suppress = True
        results = await asyncio.gather(*tasks)
        for result in results:
            if isinstance(result, discord.File):
                files.append(result)
            else:
                suppress = False
                caption += "\n" + result

        for video in videos:
            files.append(
                discord.File(
                    video,
                    spoiler=options.spoiler if options else False,
                )
            )

        return {
            "content": caption,
            "files": files,
            "view": MediaUI(
                "View on Reddit",
                "https://reddit.com" + post.url,
                should_suppress=suppress,
            ),
            "suppress_embeds": suppress,
        }


class InstagramEmbedder(BaseEmbedder):
    NAME = "instagram"
    EMOJI = "<:ig:937425165162262528>"
    NO_RESULTS_ERROR = "Found no valid Instagram posts to embed!"

    @staticmethod
    def extract_links(text: str, include_shortcodes=True) -> list[InstagramPost]:
        text = "\n".join(text.split())
        instagram_regex = (
            r"(?:https?:\/\/)?(?:www.)?instagram.com\/"
            r"?([a-zA-Z0-9\.\_\-]+)?\/([p]+)?([reel]+)?([tv]+)?([stories]+)?\/"
            r"([a-zA-Z0-9\-\_\.]+)\/?([0-9]+)?"
        )
        results: list[InstagramPost] = []
        for match in regex.finditer(instagram_regex, text):
            # group 1 for username
            # group 2 for p
            # group 3 for reel
            # group 4 for tv
            # group 5 for stories
            # group 6 for shortcode and username stories
            # group 7 for stories pk
            if match.group(5) == "stories":
                # stories are not supported at this point
                pass

            elif match.group(6):
                results.append(InstagramPost(shortcode=match.group(6)))

        if include_shortcodes:
            shortcode_regex = r"(?:\s|^)([^-][a-zA-Z0-9\-\_\.]{9,})(?=\s|$)"
            for match in regex.finditer(shortcode_regex, text):
                results.append(InstagramPost(shortcode=match.group(1)))

        return results

    async def create_message(
        self,
        channel: "discord.abc.MessageableChannel",
        instagram_asset: InstagramPost,
        options: Options | None = None,
    ):
        providers = []
        if isinstance(instagram_asset, InstagramPost):
            providers += [
                EmbedEz(self.bot),
                InstaFix(self.bot.session),
            ]

        error = None
        post = None
        results = []

        for provider in providers:
            try:
                post = await provider.get_post(instagram_asset.shortcode)
                identifier = instagram_asset.shortcode

                tasks = []
                if not post.media:
                    raise InstagramError("Unable to fetch media for this post")
                for n, media in enumerate(post.media, start=1):
                    ext = (
                        "mp4"
                        if media.media_type == instagram.MediaType.VIDEO
                        else "jpg"
                    )
                    filename = f"@{post.user.username}-{identifier}-{n}.{ext}"
                    tasks.append(
                        self.download_media(
                            media.url,
                            filename,
                            filesize_limit(channel.guild),
                            url_tags=["instagram"],
                            spoiler=options.spoiler if options else False,
                        )
                    )
                results = await asyncio.gather(*tasks)
            except (InstagramError, DownloadError) as e:
                logger.warning(f"{provider} failed with {e}")
                error = e
                continue
            else:
                error = None
                break

        if error is not None:
            raise error

        if not post:
            raise InstagramError("No post found")

        if post.user.name:
            caption = f"{self.EMOJI} **{post.user.name}** `@{post.user.username}`"
        else:
            caption = (
                f"{self.EMOJI} **@{discord.utils.escape_markdown(post.user.username)}**"
            )

        if post.timestamp:
            caption += f" <t:{post.timestamp}:d>"

        if post.caption and options and options.captions:
            caption += f"\n>>> {post.caption}"

        files = []
        suppress = True
        for result in results:
            if isinstance(result, discord.File):
                files.append(result)
            else:
                suppress = False
                caption += "\n" + result

        return {
            "content": caption,
            "files": files,
            "view": MediaUI("View on Instagram", post.url, should_suppress=suppress),
            "suppress_embeds": suppress,
        }


class TikTokEmbedder(BaseEmbedder):
    NAME = "tiktok"
    EMOJI = "<:tiktok:1050401570090647582>"
    NO_RESULTS_ERROR = "Found no TikTok links to embed!"

    def __init__(self, bot: "MisoBot"):
        self.downloader = TikTokNew(bot.session)
        super().__init__(bot)

    @staticmethod
    def extract_links(text: str):
        text = "\n".join(text.split())
        video_id_pattern = (
            r"\bhttps?:\/\/(?:m\.|www\.|vm\.|)tiktok\.com\/.*\b(?:(?:usr|v|embed|user|video|t)\/"
            r"|\?shareId=|\&item_id=)(\d+)(\b|\S+\b)"
        )

        shortcode_pattern = r"\bhttps?:\/\/(?:vm|vt|www)\.tiktok\.com\/(t/|)(\w+)/?"

        validated_urls = [
            f"https://m.tiktok.com/v/{match.group(1)}"
            for match in regex.finditer(video_id_pattern, text)
        ]
        validated_urls.extend(
            f"https://vm.tiktok.com/{match.group(2)}"
            for match in regex.finditer(shortcode_pattern, text)
        )

        return validated_urls

    async def create_message(
        self,
        channel: "discord.abc.MessageableChannel",
        tiktok_url: str,
        options: Options | None = None,
    ):
        video = await self.downloader.get_video(tiktok_url)
        file = await self.download_media(
            video.video_url,
            f"{video.user}_{tiktok_url.split('/')[-1]}.mp4",
            filesize_limit(channel.guild),
            url_tags=["tiktok"],
            spoiler=options.spoiler if options else False,
        )
        caption = f"{self.EMOJI} **@{video.user}**"
        if options and options.captions:
            caption += f"\n>>> {video.description}"

        # file was too big to send, just use the url
        if isinstance(file, str):
            return {
                "content": f"{caption}\n{file}",
                "view": MediaUI("View on TikTok", tiktok_url, should_suppress=False),
            }

        return {
            "content": caption,
            "file": file,
            "view": MediaUI("View on TikTok", tiktok_url),
            "suppress_embeds": True,
        }


class TwitterEmbedder(BaseEmbedder):
    NAME = "twitter"
    EMOJI = "<:x_:1135484782642466897>"
    NO_RESULTS_ERROR = "Found no Twitter/X links to embed!"

    @staticmethod
    def remove_tco(text: str) -> str:
        """Get rid of the t.co link to the same tweet"""
        if text.startswith("https://t.co"):
            # the caption is only the link
            return ""

        try:
            pre_text, tco = text.rsplit(maxsplit=1)
            if tco.startswith("https://t.co"):
                return pre_text
        except ValueError:
            pass

        return text

    @staticmethod
    def extract_links(text: str, include_id_only=True):
        text = "\n".join(text.split())
        results = [
            int(match.group(2))
            for match in regex.finditer(
                r"(?:https?:\/\/)?(?:www.)?(?:twitter|x).com/(\w+)/status/(\d+)", text
            )
        ]

        if include_id_only:
            for word in text.split():
                try:
                    results.append(int(word))
                except ValueError:
                    pass

        return results

    async def create_message(
        self,
        channel: "discord.abc.MessageableChannel",
        tweet_id: int,
        options: Options | None = None,
    ):
        api_route = "https://api.fxtwitter.com/u/status/{0}"
        media_urls = []
        async with self.bot.session.get(api_route.format(tweet_id)) as response:
            if not response.ok:
                raise exceptions.CommandWarning(
                    f"Tweet with id `{tweet_id}` returned **{response.status}**!"
                )
            tweet = await response.json()

        too_big_files = []
        if tweet.get("tweet"):
            tweet = tweet["tweet"]

        if tweet.get("media_extended"):
            # it's vxtwitter
            medias = tweet["media_extended"]
        elif tweet.get("media"):
            # fxtwitter
            medias = tweet["media"].get("all", [])
            if tweet["media"].get("external"):
                too_big_files.append(tweet["media"]["external"]["url"])
        else:
            raise exceptions.CommandWarning(
                f"Tweet with id `{tweet_id}` does not contain any media!",
            )

        for media in medias:
            if media["type"] in ["video", "gif"]:
                media_urls.append(("mp4", media["url"]))
            else:
                base, extension = media["url"].rsplit(".", 1)
                media_urls.append(
                    ("jpg", f"{base}?format={extension}&name=orig"),
                )

        screen_name = tweet.get("user_screen_name") or tweet["author"]["screen_name"]
        caption = f"{self.EMOJI} **@{discord.utils.escape_markdown(screen_name)}**"

        timestamp = arrow.get(tweet.get("date_epoch") or tweet.get("created_timestamp"))
        ts_format = timestamp.format("YYMMDD") + "-"
        caption += f" <t:{int(timestamp.timestamp())}:d>"

        tasks = []
        for n, (extension, media_url) in enumerate(media_urls, start=1):
            filename = f"{ts_format}@{screen_name}-{tweet_id}-{n}.{extension}"
            tasks.append(
                self.download_media(
                    media_url,
                    filename,
                    filesize_limit(channel.guild),
                    url_tags=["twitter"],
                    spoiler=options.spoiler if options else False,
                )
            )

        files = []
        results = await asyncio.gather(*tasks)
        for result in results:
            if isinstance(result, discord.File):
                files.append(result)
            else:
                too_big_files.append(result)

        if options and options.captions:
            tweet_text = self.remove_tco(tweet["text"])
            if tweet_text:
                caption += f"\n>>> {tweet_text}"

        caption = "\n".join([caption] + too_big_files)
        suppress = len(too_big_files) == 0
        return {
            "content": caption,
            "files": files,
            "view": MediaUI(
                "View on X",
                f"https://twitter.com/{screen_name}/status/{tweet_id}",
                should_suppress=suppress,
            ),
            "suppress_embeds": suppress,
        }


class MediaUI(View):
    def __init__(self, label: str, url: str, should_suppress: bool = True):
        super().__init__(timeout=60)
        linkbutton = discord.ui.Button(label=label, url=url)
        self.add_item(linkbutton)
        self.message_ref: discord.Message | None = None
        self.delete_with: list[discord.Message] = []
        self.approved_deletors: list[discord.User] = []
        self.should_suppress = should_suppress
        self._children.reverse()

    @discord.ui.button(emoji=emojis.REMOVE, style=discord.ButtonStyle.danger)
    async def delete_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if self.delete_with and interaction.user in self.approved_deletors:
            for msg in self.delete_with:
                await msg.delete()
        else:
            await interaction.response.defer()

    async def on_timeout(self):
        self.remove_item(self.delete_button)
        if self.message_ref:
            try:
                await self.message_ref.edit(view=self, suppress=self.should_suppress)
            except discord.NotFound:
                pass
