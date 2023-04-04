# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot 

import asyncio
import copy
import io
import math
import os
import re
from collections import namedtuple
from time import time
from typing import TYPE_CHECKING, Callable, Optional

import aiohttp
import arrow
import colorgram
import discord
import regex
from discord.ext import commands
from durations_nlp import Duration
from loguru import logger
from PIL import Image, UnidentifiedImageError
from random_user_agent.params import HardwareType
from random_user_agent.user_agent import UserAgent

from modules import emoji_literals, emojis, exceptions, queries

if TYPE_CHECKING:
    from modules.misobot import MisoBot

IMAGE_SERVER_HOST = os.environ.get("IMAGE_SERVER_HOST")

Rgb = namedtuple("Rgb", ("r", "g", "b"))


class ErrorMessage(Exception):
    pass


class PatronCheckFailure(commands.CheckFailure):
    pass


class KeywordArguments:
    @classmethod
    def from_arguments(cls, args: tuple):
        try:
            return cls(**{k: v for d in args for k, v in d.items()})
        except TypeError as e:
            arg = str(e).split("'")[1]
            options = [f"`{o}`" for o in cls.__init__.__code__.co_varnames[1:]]
            raise exceptions.CommandWarning(
                f"Unknown option `{arg}`, available options: {', '.join(options)}"
            )


class KeywordCommandArgument:
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            option, value = argument.split("=", 1)
        except ValueError:
            raise commands.BadArgument(
                f"Cannot parse `{argument}`, Please give arguments in `option=value` format.\n"
                "Refer to the command help for list of options (`>help [commandname]`)"
            )
        return {option: value}


async def suppress(message: discord.Message):
    try:
        await message.edit(suppress=True)
    except (discord.Forbidden, discord.NotFound):
        pass


def displayname(member: Optional[discord.User | discord.Member], escape=True):
    if member is None:
        return None

    name = member.name
    if isinstance(member, discord.Member) and member.nick is not None:
        name = member.nick

    if escape:
        name = discord.utils.escape_markdown(name)

    return name


def displaychannel(
    channel: Optional[
        discord.StageChannel
        | discord.TextChannel
        | discord.Thread
        | discord.DMChannel
        | discord.VoiceChannel
        | discord.GroupChannel
        | discord.PartialMessageable
    ],
):
    match channel:
        case discord.Thread():
            return f"#{channel.parent}/{channel.name}"
        case discord.DMChannel():
            return f"@{channel.recipient}"
        case discord.TextChannel() | discord.GroupChannel():
            return f"#{channel.name}"
        case discord.VoiceChannel():
            return f"🔊 {channel.name}"
        case None:
            return "Unknown Channel"
        case _:
            return f"#{channel.id}"


async def send_success(target: discord.abc.Messageable, message: str):
    await target.send(
        embed=discord.Embed(
            description=f":white_check_mark: {message}",
            color=int("77b255", 16),
        )
    )


async def find_user(bot: "MisoBot", user_id: int) -> discord.User | None:
    if user := bot.get_user(user_id):
        return user

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        return None


async def determine_prefix(bot, message: discord.Message):
    """Get the prefix used in the invocation context"""
    if message.guild:
        prefix = bot.cache.prefixes.get(str(message.guild.id), bot.default_prefix)
        return commands.when_mentioned_or(prefix)(bot, message)
    return commands.when_mentioned_or(bot.default_prefix)(bot, message)


async def is_blacklisted(ctx: commands.Context) -> bool:
    """Check command invocation context for blacklist triggers"""
    if ctx.author.id in ctx.bot.cache.blacklist["global"]["user"]:
        raise exceptions.BlacklistedUser()

    if ctx.guild is None or ctx.command is None:
        return True

    if ctx.guild.id in ctx.bot.cache.blacklist["global"]["guild"]:
        raise exceptions.BlacklistedGuild()

    if ctx.channel.id in ctx.bot.cache.blacklist["global"]["channel"]:
        raise exceptions.BlacklistedChannel()

    if ctx.bot.cache.blacklist.get(str(ctx.guild.id)) is not None:
        if ctx.author.id in ctx.bot.cache.blacklist[str(ctx.guild.id)]["member"]:
            raise exceptions.BlacklistedMember()

        if (
            ctx.command.qualified_name.lower()
            in ctx.bot.cache.blacklist[str(ctx.guild.id)]["command"]
        ):
            raise exceptions.BlacklistedCommand()

    return True


def flags_to_badges(user: discord.User | discord.Member):
    """Get list of badge emojis from public user flags"""
    result = []
    for flag, value in iter(user.public_flags):
        if value:
            try:
                result.append(emojis.Badge[flag].value)
            except KeyError:
                logger.warning(f"Badge with no emoji associated with it: {flag}")

    if isinstance(user, discord.Member) and user.premium_since is not None:
        result.append(emojis.Badge["boosting"].value)
    return result or ["-"]


async def send_as_pages(
    ctx: commands.Context,
    content: discord.Embed,
    rows: list[str],
    maxrows=15,
    maxpages=10,
    send_to: Optional[discord.abc.Messageable] = None,
):
    """
    :param ctx     : Context
    :param content : Base embed
    :param rows    : Embed description rows
    :param maxrows : Maximum amount of rows per page
    :param maxpages: Maximum amount of pages untill cut off
    """
    pages = create_pages(content, rows, maxrows, maxpages)
    if len(pages) > 1:
        await page_switcher(ctx, pages, send_to=send_to)
    else:
        await (send_to or ctx).send(embed=pages[0])


async def text_based_page_switcher(
    ctx: commands.Context, pages: list[str], prefix="```", suffix="```", numbers=True
):
    """
    :param ctx    : Context
    :param pages  : List of strings
    :param prefix : String to prefix every page with
    :param suffix : String to suffix every page with
    :param numbers: Add page numbers to suffix
    """
    total_rows = len("\n".join(pages).split("\n"))

    # add all page numbers
    if numbers:
        seen_rows = 0
        for i, page in enumerate(pages, start=1):
            seen_rows += len(page.split("\n"))
            page += f"\n{i}/{len(pages)} | {seen_rows}/{total_rows}{suffix}"
            page = prefix + "\n" + page
            pages[i - 1] = page

    page_iterator = TwoWayIterator(pages)

    msg = await ctx.send(page_iterator.current())

    async def switch_page(new_page):
        await msg.edit(content=new_page)

    async def previous_page():
        content = page_iterator.previous()
        if content is not None:
            await switch_page(content)

    async def next_page():
        content = page_iterator.next()
        if content is not None:
            await switch_page(content)

    functions = {"⬅": previous_page, "➡": next_page}
    asyncio.ensure_future(reaction_buttons(ctx, msg, functions))


async def page_switcher(
    ctx: commands.Context,
    pages: list[discord.Embed],
    send_to: Optional[discord.abc.Messageable] = None,
):
    """
    :param ctx   : Context
    :param pages : List of embeds to use as pages
    """
    if len(pages) == 1:
        return await (send_to or ctx).send(embed=pages[0])

    page_iterator = TwoWayIterator(pages)

    # add all page numbers
    for i, page in enumerate(page_iterator.items, start=1):
        old_footer = page.footer.text
        page.set_footer(
            text=f"{i}/{len(page_iterator.items)}"
            + (f" | {old_footer}" if old_footer is not None else "")
        )

    msg = await (send_to or ctx).send(embed=page_iterator.current())

    async def switch_page(content):
        await msg.edit(embed=content)

    async def previous_page():
        content = page_iterator.previous()
        if content is not None:
            await switch_page(content)

    async def next_page():
        content = page_iterator.next()
        if content is not None:
            await switch_page(content)

    functions = {"⬅": previous_page, "➡": next_page}
    asyncio.ensure_future(reaction_buttons(ctx, msg, functions))


def create_pages(content: discord.Embed, rows: list[str], maxrows=15, maxpages=10):
    """
    :param content : Embed object to use as the base
    :param rows    : List of rows to use for the embed description
    :param maxrows : Maximum amount of rows per page
    :param maxpages: Maximu amount of pages until cut off
    :returns       : List of Embed objects
    """
    pages = []
    content.description = ""
    thisrow = 0
    rowcount = len(rows)
    done = False
    for row in rows:
        thisrow += 1
        if len(content.description) + len(row) < 2000 and thisrow < maxrows + 1:
            content.description += f"\n{row}"
        else:
            thisrow = 1
            if len(pages) == maxpages - 1:
                content.description += f"\n*+ {rowcount} more entries...*"
                pages.append(content)
                done = True
                break

            pages.append(content)
            content = copy.deepcopy(content)
            content.description = f"{row}"
        rowcount -= 1
    if not done and content.description != "":
        pages.append(content)

    return pages


async def paginate_list(ctx, items, use_locking=False, only_author=False, index_entries=True):
    pages = TwoWayIterator(items)
    if index_entries:
        msg = await ctx.send(f"`{pages.index + 1}.` {pages.current()}")
    else:
        msg = await ctx.send(pages.current())

    async def next_result() -> bool:
        new_content = pages.next()
        if new_content:
            if index_entries:
                await msg.edit(content=f"`{pages.index + 1}.` {new_content}", embed=None)
            else:
                await msg.edit(content=new_content, embed=None)
        return False

    async def previous_result() -> bool:
        new_content = pages.previous()
        if new_content:
            await msg.edit(content=new_content, embed=None)
        return False

    async def done() -> bool:
        await msg.edit(content=f"{pages.current()}")
        return True

    functions = {"⬅": previous_result, "➡": next_result}
    if use_locking:
        functions["🔒"] = done

    asyncio.ensure_future(reaction_buttons(ctx, msg, functions, only_author=only_author))


async def reaction_buttons(
    ctx: commands.Context,
    message: discord.Message,
    functions: dict[str, Callable],
    timeout=300.0,
    only_author=False,
    single_use=False,
    only_owner=False,
    send_to: Optional[discord.abc.Messageable] = None,
):
    """
    Handler for reaction buttons
    :param message     : message to add reactions to
    :param functions   : dictionary of {emoji : function} pairs. functions must be async.
                         return True to exit
    :param timeout     : time in seconds for how long the buttons work for.
    :param only_author : only allow the user who used the command use the buttons
    :param single_use  : delete buttons after one is used
    """
    try:
        for emojiname in functions:
            await message.add_reaction(emojiname)
    except discord.errors.Forbidden:
        return

    def check(payload):
        return (
            payload.message_id == message.id
            and str(payload.emoji) in functions
            and not payload.member == ctx.bot.user
            and (
                (payload.member.id == ctx.bot.owner_id)
                if only_owner
                else (payload.member == ctx.author or not only_author)
            )
        )

    while True:
        try:
            payload = await ctx.bot.wait_for("raw_reaction_add", timeout=timeout, check=check)

        except asyncio.TimeoutError:
            break
        else:
            try:
                exits = await functions[str(payload.emoji)]()
            except discord.errors.NotFound:
                # message was deleted
                return
            try:
                await message.remove_reaction(payload.emoji, payload.member)
            except discord.errors.NotFound:
                pass
            except discord.errors.Forbidden:
                await (send_to or ctx).send(
                    "`error: I'm missing required discord permission [ manage messages ]`"
                )
            if single_use or exits is True:
                break

    for emojiname in functions:
        try:
            await message.clear_reactions()
        except (discord.errors.NotFound, discord.errors.Forbidden):
            pass


def message_embed(message):
    """
    Creates a nice embed from message
    :param: message : discord.Message you want to embed
    :returns        : discord.Embed
    """
    content = discord.Embed()
    content.set_author(name=f"{message.author}", icon_url=message.author.display_avatar.url)
    content.description = message.content
    content.set_footer(text=f"{message.guild.name} | #{message.channel.name}")
    content.timestamp = message.created_at
    content.colour = message.author.color
    if message.attachments:
        content.set_image(url=message.attachments[0].proxy_url)

    return content


def timefromstring(s):
    """
    :param s : String to parse time from
    :returns : Time in seconds
    """
    s = s.removeprefix("for")
    return int(Duration(s).to_seconds())


def stringfromtime(t, accuracy=4):
    """
    :param t : Time in seconds
    :returns : Formatted string
    """
    m, s = divmod(t, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)

    components = []
    if d > 0:
        components.append(f"{int(d)} day" + ("s" if d != 1 else ""))
    if h > 0:
        components.append(f"{int(h)} hour" + ("s" if h != 1 else ""))
    if m > 0:
        components.append(f"{int(m)} minute" + ("s" if m != 1 else ""))
    if s > 0:
        components.append(f"{int(s)} second" + ("s" if s != 1 else ""))

    return " ".join(components[:accuracy])


def get_xp(level):
    """
    :param level : Level
    :return      : Amount of xp needed to reach the level
    """
    return math.ceil(math.pow((level - 1) / (0.05 * (1 + math.sqrt(5))), 2))


def get_level(xp):
    """
    :param xp : Amount of xp
    :returns  : Current level based on the amount of xp
    """
    return math.floor(0.05 * (1 + math.sqrt(5)) * math.sqrt(xp)) + 1


def xp_to_next_level(level):
    return get_xp(level + 1) - get_xp(level)


def xp_from_message(message):
    """
    :param message : Message to get the xp from
    :returns       : Amount of xp rewarded from given message. Minimum 1
    """
    words = message.content.split(" ")
    eligible_words = sum(len(x) > 1 for x in words)
    xp = eligible_words + (10 * len(message.attachments))
    if xp == 0:
        xp = 1

    return min(xp, 50)


async def get_user(ctx, argument, fallback=None) -> discord.User | None:
    """
    :param argument : name, nickname, id, mention
    :param fallback : return this if not found
    :returns        : discord.User
    """
    if argument is None:
        return fallback
    try:
        return await commands.UserConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        return fallback


async def get_member(
    ctx, argument, fallback=None, try_user=False
) -> discord.Member | discord.User | None:
    """
    :param argument : name, nickname, id, mention
    :param fallback : return this if not found
    :param try_user : try to get user if not found
    :returns        : discord.Member | discord.User
    """
    if argument is None:
        return fallback
    try:
        return await commands.MemberConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        return await get_user(ctx, argument, fallback) if try_user else fallback


async def get_textchannel(ctx, argument, fallback=None, guildfilter=None):
    """
    :param argument    : name, id, mention
    :param fallback    : return this if not found
    :param guildfilter : guild to search for the channel in. defaults to ctx.guild
    :returns           : discord.TextChannel
    """
    if argument is None:
        return fallback
    if guildfilter is None:
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.errors.BadArgument:
            return fallback
    else:
        result = discord.utils.find(
            lambda m: argument in (m.name, m.id), guildfilter.text_channels
        )
        return result or fallback


async def get_role(ctx, argument, fallback=None):
    """
    :param argument : name, id, mention
    :param fallback : return this if not found
    :returns        : discord.Role
    """
    if argument is None:
        return fallback
    try:
        return await commands.RoleConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        return fallback


async def get_color(ctx, argument: str, fallback=None):
    """
    :param argument : hex or discord color name
    :param fallback : return this if not found
    :returns        : discord.Color or None
    """
    if argument is None:
        return fallback
    try:
        return await commands.ColourConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        try:
            return await commands.ColourConverter().convert(ctx, f"#{argument}")
        except commands.errors.BadArgument:
            return fallback


async def get_emoji(ctx, argument, fallback=None):
    """
    :param argument : name, id, message representation
    :param fallback : return this if not found
    :returns        : discord.Emoji | discord.PartialEmoji
    """
    if argument is None:
        return fallback
    try:
        return await commands.EmojiConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        try:
            return await commands.PartialEmojiConverter().convert(ctx, argument)
        except commands.errors.BadArgument:
            return fallback


async def get_guild(ctx, argument, fallback=None):
    """
    :param argument : name, id
    :param fallback : return this if not found
    :returns        : discord.Guild
    """
    result = discord.utils.find(lambda m: argument in (m.name, m.id), ctx.bot.guilds)
    return result or fallback


async def command_group_help(ctx):
    """Sends default command help if group command is invoked on it's own"""
    if ctx.invoked_subcommand is None:
        await ctx.bot.help_command.group_help_brief(ctx, ctx.command)
        return True
    return False


async def send_command_help(ctx):
    """Sends default command help"""
    await ctx.send_help(ctx.invoked_subcommand or ctx.command)


def map_to_range(input_value, input_start, input_end, output_start, output_end):
    return output_start + ((output_end - output_start) / (input_end - input_start)) * (
        input_value - input_start
    )


def rgb_to_hex(rgb):
    """
    :param rgb : RBG color in tuple of 3
    :return    : Hex color string
    """
    r, g, b = rgb

    def clamp(x):
        return max(0, min(x, 255))

    return "{0:02x}{1:02x}{2:02x}".format(clamp(r), clamp(g), clamp(b))


async def color_from_image_url(
    session,
    url,
    fallback="202225",
    size_limit=False,
    ignore_errors=True,
):
    """
    :param url      : image url
    :param fallback : the color to return in case the operation fails
    :return         : hex color code of the most dominant color in the image
    """
    if url.strip() == "":
        return fallback
    try:
        async with session.get(url) as response:
            image = Image.open(io.BytesIO(await response.read()))
            if size_limit and sum(image.size) > 2048:
                raise ValueError("Image is too large")
            colors = await asyncio.get_running_loop().run_in_executor(
                None, lambda: colorgram.extract(image, 1)
            )
            dominant_color: Rgb = colors[0].rgb
    except Exception as e:
        if ignore_errors:
            return fallback
        else:
            raise e

    return rgb_to_hex(dominant_color)


async def rgb_from_image_url(session: aiohttp.ClientSession, url: str) -> Rgb | None:
    try:
        async with session.get(url) as response:
            image = Image.open(io.BytesIO(await response.read()))
            colors = await asyncio.get_running_loop().run_in_executor(
                None, lambda: colorgram.extract(image, 1)
            )
            return colors[0].rgb
    except aiohttp.InvalidURL:
        return None


def find_unicode_emojis(text):
    """Finds and returns all unicode emojis from a string"""
    emoji_list = set()

    # yeah.
    # it's an emoji regex.
    # what do you want from me.
    data = regex.findall(
        r"(?:\U0001f1e6[\U0001f1e8-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f2\U0001f1f4\U0001f1f6-\U0001f1fa\U0001f1fc\U0001f1fd\U0001f1ff])\|(?:\U0001f1e7[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ef\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1e8[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ee\U0001f1f0-\U0001f1f5\U0001f1f7\U0001f1fa-\U0001f1ff])|(?:\U0001f1e9[\U0001f1ea\U0001f1ec\U0001f1ef\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1ff])|(?:\U0001f1ea[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ed\U0001f1f7-\U0001f1fa])|(?:\U0001f1eb[\U0001f1ee-\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1f7])|(?:\U0001f1ec[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ee\U0001f1f1-\U0001f1f3\U0001f1f5-\U0001f1fa\U0001f1fc\U0001f1fe])|(?:\U0001f1ed[\U0001f1f0\U0001f1f2\U0001f1f3\U0001f1f7\U0001f1f9\U0001f1fa])|(?:\U0001f1ee[\U0001f1e8-\U0001f1ea\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9])|(?:\U0001f1ef[\U0001f1ea\U0001f1f2\U0001f1f4\U0001f1f5])|(?:\U0001f1f0[\U0001f1ea\U0001f1ec-\U0001f1ee\U0001f1f2\U0001f1f3\U0001f1f5\U0001f1f7\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1f1[\U0001f1e6-\U0001f1e8\U0001f1ee\U0001f1f0\U0001f1f7-\U0001f1fb\U0001f1fe])|(?:\U0001f1f2[\U0001f1e6\U0001f1e8-\U0001f1ed\U0001f1f0-\U0001f1ff])|(?:\U0001f1f3[\U0001f1e6\U0001f1e8\U0001f1ea-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f4\U0001f1f5\U0001f1f7\U0001f1fa\U0001f1ff])|\U0001f1f4\U0001f1f2|(?:\U0001f1f4[\U0001f1f2])|(?:\U0001f1f5[\U0001f1e6\U0001f1ea-\U0001f1ed\U0001f1f0-\U0001f1f3\U0001f1f7-\U0001f1f9\U0001f1fc\U0001f1fe])|\U0001f1f6\U0001f1e6|(?:\U0001f1f6[\U0001f1e6])|(?:\U0001f1f7[\U0001f1ea\U0001f1f4\U0001f1f8\U0001f1fa\U0001f1fc])|(?:\U0001f1f8[\U0001f1e6-\U0001f1ea\U0001f1ec-\U0001f1f4\U0001f1f7-\U0001f1f9\U0001f1fb\U0001f1fd-\U0001f1ff])|(?:\U0001f1f9[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ed\U0001f1ef-\U0001f1f4\U0001f1f7\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1ff])|(?:\U0001f1fa[\U0001f1e6\U0001f1ec\U0001f1f2\U0001f1f8\U0001f1fe\U0001f1ff])|(?:\U0001f1fb[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ee\U0001f1f3\U0001f1fa])|(?:\U0001f1fc[\U0001f1eb\U0001f1f8])|\U0001f1fd\U0001f1f0|(?:\U0001f1fd[\U0001f1f0])|(?:\U0001f1fe[\U0001f1ea\U0001f1f9])|(?:\U0001f1ff[\U0001f1e6\U0001f1f2\U0001f1fc])|(?:\U0001f3f3\ufe0f\u200d\U0001f308)|(?:\U0001f441\u200d\U0001f5e8)|(?:[\U0001f468\U0001f469]\u200d\u2764\ufe0f\u200d(?:\U0001f48b\u200d)?[\U0001f468\U0001f469])|(?:(?:(?:\U0001f468\u200d[\U0001f468\U0001f469])|(?:\U0001f469\u200d\U0001f469))(?:(?:\u200d\U0001f467(?:\u200d[\U0001f467\U0001f466])?)|(?:\u200d\U0001f466\u200d\U0001f466)))|(?:(?:(?:\U0001f468\u200d\U0001f468)|(?:\U0001f469\u200d\U0001f469))\u200d\U0001f466)|[\u2194-\u2199]|[\u23e9-\u23f3]|[\u23f8-\u23fa]|[\u25fb-\u25fe]|[\u2600-\u2604]|[\u2638-\u263a]|[\u2648-\u2653]|[\u2692-\u2694]|[\u26f0-\u26f5]|[\u26f7-\u26fa]|[\u2708-\u270d]|[\u2753-\u2755]|[\u2795-\u2797]|[\u2b05-\u2b07]|[\U0001f191-\U0001f19a]|[\U0001f1e6-\U0001f1ff]|[\U0001f232-\U0001f23a]|[\U0001f300-\U0001f321]|[\U0001f324-\U0001f393]|[\U0001f399-\U0001f39b]|[\U0001f39e-\U0001f3f0]|[\U0001f3f3-\U0001f3f5]|[\U0001f3f7-\U0001f3fa]|[\U0001f400-\U0001f4fd]|[\U0001f4ff-\U0001f53d]|[\U0001f549-\U0001f54e]|[\U0001f550-\U0001f567]|[\U0001f573-\U0001f57a]|[\U0001f58a-\U0001f58d]|[\U0001f5c2-\U0001f5c4]|[\U0001f5d1-\U0001f5d3]|[\U0001f5dc-\U0001f5de]|[\U0001f5fa-\U0001f64f]|[\U0001f680-\U0001f6c5]|[\U0001f6cb-\U0001f6d2]|[\U0001f6e0-\U0001f6e5]|[\U0001f6f3-\U0001f6f6]|[\U0001f910-\U0001f91e]|[\U0001f920-\U0001f927]|[\U0001f933-\U0001f93a]|[\U0001f93c-\U0001f93e]|[\U0001f940-\U0001f945]|[\U0001f947-\U0001f94b]|[\U0001f950-\U0001f95e]|[\U0001f980-\U0001f991]|\u00a9|\u00ae|\u203c|\u2049|\u2122|\u2139|\u21a9|\u21aa|\u231a|\u231b|\u2328|\u23cf|\u24c2|\u25aa|\u25ab|\u25b6|\u25c0|\u260e|\u2611|\u2614|\u2615|\u2618|\u261d|\u2620|\u2622|\u2623|\u2626|\u262a|\u262e|\u262f|\u2660|\u2663|\u2665|\u2666|\u2668|\u267b|\u267f|\u2696|\u2697|\u2699|\u269b|\u269c|\u26a0|\u26a1|\u26aa|\u26ab|\u26b0|\u26b1|\u26bd|\u26be|\u26c4|\u26c5|\u26c8|\u26ce|\u26cf|\u26d1|\u26d3|\u26d4|\u26e9|\u26ea|\u26fd|\u2702|\u2705|\u270f|\u2712|\u2714|\u2716|\u271d|\u2721|\u2728|\u2733|\u2734|\u2744|\u2747|\u274c|\u274e|\u2757|\u2763|\u2764|\u27a1|\u27b0|\u27bf|\u2934|\u2935|\u2b1b|\u2b1c|\u2b50|\u2b55|\u3030|\u303d|\u3297|\u3299|\U0001f004|\U0001f0cf|\U0001f170|\U0001f171|\U0001f17e|\U0001f17f|\U0001f18e|\U0001f201|\U0001f202|\U0001f21a|\U0001f22f|\U0001f250|\U0001f251|\U0001f396|\U0001f397|\U0001f56f|\U0001f570|\U0001f587|\U0001f590|\U0001f595|\U0001f596|\U0001f5a4|\U0001f5a5|\U0001f5a8|\U0001f5b1|\U0001f5b2|\U0001f5bc|\U0001f5e1|\U0001f5e3|\U0001f5e8|\U0001f5ef|\U0001f5f3|\U0001f6e9|\U0001f6eb|\U0001f6ec|\U0001f6f0|\U0001f930|\U0001f9c0|[#|0-9]\u20e3",
        text,
    )
    for word in data:
        name = emoji_literals.UNICODE_TO_NAME.get(word)
        if name is not None:
            emoji_list.add(name)

    return emoji_list


def find_custom_emojis(text):
    """Finds and returns all custom discord emojis from a string"""
    data = regex.findall(r"<(a?):([a-zA-Z0-9\_]+):([0-9]+)>", text)
    return {(emoji_name, emoji_id) for _a, emoji_name, emoji_id in data}


async def image_info_from_url(session: aiohttp.ClientSession, url) -> Optional[dict]:
    """Return dictionary containing filesize, filetype and dimensions of an image"""
    async with session.get(str(url)) as response:
        filesize = int(response.headers.get("Content-Length", 0)) / 1024
        filetype = response.headers.get("Content-Type")
        try:
            image = Image.open(io.BytesIO(await response.read()))
        except UnidentifiedImageError:
            return None

        dimensions = image.size
        if filesize > 1024:
            filesize = f"{filesize/1024:.2f}MB"
        else:
            filesize = f"{filesize:.2f}KB"

        return {
            "filesize": filesize,
            "filetype": filetype,
            "dimensions": f"{dimensions[0]}x{dimensions[1]}",
        }


class OptionalSubstitute(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def create_welcome_embed(user, guild, messageformat):
    """Creates and returns embed for welcome message"""
    if messageformat is None:
        messageformat = "Welcome **{username}** {mention} to **{server}**"

    content = discord.Embed(title="New member! :wave:", color=int("5dadec", 16))
    content.set_thumbnail(url=user.display_avatar.url)
    content.timestamp = arrow.utcnow().datetime
    content.set_footer(text=f"👤#{len(guild.members)}")
    substitutes = OptionalSubstitute(
        {
            "mention": user.mention,
            "user": user,
            "id": user.id,
            "server": guild.name,
            "guild": guild.name,
            "username": user.name,
        }
    )
    content.description = messageformat.format_map(substitutes)
    return content


def create_goodbye_message(user, guild, messageformat):
    """Formats a goodbye message"""
    if messageformat is None:
        messageformat = "Goodbye **{username}** {mention}"

    substitutes = OptionalSubstitute(
        {
            "mention": user.mention,
            "user": user,
            "id": user.id,
            "server": guild.name,
            "guild": guild.name,
            "username": user.name,
        }
    )
    return messageformat.format_map(substitutes)


class UserActivity:
    def __init__(self, activities):
        self.emoji: Optional[discord.PartialEmoji] = None
        self.status_texts: Optional[str] = None
        self.base: str = ""
        self.spotify: bool = False

        if activities is None:
            return

        for activity in activities:
            if isinstance(activity, discord.CustomActivity):
                self.emoji = activity.emoji
                self.status_text = activity.name

            elif isinstance(activity, discord.Activity):
                prefix = None
                if activity.type == discord.ActivityType.playing:
                    prefix = "Playing"
                elif activity.type == discord.ActivityType.streaming:
                    prefix = "Streaming"
                elif activity.type == discord.ActivityType.listening:
                    prefix = "Listening"
                elif activity.type == discord.ActivityType.watching:
                    prefix = "Watching"
                if prefix:
                    self.base = f"{prefix} "
                self.base += f"**{activity.name}**"

            elif isinstance(activity, discord.Spotify):
                self.spotify = True

            else:
                raise AttributeError(str(activity))

    def display(self):
        """Print user activity as it shows up on the sidebar"""
        result = ""
        if self.emoji:
            result += str(self.emoji)
            result += " "

        if self.status_text:
            result += self.status_text
        elif self.base:
            result += self.base
        elif self.spotify:
            result += "Listening to **Spotify**"

        return result


async def send_tasks_result_list(ctx, successful_operations, failed_operations, title=None):
    content = discord.Embed(
        color=(int("77b255", 16) if successful_operations else int("dd2e44", 16))
    )
    rows = [f":white_check_mark: {op}" for op in successful_operations]
    rows.extend(f":x: {op}" for op in failed_operations)
    content.description = "\n".join(rows)
    if title:
        content.title = title
    await ctx.send(embed=content)


async def patron_check(ctx):
    if ctx.author.id == ctx.bot.owner_id:
        return True
    if await queries.is_donator(ctx, ctx.author):
        return True
    if await queries.is_vip(ctx.bot, ctx.author):
        return True
    raise PatronCheckFailure


def patrons_only():
    async def predicate(ctx):
        return await patron_check(ctx)

    return commands.check(predicate)


def format_html(template, replacements):
    def dictsub(m):
        return str(replacements[m.group().strip("$")])

    return re.sub(r"\$(\S*?)\$", dictsub, template)


async def render_html(bot, payload, endpoint="html"):
    try:
        async with bot.session.post(
            f"http://{IMAGE_SERVER_HOST}:3000/{endpoint}", data=payload
        ) as response:
            if response.status == 200:
                return io.BytesIO(await response.read())
            raise exceptions.RendererError(f"{response.status} : {await response.text()}")
    except aiohttp.ClientConnectionError:
        raise exceptions.RendererError("Unable to connect to the HTML Rendering server")


def ordinal(n):
    """Return number with ordinal suffix eg. 1st, 2nd, 3rd, 4th..."""
    return str(n) + {1: "st", 2: "nd", 3: "rd"}.get(4 if 10 <= n % 100 < 20 else n % 10, "th")


async def require_chunked(guild: discord.Guild):
    if guild is not None and not guild.chunked:
        start_time = time()
        await guild.chunk(cache=True)
        logger.info(
            f"Chunked [{guild}] with {guild.member_count} members in {time() - start_time:.2f} seconds"
        )


user_agent_rotator = UserAgent(hardware_types=[HardwareType.COMPUTER.value], limit=100)


def random_user_agent():
    """Random User Agent String"""
    return user_agent_rotator.get_random_user_agent()


def asset_full_size(asset: discord.Asset) -> str:
    return asset.replace(size=4096).url


class TwoWayIterator:
    """Two way iterator class that is used as the backend for paging"""

    def __init__(self, list_of_stuff, loop=False):
        self.items = list_of_stuff
        self.loop = loop
        self.index = 0

    def next(self):
        if self.index == len(self.items) - 1:
            if self.loop:
                self.index = -1
            else:
                return None
        self.index += 1
        return self.items[self.index]

    def previous(self):
        if self.index == 0:
            if self.loop:
                self.index = len(self.items)
            else:
                return None
        self.index -= 1
        return self.items[self.index]

    def current(self):
        return self.items[self.index]


def log_command_format(ctx, extra: str = ""):
    try:
        took = time() - ctx.timer
    except AttributeError:
        took = 0

    guild = ctx.guild.name if ctx.guild is not None else "DM"
    user = str(ctx.author)
    return f"{guild} @ {user} : {ctx.message.content} ({took:.2f}s) {extra}"


async def shorten_url(bot: "MisoBot", long_url: str, tags: list[str] = list()):
    data = {
        "longUrl": long_url,
        "validateUrl": True,
        "tags": tags,
        "title": "string",
        "crawlable": True,
        "findIfExists": True,
    }

    headers = {"accept": "application/json", "X-Api-Key": bot.keychain.SHLINK_API_KEY}
    async with bot.session.post(
        "http://shlink:8080/rest/v3/short-urls", json=data, headers=headers
    ) as response:
        response.raise_for_status()
        data = await response.json()
        return data["shortUrl"]
