import math
import asyncio
from discord.ext import commands


async def send_as_pages(ctx, client, content, rows, maxrows=15):

    pages = create_pages(rows, maxrows)
    content.description = pages[0]
    if len(pages) > 1:
        content.set_footer(text=f"page 1 of {len(pages)}")
    my_msg = await ctx.send(embed=content)

    current_page = 0

    if len(pages) > 1:

        def check(_reaction, _user):
            return _reaction.message.id == my_msg.id and _reaction.emoji in ["⬅", "➡"] \
                   and not _user == client.user

        await my_msg.add_reaction("⬅")
        await my_msg.add_reaction("➡")

        while True:
            try:
                reaction, user = await client.wait_for('reaction_add', timeout=3600.0, check=check)
            except asyncio.TimeoutError:
                await my_msg.clear_reactions()
                return
            else:
                try:
                    if reaction.emoji == "⬅" and current_page > 0:
                        content.description = pages[current_page - 1]
                        current_page -= 1
                        await my_msg.remove_reaction("⬅", user)
                    elif reaction.emoji == "➡":
                        content.description = pages[current_page + 1]
                        current_page += 1
                        await my_msg.remove_reaction("➡", user)
                    else:
                        continue
                    content.set_footer(text=f"page {current_page + 1} of {len(pages)}")
                    await my_msg.edit(embed=content)
                except IndexError:
                    continue


def create_pages(rows, maxrows=15):
    pages = []
    description = ""
    thisrow = 0
    for row in rows:
        thisrow += 1
        if len(description) + len(row) < 2000 and thisrow < maxrows+1:
            description += f"\n{row}"
        else:
            thisrow = 0
            pages.append(f"{description}")
            description = f"\n{row}"
    if not description == "":
        pages.append(f"{description}")
    return pages


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
