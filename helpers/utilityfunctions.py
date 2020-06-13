import math
import asyncio
import discord
import copy
import regex
import colorgram
import random
import datetime
import io
import emoji
import aiohttp
from discord.ext import commands
from PIL import Image
from data import database as db


class ErrorMessage(Exception):
    pass


async def determine_prefix(bot, message):
    """Get the prefix used in the invocation context."""
    guild = message.guild
    prefix = bot.default_prefix
    if guild:
        data = db.query("SELECT prefix FROM prefixes WHERE guild_id = ?", (guild.id,))
        if data is not None:
            prefix = data[0][0]

    return prefix


async def send_as_pages(ctx, content, rows, maxrows=15, maxpages=10):
    """
    :param ctx     : Context
    :param content : Base embed
    :param rows    : Embed description rows
    :param maxrows : Maximum amount of rows per page
    :param maxpages: Maximum amount of pages untill cut off
    """
    pages = create_pages(content, rows, maxrows, maxpages)
    if len(pages) > 1:
        await page_switcher(ctx, pages)
    else:
        await ctx.send(embed=pages[0])


async def text_based_page_switcher(
    ctx, pages, prefix="```", suffix="```", numbers=True
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

    pages = TwoWayIterator(pages)

    msg = await ctx.send(pages.current())

    async def switch_page(new_page):
        await msg.edit(content=new_page)

    async def previous_page():
        content = pages.previous()
        if content is not None:
            await switch_page(content)

    async def next_page():
        content = pages.next()
        if content is not None:
            await switch_page(content)

    functions = {"⬅": previous_page, "➡": next_page}
    asyncio.ensure_future(reaction_buttons(ctx, msg, functions))


async def page_switcher(ctx, pages):
    """
    :param ctx   : Context
    :param pages : List of embeds to use as pages
    """
    pages = TwoWayIterator(pages)

    # add all page numbers
    for i, page in enumerate(pages.items, start=1):
        old_footer = page.footer.text
        if old_footer == discord.Embed.Empty:
            old_footer = None
        page.set_footer(
            text=f"{i}/{len(pages.items)}"
            + (f" | {old_footer}" if old_footer is not None else "")
        )

    msg = await ctx.send(embed=pages.current())

    async def switch_page(content):
        await msg.edit(embed=content)

    async def previous_page():
        content = pages.previous()
        if content is not None:
            await switch_page(content)

    async def next_page():
        content = pages.next()
        if content is not None:
            await switch_page(content)

    functions = {"⬅": previous_page, "➡": next_page}
    asyncio.ensure_future(reaction_buttons(ctx, msg, functions))


def create_pages(content, rows, maxrows=15, maxpages=10):
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
    for row in rows:
        thisrow += 1
        if len(content.description) + len(row) < 2000 and thisrow < maxrows + 1:
            content.description += f"\n{row}"
            rowcount -= 1
        else:
            thisrow = 1
            if len(pages) == maxpages - 1:
                content.description += f"\n*+ {rowcount} more entries...*"
                pages.append(content)
                content = None
                break

            pages.append(content)
            content = copy.deepcopy(content)
            content.description = f"{row}"
            rowcount -= 1

    if content is not None and not content.description == "":
        pages.append(content)

    return pages


async def reaction_buttons(
    ctx, message, functions, timeout=300.0, only_author=False, single_use=False
):
    """Handler for reaction buttons
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
            and (payload.member == ctx.author or not only_author)
        )

    while True:
        try:
            payload = await ctx.bot.wait_for(
                "raw_reaction_add", timeout=timeout, check=check
            )

        except asyncio.TimeoutError:
            break
        else:
            exits = await functions[str(payload.emoji)]()
            try:
                await message.remove_reaction(payload.emoji, payload.member)
            except discord.errors.NotFound:
                pass
            except discord.errors.Forbidden:
                await ctx.send(
                    "`error: I'm missing required discord permission [ manage messages ]`"
                )
            if single_use or exits is True:
                break

    for emojiname in functions:
        try:
            await message.clear_reaction(emojiname)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            pass


def message_embed(message):
    """Creates a nice embed from message
    :param: message : discord.Message you want to embed
    :returns        : discord.Embed
    """
    content = discord.Embed()
    content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
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
    t = 0
    words = s.split(" ")
    prev = words[0]
    for word in words[1:]:
        try:
            if word in ["hours", "hour"]:
                t += int(prev) * 3600
            elif word in ["minutes", "minute", "min"]:
                t += int(prev) * 60
            elif word in ["seconds", "second", "sec"]:
                t += int(prev)
        except ValueError:
            pass
        prev = word

    return t


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
        components.append(f"{int(d)} day" + ("s" if d > 1 else ""))
    if h > 0:
        components.append(f"{int(h)} hour" + ("s" if h > 1 else ""))
    if m > 0:
        components.append(f"{int(m)} minute" + ("s" if m > 1 else ""))
    if s > 0:
        components.append(f"{int(s)} second" + ("s" if s > 1 else ""))

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
    eligible_words = 0
    for x in words:
        if len(x) > 1:
            eligible_words += 1
    xp = eligible_words + (10 * len(message.attachments))
    if xp == 0:
        xp = 1
    return xp


async def get_user(ctx, argument, fallback=None):
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


async def get_member(ctx, argument, fallback=None, try_user=False):
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
        if try_user:
            return await get_user(ctx, argument, fallback)
        else:
            return fallback


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


async def get_color(ctx, argument, fallback=None):
    """
    :param argument : hex or discord color name
    :param fallback : return this if not found
    :returns        : discord.Color
    """
    if argument is None:
        return fallback
    try:
        return await commands.ColourConverter().convert(ctx, argument)
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
        await send_command_help(ctx)


async def send_command_help(ctx):
    """Sends default command help"""
    await ctx.send_help(ctx.invoked_subcommand or ctx.command)


def escape_md(s):
    """
    :param s : String to espace markdown from
    :return  : The escaped string
    """
    transformations = {
        regex.escape(c): "\\" + c for c in ("*", "`", "_", "~", "\\", "||")
    }

    def replace(obj):
        return transformations.get(regex.escape(obj.group(0)), "")

    pattern = regex.compile("|".join(transformations.keys()))
    return pattern.sub(replace, s)


def rgb_to_hex(rgb):
    """
    :param rgb : RBG color in tuple of 3
    :return    : Hex color string
    """
    r, g, b = rgb

    def clamp(x):
        return max(0, min(x, 255))

    return "{0:02x}{1:02x}{2:02x}".format(clamp(r), clamp(g), clamp(b))


async def color_from_image_url(url, fallback="E74C3C"):
    """
    :param url      : image url
    :param fallback : the color to return in case the operation fails
    :return         : hex color code of the most dominant color in the image
    """
    if url.strip() == "":
        return fallback
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                image = Image.open(io.BytesIO(await response.read()))
                colors = colorgram.extract(image, 1)
                dominant_color = colors[0].rgb

        return rgb_to_hex(dominant_color)
    except Exception as e:
        print(e)
        return fallback


def useragent():
    """Returns random user agent to use in web scraping."""
    agents = db.get_from_data_json(["useragents"])
    return random.choice(agents)


def bool_to_int(value: bool):
    """Turn boolean into 1 or 0."""
    if value is True:
        return 1
    else:
        return 0


def int_to_bool(value):
    """Turn integer into boolean."""
    if value is None or value == 0:
        return False
    else:
        return True


def find_unicode_emojis(text):
    """Finds and returns all unicode emojis from a string"""
    emoji_list = []
    data = regex.findall(r"\X", text)
    flags = regex.findall("[\U0001F1E6-\U0001F1FF]", text)
    for word in data:
        if any(char in emoji.UNICODE_EMOJI for char in word):
            if word in flags:
                continue
            emoji_list.append(emoji.demojize(word))

    for i in range(math.floor(len(flags) / 2)):
        emoji_list.append("".join(emoji.demojize(x) for x in flags[i : i + 2]))

    return emoji_list


def find_custom_emojis(text):
    """Finds and returns all custom discord emojis from a string"""
    emoji_list = []
    data = regex.findall(r"<(a?):([a-zA-Z0-9\_]+):([0-9]+)>", text)
    for a, emoji_name, emoji_id in data:
        emoji_list.append(f"<{a}:{emoji_name}:{emoji_id}>")

    return emoji_list


async def image_info_from_url(url):
    """Return dictionary containing filesize, filetype and dimensions of an image."""
    async with aiohttp.ClientSession() as session:
        async with session.get(str(url)) as response:
            filesize = int(response.headers.get("Content-Length")) / 1024
            filetype = response.headers.get("Content-Type")
            image = Image.open(io.BytesIO(await response.read()))
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


def create_welcome_embed(user, guild, messageformat):
    """Creates and returns embed for welcome message."""
    content = discord.Embed(title="New member! :wave:", color=discord.Color.green())
    content.set_thumbnail(url=user.avatar_url)
    content.timestamp = datetime.datetime.utcnow()
    content.set_footer(text=f"👤#{len(guild.members)}")
    content.description = messageformat.format(
        mention=user.mention,
        user=user,
        id=user.id,
        server=guild.name,
        username=user.name,
    )
    return content


def create_goodbye_message(user, guild, messageformat):
    """Formats a goodbye message."""
    return messageformat.format(
        mention=user.mention,
        user=user,
        id=user.id,
        server=guild.name,
        username=user.name,
    )


def get_full_class_name(obj, limit=2):
    """Gets full class name of any python object. Used for error names"""
    module = obj.__class__.__module__
    if module is None or module == str.__class__.__module__:
        name = obj.__class__.__name__
    else:
        name = module + "." + obj.__class__.__name__
    return ".".join(name.split(".")[-limit:])


def activities_string(activities, markdown=True, show_emoji=True):
    """Print user activity as it shows up on the sidebar."""
    if not activities:
        return None

    custom_activity = None
    base_activity = None
    spotify_activity = None
    for act in activities:
        if isinstance(act, discord.CustomActivity):
            custom_activity = act
        elif isinstance(act, discord.BaseActivity):
            base_activity = act
        elif isinstance(act, discord.Spotify):
            spotify_activity = act
        else:
            print(act)
            return "Unknown activity"

    emoji = None
    message = None
    if custom_activity:
        emoji = custom_activity.emoji
        message = custom_activity.name

    if message is None and spotify_activity is not None:
        message = "Listening to " + ("**Spotify**" if markdown else "Spotify")

    if message is None and base_activity is not None:
        if base_activity.type == discord.ActivityType.playing:
            prefix = "Playing"
        elif base_activity.type == discord.ActivityType.streaming:
            prefix = "Streaming"
        elif base_activity.type == discord.ActivityType.listening:
            prefix = "Listening"
        elif base_activity.type == discord.ActivityType.watching:
            prefix = "Watching"

        message = (
            prefix
            + " "
            + (f"**{base_activity.name}**" if markdown else base_activity.name)
        )

    text = ""
    if emoji is not None and show_emoji:
        text += f"{emoji} "

    if message is not None:
        text += message

    return text if text != "" else None


class TwoWayIterator:
    """Two way iterator class that is used as the backend for paging."""

    def __init__(self, list_of_stuff):
        self.items = list_of_stuff
        self.index = 0

    def next(self):
        if self.index == len(self.items) - 1:
            return None
        else:
            self.index += 1
            return self.items[self.index]

    def previous(self):
        if self.index == 0:
            return None
        else:
            self.index -= 1
            return self.items[self.index]

    def current(self):
        return self.items[self.index]
