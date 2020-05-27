import discord
import aiohttp
from bs4 import BeautifulSoup
from discord.ext import commands
from helpers import utilityfunctions as util


class GGSoup:
    def __init__(self):
        self.soup = None

    async def create(self, region, summoner_name, sub_url=""):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://{region}.op.gg/summoner/{sub_url}userName={summoner_name}"
            ) as response:
                data = await response.text()
                self.soup = BeautifulSoup(data, "html.parser")

    def text(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        return source.find(obj, {"class": classname}).text.strip()

    def src(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        return "https:" + source.find(obj, {"class": classname}).get("src")


class OPGG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.regions = {
            "kr": "www",
            "korea": "www",
            "eune": "eune",
            "euw": "euw",
            "jp": "jp",
            "japan": "jp",
            "na": "na",
            "oceania": "oce",
            "oce": "oce",
            "brazil": "br",
            "las": "las",
            "russia": "ru",
            "ru": "ru",
            "turkey": "tr",
            "tr": "tr",
        }

    @commands.group(aliases=["league"], case_insensitive=True)
    async def opgg(self, ctx):
        await util.command_group_help(ctx)

    @opgg.command()
    async def profile(self, ctx, region, *, summoner_name):
        parsed_region = self.regions.get(region.lower())
        if parsed_region is None:
            return await ctx.send(f":warning: Unknown region `{region}`")

        region = parsed_region

        ggsoup = GGSoup()
        await ggsoup.create(region, summoner_name)

        content = discord.Embed()
        content.set_author(
            name=f"{ggsoup.text('span', 'Name')} [{region.upper()}]",
            icon_url=ggsoup.src("img", "ProfileImage"),
        )

        rank = ggsoup.text("div", "TierRank")
        lp = ""
        wins_losses = ""
        if rank != "Unranked":
            lp = ggsoup.text("span", "LeaguePoints")
            wins_losses = (
                f"{ggsoup.text('span', 'wins')} {ggsoup.text('span', 'losses')} "
                f"({ggsoup.text('span', 'winratio').split()[-1]})"
            )

        content.add_field(
            name="Rank",
            value=f"**{rank}**"
            + (f" {lp} **|** {wins_losses}" if rank != "Unranked" else ""),
            inline=False,
        )

        rank_image = "https:" + ggsoup.soup.find("div", {"class": "Medal"}).find(
            "img"
        ).get("src")
        content.set_thumbnail(url=rank_image)
        content.colour = int("5383e8", 16)

        champions = []
        for championbox in ggsoup.soup.findAll("div", {"class": "ChampionBox"}):
            name = championbox.find("div", {"class": "ChampionName"}).get("title")
            played_div = championbox.find("div", {"class": "Played"})
            played_count = played_div.find("div", {"class": "Title"}).text.strip()
            winrate = played_div.find("div", {"class": "WinRatio"}).text.strip()
            champions.append(
                f"**{played_count.replace(' Played', '** Played')} **{name}** ({winrate})"
            )

        content.add_field(
            name="Champions", value="\n".join(champions) if champions else "None"
        )

        match_history = []
        for match in ggsoup.soup.findAll("div", {"class": "GameItem"}):
            gametype = ggsoup.text("div", "GameType", match)
            champion = (
                match.find("div", {"class": "ChampionName"}).find("a").text.strip()
            )
            win = match.get("data-game-result") == "win"
            kda = "".join(
                ggsoup.text("div", "KDA", match.find("div", {"class": "KDA"})).split()
            )
            emoji = ":blue_square:" if win else ":red_square:"
            match_history.append(f"{emoji} **{gametype}** as **{champion}** `{kda}`")

        content.add_field(
            name="Match History",
            value="\n".join(match_history) if match_history else "No matches found",
        )

        await ctx.send(embed=content)

    @opgg.command()
    async def nowplaying(self, ctx, region, *, summoner_name):
        parsed_region = self.regions.get(region.lower())
        if parsed_region is None:
            return await ctx.send(f":warning: Unknown region `{region}`")

        region = parsed_region

        content = discord.Embed(title=f"{summoner_name} current game")

        ggsoup = GGSoup()
        await ggsoup.create(region, summoner_name, sub_url="spectator/")

        blue_team = ggsoup.soup.find("table", {"class": "Team-100"})
        red_team = ggsoup.soup.find("table", {"class": "Team-200"})
        for title, team in [("Blue Team", blue_team), ("Red Team", red_team)]:
            rows = []
            players = team.find("tbody").findAll("tr")
            for player in players:
                champion = (
                    player.find("td", {"class": "ChampionImage"})
                    .find("a")
                    .get("href")
                    .split("/")[2]
                )
                summoner = ggsoup.text("a", "SummonerName", player)
                url = f"https://{region}.op.gg/summoner/userName={summoner.replace(' ', '%20')}"
                rank = ggsoup.text("div", "TierRank", player)
                rows.append(f"`{rank:20} |` [{summoner}]({url}) as **{champion}**")

            content.add_field(name=title, value="\n".join(rows), inline=False)

        await ctx.send(embed=content)


def setup(bot):
    bot.add_cog(OPGG(bot))
