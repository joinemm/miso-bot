import discord
import random
import aiohttp
import os
import arrow
import asyncio
import datetime
import humanize
import csv
import json
import async_cse
from bs4 import BeautifulSoup
from discord.ext import commands
from modules import exceptions, util

GCS_DEVELOPER_KEY = os.environ.get("GOOGLE_KEY")


class Kpop(commands.Cog):
    """Kpop related commands"""

    def __init__(self, bot):
        self.bot = bot
        self.google_client = async_cse.Search(GCS_DEVELOPER_KEY)
        self.icon = "💃"
        self.gender_icon = {
            "F": ":female_sign: ",
            "M": ":male_sign: ",
        }
        with open("data/data.json", "r") as f:
            data = json.load(f)
            try:
                self.artist_list = data["artists"]
            except KeyError:
                self.artist_list = []

    def cog_unload(self):
        self.bot.loop.create_task(self.shutdown())

    async def shutdown(self):
        await self.google_client.close()

    async def google_image_search(self, keyword):
        try:
            results = await self.google_client.search(keyword, safesearch=False, image_search=True)
        except async_cse.search.APIError:
            return ""
        if results:
            return results[0].image_url
        else:
            return ""

    @commands.group(case_insensitive=True)
    async def idol(self, ctx):
        """Kpop idols database."""
        await util.command_group_help(ctx)

    @idol.command()
    async def birthdays(self, ctx, month: int, day: int):
        dt = datetime.date(month=month, day=day, year=2020)
        idol_data = await self.bot.db.execute(
            """
            SELECT gender, group_name, stage_name, date_of_birth FROM kpop_idol WHERE
                MONTH(date_of_birth)=MONTH(%s)
                AND DAY(date_of_birth)=DAY(%s)
            ORDER BY YEAR(date_of_birth)
            """,
            dt,
            dt,
        )
        rows = []
        for gender, group, name, dob in idol_data:
            rows.append(
                f"{self.gender_icon.get(gender, '')} **{f'{group} ' if group is not None else ''} {name}** ({dob.year})"
            )
        content = discord.Embed(title=f"Kpop idols born on {humanize.naturalday(dt)}")
        if not rows:
            content.description = "No idols found with this birthday :("
            await ctx.send(embed=content)
        else:
            await util.send_as_pages(ctx, content, rows)

    @idol.command()
    async def random(self, ctx, gender=None):
        """Get a random kpop idol."""
        gender = get_gender(gender)

        idol_id_list = await self.bot.db.execute(
            "SELECT idol_id FROM kpop_idol WHERE gender IN %s",
            gender,
            as_list=True,
        )
        if not idol_id_list:
            raise exceptions.Error("Looks like there are no idols in the database!")

        chosen_id = random.choice(idol_id_list)
        await self.send_idol(ctx, chosen_id)

    async def send_idol(self, ctx, idol_id):
        idol_data = await self.bot.db.execute(
            """
            SELECT full_name, stage_name, korean_name, korean_stage_name,
                   date_of_birth, country, birthplace, group_name, height, weight, gender
                FROM kpop_idol
            WHERE idol_id = %s
            """,
            idol_id,
            one_row=True,
        )
        if not idol_data:
            raise exceptions.Error("There was an error getting idol data.")

        (
            full_name,
            stage_name,
            korean_name,
            korean_stage_name,
            date_of_birth,
            country,
            birthplace,
            group_name,
            height,
            weight,
            gender,
        ) = idol_data

        if group_name is None:
            search_term = full_name
        else:
            search_term = f"{group_name} {stage_name}"

        image = await self.google_image_search(search_term)
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
        content.set_image(url=image)
        content.add_field(name="Full name", value=full_name)
        content.add_field(name="Korean name", value=f"{korean_stage_name} ({korean_name})")
        content.add_field(
            name="Birthday", value=arrow.get(date_of_birth).format("YYYY-MM-DD") + f" (age {age})"
        )
        content.add_field(name="Country", value=country)
        content.add_field(name="Height", value=f"{height} cm" if height else "unknown")
        content.add_field(name="Weight", value=f"{weight} kg" if weight else "unknown")

        await ctx.send(embed=content)

    @commands.group(invoke_without_command=True)
    async def stan(self, ctx):
        """Get a random kpop artist to stan."""
        if self.artist_list:
            await ctx.send(f"stan **{random.choice(self.artist_list)}**")
        else:
            raise exceptions.Warning("Artist list is empty :thinking:")

    @commands.is_owner()
    @stan.command(hidden=True)
    async def update(self, ctx):
        """Update the artist database."""
        artist_list_new = set()
        urls_to_scrape = [
            "https://kprofiles.com/k-pop-girl-groups/",
            "https://kprofiles.com/disbanded-kpop-groups-list/",
            "https://kprofiles.com/disbanded-kpop-boy-groups/",
            "https://kprofiles.com/k-pop-boy-groups/",
            "https://kprofiles.com/co-ed-groups-profiles/",
            "https://kprofiles.com/kpop-duets-profiles/",
            "https://kprofiles.com/kpop-solo-singers/",
        ]

        async def scrape(session, url):
            artists = []
            async with session.get(url) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")
                content = soup.find("div", {"class": "entry-content herald-entry-content"})
                outer = content.find_all("p")
                for p in outer:
                    for artist in p.find_all("a"):
                        artist = artist.text.replace("Profile", "").replace("profile", "").strip()
                        if not artist == "":
                            artists.append(artist)
            return artists

        tasks = []
        async with aiohttp.ClientSession() as session:
            for url in urls_to_scrape:
                tasks.append(scrape(session, url))

            artist_list_new = list(set(sum(await asyncio.gather(*tasks), [])))

        with open("data/data.json", "w") as f:
            json.dump({"artists": artist_list_new}, f, indent=4)

        await util.send_success(
            ctx,
            f"**Artist list updated**\n"
            f"New entries: **{len(artist_list_new) - len(self.artist_list)}**\n"
            f"Total: **{len(artist_list_new)}**",
        )
        self.artist_list = artist_list_new

    @commands.is_owner()
    @commands.command(name="rebuildkpopdb")
    async def parse_kpop_sheets(self, groups: bool = True, idols: bool = True):
        """Rebuild the kpop idol database."""
        if groups:
            await self.bot.db.execute("DELETE FROM kpop_group")
            with open("data/kpopdb_girlgroups.tsv") as tsv_file:
                values = []
                read_tsv_gg = csv.reader(tsv_file, delimiter="\t")
                with open("data/kpopdb_boygroups.tsv") as tsv_file:
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
                                active.lower(),
                                gender,
                            ]
                            values.append(value)
                            print(value)

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

        if idols:
            await self.bot.db.execute("DELETE FROM kpop_idol")
            values = []
            with open("data/kpopdb_idols.tsv") as tsv_file:
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
                        other_group,
                        former_group,
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


def setup(bot):
    bot.add_cog(Kpop(bot))


def get_gender(user_input):
    if user_input is not None:
        user_input = user_input.lower()
        if user_input in ["f", "girl", "girls", "female", "females"]:
            return ("F",)
        elif user_input in ["m", "boy", "boys", "man", "men"]:
            return ("M",)
    return (
        "F",
        "M",
        None,
    )
