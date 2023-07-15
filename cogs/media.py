# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import random
from typing import Literal, Optional

import discord
import orjson
from bs4 import BeautifulSoup
from discord.ext import commands
from modules.media_embedders import InstagramEmbedder, TikTokEmbedder, TwitterEmbedder
from modules.misobot import MisoBot

from modules import emojis, exceptions, util


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🌐"

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

    @commands.command(usage="<instagram | tiktok> <on | off>")
    async def autoembedder(
        self,
        ctx: commands.Context,
        provider: Literal["instagram", "tiktok"],
        enabled: Optional[bool] = None,
    ):
        """Set up automatic embeds for various media sources

        The links will be expanded automatically when detected in chat,
        without requiring the use use the corresponding command

        Example:
            >autoembedder instagram on
            >autoembedder tiktok off
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        if enabled is None:
            # show current state
            data = await self.bot.db.fetch_value(
                f"""
                SELECT {provider} FROM media_auto_embed_settings WHERE guild_id = %s
                """,
                ctx.guild.id,
            )
            if data is None:
                current_state = "Not configured"
            elif data:
                current_state = "ON"
            else:
                current_state = "OFF"

            return await ctx.send(
                embed=discord.Embed(
                    description=(
                        f"{provider.capitalize()} automatic embeds are "
                        f"currently **{current_state}** for this server"
                    )
                )
            )

        # set new state
        if enabled:
            # check for donation status if trying to turn on
            await util.patron_check(ctx)

        await self.bot.db.execute(
            f"""
            INSERT INTO media_auto_embed_settings (guild_id, {provider})
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                {provider} = %s
            """,
            ctx.guild.id,
            enabled,
            enabled,
        )

        await self.bot.cache.cache_auto_embedders()

        await util.send_success(
            ctx,
            f"{provider.capitalize()} automatic embeds are now "
            f"**{'ON' if enabled else 'OFF'}** for this server",
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

    # @discord.ui.button(
    #     label="Powered by GIPHY", style=discord.ButtonStyle.secondary, disabled=True
    # )
    # async def giphy_label(self, _, __):
    #     pass

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
