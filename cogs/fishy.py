from discord.ext import commands
import random
from datetime import datetime

import helpers.log
import data.database as db

COOLDOWN = 3600
TRASH_ICONS = (':moyai:', ':stopwatch:', ':wrench:', ':hammer:', ':pick:', ':nut_and_bolt:', ':gear:', ':toilet:',
               ':alembic:', ':bathtub:', ':paperclip:', ':scissors:', ':boot:', ':high_heel:', ':spoon:',
               ':saxophone:', ':trumpet:', ':scooter:', ':anchor:')


class Fishy(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.__FISHTYPES = []
        self.__WEIGHTS = []

    @commands.command()
    async def fishy(self, ctx, mention=None):
        gift = False
        if mention is not None:
            receiver = commands.MemberConverter().convert(ctx, mention)
            if receiver is not None and receiver is not ctx.author:
                gift = True
        else:
            receiver = ctx.author

        fishdata = db.fishdata(ctx.author.id)

        if fishdata.timestamp is not None:
            time_since_fishy = ctx.created_at.timestamp() - fishdata.timestamp
        else:
            time_since_fishy = COOLDOWN

        if time_since_fishy < COOLDOWN:
            return await ctx.send(f"Not yet, wait like {(COOLDOWN - time_since_fishy) // 60} minutes ok")

        catch = random.choices(self.__FISHTYPES, self.__WEIGHTS)
        catch(ctx, receiver, gift)

async def fish_common(ctx, user, gift):
    amount = random.randint(1, 29)
    if amount == 1:
        await ctx.send(f"Caught only **{amount}** fishy " + (f"for **{user.name}**" if gift else "") +
                       "! :fishing_pole_and_fish:")
    else:
        await ctx.send(f"Caught **{amount}** fishies " + (f"for **{user.name}**" if gift else "") +
                       "! :fishing_pole_and_fish:")
    db.add_fishy(user.id, "common", amount, ctx.message.created_at)

async def fish_uncommon(ctx, user, gift):
    amount = random.randint(30, 99)

async def fish_rare(ctx, user, gift):
    amount = random.randint(100, 399)

async def fish_legendary(ctx, user, gift):
    pass
        

# TODO: fish functions


def setup(client):
    client.add_cog(Fishy(client))
