import math
import asyncio
from discord.ext import commands
import discord
import copy
import re
import regex
import colorgram
from PIL import Image
import data.database as db
import random
import datetime
import io
import emoji
import aiohttp

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
    :param ctx   : Context
    :param pages : List of embeds to use as pages
    """
    pages = TwoWayIterator(pages)

    # add all page numbers
    for i, page in enumerate(pages.items, start=1):
        old_footer = page.footer.text
        if old_footer == discord.Embed.Empty:
            old_footer = None
        page.set_footer(text=f"{i}/{len(pages.items)}" + (f' | {old_footer}' if old_footer is not None else ''))

    msg = await ctx.send(embed=pages.current())

    async def switch_page(content):
        await msg.edit(embed=content)

    async def previous_page():
        content = pages.previous()
        if content is None:
            return
        await switch_page(content)

    async def next_page():
        content = pages.next()
        if content is None:
            return
        await switch_page(content)

    functions = {"⬅": previous_page,
                 "➡": next_page}

    asyncio.ensure_future(reaction_buttons(ctx, msg, functions))


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
    :param timeout     : time in seconds for how long the buttons work for. default 10 minutes (600.0)
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
            try:
                await message.remove_reaction(reaction.emoji, user)
            except discord.errors.NotFound:
                pass
            except discord.errors.Forbidden:
                await ctx.send("`error: i'm missing required discord permission [ manage messages ]`")
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

    return math.ceil(math.pow((level-1)/(0.05*(1 + math.sqrt(5))), 2))


def get_level(xp):
    """
    :param xp : Amount of xp
    :returns  : Current level based on the amount of xp
    """

    return math.floor(0.05*(1 + math.sqrt(5))*math.sqrt(xp)) + 1


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
    """Get a discord user from mention, name, or id"""
    if argument is None:
        return fallback
    try:
        return await commands.UserConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        return fallback


async def get_member(ctx, argument, fallback=None, try_user=False):
    """Get a discord guild member from mention, name, or id"""
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
    """Get a discord text channel from mention, name, or id"""
    if argument is None:
        return fallback
    if guildfilter is None:
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.errors.BadArgument:
            return fallback
    else:
        result = discord.utils.find(lambda m: m.name == argument or m.id == argument, guildfilter.text_channels)
        return result or fallback


async def get_role(ctx, argument, fallback=None):
    """Get a discord role from mention, name, or id"""
    if argument is None:
        return fallback
    try:
        return await commands.RoleConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        return fallback


async def get_color(ctx, argument, fallback=None):
    """Get a discord color from hex value"""
    if argument is None:
        return fallback
    try:
        return await commands.ColourConverter().convert(ctx, argument)
    except commands.errors.BadArgument:
        return fallback


async def get_emoji(ctx, argument, fallback=None):
    """Try to get full emoji, fallback to partial emoji if not successfull"""
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
    """Get a guild that bot can see"""
    result = discord.utils.find(lambda m: m.name == argument or m.id == argument, ctx.bot.guilds)
    return result or fallback


async def command_group_help(ctx):
    """Sends default command help if group command is invoked on it's own"""
    if ctx.invoked_subcommand is None or isinstance(ctx.invoked_subcommand, commands.Group):
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
        re.escape(c): '\\' + c
        for c in ('*', '`', '_', '~', '\\', '||')
    }

    def replace(obj):
        return transformations.get(re.escape(obj.group(0)), '')

    pattern = re.compile('|'.join(transformations.keys()))
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


async def color_from_image_url(url, fallback='E74C3C'):
    """
    :param url      : Url to an image to capture colors from
    :param fallback : The color to fallback to incase the operation fails
    :return         : Hex color code of the most dominant color in the image
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
    """Returns random user agent to use in web scraping"""
    agents = db.get_from_data_json(['useragents'])
    return random.choice(agents)


def bool_to_int(value: bool):
    """Turn boolean into 1 or 0"""
    if value is True:
        return 1
    else:
        return 0


def int_to_bool(value):
    """Turn integer into boolean"""
    if value is None or value == 0:
        return False
    else:
        return True


def find_unicode_emojis(text):
    emoji_list = []
    data = regex.findall(r'\X', text)
    flags = regex.findall(u'[\U0001F1E6-\U0001F1FF]', text)
    for word in data:
        if any(char in emoji.UNICODE_EMOJI for char in word):
            if word in flags:
                continue
            emoji_list.append(emoji.demojize(word))
    
    for i in range(math.floor(len(flags)/2)):
        emoji_list.append(''.join([emoji.demojize(x) for x in flags[i:i+2]]))

    return emoji_list


def find_custom_emojis(text):
    emoji_list = []
    data = regex.findall(r'<(a?):([a-zA-Z0-9\_]+):([0-9]+)>', text)
    for a, emoji_name, emoji_id in data:
        emoji_list.append(f"<{a}:{emoji_name}:{emoji_id}>")

    return emoji_list


async def image_info_from_url(url):
    """Return dictionary containing information about image"""
    async with aiohttp.ClientSession() as session:
        async with session.get(str(url)) as response:
            filesize = int(response.headers.get('Content-Length'))/1024
            filetype = response.headers.get('Content-Type')
            image = Image.open(io.BytesIO(await response.read()))
            dimensions = image.size
            if filesize > 1024:
                filesize = f"{filesize/1024:.2f}MB"
            else:
                filesize = f"{filesize:.2f}KB"

            return {
                'filesize': filesize,
                'filetype': filetype,
                'dimensions': f"{dimensions[0]}x{dimensions[1]}"
            }

def create_welcome_embed(user, guild, messageformat):
    """Creates and returns embed for welcome message"""
    content = discord.Embed(title="New member! :wave:", color=discord.Color.green())
    content.set_thumbnail(url=user.avatar_url)
    content.timestamp = datetime.datetime.utcnow()
    content.set_footer(text=f"👤#{len(guild.members)}")
    content.description = messageformat.format(mention=user.mention, user=user, id=user.id,
                                               server=guild.name, username=user.name)
    return content


def activityhandler(activity_tuple):
    """
    :param activity_tuple : Discord activity tuple (None, Spotify, Streaming, Playing)
    :return               : Activity dictionary
    """
    if not activity_tuple:
        return {'text': '', 'icon': ''}

    activity = activity_tuple[0]
    
    activity_dict = {}
    if isinstance(activity, discord.Spotify):
        activity_dict['text'] = f"Listening to <strong>{activity.title}</strong><br>by <strong>{activity.artist}</strong>"
        activity_dict['icon'] = 'fab fa-spotify'
    elif isinstance(activity, discord.Game):
        activity_dict['text'] = f"Playing {activity.name}<br>for{stringfromtime((datetime.datetime.utcnow() - activity.start).totalseconds(), accuracy=1)}"
        activity_dict['icon'] = 'fas fa-gamepad'
    elif isinstance(activity, discord.Streaming):
        activity_dict['text'] = f"Streaming {activity.details} as {activity.twitch_name}<br>{activity.name}"
        activity_dict['icon'] = 'fab fa-twitch'
    else:
        activity_dict['text'] = "{activity}"
        activity_dict['icon'] = ''
    return activity_dict


class TwoWayIterator:
    """Two way iterator class that is used as the backend for paging"""

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
