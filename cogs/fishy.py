import discord
from discord.ext import commands
import random
import data.database as db
import helpers.utilityfunctions as util

COOLDOWN = 7200
TRASH_ICONS = (':moyai:', ':stopwatch:', ':wrench:', ':hammer:', ':pick:', ':nut_and_bolt:', ':gear:', ':toilet:',
               ':alembic:', ':bathtub:', ':paperclip:', ':scissors:', ':boot:', ':high_heel:',
               ':saxophone:', ':trumpet:', ':scooter:', ':anchor:')


class Fishy(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.__FISHTYPES = {"trash": trash, "common": fish_common, "uncommon": fish_uncommon,
                            "rare": fish_rare, "legendary": fish_legendary}
        self.__WEIGHTS = [0.09, 0.6, 0.2, 0.1, 0.01]

    @commands.command(aliases=["fish", "fihy", "fisy", "foshy", "fisyh", "fsihy", "fin"])
    async def fishy(self, ctx, user=''):
        """Go fishing and receive / give random fish"""
        receiver = await util.get_member(ctx, user, fallback=ctx.author)
        if receiver is not None and receiver is not ctx.author:
            gift = True
        else:
            gift = False

        fishdata = db.fishdata(ctx.author.id)

        if fishdata is not None and fishdata.timestamp is not None:
            time_since_fishy = ctx.message.created_at.timestamp() - fishdata.timestamp
        else:
            time_since_fishy = COOLDOWN

        if time_since_fishy < COOLDOWN:
            not_yet_quotes = [
                "Bro chill, you can't fish yet! You gotta wait like",
                "You can't fish yet, fool! Please wait",
                "You're fishing too fast! Please wait",
                "You're still on cooldown buddy. You need to wait"
            ]
            return await ctx.send(f"{random.choice(not_yet_quotes)} "
                                  f"**{util.stringfromtime(COOLDOWN - time_since_fishy, 2)}**")

        catch = random.choices(list(self.__FISHTYPES.keys()), self.__WEIGHTS)[0]
        amount = await self.__FISHTYPES[catch](ctx, receiver, gift)
        db.add_fishy(receiver.id, catch, amount, ctx.message.created_at.timestamp(),
                     fisher_id=(ctx.author.id if gift else None))

    @commands.command()
    async def fishystats(self, ctx, mention=''):
        """Shows fishing statistics"""
        globaldata = mention == 'global'
        if not globaldata:
            user = await util.get_user(ctx, mention, fallback=ctx.author)
        else:
            user = ctx.author

        if globaldata:
            fishdata = None
            users = db.query("select user_id from fishy")
            for user_id in users:
                user_fishdata = db.fishdata(user_id[0])
                if fishdata is None:
                    fishdata = user_fishdata
                else:
                    fishdata = fishdata._replace(
                        fishy=fishdata.fishy + user_fishdata.fishy,
                        fishy_gifted=fishdata.fishy_gifted + user_fishdata.fishy_gifted,
                        trash=fishdata.trash + user_fishdata.trash,
                        common=fishdata.common + user_fishdata.common,
                        uncommon=fishdata.uncommon + user_fishdata.uncommon,
                        rare=fishdata.rare + user_fishdata.rare,
                        legendary=fishdata.legendary + user_fishdata.legendary)

        else:
            fishdata = db.fishdata(user.id)
        content = discord.Embed(title=f"{'global' if globaldata else user.name} fishy stats")
        if fishdata is not None:
            total = fishdata.trash + fishdata.common + fishdata.uncommon + fishdata.rare + fishdata.legendary
            content.description = f"""
                Total fishy: **{fishdata.fishy}**
                Fishy gifted: **{fishdata.fishy_gifted}**
                
                Trash: **{fishdata.trash}** - {(fishdata.trash / total) * 100:.1f}%
                Common: **{fishdata.common}** - {(fishdata.common / total) * 100:.1f}%
                Uncommon: **{fishdata.uncommon}** - {(fishdata.uncommon / total) * 100:.1f}%
                Rare: **{fishdata.rare}** - {(fishdata.rare / total) * 100:.1f}%
                Legendary: **{fishdata.legendary}** - {(fishdata.legendary / total) * 100:.1f}%
                
                Total fish count: **{total}**
                Average fishy: **{fishdata.fishy / total:.2f}**
                """
        await ctx.send(embed=content)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def fishdistributiontest(self, ctx, amount=100):
        """Test the distribution of fish"""
        fishes = {"trash": 0, "fish_common": 0, "fish_uncommon": 0, "fish_rare": 0, "fish_legendary": 0}
        for i in range(amount):
            f = self.__FISHTYPES[random.choices(list(self.__FISHTYPES.keys()), self.__WEIGHTS)[0]].__name__
            fishes[f] += 1

        await ctx.send(f"**Fishing {amount} times...**\n" + "\n".join(f"{k} : {v}" for k, v in fishes.items()))


async def fish_common(ctx, user, gift):
    amount = random.randint(1, 29)
    if amount == 1:
        await ctx.send(f"Caught only **{amount}** fishy " + (f"for **{user.name}**" if gift else "") +
                       "! :fishing_pole_and_fish:")
    else:
        await ctx.send(f"Caught **{amount}** fishies " + (f"for **{user.name}**" if gift else "") +
                       "! :fishing_pole_and_fish:")
    return amount


async def fish_uncommon(ctx, user, gift):
    amount = random.randint(30, 99)
    await ctx.send(f"**Caught an uncommon fish" + (f" for {user.name}" if gift else "") +
                   f"!** (**{amount}** fishies) :blowfish:")
    return amount


async def fish_rare(ctx, user, gift):
    amount = random.randint(100, 399)
    await ctx.send(f":star: **Caught a super rare fish" + (f" for {user.name}" if gift else "") + f"! :star: ({amount} "
                   "fishies)** :tropical_fish:")
    return amount


async def fish_legendary(ctx, user, gift):
    amount = random.randint(400, 750)
    await ctx.send(f":star2: **Caught a *legendary* fish" +
                   (f" for {user.name}" if gift else "") + f"!! :star2: ({amount} "
                   "fishies)** :dolphin:")
    return amount


async def trash(ctx, user, gift):
    icon = random.choice(TRASH_ICONS)
    await ctx.send(f"Caught **trash{'!' if not gift else ''}**  {icon}" + (f" for {user.name}!" if gift else "")
                   + " Better luck next time.")
    return 0


def setup(client):
    client.add_cog(Fishy(client))
