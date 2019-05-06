import math
import asyncio
from discord.ext import commands
import discord
import copy
import re
import requests
import colorgram
from PIL import Image


async def send_as_pages(ctx, content, rows, maxrows=15):
    """
    :param ctx     : Context
    :param content : Base embed
    :param rows    : Embed description rows
    :param maxrows : Max amount of rows per page
    """
    pages = create_pages(content, rows, maxrows)
    if len(pages) > 1:
        await page_switcher(ctx, pages)
    else:
        await ctx.send(embed=pages[0])


async def page_switcher(ctx, pages):
    """
    :param ctx    : Context
    :param pages  : List of embeds to use as pages
    """
    pages = TwoWayIterator(pages)
    old_footer = pages.current().footer.text
    if old_footer == discord.Embed.Empty:
        old_footer = None
    pages.current().set_footer(text=f"1/{len(pages.items)}" + (f' | {old_footer}' if old_footer is not None else ''))
    msg = await ctx.send(embed=pages.current())

    async def switch_page(content):
        content.set_footer(text=f"{pages.index + 1}/{len(pages.items)}" + (f' | {old_footer}' if old_footer is not None
                                                                           else ''))
        await msg.edit(embed=content)

    async def previous_page():
        content = pages.previous()
        await switch_page(content)

    async def next_page():
        content = pages.next()
        await switch_page(content)

    functions = {"⬅": previous_page,
                 "➡": next_page}

    await reaction_buttons(ctx, msg, functions)


def create_pages(content, rows, maxrows=15):
    """
    :param content : Embed object to use as the base
    :param rows    : List of rows to use for the embed description
    :param maxrows : Maximum amount of rows per page
    :returns       : List of Embed objects
    """
    pages = []
    content.description = ""
    thisrow = 0
    for row in rows:
        thisrow += 1
        if len(content.description) + len(row) < 2000 and thisrow < maxrows+1:
            content.description += f"\n{row}"
        else:
            thisrow = 1
            pages.append(content)
            content = copy.deepcopy(content)
            content.description = f"{row}"
    if not content.description == "":
        pages.append(content)
    return pages


async def reaction_buttons(ctx, message, functions, timeout=600.0, only_author=False, single_use=False):
    """Handler for reaction buttons
    :param message     : message to add reactions to
    :param functions   : dictionary of {emoji : function} pairs. functions must be async. return True to exit
    :param timeout     : float, default 10 minutes (600.0)
    :param only_author : only allow the user who used the command use the buttons
    :param single_use  : delete buttons after one is used
    """

    for emoji in functions:
        await message.add_reaction(emoji)

    def check(_reaction, _user):
        return _reaction.message.id == message.id \
               and _reaction.emoji in functions \
               and not _user == ctx.bot.user \
               and (_user == ctx.author or not only_author)

    while True:
        try:
            reaction, user = await ctx.bot.wait_for('reaction_add', timeout=timeout, check=check)
        except asyncio.TimeoutError:
            break
        else:
            exits = await functions[str(reaction.emoji)]()
            await message.remove_reaction(reaction.emoji, user)
            if single_use or exits is True:
                break

    try:
        for emoji in functions:
            await message.remove_reaction(emoji, ctx.bot.user)
    except discord.errors.NotFound:
        pass


def message_embed(message):
    """
    :param: message : Discord message object
    :returns        : Discord embed object
    """
    content = discord.Embed()
    content.set_author(name=f"{message.author}", icon_url=message.author.avatar_url)
    content.description = message.content
    content.set_footer(text=f"{message.guild.name} | #{message.channel.name}")
    content.timestamp = message.created_at


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
            if word in ['hours', 'hour']:
                t += int(prev) * 3600
            elif word in ['minutes', 'minute', 'min']:
                t += int(prev) * 60
            elif word in ['seconds', 'second', 'sec']:
                t += int(prev)
        except ValueError:
            pass
        prev = word

    return t


def stringfromtime(t):
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

    return " ".join(components)


def get_xp(level):
    """
    :param level : Level
    :return      : Amount of xp needed to reach the level
    """
    a = 0
    for x in range(1, level):
        a += math.floor(x + 300 * math.pow(2, (x / 7)))
    return math.floor(a / 4)


def get_level(xp):
    """
    :param xp : Amount of xp
    :returns  : Current level based on the amount of xp
    """
    i = 1
    while get_xp(i + 1) < xp:
        i += 1
    return i


def xp_to_next_level(level):
    return get_xp(level + 1) - get_xp(level)


def xp_from_message(message):
    """
    :param message: Message to get the xp from
    :returns: Amount of xp rewarded from given message. Minimum 1
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


async def get_user(ctx, mention):
    try:
        return await commands.UserConverter().convert(ctx, mention)
    except commands.errors.BadArgument as e:
        return None


async def get_member(ctx, mention):
    try:
        return await commands.MemberConverter().convert(ctx, mention)
    except commands.errors.BadArgument as e:
        return None


async def get_textchannel(ctx, mention):
    try:
        return await commands.TextChannelConverter().convert(ctx, mention)
    except commands.errors.BadArgument as e:
        return None


async def get_role(ctx, mention):
    try:
        return await commands.RoleConverter().convert(ctx, mention)
    except commands.errors.BadArgument as e:
        return None


async def get_color(ctx, mention):
    try:
        return await commands.ColourConverter().convert(ctx, mention)
    except commands.errors.BadArgument as e:
        return None


async def command_group_help(ctx):
    """Sends default command help if group command is invoked on it's own"""
    if ctx.invoked_subcommand is None or isinstance(ctx.invoked_subcommand, commands.Group):
        await send_command_help(ctx)


async def send_command_help(ctx):
    """Sends default command help"""
    await ctx.send_help(ctx.invoked_subcommand or ctx.command)


def escape_md(s):
    transformations = {
        re.escape(c): '\\' + c
        for c in ('*', '`', '_', '~', '\\', '||')
    }

    def replace(obj):
        return transformations.get(re.escape(obj.group(0)), '')

    pattern = re.compile('|'.join(transformations.keys()))
    return pattern.sub(replace, s)


def rgb_to_hex(rgb):
    r, g, b = rgb

    def clamp(x):
        return max(0, min(x, 255))

    return "{0:02x}{1:02x}{2:02x}".format(clamp(r), clamp(g), clamp(b))


def color_from_image_url(url, fallback='f81894'):
    if url.strip() == "":
        return fallback
    try:
        response = requests.get(url, stream=True)
        response.raw.decode_content = True
        image = Image.open(response.raw)

        colors = colorgram.extract(image, 1)
        dominant_color = colors[0].rgb

        return rgb_to_hex(dominant_color)
    except Exception as e:
        print(e)
        return fallback


class TwoWayIterator:

    def __init__(self, list_of_stuff):
        self.items = list_of_stuff
        self.index = 0

    def next(self):
        if not self.index == len(self.items) - 1:
            self.index += 1
        return self.items[self.index]

    def previous(self):
        if not self.index == 0:
            self.index -= 1
        return self.items[self.index]

    def current(self):
        return self.items[self.index]
