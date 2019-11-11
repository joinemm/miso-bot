import discord
import random
import os
import arrow
import aiohttp
import asyncio 
from bs4 import BeautifulSoup
from libraries import minestat
from discord.ext import commands
from google_images_search import GoogleImagesSearch
from data import database as db
from helpers import utilityfunctions as util


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

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['random'])
    async def rng(self, ctx, cap: int):
        """Random number generator"""
        choice = random.randint(0, cap)
        await ctx.send(f"Random number [0-{cap}]: **{choice}**")

    @commands.command()
    async def ascii(self, ctx, *, text):
        """Turn text into fancy ascii art"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://artii.herokuapp.com/make?text={text}") as response:
                content = await response.text()

        await ctx.send(content)

    @commands.command(aliases=['8ball'])
    async def eightball(self, ctx, *, question):
        """Ask a yes/no question"""
        if question:
            choices = [
                "Yes, definitely",
                "Yes",
                "Most likely yes",
                "I think so, yes",
                "Absolutely!",
                "Maybe",
                "Perhaps",
                "Possibly", 
                "I don't think so",
                "No",
                "Most likely not",
                "Absolutely not!",
                "There is no way"
            ]
            answer = random.choice(choices)
            question = question + ('?' if not question.endswith('?') else '')
            await ctx.send(f"> {question}\n**{answer}**")
        else:
            await ctx.send("You must ask something to receive an answer!")

    @commands.command()
    async def choose(self, ctx, *, choices):
        """Choose from given options. Split options with 'or'"""
        choices = choices.split(" or ")
        if len(choices) < 2:
            return await ctx.send("Give me at least 2 options to choose from! (separate options with `or`)")
        choice = random.choice(choices).strip()
        await ctx.send(f"I choose **{choice}**")

    @commands.group(invoke_without_command=True)
    async def stan(self, ctx):
        """Get a random kpop artist to stan.

        Use >stan update to update the database.
        """
        artist_list = db.get_from_data_json(['artists'])
        if artist_list:
            await ctx.send(f"stan **{random.choice(artist_list)}**")
        else:
            await ctx.send(f":warning: Artist list is empty :thinking: Update it with `>stan update`")

    @stan.command()
    async def update(self, ctx):
        """Update the artist database"""
        artist_list_old = db.get_from_data_json(['artists'])
        artist_list_new = set()
        urls_to_scrape = [
            'https://kprofiles.com/k-pop-girl-groups/',
            'https://kprofiles.com/k-pop-boy-groups/',
            'https://kprofiles.com/co-ed-groups-profiles/',
            'https://kprofiles.com/kpop-duets-profiles/',
            'https://kprofiles.com/kpop-solo-singers/'
        ]

        async def scrape(session, url):
            artists = []
            async with session.get(url) as response:
                soup = BeautifulSoup(await response.text(), 'html.parser')
                content = soup.find("div", {'class': 'entry-content herald-entry-content'})
                outer = content.find_all('p')
                for p in outer:
                    for artist in p.find_all('a'):
                        artist = artist.text.replace("Profile", "").replace("profile", "").strip()
                        if not artist == "":
                            artists.append(artist)
            return artists
        
        tasks = []
        async with aiohttp.ClientSession() as session:
            for url in urls_to_scrape:
                tasks.append(scrape(session, url))
        
            artist_list_new = set(sum(await asyncio.gather(*tasks), []))

        db.save_into_data_json(['artists'], list(artist_list_new))
        await ctx.send(
            f"**Artist list updated**\n"
            f"New entries: **{len(artist_list_new) - len(artist_list_old)}**\n"
            f"Total: **{len(artist_list_new)}**"
        )

    @commands.command()
    async def ship(self, ctx, *, names):
        """Ship two people, separate names with 'and'"""
        nameslist = names.split(' and ')
        if not len(nameslist) == 2:
            nameslist = names.split(" ", 1)
            if len(nameslist) < 1:
                return await ctx.send("Please give two names separated with `and`")

        url = "https://www.calculator.net/love-calculator.html"
        params = {
            'cnameone': nameslist[0],
            'cnametwo': nameslist[1],
            'x': 0,
            'y': 0
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as session:
                soup = BeautifulSoup(await response.text(), 'html.parser')

        percentage = int(soup.find("font", {'color': 'green'}).find('b').text.strip('%'))
        text = soup.find("div", {'id': 'content'}).find_all('p')[2].text

        if percentage < 26:
            emoji = ":broken_heart:"
        elif percentage > 74:
            emoji = ":sparkling_heart:"
        else:
            emoji = ":hearts:"

        content = discord.Embed(
            title=f"{nameslist[0]} {emoji} {nameslist[1]} - {percentage}%",
            colour=discord.Colour.magenta()
        )
        content.description = text
        await ctx.send(embed=content)

    @commands.command(aliases=['mc'])
    @commands.guild_only()
    async def minecraft(self, ctx, address=None, port=None):
        """Get the status of a minecraft server."""
        if address == "set":
            if port is None:
                return await ctx.send(
                    f"Save minecraft server address for this discord server:\n"
                    f"`{ctx.prefix}minecraft set <address>` (port defaults to 25565)\n"
                    f"`{ctx.prefix}minecraft set <address>:<port>`"
                )

            address = port.split(":")[0]
            try:
                port = int(port.split(":")[1])
            except IndexError:
                port = 25565

            db.execute("""REPLACE INTO minecraft VALUES (?, ?, ?)""", (ctx.guild.id, address, port))
            return await ctx.send(f"Minecraft server of this discord set to `{address}:{port}`")

        if address is None:
            serverdata = db.query("""SELECT address, port FROM minecraft WHERE guild_id = ?""", (ctx.guild.id,))
            if serverdata is None:
                return await ctx.send("No minecraft server saved for this discord server!")
            else:
                address, port = serverdata[0]

        server = await self.bot.loop.run_in_executor(
            None, lambda: minestat.MineStat(address, int(port or '25565'))
        )
        content = discord.Embed()
        content.colour = discord.Color.green()
        if server.online:
            content.add_field(name="Server Address", value=f"`{server.address}`")
            content.add_field(name="Version", value=server.version)
            content.add_field(name="Players", value=f"{server.current_players}/{server.max_players}")
            content.add_field(name="Latency", value=f"{server.latency}ms")
            content.set_footer(text=f"Message of the day: {server.motd}")
        else:
            content.description = ":warning: **Server is offline**"
        content.set_thumbnail(
            url="https://vignette.wikia.nocookie.net/potcoplayers/images/c/c2/"
                "Minecraft-icon-file-gzpvzfll.png/revision/latest?cb=20140813205910"
        )
        await ctx.send(embed=content)

    @commands.command()
    async def clap(self, ctx, *words):
        """Add a clap emoji between words."""
        await ctx.send(' 👏 '.join(words) + ' 👏')

    @commands.group(aliases=['hs'])
    async def horoscope(self, ctx):
        """Get your daily horoscope."""
        if ctx.invoked_subcommand is not None:
            return

        sign = db.userdata(ctx.author.id).sunsign
        if sign is None:
            return await ctx.send(
                "Please save your sunsign using `>horoscope set <sign>`\n"
                "use `>horoscope list` if you don't know which one you are."
            )

        params = {
            'sign': sign,
            'day': 'today'
        }
        async with aiohttp.ClientSession() as session:
            async with session.post('https://aztro.sameerkumar.website/', params=params) as response:
                data = await response.json()

        content = discord.Embed(color=hs_colors[sign])
        content.title = f"{sign.capitalize()} - {data['current_date']}"
        content.description = data['description']

        content.add_field(name='Mood', value=data['mood'], inline=True)
        content.add_field(name='Compatibility', value=data['compatibility'], inline=True)
        content.add_field(name='Color', value=data['color'], inline=True)
        content.add_field(name='Lucky number', value=data['lucky_number'], inline=True)
        content.add_field(name='Lucky time', value=data['lucky_time'], inline=True)
        content.add_field(name='Date range', value=data['date_range'], inline=True)

        await ctx.send(embed=content)

    @horoscope.command()
    async def set(self, ctx, sign):
        """Set your sunsign"""
        hs = [
            'aries',
            'taurus',
            'gemini', 
            'cancer',
            'leo',
            'virgo',
            'libra',
            'scorpio',
            'sagittarius',
            'capricorn',
            'aquarius',
            'pisces'
        ]
        sign = sign.lower()
        if sign not in hs:
            return await ctx.send(f"`{sign}` is not a valid sunsign! Use `>horoscope list` for a list of sunsigns.")

        db.update_user(ctx.author.id, "sunsign", sign)
        await ctx.send(f"Sunsign saved as `{sign}`")

    @horoscope.command()
    async def list(self, ctx):
        """Get list of all sunsigns"""
        sign_list = [
            "`(Mar 21-Apr 19)` **Aries**",
            "`(Apr 20-May 20)` **Taurus**",
            "`(May 21-Jun 20)` **Gemini**",
            "`(Jun 21-Jul 22)` **Cancer**",
            "`(Jul 23-Aug 22)` **Leo**",
            "`(Aug 23-Sep 22)` **Virgo**",
            "`(Sep 23-Oct 22)` **Libra**",
            "`(Oct 23-Nov 21)` **Scorpio**",
            "`(Nov 22-Dec 21)` **Sagittarius**",
            "`(Dec 22-Jan 19)` **Capricorn**",
            "`(Jan 20-Feb 18)` **Aquarius**",
            "`(Feb 19-Mar 20)` **Pisces**"
        ]
        content = discord.Embed(color=discord.Color.gold())
        content.title = f"Sunsign list"
        content.description = '\n'.join(sign_list)
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
        image = await self.bot.loop.run_in_executor(
            None, lambda: image_search(data.stage_name + ' ' + (data.group or ''))
        )
        content = discord.Embed(color=discord.Color.blurple())
        content.set_image(url=image)
        content.title = (f'{data.group} ' if data.group is not None else '') + data.stage_name
        content.description = f"**Full name:** {data.full_name}\n" \
                              f"**Korean name:** {data.k_stage_name} ({data.korean_name})\n" \
                              f"**Birthday:** {data.date_of_birth}\n" \
                              f"**Country:** {data.country}\n" \
                              + (f'**Birthplace:** {data.birthplace}' if data.birthplace is not None else '')
        
        await ctx.send(embed=content)

    @commands.command(name="emoji")
    async def big_emoji(self, ctx, emoji):
        """
        Get source image and stats of emoji

        Will display additional info if Miso is in the server where the emoji is located in.
        Displaying who added the emoji requires [manage_emojis] permission!
        
        Usage:
            >emoji :emoji:
        """
        emoji = await util.get_emoji(ctx, emoji)
        if emoji is None:
            return await ctx.send(":warning: I don't know this emoji!")
        
        color_hex = await util.color_from_image_url(str(emoji.url) + '?size=32')
        content = discord.Embed(
            title=f"`:{emoji.name}:`",
            color=await util.get_color(ctx, color_hex)
        )
        content.set_image(url=emoji.url)
        stats = await util.image_info_from_url(emoji.url)
        content.set_footer(text=f"Type: {stats['filetype']}")

        content.description = ""
        if isinstance(emoji, discord.Emoji):
            # is full emoji
            fuller_emoji = await emoji.guild.fetch_emoji(emoji.id)
            if fuller_emoji is not None and fuller_emoji.user is not None:     
                content.description += f"Added by {fuller_emoji.user.mention}"
            else:
                content.description += f"Added"
            
            content.description += f" on `{arrow.get(emoji.created_at).format('D/M/YYYY')}`\nLocated in `{emoji.guild}`"

        else:
            # is partial emoji
            pass

        content.set_footer(text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}")
        await ctx.send(embed=content)


def setup(bot):
    bot.add_cog(Miscellaneous(bot))


def image_search(query):
    gis = GoogleImagesSearch(GCS_DEVELOPER_KEY, '016720228003584159752:xwo6ysur40a')
    _search_params = {
        'q': query,
        'safe': 'off',
    }

    try:
        gis.search(search_params=_search_params)
        img = gis.results()[0].url
        return img
    except Exception as e:
        return ''
