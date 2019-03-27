import math
import asyncio
from discord.ext import commands
import discord
import copy


async def send_as_pages(ctx, client, content, rows, maxrows=15):
    pages = create_pages(content, rows, maxrows)
    if len(pages) > 1:
        await page_switcher(ctx, client, pages)
    else:
        await ctx.send(embed=pages[0])


async def page_switcher(ctx, client, pages):
    current_page = 0
    pages[0].set_footer(text=f"page {current_page + 1} of {len(pages)}")
    my_msg = await ctx.send(embed=pages[0])

    def check(_reaction, _user):
        return _reaction.message.id == my_msg.id and _reaction.emoji in ["⬅", "➡"] \
               and not _user == client.user

    await my_msg.add_reaction("⬅")
    await my_msg.add_reaction("➡")

    while True:
        try:
            reaction, user = await client.wait_for('reaction_add', timeout=3600.0, check=check)
        except asyncio.TimeoutError:
            await my_msg.remove_reaction("⬅", client.user)
            await my_msg.remove_reaction("➡", client.user)
            return
        else:
            await my_msg.remove_reaction("⬅", user)
            await my_msg.remove_reaction("➡", user)
            try:
                if reaction.emoji == "⬅" and current_page > 0:
                    content = pages[current_page - 1]
                    current_page -= 1
                elif reaction.emoji == "➡":
                    content = pages[current_page + 1]
                    current_page += 1
                else:
                    continue
                content.set_footer(text=f"page {current_page + 1} of {len(pages)}")
                await my_msg.edit(embed=content)
            except IndexError:
                continue


def create_pages(content, rows, maxrows=15):
    pages = []
    content.description = ""
    thisrow = 0
    for row in rows:
        thisrow += 1
        if len(content.description) + len(row) < 2000 and thisrow < maxrows+1:
            content.description += f"\n{row}"
        else:
            thisrow = 0
            pages.append(content)
            content = copy.deepcopy(content)
            content.description = f"{row}"
    if not content.description == "":
        pages.append(content)
    return pages


def timefromstring(s):
    """parse string for a timeframe
    :returns time in seconds"""
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
    m, s = divmod(t, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)

    components = []
    if d > 0:
        components.append(f"{d} day" + ("s" if d > 1 else ""))
    if h > 0:
        components.append(f"{h} hour" + ("s" if h > 1 else ""))
    if m > 0:
        components.append(f"{m} minute" + ("s" if m > 1 else ""))
    if s > 0:
        components.append(f"{s} second" + ("s" if s > 1 else ""))

    return " ".join(components)


def get_xp(level):
    a = 0
    for x in range(1, level):
        a += math.floor(x + 300 * math.pow(2, (x / 7)))
    return math.floor(a / 4)


def get_level(xp):
    i = 1
    while get_xp(i + 1) < xp:
        i += 1
    return i


def xp_to_next_level(level):
    return get_xp(level + 1) - get_xp(level)


def xp_from_message(message):
    words = message.content.split(" ")
    eligible_words = 0
    for x in words:
        if len(x) > 1:
            eligible_words += 1
    xp = eligible_words + 10 * len(message.attachments)
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


async def command_group_help(ctx):
    if ctx.invoked_subcommand is None or isinstance(ctx.invoked_subcommand, commands.Group):
        await send_command_help(ctx)


async def send_command_help(ctx):
    await ctx.bot.get_command('help').callback(ctx, ctx.command.name)
