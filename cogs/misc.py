# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import base64
import os
import random
import re
import urllib.parse
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

import arrow
import discord
import minestat
import orjson
from aiohttp import ClientResponseError
from bs4 import BeautifulSoup
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from modules import emoji_literals, exceptions, util
from modules.emojifier import Emojifier
from modules.misobot import MisoBot

EMOJIFIER_HOST = os.environ.get("EMOJIFIER_HOST")


class Misc(commands.Cog):
    """Miscellaneous commands"""

    def __init__(self, bot: MisoBot):
        self.bot: MisoBot = bot
        self.icon: str = "🔮"
        self.emojifier: Emojifier = Emojifier(bot)
        self.hs: dict = {
            "aries": {
                "name": "Aries",
                "emoji": ":aries:",
                "date_range": "Mar 21 - Apr 19",
                "id": 1,
            },
            "taurus": {
                "name": "Taurus",
                "emoji": ":taurus:",
                "date_range": "Apr 20 - May 20",
                "id": 2,
            },
            "gemini": {
                "name": "Gemini",
                "emoji": ":gemini:",
                "date_range": "May 21 - Jun 20",
                "id": 3,
            },
            "cancer": {
                "name": "Cancer",
                "emoji": ":cancer:",
                "date_range": "Jun 21 - Jul 22",
                "id": 4,
            },
            "leo": {
                "name": "Leo",
                "emoji": ":leo:",
                "date_range": "Jul 23 - Aug 22",
                "id": 5,
            },
            "virgo": {
                "name": "Virgo",
                "emoji": ":virgo:",
                "date_range": "Aug 23 - Sep 22",
                "id": 6,
            },
            "libra": {
                "name": "Libra",
                "emoji": ":libra:",
                "date_range": "Sep 23 - Oct 22",
                "id": 7,
            },
            "scorpio": {
                "name": "Scorpio",
                "emoji": ":scorpius:",
                "date_range": "Oct 23 - Nov 21",
                "id": 8,
            },
            "sagittarius": {
                "name": "Sagittarius",
                "emoji": ":sagittarius:",
                "date_range": "Nov 22 - Dec 21",
                "id": 9,
            },
            "capricorn": {
                "name": "Capricorn",
                "emoji": ":capricorn:",
                "date_range": "Dec 22 - Jan 19",
                "id": 10,
            },
            "aquarius": {
                "name": "Aquarius",
                "emoji": ":aquarius:",
                "date_range": "Jan 20 - Feb 18",
                "id": 11,
            },
            "pisces": {
                "name": "Pisces",
                "emoji": ":pisces:",
                "date_range": "Feb 19 - Mar 20",
                "id": 12,
            },
        }

    @commands.command(aliases=["random"], usage="<n>-[m]")
    async def rng(self, ctx: commands.Context, *, number_range):
        """Random number generator

        Usage:
            >rng <n>
            >rng <n-m>
        """
        try:
            values = [int(x) for x in number_range.split("-")]
        except ValueError:
            return await ctx.send(
                ":warning: Please give a valid number range to choose from"
            )
        if len(values) == 2:
            start, end = values
        else:
            start = 0
            end = values[0]
        choice = random.randint(start, end)
        await ctx.send(f"Random range `{start}-{end}`\n> **{choice}**")

    @commands.command()
    async def advice(self, ctx: commands.Context):
        """Get some life advice"""
        # for some reason the api is missing content for these ids
        missing_ids = {0, 22, 48, 67}
        slip_id = 0
        while slip_id in missing_ids:
            slip_id = random.randint(1, 224)
        url = f"https://api.adviceslip.com/advice/{slip_id}"
        async with self.bot.session.get(url) as response:
            data = orjson.loads(await response.text())
        try:
            await ctx.send(f"*{data['slip']['advice']}*")
        except KeyError:
            raise exceptions.CommandError(f"slip_id={slip_id} :: {data}")

    @commands.command()
    async def affirmation(self, ctx: commands.Context):
        """Get some affirmation"""
        async with self.bot.session.get("https://www.affirmations.dev") as response:
            data = await response.json(loads=orjson.loads)
        await ctx.send(f"*{data['affirmation']}*")

    @commands.command()
    async def joke(self, ctx: commands.Context):
        """Get a random dad joke"""
        async with self.bot.session.get(
            "https://icanhazdadjoke.com/",
            headers={"Accept": "application/json"},
        ) as response:
            data = await response.json(loads=orjson.loads)

        await ctx.send(f"<:funwaa:1063446110565310515> {data['joke']}")

    @commands.command(aliases=["imbored"])
    async def iambored(self, ctx: commands.Context):
        """Get something to do"""
        url = "https://bored.api.lewagon.com/api/activity"
        async with self.bot.session.get(url) as response:
            data = await response.json(loads=orjson.loads)

        activity_emoji = {
            "education": ":books:",
            "recreational": ":carousel_horse:",
            "social": ":champagne_glass:",
            "diy": ":tools:",
            "charity": ":juggling:",
            "cooking": ":cook:",
            "relaxation": ":beach:",
            "music": ":saxophone:",
            "busywork": ":broom:",
        }
        await ctx.send(f"{activity_emoji.get(data['type'], '')} {data['activity']}")

    @commands.command(aliases=["8ball"])
    async def eightball(self, ctx: commands.Context, *, question):
        """Ask a yes/no question"""
        choices = [
            # yes
            "Yes, definitely",
            "Yes",
            "Yass",
            "Most likely yes",
            "I think so, yes",
            "Absolutely!",
            # indecisive
            "Maybe",
            "Perhaps",
            "Possibly",
            # no
            "I don't think so",
            "No",
            "Most likely not",
            "Absolutely not!",
            "In your dreams",
            "Naur",
        ]
        answer = random.choice(choices)
        question = question + ("" if question.endswith("?") else "?")
        await ctx.send(f"> {question}\n**{answer}**")

    @commands.command()
    async def choose(self, ctx: commands.Context, *, choices):
        """Choose from given options.

        Usage:
            >choose <thing_1> or <thing_2> or ... or <thing_n>
        """
        choices = choices.split(" or ")
        if len(choices) < 2:
            return await ctx.send(
                "Give me at least 2 options to choose from! (separate options with `or`)"
            )
        choice = random.choice(choices).strip()
        await ctx.send(f"I choose **{choice}**")

    @commands.command()
    async def ship(self, ctx: commands.Context, *, names):
        """Ship two names and get your chance for succesful love.

        Usage:
            >ship <name> and <name>
        """
        nameslist = names.split(" and ")
        if len(nameslist) != 2:
            nameslist = names.split(" ", 1)
            if len(nameslist) < 2:
                return await ctx.send("Please give two names separated with `and`")

        lovenums = [0, 0, 0, 0, 0]
        for c in names:
            c = c.lower()
            if c == "e":
                lovenums[3] += 1
            elif c == "l":
                lovenums[0] += 1
            elif c == "o":
                lovenums[1] += 1
            elif c == "s":
                lovenums[4] += 1

            elif c == "v":
                lovenums[2] += 1
        while max(lovenums) > 9:
            newnums = []
            for n in lovenums:
                if n > 9:
                    newnums.extend((n // 10, n % 10))
                else:
                    newnums.append(n)
            lovenums = newnums

        it = 0
        maxit = (
            100  # Maximum iterations allowed in below algorithm to attempt convergence
        )
        maxlen = 100  # Maximum length of generated list allowed (some cases grow list infinitely)
        while len(lovenums) > 2 and it < maxit and len(lovenums) < maxlen:
            newnums = []
            it += 1
            for i in range(len(lovenums) - 1):
                pairsum = lovenums[i] + lovenums[i + 1]
                if pairsum < 10:
                    newnums.append(pairsum)
                else:
                    newnums.extend((1, pairsum % 10))
            lovenums = newnums

        # This if-else matches with original site alg handling of
        # non-convergent result. (i.e. defaulting to 1%)
        # Technically, you can leave this section as it was previously
        # and still get a non-trivial outputtable result since the length is always at least 2.
        percentage = lovenums[0] * 10 + lovenums[1] if len(lovenums) == 2 else 1
        if percentage < 25:
            emoji = ":broken_heart:"
            text = (
                f"Dr. Love thinks a relationship might work out between {nameslist[0]} "
                f"and {nameslist[1]}, but the chance is very small. "
                "A successful relationship is possible, but you both have to work on it. "
                "Do not sit back and think that it will all work out fine, "
                "because it might not be working out the way you wanted it to. "
                "Spend as much time with each other as possible. Again, the chance of this "
                "relationship working out is very small, so even when you do work hard on it, "
                "it still might not work out."
            )
        elif percentage < 50:
            emoji = ":heart:"
            text = (
                f"The chance of a relationship working out between {nameslist[0]} and "
                f"{nameslist[1]} is not very big, but a relationship is very well possible, "
                "if the two of you really want it to, and are prepared to make some sacrifices for "
                "it. You'll have to spend a lot of quality time together. You must be aware of the "
                "fact that this relationship might not work out at all, "
                "no matter how much time you invest in it."
            )
        elif percentage < 75:
            emoji = ":heart:"
            text = (
                f"Dr. Love thinks that a relationship between {nameslist[0]} and {nameslist[1]} "
                "has a reasonable chance of working out, but on the other hand, it might not. "
                "Your relationship may suffer good and bad times. If things might not be working "
                "out as you would like them to, do not hesitate to talk about it with the person "
                "involved. Spend time together, talk with each other."
            )
        else:
            emoji = ":sparkling_heart:"
            text = (
                f"Dr. Love thinks that a relationship between {nameslist[0]} and {nameslist[1]} "
                "has a very good chance of being successful, but this doesn't mean that you don't "
                "have to work on the relationship. Remember that every relationship needs spending "
                "time together, talking with each other etc."
            )

        content = discord.Embed(
            title=f"{nameslist[0]} {emoji} {nameslist[1]} - {percentage}%",
            colour=discord.Colour.magenta(),
        )
        content.description = text
        await ctx.send(embed=content)

    @commands.command(aliases=["mc"])
    @commands.guild_only()
    async def minecraft(self, ctx: commands.Context, address=None, port=None):
        """Get the status of a minecraft server"""
        if address == "set" and ctx.guild:
            if port is None:
                return await ctx.send(
                    f"Save minecraft server address for this discord server:\n"
                    f"`{ctx.prefix}minecraft set <address>` (port defaults to 25565)\n"
                    f"`{ctx.prefix}minecraft set <address>:<port>`"
                )

            address = port.split(":")[0]
            try:
                port = int(port.split(":")[1])
            except IndexError:
                port = 25565

            await self.bot.db.execute(
                """
                INSERT INTO minecraft_server (guild_id, server_address, port)
                    VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    server_address = VALUES(server_address),
                    port = VALUES(port)
                """,
                ctx.guild.id,
                address,
                port,
            )
            return await util.send_success(
                ctx,
                f"Default Minecraft server of this discord saved as `{address}:{port}`",
            )

        if address is None:
            data = (
                await self.bot.db.fetch_row(
                    "SELECT server_address, port FROM minecraft_server WHERE guild_id = %s",
                    ctx.guild.id,
                )
                if ctx.guild
                else None
            )
            if not data:
                raise exceptions.CommandInfo(
                    "No default Minecraft server saved for this discord server!"
                    f"Use `{ctx.prefix}minecraft set` to save one or"
                    f"`{ctx.prefix}minecraft <address> <port>` to see any server"
                )

            address, port = data

        server = await self.bot.loop.run_in_executor(
            None, lambda: minestat.MineStat(address, int(port) if port else 0)
        )
        content = discord.Embed()
        if server.online:
            content.color = int("43b581", 16)
            content.add_field(name="Server Address", value=f"`{server.address}`")
            content.add_field(name="Port", value=f"`{server.port}`")
            content.add_field(
                name="Players", value=f"{server.current_players}/{server.max_players}"
            )
            content.add_field(
                name="Status", value="<:online:783745533457203212> Online"
            )
            content.add_field(name="Latency", value=f"{server.latency}ms")
            content.add_field(name="Version", value=server.version)
            content.set_footer(text=f"{server.stripped_motd}")
        else:
            content.color = int("ff0000", 16)
            content.add_field(name="Server Address", value=f"`{server.address}`")
            content.add_field(name="Port", value=f"`{server.port}`")
            content.add_field(
                name="Status", value="<:offline:749966834031394886> Offline"
            )
            content.description = f"**`{server.connection_status}`**"

        favicon = server.favicon_b64
        if favicon:
            missing_padding = len(favicon) % 4
            if missing_padding:
                favicon += "=" * (4 - missing_padding)

            favicon_data = base64.b64decode(favicon.split(",")[1])
            file = discord.File(
                filename="servericon.png",
                fp=BytesIO(favicon_data),
            )
            content.set_thumbnail(url="attachment://servericon.png")
            await ctx.send(embed=content, file=file)
        else:
            content.set_thumbnail(
                url="https://media.minecraftforum.net/attachments/300/619/636977108000120237.png"
            )
            await ctx.send(embed=content)

    @commands.command()
    async def clap(self, ctx: commands.Context[MisoBot], *sentence):
        """Add a clap emoji between words"""
        await ctx.send(" 👏 ".join(sentence) + " 👏")

    @commands.group(aliases=["hs"], case_insensitive=True)
    async def horoscope(self, ctx: commands.Context[MisoBot]):
        """Get your daily horoscope"""
        if ctx.invoked_subcommand is None:
            await self.send_hs(ctx, "daily-today")

    @horoscope.command(name="tomorrow")
    async def horoscope_tomorrow(self, ctx: commands.Context[MisoBot]):
        """Get tomorrow's horoscope"""
        await self.send_hs(ctx, "daily-tomorrow")

    @horoscope.command(name="yesterday")
    async def horoscope_yesterday(self, ctx: commands.Context[MisoBot]):
        """Get yesterday's horoscope"""
        await self.send_hs(ctx, "daily-yesterday")

    @horoscope.command(name="weekly", aliases=["week"])
    async def horoscope_weekly(self, ctx: commands.Context[MisoBot]):
        """Get this week's horoscope"""
        await self.send_hs(ctx, "weekly")

    @horoscope.command(name="monthly", aliases=["month"])
    async def horoscope_monthly(self, ctx: commands.Context[MisoBot]):
        """Get this month's horoscope"""
        await self.send_hs(ctx, "monthly")

    async def send_hs(
        self,
        ctx: commands.Context[MisoBot],
        variant: Literal[
            "daily-yesterday", "daily-today", "daily-tomorrow", "weekly", "monthly"
        ],
    ):
        sunsign = await self.bot.db.fetch_value(
            "SELECT sunsign FROM user_settings WHERE user_id = %s",
            ctx.author.id,
        )
        if not sunsign or sunsign is None:
            raise exceptions.CommandInfo(
                "Please save your zodiac sign using `>horoscope set <sign>`\n"
                "Use `>horoscope list` if you don't know which one you are."
            )

        sign = self.hs[sunsign]

        async with self.bot.session.get(
            f"https://www.horoscope.com/us/horoscopes/general/horoscope-general-{variant}.aspx",
            params={"sign": sign["id"]},
        ) as response:
            response.raise_for_status()
            soup = BeautifulSoup(await response.text(), "lxml")
            paragraph = soup.select_one("p")

        if paragraph is None:
            raise exceptions.CommandError(
                "Something went wrong trying to get horoscope text"
            )

        date_node = paragraph.find("strong")
        if date_node is not None:
            date = date_node.text.strip()
            date_node.clear()  # type: ignore
        else:
            date = "[ERROR]"

        for line_break in paragraph.findAll("br"):
            line_break.replaceWith("\n")
        hs_text = paragraph.get_text().strip("- ")

        content = discord.Embed(
            color=int("9266cc", 16),
            title=f"{sign['emoji']} {sign['name']} | {date}",
            description=hs_text,
        )

        if variant.startswith("daily"):
            async with self.bot.session.get(
                f"https://www.horoscope.com/star-ratings/{variant.split('-')[-1]}/{sunsign}"
            ) as response:
                second_soup = BeautifulSoup(await response.text(), "lxml")
                wrapper = second_soup.select_one(".module-skin")

            if wrapper:
                titles = wrapper.findAll("h3")
                text = wrapper.findAll("p")
                for title, text in zip(titles, text):
                    star_count = len(title.select(".highlight"))
                    stars = star_count * ":star:"
                    emptystars = (5 - star_count) * "<:no_star:1092503441991008306>"
                    title_text = title.text.strip()
                    if title_text == "Sex":
                        title_text = "Romance"
                    content.add_field(
                        name=f"{title_text} {stars}{emptystars}",
                        value=text.text,
                        inline=False,
                    )

        await ctx.send(embed=content)

    @horoscope.command(name="set")
    async def horoscope_set(self, ctx: commands.Context, sign):
        """Save your zodiac sign"""
        sign = sign.lower()
        if self.hs.get(sign) is None:
            raise exceptions.CommandInfo(
                f"`{sign}` is not a valid zodiac! Use `>horoscope list` for a list of zodiacs."
            )

        await ctx.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, sunsign)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                sunsign = VALUES(sunsign)
            """,
            ctx.author.id,
            sign,
        )
        await ctx.send(
            f"Zodiac saved as **{sign.capitalize()}** {self.hs[sign]['emoji']}"
        )

    @horoscope.command(name="list")
    async def horoscope_list(self, ctx: commands.Context):
        """Get list of all zodiac signs"""
        content = discord.Embed(
            color=int("9266cc", 16),
            title=":crystal_ball: Zodiac signs",
            description="\n".join(
                f"{sign['emoji']} **{sign['name']}**: {sign['date_range']}"
                for sign in self.hs.values()
            ),
        )
        return await ctx.send(embed=content)

    @commands.command(
        aliases=["colour"], usage="<hex | @member | @role | 'random' | url> ..."
    )
    async def color(
        self,
        ctx: commands.Context,
        *sources: int | discord.Member | discord.Role | str,
    ):
        """
        Visualise colors

        Different color sources can be chained together to create patterns.

        Usage:
            >color <hex>
            >color <@member>
            >color <@role>
            >color random [amount]
            >color <image url>
        """
        if not sources and not ctx.message.attachments:
            return await util.send_command_help(ctx)

        if len(sources) > 50:
            await ctx.send("Maximum amount of colors is 50, ignoring rest...")

        colors = []
        next_is_random_count = False
        for source in sources[:50]:
            # random used with an amount
            if next_is_random_count and isinstance(source, int):
                slots = 50 - len(colors)
                amount = min(source, slots)
                colors += [
                    "{:06x}".format(random.randint(0, 0xFFFFFF)) for _ in range(amount)
                ]
                next_is_random_count = False
            # member or role color
            elif isinstance(source, (discord.Member, discord.Role)):
                colors.append(str(source.color))

            else:
                source = str(source).strip("#")
                converted_color = await util.get_color(ctx, source)
                # random without an amount
                if next_is_random_count:
                    colors.append("{:06x}".format(random.randint(0, 0xFFFFFF)))
                    next_is_random_count = False

                # image url
                elif source.startswith("http"):
                    try:
                        url_color = await util.color_from_image_url(
                            self.bot.session,
                            source,
                            fallback="",
                            size_limit=True,
                            ignore_errors=False,
                        )
                    except ValueError:
                        await ctx.send("Supplied image is too large!")
                    except UnidentifiedImageError:
                        await ctx.send("Supplied url is not an image!")
                    else:
                        if url_color:
                            colors.append(url_color)

                # random
                elif source.lower() == "random":
                    next_is_random_count = True

                # hex or named discord color
                elif converted_color is not None:
                    colors.append(str(converted_color))

                else:
                    await ctx.send(f"I don't know what to do with `{source}`")

        # random was last input without an amount
        if next_is_random_count:
            colors.append("{:06x}".format(random.randint(0, 0xFFFFFF)))

        # try attachments too
        for a in ctx.message.attachments:
            try:
                url_color = await util.color_from_image_url(
                    self.bot.session,
                    a.url,
                    fallback="",
                    size_limit=True,
                    ignore_errors=False,
                )
            except ValueError:
                await ctx.send("Supplied attachment is too large!")
            except UnidentifiedImageError:
                await ctx.send("Supplied attachment is not an image!")
            else:
                if url_color is not None:
                    colors.append(url_color)

        if not colors:
            raise exceptions.CommandInfo("There is nothing to show")

        colors = [x.strip("#") for x in colors]

        discord_color = await util.get_color(ctx, colors[0])
        if discord_color is None:
            raise exceptions.CommandError(f"Invalid color `#{colors[0]}`")

        content = discord.Embed(colour=int(colors[0], 16))
        url = "https://api.color.pizza/v1/" + ",".join(colors)
        async with self.bot.session.get(url) as response:
            colordata = await response.json(loads=orjson.loads)
            content.title = colordata["paletteTitle"]

        if len(colors) == 1:
            hexvalue = "#" + colors[0]
            rgbvalue = discord_color.to_rgb()
            content.add_field(name="Hex", value=f"`{hexvalue}`")
            content.add_field(name="RGB", value=f"`rgb{rgbvalue}`")
            image_url = (
                f"https://preview.colorkit.co/color/{colors[0]}.png"
                f"?type=article-preview-logo&size=social&colorname={urllib.parse.quote_plus(colordata['paletteTitle'])}"
            )
            content.set_image(url=image_url)
        else:
            content.description = "\n".join(
                [
                    f"`{c['requestedHex']}` **| {c['name']}**"
                    for c in colordata["colors"]
                ]
            )
            image_url = (
                "https://preview.colorkit.co/palette/"
                f"{'-'.join(x['requestedHex'].strip('#') for x in colordata['colors'])}.png?size=social"
            )
            content.set_image(url=image_url)

        await ctx.send(embed=content)

    @commands.command(name="emoji", aliases=["emote"])
    async def big_emoji(self, ctx: commands.Context, emoji_str: int | str):
        """
        Get source image and stats of an emoji

        Will display additional info if Miso is in the server where the emoji is located in.
        Displaying who added the emoji requires Miso to have manage emojis permission!

        Usage:
            >emoji :emoji:
        """
        my_emoji = self.parse_emoji(emoji_str)
        if my_emoji.name is None and my_emoji.id is None:
            return await ctx.send(my_emoji.url)

        content = discord.Embed(title=f"`:{my_emoji.name}:`")
        content.set_image(url=my_emoji.url)
        stats = await util.image_info_from_url(self.bot.session, my_emoji.url)
        if stats:
            content.set_footer(
                text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
            )

        if my_emoji.id and my_emoji.name:
            discord_emoji = self.bot.get_emoji(my_emoji.id)
            if discord_emoji and discord_emoji.guild:
                emoji = await discord_emoji.guild.fetch_emoji(my_emoji.id)
                desc = [f"Uploaded {arrow.get(emoji.created_at).format('D/M/YYYY')}"]
                if emoji.user:
                    desc.append(f"by **{emoji.user}**")
                if ctx.guild != emoji.guild:
                    desc.append(f"in **{emoji.guild}**")

                content.description = "\n".join(desc)
        else:
            content.description = "Default emoji"

        await ctx.send(embed=content)

    @commands.command()
    @commands.has_permissions(manage_emojis=True)
    async def steal(self, ctx: commands.Context, *emojis: int | str):
        """Steal emojis to your own server

        Use this command in the server where you want to add the emojis.
        Also works with emoji ID if you don't have access to it.

        You can also reply to any emoji with this command.
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        parsed_emojis = []
        if not emojis:
            if (
                ctx.message.reference
                and ctx.message.reference.message_id
                and isinstance(ctx.channel, (discord.Thread, discord.TextChannel))
            ):
                reply_message = await ctx.channel.fetch_message(
                    ctx.message.reference.message_id
                )
                parsed_emojis = [
                    f"<:{name}:{id}>"
                    for name, id in util.find_custom_emojis(reply_message.content)
                ]
                if not parsed_emojis:
                    raise exceptions.CommandWarning("Replied to message has no emojis")
            else:
                return await util.send_command_help(ctx)

        for emoji in parsed_emojis:
            my_emoji = self.parse_emoji(emoji)

            if my_emoji.name and not my_emoji.id:
                raise exceptions.CommandWarning(
                    "Why are you trying to steal a default emoji? :skull:"
                )

            async with self.bot.session.get(my_emoji.url) as response:
                try:
                    response.raise_for_status()
                    image_bytes = await response.read()
                except ClientResponseError:
                    raise exceptions.CommandWarning(f"No such emoji `{my_emoji.url}`")

            my_new_emoji = await ctx.guild.create_custom_emoji(
                name=my_emoji.name or "stolen_emoji",
                reason=f"Stolen by {ctx.author}",
                image=image_bytes,
            )

            await ctx.send(
                embed=discord.Embed(
                    description=(
                        f":pirate_flag: Succesfully stole `:{my_new_emoji.name}:` "
                        f"and added it to this server {my_new_emoji}"
                    ),
                    color=int("e6e7e8", 16),
                )
            )

    @commands.command(usage="<sticker>")
    @commands.has_permissions(manage_emojis=True)
    async def stealsticker(self, ctx: commands.Context):
        """Steal a sticker to your own server

        Use this command in the server where you want to add the stickers.

        You can also reply to any sticker with this command.
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        stickers = ctx.message.stickers
        if not stickers:
            if (
                ctx.message.reference
                and ctx.message.reference.message_id
                and isinstance(ctx.channel, (discord.Thread, discord.TextChannel))
            ):
                reply_message = await ctx.channel.fetch_message(
                    ctx.message.reference.message_id
                )
                if reply_message.stickers:
                    stickers = reply_message.stickers
                else:
                    raise exceptions.CommandWarning(
                        "Replied to message has no stickers"
                    )
            else:
                await util.send_command_help(ctx)

        for sticker in stickers:
            fetched_sticker = await sticker.fetch()

            if not isinstance(fetched_sticker, discord.GuildSticker):
                raise exceptions.CommandWarning(
                    "I cannot steal default discord stickers!"
                )

            sticker_file = await fetched_sticker.to_file()

            my_new_sticker = await ctx.guild.create_sticker(
                name=fetched_sticker.name,
                description=fetched_sticker.description or "",
                emoji=fetched_sticker.emoji,
                file=sticker_file,
            )
            content = discord.Embed(
                description=(
                    f":pirate_flag: Succesfully stole sticker `{my_new_sticker.name}` "
                    "and added it to this server"
                ),
                color=int("e6e7e8", 16),
            )
            content.set_thumbnail(url=my_new_sticker.url)
            await ctx.send(embed=content)

    @commands.command()
    async def emojify(
        self, ctx: commands.Context, *, text: discord.Message | str | None = None
    ):
        """Emojify some text.

        You can also reply to someone else's message to emojify it

        Usage:
            (as as reply) >emojify
            >emojify <text...>
            >emojify <link to message>
        """
        if (
            text is None
            and ctx.message.reference
            and ctx.message.reference.message_id
            and isinstance(ctx.channel, (discord.Thread, discord.TextChannel))
        ):
            reply_message = await ctx.channel.fetch_message(
                ctx.message.reference.message_id
            )
            input_text = reply_message.content
        else:
            input_text = (
                text.content if isinstance(text, discord.Message) else str(text)
            )

        result = self.emojifier.convert(input_text)

        try:
            await ctx.send(result)
        except discord.errors.HTTPException:
            raise exceptions.CommandWarning(
                "Your text once emojified is too long to send!"
            )

    @commands.command()
    async def meme(self, ctx: commands.Context, template: str, *, content):
        """Make memes with given templates of empty signs

        Available templates:
            olivia, yyxy, haseul, jihyo, dubu, chaeyoung, nayeon, trump, yeji
        """

        options = {}
        match template:
            case "olivia":
                options = {
                    "filename": "images/hye.jpg",
                    "boxdimensions": (206, 480, 530, 400),
                    "angle": 2,
                }
            case "yyxy":
                options = {
                    "filename": "images/yyxy.png",
                    "boxdimensions": (500, 92, 315, 467),
                    "angle": 1,
                }
            case "haseul":
                options = {
                    "filename": "images/haseul.jpg",
                    "boxdimensions": (212, 395, 275, 279),
                    "wm_size": 20,
                    "wm_color": (50, 50, 50, 100),
                    "angle": 4,
                }
            case "jihyo":
                options = {
                    "filename": "images/jihyo.jpg",
                    "boxdimensions": (272, 441, 518, 353),
                    "wm_color": (255, 255, 255, 255),
                    "angle": -7,
                }
            case "trump":
                options = {
                    "filename": "images/trump.jpg",
                    "boxdimensions": (761, 579, 406, 600),
                    "wm_color": (255, 255, 255, 255),
                }
            case "dubu":
                options = {
                    "filename": "images/dubu.jpg",
                    "boxdimensions": (287, 454, 512, 347),
                    "wm_color": (255, 255, 255, 255),
                    "angle": -3,
                }
            case "chaeyoung":
                options = {
                    "filename": "images/chae.jpg",
                    "boxdimensions": (109, 466, 467, 320),
                    "wm_color": (255, 255, 255, 255),
                    "angle": 3,
                }
            case "nayeon":
                options = {
                    "filename": "images/nayeon.jpg",
                    "boxdimensions": (247, 457, 531, 353),
                    "wm_color": (255, 255, 255, 255),
                    "angle": 5,
                }
            case "yeji":
                options = {
                    "filename": "images/yeji.jpg",
                    "boxdimensions": (139, 555, 529, 350),
                    "wm_color": (255, 255, 255, 255),
                    "angle": 0,
                }
            case _:
                raise exceptions.CommandWarning(f"No meme template called `{template}`")

        meme = await self.bot.loop.run_in_executor(
            None, lambda: self.meme_factory(ctx, text=content, **options)
        )
        await ctx.send(file=meme)

    @staticmethod
    def meme_factory(
        ctx: commands.Context,
        filename: str,
        boxdimensions: tuple[int, int, int, int],
        text: str,
        color: tuple[int, int, int] = (40, 40, 40),
        wm_size=30,
        wm_color: tuple[int, int, int, int] = (150, 150, 150, 100),
        angle=0,
    ):
        image = ImageObject(filename)
        image.write_box(*boxdimensions, color, text, angle=angle)
        image.write_watermark(wm_size, wm_color)

        save_location = f"downloads/{ctx.message.id}_output_{filename.split('/')[-1]}"
        image.save(save_location)

        with open(save_location, "rb") as img:
            meme = discord.File(img)

        os.remove(save_location)
        return meme

    def parse_emoji(self, emoji_str: str | int):
        my_emoji = DisplayEmoji(None, "", None)
        if isinstance(emoji_str, int):
            if discord_emoji := self.bot.get_emoji(emoji_str):
                my_emoji.id = discord_emoji.id
                my_emoji.animated = discord_emoji.animated
                my_emoji.name = discord_emoji.name
                my_emoji.url = discord_emoji.url
            else:
                # cant get any info about it just send the image
                my_emoji.url = f"https://cdn.discordapp.com/emojis/{emoji_str}"

        elif custom_emoji_match := re.search(r"<(a?)?:(\w+):(\d+)>", emoji_str):
            # is a custom emoji
            animated, emoji_name, emoji_id = custom_emoji_match.groups()
            my_emoji.url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}"
            my_emoji.name = emoji_name
            my_emoji.animated = animated == "a"
            my_emoji.id = int(emoji_id)
        elif emoji_name := emoji_literals.UNICODE_TO_NAME.get(emoji_str):
            codepoint = "-".join(
                f"{ord(e):x}" for e in emoji_literals.NAME_TO_UNICODE[emoji_name]
            )
            my_emoji.name = emoji_name.strip(":")
            my_emoji.url = f"https://twemoji.maxcdn.com/v/13.0.1/72x72/{codepoint}.png"
        else:
            # its nothin
            raise exceptions.CommandWarning("Invalid emoji!")

        return my_emoji


async def setup(bot):
    await bot.add_cog(Misc(bot))


@dataclass
class DisplayEmoji:
    id: int | None
    url: str
    name: str | None
    animated: bool = False


class ImageObject:
    def __init__(self, filename):
        self.filename = filename
        self.image = Image.open(self.filename)
        self.draw = ImageDraw.Draw(self.image)
        self.font = "NanumGothic.ttf"

    def get_text_size(self, font_size, text):
        font = ImageFont.truetype(self.font, font_size)
        return font.getbbox(text)[2:4]

    def save(self, filename=None):
        self.image.save(filename or self.filename)

    def write_watermark(self, size, color):
        font = ImageFont.truetype(self.font, size)
        self.draw.text((5, 5), "Created with Miso Bot", font=font, fill=color)

    def write_box(self, x, y, width, height, color, text, angle=0):
        font_size = 300

        while True:
            lines = []
            line = []
            size = (0, 0)
            line_height = 0
            words = text.split(" ")
            for word in words:
                if "\n" in word:
                    newline_words = word.split("\n")
                    new_line = " ".join(line + [newline_words[0]])
                    size = self.get_text_size(font_size, new_line)
                    line_height = size[1]
                    if size[0] <= width:
                        line.append(newline_words[0])
                    else:
                        lines.append(line)
                        line = [newline_words[0]]
                    lines.append(line)
                    if len(word.split("\n")) > 2:
                        lines.extend(
                            [newline_words[i]]
                            for i in range(1, len(word.split("\n")) - 1)
                        )
                    line = [newline_words[-1]]
                else:
                    new_line = " ".join(line + [word])
                    size = self.get_text_size(font_size, new_line)
                    line_height = size[1]
                    if size[0] <= width:
                        line.append(word)
                    else:
                        lines.append(line)
                        line = [word]

                # check after every word to exit prematurely
                size = self.get_text_size(font_size, " ".join(line))
                text_height = len(lines) * line_height
                if text_height > height or size[0] > width:
                    break

            # add leftover line to total
            if line:
                lines.append(line)

            text_height = len(lines) * line_height
            if text_height <= height and size[0] <= width:
                break

            font_size -= 1

        lines = [" ".join(line) for line in lines]
        font = ImageFont.truetype(self.font, font_size)

        txt = None
        if angle != 0:
            txt = Image.new("RGBA", (self.image.size))
            txtd = ImageDraw.Draw(txt)
        else:
            txtd = self.draw
        height = y
        for line in lines:
            total_size = self.get_text_size(font_size, line)
            x_left = int(x + ((width - total_size[0]) / 2))
            txtd.text((x_left, height), line, font=font, fill=color)
            height += line_height

        if angle != 0 and txt:
            txt = txt.rotate(angle, resample=Image.Resampling.BILINEAR)
            self.image.paste(txt, mask=txt)
