# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import random
from typing import Literal

import discord
import orjson
from bs4 import BeautifulSoup
from discord.ext import commands
from modules.media_embedders import (
    BaseEmbedder,
    InstagramEmbedder,
    TikTokEmbedder,
    TwitterEmbedder,
)
from modules.misobot import MisoBot

from modules import emojis, exceptions, util


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🖼️"

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

    @util.patrons_only()
    @commands.group()
    async def autoembedder(self, ctx: commands.Context, provider: Literal["instagram", "tiktok"]):
        """Set up automatic embeds for various media sources

        The links will be expanded automatically when detected in chat,
        without requiring the use of the corresponding command
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if ctx.invoked_subcommand is None:
            enabled = await self.bot.db.fetch_value(
                f"""
                SELECT {provider} FROM media_auto_embed_enabled WHERE guild_id = %s
                """,
                ctx.guild.id,
            )
            options_data = await self.bot.db.fetch_row(
                """
                SELECT options, reply FROM media_auto_embed_options
                    WHERE guild_id = %s AND provider = %s
                """,
                ctx.guild.id,
                provider,
            )
            if options_data:
                options, reply = options_data
            else:
                options, reply = None, None

            await ctx.send(
                embed=discord.Embed(
                    title=f"{provider.capitalize()} autoembedder",
                    description=(
                        f"ENABLED: {':white_check_mark:' if enabled else ':x:'}\n"
                        f"OPTIONS: `{options}`\n"
                        f"REPLIES: {':white_check_mark:' if reply else ':x:'}"
                    ),
                )
            )
        else:
            ctx.provider = provider

    @autoembedder.command(name="toggle")
    async def autoembedder_toggle(self, ctx: commands.Context):
        """Toggle the autoembedder on or off for given media provider"""
        data = await self.bot.db.fetch_value(
            f"""
            SELECT {ctx.provider} FROM media_auto_embed_enabled WHERE guild_id = %s
            """,
            ctx.guild.id,
        )
        await self.bot.db.execute(
            f"""
            INSERT INTO media_auto_embed_enabled (guild_id, {ctx.provider})
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                {ctx.provider} = %s
            """,
            ctx.guild.id,
            not data,
            not data,
        )

        await self.bot.cache.cache_auto_embedders()

        await util.send_success(
            ctx,
            f"{ctx.provider.capitalize()} automatic embeds are now "
            f"**{'OFF' if data else 'ON'}** for this server",
        )

    @autoembedder.command(name="options")
    async def autoembedder_options(self, ctx: commands.Context, *, options: str):
        """Set options to be applied to an automatic embed

        Refer to the help of the embedder commands for list of options.
        """
        parsed_options = BaseEmbedder.get_options(options)
        options = parsed_options.sanitized_string

        await self.bot.db.execute(
            """
            INSERT INTO media_auto_embed_options (guild_id, provider, options)
                VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                options = %s
            """,
            ctx.guild.id,
            ctx.provider,
            options,
            options,
        )

        await util.send_success(
            ctx,
            f"{ctx.provider.capitalize()} automatic embed OPTIONS are now:\n"
            f"```yml\nCAPTIONS: {parsed_options.captions}\n"
            f"DELETE_AFTER: {parsed_options.delete_after}\n"
            f"SPOILER: {parsed_options.spoiler}```\n",
        )

    @autoembedder.command(name="reply", usage="<on | off>")
    async def autoembedder_reply(self, ctx: commands.Context, on_or_off: bool):
        """Should the automatic embed be a reply to the invoking message"""
        await self.bot.db.execute(
            """
            INSERT INTO media_auto_embed_options (guild_id, provider, reply)
                VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                reply = %s
            """,
            ctx.guild.id,
            ctx.provider,
            on_or_off,
            on_or_off,
        )

        await util.send_success(
            ctx,
            f"{ctx.provider.capitalize()} automatic embed is now "
            f"{'' if on_or_off else 'NOT '}a reply",
        )

    @commands.command(
        aliases=["ig", "insta"],
        usage="[OPTIONS] <links...>",
    )
    async def instagram(self, ctx: commands.Context, *, links: str):
        """Retrieve media from Instagram post, reel or story

        OPTIONS
            `-c`, `--caption` : also include the caption/text of the media
            `-s`, `--spoiler` : spoiler the uploaded images and text
            `-d`, `--delete`  : delete your message when the media is done embedding
        """
        await InstagramEmbedder(self.bot).process(ctx, links)

    @commands.command(
        aliases=["twt"],
        usage="[OPTIONS] <links...>",
    )
    async def twitter(self, ctx: commands.Context, *, links: str):
        """Retrieve media from a tweet

        OPTIONS
            `-c`, `--caption` : also include the caption/text of the media
            `-s`, `--spoiler` : spoiler the uploaded images and text
            `-d`, `--delete`  : delete your message when the media is done embedding
        """
        await TwitterEmbedder(self.bot).process(ctx, links)

    @commands.command(
        aliases=["tik", "tok", "tt"],
        usage="[OPTIONS] <links...>",
    )
    async def tiktok(self, ctx: commands.Context, *, links: str):
        """Retrieve video without watermark from a TikTok

        OPTIONS
            `-c`, `--caption` : also include the caption/text of the media
            `-s`, `--spoiler` : spoiler the uploaded images and text
            `-d`, `--delete`  : delete your message when the media is done embedding
        """
        await TikTokEmbedder(self.bot).process(ctx, links)

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx: commands.Context, *, query):
        """Search for a gfycat gif"""

        async def extract_scripts(session, url):
            async with session.get(url) as response:
                data = await response.text()
                soup = BeautifulSoup(data, "lxml")
                return soup.find_all("script", {"type": "application/ld+json"})

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
                        urls.append(x)
            except orjson.JSONDecodeError:
                continue

        if not urls:
            return await ctx.send("Found nothing!")

        await GiphyUI(urls).run(ctx)

    @commands.command(enabled=False)
    async def giphy(self, ctx: commands.Context, *, query):
        """Search for gif from Giphy"""
        URL = "https://api.giphy.com/v1/gifs/search"
        params = {
            "q": query,
            "api_key": self.bot.keychain.GIPHY_API_KEY,
            "limit": 50,
        }
        async with self.bot.session.get(URL, params=params) as response:
            data = await response.json()
            gifs = data["data"]

        await GiphyUI(gifs).run(ctx)

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
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0"
            ),
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
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"
                ),
            }
            async with self.bot.session.get(url, headers=headers) as response:
                location = str(response.url)
        else:
            location = f"https://xkcd.com/{comic_id}/"
        await ctx.send(location)


async def setup(bot):
    await bot.add_cog(Media(bot))


class GiphyUI(discord.ui.View):
    def __init__(self, urls: list):
        super().__init__()
        self.message: discord.Message
        self.gifs = urls

    async def run(self, ctx: commands.Context):
        self.message = await ctx.send(random.choice(self.gifs)["url"], view=self)

    @discord.ui.button(emoji=emojis.REMOVE, style=discord.ButtonStyle.danger)
    async def toggle(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.defer()
        await self.message.delete()

    @discord.ui.button(emoji=emojis.REPEAT, style=discord.ButtonStyle.primary)
    async def randomize(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.defer()
        await self.message.edit(content=random.choice(self.gifs)["url"])

    @discord.ui.button(emoji=emojis.CONFIRM, style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.defer()
        await self.remove_ui()

    async def remove_ui(self):
        for item in self.children:
            item.disabled = True  # type: ignore

        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass

    async def on_timeout(self):
        await self.remove_ui()
