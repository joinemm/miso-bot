# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import io
from typing import Any

import arrow
import discord
import regex
import tweepy
import tweepy.asynchronous as aiotweepy
import yarl
from aiohttp import ClientConnectorError
from attr import dataclass
from discord.ext import commands
from discord.ui import View
from loguru import logger

from modules import emojis, exceptions, instagram, util
from modules.misobot import MisoBot
from modules.tiktok import TikTok


@dataclass
class InstagramPost:
    shortcode: str


@dataclass
class InstagramStory:
    username: str
    story_pk: str


@dataclass
class Options:
    captions: bool = False


def filesize_limit(guild: discord.Guild | None):
    """discord normally has 8MB file size limit,
    but it can be increased in some guilds due to boosting
    and we want to take full advantage of that"""
    if guild is None:
        return 8388608

    return guild.filesize_limit


class BaseEmbedder:
    NO_RESULTS_ERROR = "..."

    def __init__(self, bot) -> None:
        self.bot: MisoBot = bot

    @staticmethod
    def get_options(text: str):
        options = Options()
        words = text.lower().split()
        if "-c" in words or "--caption" in words:
            options.captions = True

        return options

    async def process(self, ctx: commands.Context, user_input: str):
        """Process user input and embed any links found"""
        results = self.extract_links(user_input)
        options = self.get_options(user_input)
        if not results:
            raise exceptions.CommandWarning(self.NO_RESULTS_ERROR)

        for result in results:
            await self.send(ctx, result, options=options)

        await util.suppress(ctx.message)

    async def create_message(
        self, channel: "discord.abc.MessageableChannel", media: Any, options: Options | None = None
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
    ) -> str | discord.File:
        """Downloads media content respecting discord's filesize limit for each guild"""
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
            if content_length and int(content_length) < max_filesize:
                buffer = io.BytesIO(await response.read())
                return discord.File(fp=buffer, filename=filename)
            try:
                # try to stream until we hit our limit
                buffer = b""
                async for chunk in response.content.iter_chunked(1024):
                    buffer += chunk
                    if len(buffer) > max_filesize:
                        raise ValueError
                return discord.File(fp=io.BytesIO(buffer), filename=filename)
            except ValueError:
                pass

        try:
            return await util.shorten_url(self.bot, media_url, tags=url_tags)
        except ClientConnectorError:
            return media_url

    async def send(self, ctx: commands.Context, media: Any, options: Options | None = None):
        """Send the media to given context"""
        message_contents = await self.create_message(ctx.channel, media, options=options)
        msg = await ctx.send(**message_contents)
        message_contents["view"].message_ref = msg
        message_contents["view"].approved_deletors.append(ctx.author)

    async def send_contextless(
        self, channel: "discord.abc.MessageableChannel", author: discord.User, media: Any
    ):
        """Send the media without relying on command context, for example in a message event"""
        message_contents = await self.create_message(channel, media)
        msg = await channel.send(**message_contents)
        message_contents["view"].message_ref = msg
        message_contents["view"].approved_deletors.append(author)

    async def send_reply(self, message: discord.Message, media: Any):
        """Send the media as a reply to another message"""
        message_contents = await self.create_message(message.channel, media)
        msg = await message.reply(**message_contents, mention_author=False)
        message_contents["view"].message_ref = msg
        message_contents["view"].approved_deletors.append(message.author)


class InstagramEmbedder(BaseEmbedder):
    EMOJI = "<:ig:937425165162262528>"
    NO_RESULTS_ERROR = "Found no Instagram links to embed!"

    @staticmethod
    def extract_links(text: str, include_shortcodes=True) -> list[InstagramPost | InstagramStory]:
        text = "\n".join(text.split())
        instagram_regex = r"(?:https?:\/\/)?(?:www.)?instagram.com\/?([a-zA-Z0-9\.\_\-]+)?\/([p]+)?([reel]+)?([tv]+)?([stories]+)?\/([a-zA-Z0-9\-\_\.]+)\/?([0-9]+)?"
        results = []
        for match in regex.finditer(instagram_regex, text):
            # group 1 for username
            # group 2 for p
            # group 3 for reel
            # group 4 for tv
            # group 5 for stories
            # group 6 for shortcode and username stories
            # group 7 for stories pk
            if match.group(5) == "stories":
                username = match.group(6)
                story_id = match.group(7)
                if username and story_id:
                    results.append(InstagramStory(username, story_id))

            elif match.group(6):
                results.append(InstagramPost(match.group(6)))

        if include_shortcodes:
            shortcode_regex = r"^([a-zA-Z0-9\-\_\.]+)$"
            for match in regex.finditer(shortcode_regex, text):
                results.append(InstagramPost(match.group(1)))

        return results

    async def create_message(
        self,
        channel: "discord.abc.MessageableChannel",
        instagram_asset: InstagramPost | InstagramStory,
        options: Options | None = None,
    ):
        if isinstance(instagram_asset, InstagramPost):
            post = await self.bot.datalama.get_post_v1(instagram_asset.shortcode)
            identifier = instagram_asset.shortcode
        elif isinstance(instagram_asset, InstagramStory):
            post = await self.bot.datalama.get_story_v1(
                instagram_asset.username, instagram_asset.story_pk
            )
            identifier = instagram_asset.story_pk

        username = discord.utils.escape_markdown(post.user.username)
        caption = f"{self.EMOJI} **@{username}** <t:{post.timestamp}:d>"
        if options and options.captions:
            caption += f"\n>>> {post.caption}"
        tasks = []
        for n, media in enumerate(post.media, start=1):
            ext = "mp4" if media.media_type == instagram.MediaType.VIDEO else "jpg"
            dateformat = arrow.get(post.timestamp).format("YYMMDD")
            filename = f"{dateformat}-@{post.user.username}-{identifier}-{n}.{ext}"
            tasks.append(
                self.download_media(
                    media.url,
                    filename,
                    filesize_limit(channel.guild),
                    url_tags=["instagram"],
                )
            )

        files = []
        results = await asyncio.gather(*tasks)
        for result in results:
            if isinstance(result, discord.File):
                files.append(result)
            else:
                caption += "\n" + result

        return {
            "content": caption,
            "files": files,
            "view": MediaUI("View on Instagram", post.url),
        }


class TikTokEmbedder(BaseEmbedder):
    EMOJI = "<:tiktok:1050401570090647582>"
    NO_RESULTS_ERROR = "Found no TikTok links to embed!"

    def __init__(self, bot: "MisoBot"):
        self.downloader = TikTok()
        super().__init__(bot)

    @staticmethod
    def extract_links(text: str):
        text = "\n".join(text.split())
        pattern = r"\bhttps?:\/\/(?:m|www|vm)\.tiktok\.com\/.*\b(?:(?:usr|v|embed|user|video|t)\/|\?shareId=|\&item_id=)(\d+)\b"
        vm_pattern = r"\bhttps?:\/\/(?:vm|vt)\.tiktok\.com\/.*\b(\S+)\b"

        validated_urls = [
            f"https://m.tiktok.com/v/{match.group(1)}" for match in regex.finditer(pattern, text)
        ]
        validated_urls.extend(
            f"https://vm.tiktok.com/{match.group(1)}" for match in regex.finditer(vm_pattern, text)
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
        )
        caption = f"{self.EMOJI} **@{video.user}**"
        if options and options.captions:
            caption += f"\n>>> {video.description}"

        ui = MediaUI("View on TikTok", tiktok_url)

        # file was too big to send, just use the url
        if isinstance(file, str):
            return {
                "content": f"{caption}\n{file}",
                "view": ui,
            }

        return {
            "content": caption,
            "file": file,
            "view": ui,
        }


class TwitterEmbedder(BaseEmbedder):
    EMOJI = "<:twitter:937425165241946162>"
    NO_RESULTS_ERROR = "Found no Twitter links to embed!"

    def __init__(self, bot: "MisoBot"):
        self.tweepy = aiotweepy.AsyncClient(
            bot.keychain.TWITTER_BEARER_TOKEN,
            wait_on_rate_limit=True,
        )
        super().__init__(bot)

    @staticmethod
    def extract_links(text: str, include_id_only=True):
        text = "\n".join(text.split())
        results = [
            int(match.group(2))
            for match in regex.finditer(
                r"(?:https?:\/\/)?(?:www.)?twitter.com/(\w+)/status/(\d+)", text
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
        response = await self.tweepy.get_tweet(
            tweet_id,
            tweet_fields=["attachments", "created_at"],
            expansions=["attachments.media_keys", "author_id"],
            media_fields=["variants", "url", "alt_text"],
            user_fields=["profile_image_url"],
        )

        if response.errors:  # type: ignore
            raise exceptions.CommandWarning(response.errors[0]["detail"])  # type: ignore

        tweet: tweepy.Tweet = response.data  # type: ignore
        media_urls = []

        user = response.includes["users"][0]  # type: ignore
        screen_name = user.username
        tweet_url = f"https://twitter.com/{screen_name}/status/{tweet.id}"

        media: tweepy.Media
        for media in response.includes.get("media", []):  # type: ignore
            if media.type == "photo":
                base, extension = media.url.rsplit(".", 1)
                media_urls.append(("jpg", f"{base}?format={extension}&name=orig"))
            else:
                variants = sorted(
                    filter(lambda x: x["content_type"] == "video/mp4", media.data["variants"]),
                    key=lambda y: y["bit_rate"],
                    reverse=True,
                )
                media_urls.append(("mp4", variants[0]["url"]))

        if not media_urls:
            raise exceptions.CommandWarning(f"Tweet `{tweet_url}` does not include any media.")

        timestamp = arrow.get(tweet.created_at)

        tasks = []
        for n, (extension, media_url) in enumerate(media_urls, start=1):
            filename = f"{timestamp.format('YYMMDD')}-@{screen_name}-{tweet.id}-{n}.{extension}"
            tasks.append(
                self.download_media(
                    media_url,
                    filename,
                    filesize_limit(channel.guild),
                    url_tags=["twitter"],
                )
            )

        username = discord.utils.escape_markdown(screen_name)
        caption = f"{self.EMOJI} **@{username}** <t:{int(timestamp.timestamp())}:d>"
        if options and options.captions:
            caption += f"\n>>> {tweet.text.rsplit(maxsplit=1)[0]}"

        files = []
        too_big_files = []
        results = await asyncio.gather(*tasks)
        for result in results:
            if isinstance(result, discord.File):
                files.append(result)
            else:
                too_big_files.append(result)

        caption = "\n".join([caption] + too_big_files)
        return {
            "content": caption,
            "files": files,
            "view": MediaUI("View on Twitter", tweet_url),
        }


class MediaUI(View):
    def __init__(self, label: str, url: str):
        super().__init__(timeout=60)
        linkbutton = discord.ui.Button(label=label, url=url)
        self.add_item(linkbutton)
        self.message_ref: discord.Message | None = None
        self.approved_deletors = []
        self._children.reverse()

    @discord.ui.button(emoji=emojis.REMOVE, style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.message_ref and interaction.user in self.approved_deletors:
            await self.message_ref.delete()
        else:
            await interaction.response.defer()

    async def on_timeout(self):
        self.remove_item(self.delete_button)
        if self.message_ref:
            try:
                await self.message_ref.edit(view=self)
            except discord.NotFound:
                pass
