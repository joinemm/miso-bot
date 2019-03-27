import discord
from discord.ext import commands
import data.database as db
import random
import requests
from bs4 import BeautifulSoup


class Miscellaneous(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(aliases=['random'])
    async def rng(self, ctx, cap=1):
        try:
            choice = random.randint(0, int(cap))
        except ValueError:
            return await ctx.send(f"**ERROR:** `{cap}` is not a valid number")
        await ctx.send(f"Random number [0-{cap}]: **{choice}**")

    @commands.group(invoke_without_command=True)
    async def stan(self, ctx):
        artist_list = db.get_from_data_json(['artists'])
        if artist_list:
            await ctx.send(f"stan **{random.choice(artist_list)}**")
        else:
            await ctx.send(f"**ERROR:** Artist list is empty. Please use `{self.client.command_prefix}stan update`")

    @stan.command()
    async def update(self, ctx):
        artist_list_old = db.get_from_data_json(['artists'])
        artist_list_new = set()
        urls_to_scrape = ['https://kprofiles.com/k-pop-girl-groups/',
                          'https://kprofiles.com/k-pop-boy-groups/',
                          'https://kprofiles.com/co-ed-groups-profiles/',
                          'https://kprofiles.com/kpop-duets-profiles/',
                          'https://kprofiles.com/kpop-solo-singers/']
        for url in urls_to_scrape:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            content = soup.find("div", {'class': 'entry-content herald-entry-content'})
            outer = content.find_all('p')
            for p in outer:
                for x in p.find_all('a'):
                    x = x.text.replace("Profile", "").replace("profile", "").strip()
                    if not x == "":
                        artist_list_new.add(x)

        db.save_into_data_json(['artists'], list(artist_list_new))
        await ctx.send(f"**Artist list updated**\n"
                       f"New entries: **{len(artist_list_new) - len(artist_list_old)}**\n"
                       f"Total: **{len(artist_list_new)}**")


def setup(client):
    client.add_cog(Miscellaneous(client))
