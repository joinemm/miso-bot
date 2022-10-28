import random
from typing import Optional

import discord
import humanize
from discord.ext import commands

from modules import util


class Fishy(commands.Cog):
    """Fishing commands"""

    COOLDOWN = 7200
    WEIGHTS = [9, 60, 20, 10, 1]
    COOLDOWN_STRINGS = [
        "Bro chill, you can't fish yet! Please wait {time}",
        "You can't fish yet, fool! Please wait {time}",
        "You're fishing too fast! Please wait {time}",
        "You're still on cooldown buddy. Please wait {time}",
        "Please wait {time} to fish again!",
        "Sorry, but you have to wait {time} to fish again!",
        "Not so fast! Please wait {time}",
        "You must wait {time} to fish again!",
    ]
    TRASH_ICONS = [
        ":moyai:",
        ":stopwatch:",
        ":wrench:",
        ":pick:",
        ":nut_and_bolt:",
        ":gear:",
        ":toilet:",
        ":alembic:",
        ":bathtub:",
        ":scissors:",
        ":boot:",
        ":high_heel:",
        ":saxophone:",
        ":trumpet:",
        ":anchor:",
        ":shopping_cart:",
        ":paperclips:",
        ":paperclip:",
        ":prayer_beads:",
        ":oil:",
        ":compression:",
        ":radio:",
        ":fax:",
        ":movie_camera:",
        ":projector:",
        ":guitar:",
        ":violin:",
        ":telephone:",
        ":alarm_clock:",
        ":fire_extinguisher:",
        ":screwdriver:",
        ":wrench:",
        ":magnet:",
        ":coffin:",
        ":urn:",
        ":amphora:",
        ":crystal_ball:",
        ":telescope:",
        ":microscope:",
        ":microbe:",
        ":broom:",
        ":basket:",
        ":sewing_needle:",
        ":roll_of_paper:",
        ":plunger:",
        ":bucket:",
        ":toothbrush:",
        ":soap:",
        ":razor:",
        ":sponge:",
        ":squeeze_bottle:",
        ":key:",
        ":teddy_bear:",
        ":frame_photo:",
        ":nesting_dolls:",
        ":izakaya_lantern:",
        ":wind_chime:",
        ":safety_pin:",
        ":newspaper2:",
    ]

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🐟"
        self.ts_lock = {}
        self.fishtypes = {
            "trash": self.trash,
            "common": self.fish_common,
            "uncommon": self.fish_uncommon,
            "rare": self.fish_rare,
            "legendary": self.fish_legendary,
        }

    # idk why this doesnt work but it gets stuck all the time
    # @commands.max_concurrency(1, per=commands.BucketType.user)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    @commands.command(aliases=["fish", "fihy", "fisy", "foshy", "fisyh", "fsihy", "fin", "fush"])
    async def fishy(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Go fishing"""
        receiver = user or ctx.author
        gift = receiver is not ctx.author

        cached_last_fishy = self.ts_lock.get(str(ctx.author.id))
        if cached_last_fishy is None:
            last_fishy = await self.bot.db.execute(
                "SELECT last_fishy FROM fishy WHERE user_id = %s",
                ctx.author.id,
                one_value=True,
            )
            # try again to fix race condition maybe
            cached_last_fishy = self.ts_lock.get(str(ctx.author.id))
            if cached_last_fishy is not None:
                last_fishy = cached_last_fishy
            if last_fishy:
                self.ts_lock[str(ctx.author.id)] = last_fishy
        else:
            last_fishy = cached_last_fishy
        if last_fishy:
            time_since_fishy = ctx.message.created_at.timestamp() - last_fishy.timestamp()
        else:
            time_since_fishy = self.COOLDOWN

        if time_since_fishy < self.COOLDOWN:
            wait_time = f"**{humanize.precisedelta(self.COOLDOWN - time_since_fishy)}**"
            await ctx.send(random.choice(self.COOLDOWN_STRINGS).format(time=wait_time))
        else:
            catch = random.choices(list(self.fishtypes.keys()), self.WEIGHTS)[0]
            amount = await self.fishtypes[catch](ctx, receiver, gift)
            self.ts_lock[str(ctx.author.id)] = ctx.message.created_at
            await self.bot.db.execute(
                """
                INSERT INTO fishy (user_id, fishy_count, biggest_fish)
                    VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    fishy_count = fishy_count + VALUES(fishy_count),
                    biggest_fish = GREATEST(biggest_fish, VALUES(biggest_fish))
                """,
                receiver.id,
                amount,
                amount,
            )
            await self.bot.db.execute(
                f"""
                INSERT INTO fish_type (user_id, {catch})
                    VALUES (%s, 1)
                ON DUPLICATE KEY
                    UPDATE {catch} = {catch} + 1
                """,
                receiver.id,
            )

            await self.bot.db.execute(
                """
                INSERT INTO fishy (user_id, fishy_gifted_count, last_fishy)
                    VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    fishy_gifted_count = fishy_gifted_count + VALUES(fishy_gifted_count),
                    last_fishy = VALUES(last_fishy)
                """,
                ctx.author.id,
                amount if gift else 0,
                ctx.message.created_at,
            )

    @commands.command(aliases=["fintimer", "fisytimer", "foshytimer", "ft"])
    async def fishytimer(self, ctx: commands.Context):
        """Check your fishy timer"""
        last_fishy = await self.bot.db.execute(
            "SELECT last_fishy FROM fishy WHERE user_id = %s",
            ctx.author.id,
            one_value=True,
        )
        if last_fishy:
            time_since_fishy = ctx.message.created_at.timestamp() - last_fishy.timestamp()
            if time_since_fishy < self.COOLDOWN:
                remaining = self.COOLDOWN - time_since_fishy
                wait_time = humanize.precisedelta(remaining)
                clock_face = f":clock{int(util.map_to_range(remaining, 7200, 0, 1, 12))}:"
                await ctx.send(f"{clock_face} You need to wait **{wait_time}** to fish again.")
            else:
                await ctx.send(":sparkles: Good news! You can fish right now!")
        else:
            await ctx.send(":thinking: You have never fished...?")

    @commands.command(aliases=["finstats", "fisystats", "foshystats", "fs"])
    async def fishystats(self, ctx: commands.Context, user=None):
        """See fishing statistics"""
        globaldata = user == "global"
        if not globaldata:
            user = await util.get_user(ctx, user, fallback=ctx.author)
            owner = user
            data = await self.bot.db.execute(
                """
                SELECT fishy_count, fishy_gifted_count, biggest_fish,
                    trash, common, uncommon, rare, legendary
                    FROM fishy JOIN fish_type
                        ON fishy.user_id = fish_type.user_id
                    WHERE fishy.user_id = %s
                """,
                user.id,
                one_row=True,
            )

        else:
            owner = "Global"
            data = await self.bot.db.execute(
                """
                SELECT SUM(fishy_count), SUM(fishy_gifted_count), MAX(biggest_fish),
                    SUM(trash), SUM(common), SUM(uncommon), SUM(rare), SUM(legendary)
                    FROM fishy JOIN fish_type
                        ON fishy.user_id = fish_type.user_id
                """,
                one_row=True,
            )

        if not data:
            return await ctx.send("No data! Go fishing first.")

        total = sum(data[3:])
        content = discord.Embed(
            title=f":fishing_pole_and_fish: {owner} fishy stats",
            color=int("55acee", 16),
            description="\n".join(
                [
                    f"Fishy owned: **{data[0]}**",
                    f"Fishy gifted: **{data[1]}**",
                    f"Times fished: **{total}**",
                    f"Biggest fish: **{data[2]}**",
                    f"Average fish: **{data[0] / total:.2f}**",
                ]
            ),
        )
        content.add_field(
            name="Rarity breakdown",
            value="\n".join(
                [
                    f"Trash: **{data[3]}** ({(data[3] / total) * 100:.1f}%)",
                    f"Common: **{data[4]}** ({(data[4] / total) * 100:.1f}%)",
                    f"Uncommon: **{data[5]}** ({(data[5] / total) * 100:.1f}%)",
                    f"Rare: **{data[6]}** ({(data[6] / total) * 100:.1f}%)",
                    f"Legendary: **{data[7]}** ({(data[7] / total) * 100:.1f}%)",
                ]
            ),
        )
        await ctx.send(embed=content)

    @staticmethod
    async def fish_common(ctx: commands.Context, user, gift):
        amount = random.randint(1, 29)
        if amount == 1:
            await ctx.send(
                f"Caught only **{amount}** fishy"
                + (f" for **{user.name}**" if gift else "")
                + "! :fishing_pole_and_fish:"
            )
        else:
            await ctx.send(
                f"Caught **{amount}** fishies"
                + (f" for **{user.name}**" if gift else "")
                + "! :fishing_pole_and_fish:"
            )
        return amount

    @staticmethod
    async def fish_uncommon(ctx: commands.Context, user, gift):
        amount = random.randint(30, 99)
        await ctx.send(
            "**Caught an uncommon fish"
            + (f" for {user.name}" if gift else "")
            + f"!** (**{amount}** fishies) :blowfish:"
        )
        return amount

    @staticmethod
    async def fish_rare(ctx: commands.Context, user, gift):
        amount = random.randint(100, 399)
        await ctx.send(
            ":star: **Caught a super rare fish"
            + (f" for {user.name}" if gift else "")
            + f"! :star: ({amount} "
            "fishies)** :tropical_fish:"
        )
        return amount

    @staticmethod
    async def fish_legendary(ctx: commands.Context, user, gift):
        amount = random.randint(400, 750)
        await ctx.send(
            ":star2: **Caught a *legendary* fish"
            + (f" for {user.name}" if gift else "")
            + f"!! :star2: ({amount} "
            "fishies)** :dolphin:"
        )
        return amount

    async def trash(self, ctx: commands.Context, user, gift):
        icon = random.choice(self.TRASH_ICONS)
        await ctx.send(
            f"Caught **trash{'!' if not gift else ''}** {icon}"
            + (f" for {user.name}!" if gift else "")
            + " Better luck next time."
        )
        return 0


async def setup(bot):
    await bot.add_cog(Fishy(bot))
