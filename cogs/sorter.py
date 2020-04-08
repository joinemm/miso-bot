import math
import random
import discord
import asyncio
from discord.ext import commands
#from data import database as db


class Sorter(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sorter")
    async def sort(self, ctx, preset):

        if preset == "new":
            return await self.create_preset(ctx)

        # 1. get preset
        data = db.get_sorter_preset(preset)  # TODO
        if data is None:
            await ctx.send(f"No sorter preset called `{preset}` found on this server.\n"
                           f"Use `{self.bot.command_prefix}sorter new` to create a new preset")

        # 2. sorter with reaction buttons
        content = discord.Embed()

    async def create_preset(self, ctx):

        items = []

        await ctx.send("**Creating new sorter preset.**\n"
                       "Please give a name for the preset:")

        def check(_message):
            return _message.author == ctx.author

        try:
            message = await self.bot.wait_for('message', timeout=3600.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Creation timed out. Try again.")
        else:
            name = message.content
            await ctx.send(f"Preset name: `{name}`\nYou can now start listing items. "
                           f"Say `done` when you're done giving items.")

        while True:
            try:
                message = await self.bot.wait_for('message', timeout=3600.0, check=check)
            except asyncio.TimeoutError:
                return await ctx.send("Creation timed out. Try again.")
            else:
                if message.content == "done":
                    break
                else:
                    things_to_add = message.content.split("\n")
                    for x in things_to_add:
                        items.append(x)

        await ctx.send(f"Created a new sorter preset with name `{name}`, containing these items:\n"
                       + ', '.join([f"`{x}`" for x in items]))


def setup(bot):
    bot.add_cog(Sorter(bot))


def probability(rating1, rating2):
    return 1.0 * 1.0 / (1 + 1.0 * math.pow(10, 1.0 * (rating1 - rating2) / 400))


def elorating(rating_a, rating_b, k, d):
    """
    :param rating_a: elo of player 1
    :param rating_b: elo of player 2
    :param k: constant
    :param d: who wins
    """
    prob_b = probability(rating_a, rating_b)
    prob_a = probability(rating_b, rating_a)

    # Player A wins
    if d == 1:
        rating_a = rating_a + k * (1 - prob_a)
        rating_b = rating_b + k * (0 - prob_b)

    # Player B wins
    else:
        rating_a = rating_a + k * (0 - prob_a)
        rating_b = rating_b + k * (1 - prob_b)

    return rating_a, rating_b


def elo(players):
    ratings = {}

    for player in players:
        ratings[player] = {"score": 1000, "matched": [player]}

    k = 30
    while True:
        eligible = []
        for player in ratings:
            if len(ratings[player]['matched']) < len(players):
                eligible.append(player)

        if not eligible:
            break

        player_one = random.choice(eligible)
        player_two = random.choice([x for x in players if x not in ratings[player_one]['matched']])

        win = 0
        while win not in [1,2]:
            win = int(input(f"1: {player_one} vs 2: {player_two}"))

        ratings[player_one]['score'], ratings[player_two]['score'] \
            = elorating(ratings[player_one]['score'], ratings[player_two]['score'], k, win)
        ratings[player_one]['matched'].append(player_two)
        ratings[player_two]['matched'].append(player_one)

    for x in sorted(ratings, key=lambda x: ratings[x]['score']):
        print(f"{x} : {ratings[x]['score']}")


def ranking(items):
    random.shuffle(items)
    ranked_items = []

    w = int(input(f"1: {items[0]} :: 2: {items[1]} >>> "))
    if w == 1:
        ranked_items.append(items[0])
        ranked_items.append(items[1])
    else:
        ranked_items.append(items[1])
        ranked_items.append(items[0])

    del items[0]
    del items[0]

    while True:
        a = items[0]
        placement = 0
        while True:
            if placement > len(ranked_items)-1:
                ranked_items.append(a)
                break

            b = ranked_items[placement]
            win = int(input(f"1: {a} :: 2: {b} >>> "))
            if win == 1:
                ranked_items.insert(placement, a)
                break
            else:
                placement += 1
        del items[0]
        if len(items) == 0:
            break

    for x in ranked_items:
        print(x)


the_list = [
    "heejin",
    "hyunjin",
    "haseul",
    "vivi",
    "yeojin",
    "jinsoul",
    "kim lip",
    "choerry",
    "yves",
    "go won",
    "chuu",
    "olivia hye"
]

elo(the_list)
