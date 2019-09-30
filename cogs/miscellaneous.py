import discord
from discord.ext import commands
import data.database as db
import random
import requests
from bs4 import BeautifulSoup
import json
from libraries import minestat
import helpers.utilityfunctions as util
import os
from google_images_search import GoogleImagesSearch


GCS_DEVELOPER_KEY = os.environ.get('GOOGLE_KEY')

hs_colors = {
            "aries": discord.Color.red(),
            "taurus": discord.Color.dark_teal(),
            'gemini': discord.Color.gold(),
            'cancer': discord.Color.greyple(),
            'leo': discord.Color.orange(),
            'virgo': discord.Color.green(),
            'libra': discord.Color.dark_teal(),
            'scorpio': discord.Color.dark_red(),
            'sagittarius': discord.Color.purple(),
            'capricorn': discord.Color.dark_green(),
            'aquarius': discord.Color.teal(),
            'pisces': discord.Color.blurple()
        }


class Miscellaneous(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(aliases=['random'])
    async def rng(self, ctx, cap: int):
        """Random number generator"""
        choice = random.randint(0, cap)
        await ctx.send(f"Random number [0-{cap}]: **{choice}**")

    @commands.command()
    async def ascii(self, ctx, *, text):
        """Turn text into fancy ascii art"""
        response = requests.get(f"https://artii.herokuapp.com/make?text={text}")
        content = f"```{response.content.decode('utf-8')}```"
        await ctx.send(content)

    @commands.command(aliases=['8ball'])
    async def eightball(self, ctx, *question):
        """Ask a yes/no question"""
        if question:
            choices = ["Yes, definitely.", "Yes.", "Most likely yes.", "I think so, yes.", "Absolutely",
                       "Maybe.", "Perhaps.", "Possibly.", "idk"
                       "I don't think so.", "No.", "Most likely not.", "Definitely not.", "No way."]
            answer = random.choice(choices)
            await ctx.send(f"**{answer}**")
        else:
            await ctx.send("You must ask something to receive an answer!")

    @commands.command()
    async def choose(self, ctx, *, choices):
        """Choose from given options. split options with 'or'"""
        choices = choices.split(" or ")
        if len(choices) < 2:
            return await ctx.send("Give me at least 2 options to choose from! (separate options with `or`)")
        choice = random.choice(choices).strip()
        await ctx.send(f"I choose **{choice}**")

    @commands.group(invoke_without_command=True)
    async def stan(self, ctx):
        """Get a random kpop artist to stan"""
        artist_list = db.get_from_data_json(['artists'])
        if artist_list:
            await ctx.send(f"stan **{random.choice(artist_list)}**")
        else:
            await ctx.send(f"**ERROR:** Artist list is empty. Please use `{self.client.command_prefix}stan update`")

    @stan.command()
    async def update(self, ctx):
        """Update the kpop artist database"""
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

    @commands.command()
    async def ship(self, ctx, *, names):
        """Ship two people, separate names with 'and'"""
        names = names.split(' and ')
        if not len(names) == 2:
            return await ctx.send("Please give two names separated with `and`")

        url = f"https://www.calculator.net/love-calculator.html?cnameone={names[0]}&x=0&y=0&cnametwo={names[1]}"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        percentage = soup.find("font", {'color': 'green'}).find('b').text
        text = soup.find("div", {'id': 'content'}).find_all('p')[2].text

        perc = int(percentage.strip("%"))
        if perc < 26:
            emoji = ":broken_heart:"
        elif perc > 74:
            emoji = ":sparkling_heart:"
        else:
            emoji = ":hearts:"
        content = discord.Embed(title=f"{names[0]} {emoji} {names[1]} - {percentage}", colour=discord.Colour.magenta())
        content.description = text
        await ctx.send(embed=content)

    @commands.command(aliases=['mc'])
    async def minecraft(self, ctx, address=None, port=None):
        """Get the status of a minecraft server"""
        if address == "set":
            if port is None:
                return await ctx.send(f"Save minecraft server address for this discord server:\n"
                                      f"`{self.client.command_prefix}minecraft set <address>` or\n"
                                      f"`{self.client.command_prefix}minecraft set <address>:<port>`")

            address = port.split(":")[0]
            try:
                port = int(port.split(":")[1])
            except IndexError:
                port = 25565

            db.execute("""REPLACE INTO minecraft VALUES (?, ?, ?)""", (ctx.guild.id, address, port))
            return await ctx.send(f"Minecraft server of this discord set to `{address}:{port}`")

        if address is None:
            if ctx.guild is None:
                return await ctx.send("missing address!")
            else:
                serverdata = db.query("""SELECT address, port FROM minecraft WHERE guild_id = ?""", (ctx.guild.id,))
            if serverdata is None:
                return await ctx.send("No minecraft server saved for this discord server!")
            else:
                address, port = serverdata[0]

        server = minestat.MineStat(address, int(port or '25565'))
        content = discord.Embed()
        content.colour = discord.Color.green()
        if server.online:
            content.add_field(name="Server Address", value=f"`{server.address}`")
            content.add_field(name="Version", value=server.version)
            content.add_field(name="Players", value=f"{server.current_players}/{server.max_players}")
            content.add_field(name="Latency", value=f"{server.latency}ms")
            content.set_footer(text=f"Message of the day: {server.motd}")
        else:
            content.description = "**Server is offline**"
        content.set_thumbnail(url="https://vignette.wikia.nocookie.net/potcoplayers/images/c/c2/"
                                  "Minecraft-icon-file-gzpvzfll.png/revision/latest?cb=20140813205910")
        await ctx.send(embed=content)

    @commands.group(aliases=['hs'], case_insensitive=True)
    async def horoscope(self, ctx):
        """Get your daily horoscope"""
        if ctx.invoked_subcommand is not None:
            return
        sign = db.userdata(ctx.author.id).sunsign
        if sign is None:
            return await ctx.send("Please save your sunsign using `>horoscope set <sign>`\n"
                                  "use `>horoscope list` if you don't know which one you are.")

        params = (
            ('sign', sign),
            ('day', 'today'),
        )

        response = requests.post('https://aztro.sameerkumar.website/', params=params)
        response_data = json.loads(response.content.decode('utf-8'))

        content = discord.Embed(color=hs_colors[sign])
        content.title = f"{sign.capitalize()} - {response_data['current_date']}"
        content.add_field(name='Mood', value=response_data['mood'], inline=True)
        content.add_field(name='Compatibility', value=response_data['compatibility'], inline=True)
        content.add_field(name='Color', value=response_data['color'], inline=True)
        content.add_field(name='Lucky number', value=response_data['lucky_number'], inline=True)
        content.add_field(name='Lucky time', value=response_data['lucky_time'], inline=True)
        content.add_field(name='Date range', value=response_data['date_range'], inline=True)

        content.description = response_data['description']
        await ctx.send(embed=content)

    @commands.command()
    async def clap(self, ctx, *words):
        """Add a clap emoji between words"""
        await ctx.send(' 👏 '.join(words) + ' 👏')

    @horoscope.command()
    async def set(self, ctx, sign):
        """Set your sunsign"""
        hs = ['aries', 'taurus', 'gemini', 'cancer', 'leo', 'virgo', 'libra', 'scorpio', 'sagittarius', 'capricorn',
              'aquarius', 'pisces']
        sign = sign.lower()
        if sign not in hs:
            await ctx.send(f"`{sign}` is not a valid sunsign! use `>horoscope list` for a list of sunsigns.")
            return
        db.update_user(ctx.author.id, "sunsign", sign)
        await ctx.send(f"Sunsign saved as `{sign}`")

    @horoscope.command()
    async def list(self, ctx):
        """Get list of all sunsigns"""
        sign_list = """
`(Mar 21-Apr 19)` **Aries**
`(Apr 20-May 20)` **Taurus**
`(May 21-Jun 20)` **Gemini**
`(Jun 21-Jul 22)` **Cancer**
`(Jul 23-Aug 22)` **Leo**
`(Aug 23-Sep 22)` **Virgo**
`(Sep 23-Oct 22)` **Libra**
`(Oct 23-Nov 21)` **Scorpio**
`(Nov 22-Dec 21)` **Sagittarius**
`(Dec 22-Jan 19)` **Capricorn**
`(Jan 20-Feb 18)` **Aquarius**
`(Feb 19-Mar 20)` **Pisces**
"""
        content = discord.Embed(color=discord.Color.gold())
        content.title = f"Sunsign list"
        content.description = sign_list
        return await ctx.send(embed=content)

    @commands.group(case_insensitive=True)
    async def idol(self, ctx):
        await util.command_group_help(ctx)

    @idol.command()
    async def random(self, ctx, gender=None):
        if gender is not None:
            gender = gender.lower()
            if gender in ['f', 'girl', 'girls']:
                gender = 'F'
            elif gender in ['m', 'boy', 'boys']:
                gender = 'M'
            else:
                gender = None
        data = db.random_kpop_idol(gender)

        image = image_search(data.stage_name + ' ' + (data.group or ''))
        content = discord.Embed(color=await util.get_color(ctx, util.color_from_image_url(image)))
        content.set_image(url=image)
        content.title = (f'{data.group} ' if data.group is not None else '') + data.stage_name
        content.description = f"**Full name:** {data.full_name}\n" \
            f"**Korean name:** {data.k_stage_name} ({data.korean_name})\n" \
            f"**Birthday:** {data.date_of_birth}\n" \
            f"**Country:** {data.country}\n"\
                              + (f'**Birthplace:** {data.birthplace}' if data.birthplace is not None else '')
        await ctx.send(embed=content)


def setup(client):
    client.add_cog(Miscellaneous(client))


def image_search(query):
    print('searching for', query)
    gis = GoogleImagesSearch(GCS_DEVELOPER_KEY, '016720228003584159752:xwo6ysur40a')
    _search_params = {
        'q': query,
        'safe': 'off',
    }

    try:
        # this will only search for images:
        gis.search(search_params=_search_params)
        img = gis.results()[0].url
        return img
    except Exception as e:
        return ''
