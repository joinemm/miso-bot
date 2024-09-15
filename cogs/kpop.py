# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import csv
import datetime
import random

import arrow
import async_cse
import discord
import humanize
from bs4 import BeautifulSoup
from discord.ext import commands

from modules import exceptions, util
from modules.misobot import MisoBot
from modules.ui import RowPaginator


class Kpop(commands.Cog):
    """Kpop related commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.google_client = async_cse.Search(bot.keychain.GCS_DEVELOPER_KEY)
        self.icon = "💃"
        self.gender_icon = {
            "F": ":female_sign: ",
            "M": ":male_sign: ",
        }

    async def cog_unload(self):
        await self.shutdown()

    async def shutdown(self):
        await self.google_client.close()

    async def google_image_search(self, keyword):
        try:
            results = await self.google_client.search(
                keyword, safesearch=False, image_search=True
            )
        except async_cse.search.APIError:
            return ""
        return results[0].image_url if results else ""

    @commands.command(name="idol", hidden=True)
    async def deprecate_idol(self, ctx: commands.Context):
        raise exceptions.CommandInfo(
            f"This command has been moved to `{ctx.prefix}kpop idol ...`"
        )

    @commands.group(case_insensitive=True)
    async def kpop(self, ctx: commands.Context):
        """Kpop idols and groups database"""
        await util.command_group_help(ctx)

    @kpop.command()
    async def birthdays(self, ctx: commands.Context, month: int, day: int):
        dt = datetime.date(month=month, day=day, year=2020)
        idol_data = await self.bot.db.fetch(
            """
            SELECT gender, group_name, stage_name, date_of_birth FROM kpop_idol WHERE
                MONTH(date_of_birth)=MONTH(%s)
                AND DAY(date_of_birth)=DAY(%s)
            ORDER BY YEAR(date_of_birth)
            """,
            dt,
            dt,
        )
        if idol_data is None:
            raise exceptions.CommandError(
                "There was a problem fetching idol data from the database"
            )

        rows = [
            f"{self.gender_icon.get(gender, '')} "
            f"**{f'{group} ' if group is not None else ''} {name}** ({dob.year})"
            for gender, group, name, dob in idol_data
        ]
        content = discord.Embed(title=f"Kpop idols born on {humanize.naturalday(dt)}")
        if not rows:
            content.description = "No idols found with this birthday :("
            await ctx.send(embed=content)
        else:
            await RowPaginator(content, rows).run(ctx)

    @kpop.group(case_insensitive=True)
    async def idol(self, ctx: commands.Context):
        """Kpop idols"""
        await util.command_group_help(ctx)

    @idol.command(name="random")
    async def idol_random(self, ctx: commands.Context, gender=None):
        """Get a random kpop idol"""
        gender = get_gender(gender)

        idol_id_list = await self.bot.db.fetch_flattened(
            "SELECT idol_id FROM kpop_idol WHERE gender IN %s",
            gender,
        )
        if not idol_id_list:
            raise exceptions.CommandError(
                "There was a problem fetching idol data from the database"
            )

        chosen_id = random.choice(idol_id_list)
        await self.send_idol(ctx, chosen_id)

    async def send_idol(self, ctx: commands.Context, idol_id):
        idol_data = await self.bot.db.fetch_row(
            """
            SELECT idol_id, full_name, stage_name, korean_name, korean_stage_name,
                   date_of_birth, country, group_name, height, weight, gender, 
                   image_url, image_scrape_date, birthplace, former_group, instagram
                FROM kpop_idol
            WHERE idol_id = %s
            """,
            idol_id,
        )
        if not idol_data:
            raise exceptions.CommandError(
                "There was a problem fetching idol data from the database"
            )

        (
            idol_id,
            full_name,
            stage_name,
            korean_name,
            korean_stage_name,
            date_of_birth,
            country,
            group_name,
            height,
            weight,
            gender,
            image_url,
            image_scrape_date,
            birthplace,
            former_group,
            instagram,
        ) = idol_data

        content = discord.Embed()
        if gender == "F":
            content.colour = int("e7586d", 16)
        elif gender == "M":
            content.colour = int("226699", 16)

        content.title = (
            self.gender_icon.get(gender, "")
            + (f"{group_name} " if group_name is not None else "")
            + stage_name
        )
        today = datetime.date.today()
        age = (
            today.year
            - date_of_birth.year
            - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        )
        content.add_field(name="Full name", value=full_name)
        content.add_field(
            name="Korean name", value=f"{korean_stage_name} ({korean_name})"
        )
        content.add_field(
            name="Birthday",
            value=arrow.get(date_of_birth).format("YYYY-MM-DD") + f" (age {age})",
        )
        content.add_field(
            name="Birthplace",
            value=f"{birthplace}, {country}" if birthplace else country,
        )
        content.add_field(name="Height", value=f"{height} cm" if height else "unknown")
        content.add_field(name="Weight", value=f"{weight} kg" if weight else "unknown")
        if former_group:
            content.add_field(
                name="Former groups",
                value=", ".join(former_group.split(",")),
            )
        if instagram:
            content.add_field(
                name="Instagram",
                value=f"[@{instagram}](https://www.instagram.com/{instagram})",
            )

        if image_url is None or (today - image_scrape_date.date).days > 30:
            if group_name is None:
                search_term = f"{full_name} kpop"
            else:
                search_term = f"{stage_name} of {group_name} kpop"
            image_url = await self.google_image_search(search_term)
            if image_url != "":
                await self.bot.db.execute(
                    """
                    UPDATE kpop_idol 
                        SET image_url = %s, 
                        image_scrape_date = %s 
                    WHERE idol_id = %s
                    """,
                    image_url,
                    today,
                    idol_id,
                )

        content.set_image(url=image_url)
        await ctx.send(embed=content)

    @kpop.group(case_insensitive=True)
    async def group(self, ctx: commands.Context):
        """Kpop groups"""
        await util.command_group_help(ctx)

    @group.command(name="random")
    async def group_random(self, ctx: commands.Context, gender=None):
        """Get a random kpop group"""
        gender = get_gender(gender)

        group_id_list = await self.bot.db.fetch_flattened(
            "SELECT group_id FROM kpop_group WHERE gender IN %s",
            gender,
        )
        if not group_id_list:
            raise exceptions.CommandError(
                "There was a problem fetching idol data from the database"
            )

        chosen_id = random.choice(group_id_list)
        await self.send_group(ctx, chosen_id)

    async def send_group(self, ctx: commands.Context, group_id):
        group_data = await self.bot.db.fetch_row(
            """
            SELECT group_id, gender, group_name, short_name, korean_name, 
                   debut_date, company, members, image_url, image_scrape_date
                FROM kpop_group
            WHERE group_id = %s
            """,
            group_id,
        )
        if not group_data:
            raise exceptions.CommandError(
                "There was a problem fetching group data from the database"
            )

        (
            group_id,
            gender,
            name,
            short_name,
            korean_name,
            debut_date,
            company,
            members,
            image_url,
            image_scrape_date,
        ) = group_data

        content = discord.Embed()
        if gender == "F":
            content.colour = int("e7586d", 16)
        elif gender == "M":
            content.colour = int("226699", 16)

        content.title = self.gender_icon.get(gender, "") + name
        if short_name:
            content.title += f" ({short_name})"
        today = datetime.date.today()
        age = (
            today.year
            - debut_date.year
            - ((today.month, today.day) < (debut_date.month, debut_date.day))
        )
        content.add_field(name="Korean name", value=f"{korean_name}")
        content.add_field(
            name="Debut",
            value=arrow.get(debut_date).format("YYYY-MM-DD") + f" ({age} years ago)",
        )
        content.add_field(name="Company", value=company)

        member_list = await self.bot.db.fetch(
            """
            SELECT i.stage_name 
            FROM kpop_idol i JOIN group_membership gm ON i.idol_id = gm.idol_id
            JOIN kpop_group g ON gm.group_id = g.group_id
            WHERE g.group_id = %s
            """,
            group_id,
        )
        content.add_field(
            name="Members", value=", ".join(x[0] for x in member_list), inline=False
        )

        if image_url is None or (today - image_scrape_date.date).days > 30:
            search_term = f"{name} kpop group"
            image_url = await self.google_image_search(search_term)
            if image_url != "":
                await self.bot.db.execute(
                    """
                    UPDATE kpop_group 
                        SET image_url = %s, 
                        image_scrape_date = %s 
                    WHERE group_id = %s
                    """,
                    image_url,
                    today,
                    group_id,
                )

        content.set_image(url=image_url)
        await ctx.send(embed=content)

    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def stan(self, ctx: commands.Context):
        """Get a random kpop artist to stan"""
        # fast random row
        # https://stackoverflow.com/questions/4329396/mysql-select-10-random-rows-from-600k-rows-fast
        random_row = await self.bot.db.fetch_row(
            """
            SELECT * FROM stannable_artist AS t1
                JOIN (
                    SELECT id FROM stannable_artist
                    ORDER BY RAND()
                    LIMIT 1
                ) AS t2
            ON t1.id = t2.id
            """,
        )
        if not random_row:
            raise exceptions.CommandError("Could not find an artist to stan")

        await ctx.send(f"stan **{random_row[1]}**")

    @commands.is_owner()
    @stan.command(hidden=True)
    async def update(self, ctx: commands.Context):
        """Update the artist database"""
        categories = [
            ("Girl group", "https://kprofiles.com/k-pop-girl-groups/"),
            ("Disbanded", "https://kprofiles.com/disbanded-kpop-groups-list/"),
            ("Disbanded", "https://kprofiles.com/disbanded-kpop-boy-groups/"),
            ("Boy group", "https://kprofiles.com/k-pop-boy-groups/"),
            ("Co-Ed group", "https://kprofiles.com/co-ed-groups-profiles/"),
            ("Duet", "https://kprofiles.com/kpop-duets-profiles/"),
            ("Soloist", "https://kprofiles.com/kpop-solo-singers/"),
        ]

        async def scrape(category, url):
            artists = []
            async with self.bot.session.get(url) as response:
                soup = BeautifulSoup(await response.text(), "lxml")
                content = soup.find(
                    "div", {"class": "entry-content herald-entry-content"}
                )
                outer = content.find_all("p")  # type: ignore
                for p in outer:
                    for artist in p.find_all("a"):
                        artist = (
                            artist.text.replace("Profile", "")
                            .replace("profile", "")
                            .strip()
                        )
                        if artist != "":
                            artists.append([artist, category])
            return artists

        task_results = await asyncio.gather(
            *[scrape(category, url) for category, url in categories]
        )
        new_artist_list = [artist for sublist in task_results for artist in sublist]

        await self.bot.db.executemany(
            """
            INSERT IGNORE stannable_artist (artist_name, category)
                VALUES (%s, %s)
            """,
            new_artist_list,
        )

        await util.send_success(
            ctx,
            f"**Artist list updated**\n"
            f"Stannable artist count: **{len(new_artist_list)}**",
        )

    @commands.is_owner()
    @commands.command(name="generate_kpop_groups", hidden=True)
    async def generate_kpop_groups(self, ctx: commands.Context):
        values = []
        with (
            open("data/girl_groups.tsv") as tsv_f,
            open("data/boy_bands.tsv") as tsv_m,
        ):
            for gender, tsv in [
                ("F", csv.reader(tsv_f, delimiter="\t")),
                ("M", csv.reader(tsv_m, delimiter="\t")),
            ]:
                for row in tsv:
                    filtered_row = [(v if v != "" else None) for v in row]
                    values.append([gender] + filtered_row)

        await self.bot.db.execute("""DELETE FROM kpop_group""")
        await self.bot.db.executemany(
            """
            INSERT IGNORE kpop_group (
                gender,
                profile_url,
                group_name,
                short_name,
                korean_name,
                debut_date,
                company,
                members,
                orig_members,
                fanclub,
                active
            )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            values,
        )
        await ctx.send("Groups :thumbs_up:")

    @commands.is_owner()
    @commands.command(name="generate_kpop_idols", hidden=True)
    async def generate_kpop_idols(self, ctx: commands.Context):
        """Rebuild the kpop idol database"""
        values = []
        with (
            open("data/female_idols.tsv") as tsv_f,
            open("data/male_idols.tsv") as tsv_m,
        ):
            for gender, tsv in [
                ("F", csv.reader(tsv_f, delimiter="\t")),
                ("M", csv.reader(tsv_m, delimiter="\t")),
            ]:
                for row in tsv:
                    filtered_row = [(v if v != "" else None) for v in row]
                    values.append([gender] + filtered_row)

        await self.bot.db.execute("""DELETE FROM kpop_idol""")
        await self.bot.db.executemany(
            """
            INSERT IGNORE kpop_idol (
                gender,
                profile_url,
                stage_name,
                full_name,
                korean_name,
                korean_stage_name,
                date_of_birth,
                group_name,
                country,
                second_country,
                height,
                weight,
                birthplace,
                other_group,
                former_group,
                position,
                instagram,
                twitter
            )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            values,
        )

        await ctx.send("Idols :thumbs_up:")

    @commands.is_owner()
    @commands.command(name="generate_group_relations", hidden=True)
    async def generate_relationships(self, ctx: commands.Context):
        await self.bot.db.execute("""DELETE FROM group_membership""")
        idols = await self.bot.db.fetch(
            """SELECT idol_id, group_name, other_group, former_group, stage_name FROM kpop_idol"""
        )
        for idol in idols:
            groups = ([idol[1]] if idol[1] else []) + (
                idol[2].split(",") if idol[2] else []
            )
            formers = idol[3].split(",") if idol[3] else []
            print(idol[-1], "has groups", groups, "and former groups", formers)
            for groupname in groups:
                group = await self.bot.db.fetch_value(
                    """SELECT group_id FROM kpop_group WHERE group_name = %s OR short_name = %s""",
                    groupname,
                    groupname,
                )
                if group:
                    await self.bot.db.execute(
                        """
                    INSERT INTO group_membership VALUES (%s, %s, %s)
                    """,
                        idol[0],
                        group,
                        True,
                    )
            for groupname in formers:
                group = await self.bot.db.fetch_value(
                    """SELECT group_id FROM kpop_group WHERE group_name = %s OR short_name = %s""",
                    groupname,
                    groupname,
                )
                if group:
                    await self.bot.db.execute(
                        """
                    INSERT INTO group_membership VALUES (%s, %s, %s)
                    """,
                        idol[0],
                        group,
                        False,
                    )


async def setup(bot):
    await bot.add_cog(Kpop(bot))


def get_gender(user_input):
    if user_input is not None:
        user_input = user_input.lower()
        if user_input in ["f", "girl", "girls", "female", "females"]:
            return ("F",)
        if user_input in ["m", "boy", "boys", "man", "men"]:
            return ("M",)
    return (
        "F",
        "M",
        None,
    )
