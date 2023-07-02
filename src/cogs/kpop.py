# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import csv
import datetime
import os
import random

import arrow
import async_cse
import discord
import humanize
from bs4 import BeautifulSoup
from discord.ext import commands

from modules import exceptions, util
from modules.misobot import MisoBot


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
            results = await self.google_client.search(keyword, safesearch=False, image_search=True)
        except async_cse.search.APIError:
            return ""
        return results[0].image_url if results else ""

    @commands.group(case_insensitive=True)
    async def idol(self, ctx: commands.Context):
        """Kpop idols database"""
        await util.command_group_help(ctx)

    @idol.command()
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
            await util.send_as_pages(ctx, content, rows)

    @idol.command()
    async def random(self, ctx: commands.Context, gender=None):
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
                   date_of_birth, country, group_name, height, weight, gender, image_url
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
        ) = idol_data

        if group_name is None:
            search_term = full_name
        else:
            search_term = f"{group_name} {stage_name} kpop"

        if image_url is None:
            image_url = await self.google_image_search(search_term)
            if image_url != "":
                await self.bot.db.execute(
                    "UPDATE kpop_idol SET image_url = %s WHERE idol_id = %s",
                    image_url,
                    idol_id,
                )

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
        content.set_image(url=image_url)
        content.add_field(name="Full name", value=full_name)
        content.add_field(name="Korean name", value=f"{korean_stage_name} ({korean_name})")
        content.add_field(
            name="Birthday",
            value=arrow.get(date_of_birth).format("YYYY-MM-DD") + f" (age {age})",
        )
        content.add_field(name="Country", value=country)
        content.add_field(name="Height", value=f"{height} cm" if height else "unknown")
        content.add_field(name="Weight", value=f"{weight} kg" if weight else "unknown")

        await ctx.send(embed=content)

    @commands.group(invoke_without_command=True)
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
                content = soup.find("div", {"class": "entry-content herald-entry-content"})
                outer = content.find_all("p")  # type: ignore
                for p in outer:
                    for artist in p.find_all("a"):
                        artist = artist.text.replace("Profile", "").replace("profile", "").strip()
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
            f"**Artist list updated**\n" f"Stannable artist count: **{len(new_artist_list)}**",
        )

    @commands.is_owner()
    @commands.command(name="rebuildkpopdb", hidden=True)
    async def parse_kpop_sheets(
        self, ctx: commands.Context, groups: bool = True, idols: bool = True
    ):
        """Rebuild the kpop idol database"""
        if groups:
            await self.bot.db.execute("""DELETE FROM kpop_group""")
            with open(
                os.path.join(os.path.dirname(__file__), "../data/kpopdb_girlgroups.tsv")
            ) as tsv_file:
                values = []
                read_tsv_gg = csv.reader(tsv_file, delimiter="\t")
                with open(
                    os.path.join(os.path.dirname(__file__), "../data/kpopdb_boygroups.tsv")
                ) as tsv_file:
                    read_tsv_bg = csv.reader(tsv_file, delimiter="\t")
                    next(read_tsv_gg)
                    next(read_tsv_bg)
                    for gender, tsv in [("F", read_tsv_gg), ("M", read_tsv_bg)]:
                        for row in tsv:
                            filtered_row = [(v if v != "" else None) for v in row]
                            (
                                _,
                                name,
                                other_name,
                                korean_name,
                                debut_date,
                                company,
                                _,
                                _,
                                fanclub,
                                active,
                            ) = filtered_row
                            value = [
                                name,
                                other_name,
                                korean_name,
                                debut_date,
                                company,
                                fanclub,
                                active.lower() if active else active,
                                gender,
                            ]
                            values.append(value)

                await self.bot.db.executemany(
                    """
                    INSERT IGNORE kpop_group (
                        group_name, other_name, korean_name,
                        debut_date, company, fanclub, active, gender
                    )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    values,
                )
            await ctx.send("Groups :thumbs_up")

        if idols:
            await self.bot.db.execute("""DELETE FROM kpop_idol""")
            values = []

            with open(
                os.path.join(os.path.dirname(__file__), "../data/kpopdb_idols.tsv")
            ) as tsv_file:
                read_tsv = csv.reader(tsv_file, delimiter="\t")
                next(read_tsv)
                for row in read_tsv:
                    filtered_row = [(v if v != "" else None) for v in row]
                    (
                        _,
                        stage_name,
                        full_name,
                        korean_name,
                        korean_stage_name,
                        date_of_birth,
                        group,
                        country,
                        second_country,
                        height,
                        weight,
                        birthplace,
                        _other_group,
                        _former_group,
                        gender,
                        position,
                        instagram,
                        twitter,
                    ) = filtered_row
                    value = [
                        group,
                        stage_name,
                        full_name,
                        korean_name,
                        korean_stage_name,
                        date_of_birth,
                        country,
                        second_country,
                        height,
                        weight,
                        birthplace,
                        gender,
                        position,
                        instagram,
                        twitter,
                    ]
                    values.append(value)

                await self.bot.db.executemany(
                    """
                    INSERT IGNORE kpop_idol (
                        group_name,
                        stage_name,
                        full_name,
                        korean_name,
                        korean_stage_name,
                        date_of_birth,
                        country,
                        second_country,
                        height,
                        weight,
                        birthplace,
                        gender,
                        position,
                        instagram,
                        twitter
                    )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    values,
                )
            await ctx.send("Idols :thumbs_up")


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
