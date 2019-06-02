import discord
from discord.ext import commands
import random
import data.database as db
import helpers.utilityfunctions as util
import helpers.errormessages as errormsg


COOLDOWN = 21600
TRASH_ICONS = (':moyai:', ':stopwatch:', ':wrench:', ':hammer:', ':pick:', ':nut_and_bolt:', ':gear:', ':toilet:',
               ':alembic:', ':bathtub:', ':paperclip:', ':scissors:', ':boot:', ':high_heel:', ':spoon:',
               ':saxophone:', ':trumpet:', ':scooter:', ':anchor:')


class Fishy(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.__FISHTYPES = {"trash": trash, "common": fish_common, "uncommon": fish_uncommon,
                            "rare": fish_rare, "legendary": fish_legendary}
        self.__WEIGHTS = [0.09, 0.6, 0.2, 0.1, 0.01]

    @commands.command(aliases=["fish", "fihy", "fisy", "foshy", "fisyh", "fsihy", "fin"])
    async def fishy(self, ctx, user=None):
        """Go fishing and receive random fish. You can also gift fish to others.

        Usage:
            fishy
            fishy <user>
        """
        gift = False
        receiver = ctx.author
        if user is not None:
            receiver = await util.get_member(ctx, user)
            if receiver is not None and receiver is not ctx.author:
                gift = True

        fishdata = db.fishdata(ctx.author.id)

        if fishdata.timestamp is not None:
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
        if amount:
            db.add_fishy(receiver.id, catch, amount, ctx.message.created_at.timestamp(),
                         fisher_id=(ctx.author.id if gift else None))

    @commands.command()
    async def leaderboard(self, ctx, scope=None):
        """Shows the fishy leaderboard

        Usage:
            leaderboard
            leaderboard global
        """
        users = db.query("select user_id from fishy order by fishy desc")
        rows = []
        rank_icon = [':first_place:', ':second_place:', ':third_place:']
        rank = 1
        for userdata in users:
            user_id = userdata[0]
            if scope == 'global':
                user = self.client.get_user(user_id)
            else:
                user = ctx.guild.get_member(user_id)
            if user is None:
                continue

            fishdata = db.fishdata(user_id)
            if fishdata is None:
                continue

            if rank < len(rank_icon) + 1:
                ranking = rank_icon[rank-1]
            else:
                ranking = f"`{rank}.`"
            rows.append(f"{ranking} {user.name} - **{fishdata.fishy}** fishy")
            rank += 1
        content = discord.Embed(title=f"{'global' if scope == 'global' else ctx.guild.name} fishy leaderboard",
                                color=discord.Color.blue())
        if rows:
            await util.send_as_pages(ctx, content, rows, 2)
        else:
            await ctx.send(embed=content)

    @commands.command()
    async def fishystats(self, ctx, mention=None):
        """Shows fishing statistics

        Usage:
            fishystats
            fishystats <user>
            fishystats global
        """
        user = ctx.author
        globaldata = False
        if mention is not None:
            if mention == 'global':
                globaldata = True
            else:
                user = await util.get_user(ctx, mention)
                if user is None:
                    return await ctx.send(errormsg.user_not_found(mention))

        if globaldata:
            fishdata = None
            users = db.query("select user_id from fishy")
            for user_id in users:
                u = self.client.get_user(user_id[0])
                if u is None:
                    ufdata = db.fishdata(user_id[0])
                else:
                    ufdata = db.fishdata(u.id)
                if fishdata is None:
                    fishdata = ufdata
                else:
                    fishdata = fishdata._replace(fishy=fishdata.fishy + ufdata.fishy,
                                                 fishy_gifted=fishdata.fishy_gifted + ufdata.fishy_gifted,
                                                 trash=fishdata.trash + ufdata.trash,
                                                 common=fishdata.common + ufdata.common,
                                                 uncommon=fishdata.uncommon + ufdata.uncommon,
                                                 rare=fishdata.rare + ufdata.rare,
                                                 legendary=fishdata.legendary + ufdata.legendary)

        else:
            fishdata = db.fishdata(user.id)
        content = discord.Embed(title=f"{'global' if globaldata else user.name} fishy stats")
        if fishdata is not None:
            total = fishdata.trash + fishdata.common + fishdata.uncommon + fishdata.rare + fishdata.legendary
            content.description = f"Total fishies fished: **{fishdata.fishy}**\n" \
                                  f"Total fishies gifted: **{fishdata.fishy_gifted}**\n\n" \
                                  f"Trash: **{fishdata.trash}** - {(fishdata.trash/total)*100:.1f}%\n" \
                                  f"Common: **{fishdata.common}** - {(fishdata.common/total)*100:.1f}%\n" \
                                  f"Uncommon: **{fishdata.uncommon}** - {(fishdata.uncommon/total)*100:.1f}%\n" \
                                  f"Rare: **{fishdata.rare}** - {(fishdata.rare/total)*100:.1f}%\n" \
                                  f"Legendary: **{fishdata.legendary}** - {(fishdata.legendary/total)*100:.1f}%\n\n" \
                                  f"Total fish count: **{total}**\n" \
                                  f"Average fishy: **{fishdata.fishy / total:.2f}**"
        await ctx.send(embed=content)

    @commands.command(hidden=True)
    async def fishdistributiontest(self, ctx, amount=100):
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
    await ctx.send(f"**Caught an uncommon fish " + (f"for {user.name}" if gift else "") +
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
    await ctx.send(f"Caught **trash!**  {icon}" + (f" for {user.name}" if gift else "")
                   + " Better luck next time.")
    return None


def setup(client):
    client.add_cog(Fishy(client))
