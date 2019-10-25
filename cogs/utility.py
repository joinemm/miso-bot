import discord
from discord.ext import commands
import data.database as db
import requests
import json
import os
import urllib.request
import urllib
import html
import arrow
import asyncio
from helpers import utilityfunctions as util
import helpers.log as log
from time import time
from bs4 import BeautifulSoup


GOOGLE_API_KEY = os.environ.get('GOOGLE_KEY')
DARKSKY_API_KEY = os.environ.get('DARK_SKY_KEY')
TIMEZONE_API_KEY = os.environ.get('TIMEZONEDB_API_KEY')
OXFORD_APPID = os.environ.get('OXFORD_APPID')
OXFORD_TOKEN = os.environ.get('OXFORD_TOKEN')
NAVER_APPID = os.environ.get('NAVER_APPID')
NAVER_TOKEN = os.environ.get('NAVER_TOKEN')
WOLFRAM_APPID = os.environ.get('WOLFRAM_APPID')
GFYCAT_CLIENT_ID = os.environ.get('GFYCAT_CLIENT_ID')
GFYCAT_SECRET = os.environ.get('GFYCAT_SECRET')
STREAMABLE_USER = os.environ.get('STREAMABLE_USER')
STREAMABLE_PASSWORD = os.environ.get('STREAMABLE_PASSWORD')
BORING_TOKEN = os.environ.get('BORING_TOKEN')


papago_pairs = [
    'ko/en', 'ko/ja', 'ko/zh-cn', 'ko/zh-tw', 'ko/vi', 'ko/id', 'ko/de', 'ko/ru', 'ko/es', 'ko/it',
    'ko/fr', 'en/ja', 'ja/zh-cn', 'ja/zh-tw', 'zh-cn/zh-tw', 'en/ko', 'ja/ko', 'zh-cn/ko', 'zh-tw/ko',
    'vi/ko', 'id/ko', 'th/ko', 'de/ko', 'ru/ko', 'es/ko', 'it/ko', 'fr/ko', 'ja/en', 'zh-cn/ja',
    'zh-tw/ja', 'zh-tw/zh-tw'
]

weather_icons = {
    'clear-day': ':sunny:',
    'clear-night': ':night_with_stars:',
    'fog': ':foggy:',
    'hail': ':cloud_snow:',
    'sleet': ':cloud_snow:',
    'snow': ':cloud_snow:',
    'partly-cloudy-day': ':partly_sunny:',
    'cloudy': ':cloud:',
    'partly-cloudy-night': ':cloud:',
    'tornado': ':cloud_tornado:',
    'wind': ':wind_blowing_face:'
}

logger = log.get_logger(__name__)


class Utility(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command()
    async def weather(self, ctx, *address):
        """
        Get weather of a location

        Usage:
            >weather
            >weather <location>
            >weather save <location>
        """
        if len(address) == 0:
            userdata = db.userdata(ctx.author.id)
            location = userdata.location if userdata is not None else None
            if location is None:
                return await util.send_command_help(ctx)

        elif address[0] == "save":
            db.update_user(ctx.author.id, "location", " ".join(address[1:]))
            return await ctx.send(f"Saved your location as `{' '.join(address[1:])}`")

        else:
            location = " ".join(address)
            
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {'address': location, 'key': GOOGLE_API_KEY}
        response = requests.get(url, params=params)
        response.raise_for_status()
        json_data = response.json()
        try:
            json_data = json_data['results'][0]
        except IndexError:
            return await ctx.send("Could not get that location.")

        formatted_name = json_data['formatted_address']
        lat = json_data['geometry']['location']['lat']
        lon = json_data['geometry']['location']['lng']
        country = "N/A"
        for comp in json_data['address_components']:
            if 'country' in comp['types']:
                country = comp['short_name'].lower()

        # we have lat and lon now, plug them into dark sky
        response = requests.get(f"https://api.darksky.net/forecast/{DARKSKY_API_KEY}/{lat},{lon}?units=si")
        response.raise_for_status()

        json_data = json.loads(response.content.decode('utf-8'))
        current = json_data['currently']
        hourly = json_data['hourly']
        daily = json_data['daily']
        localtime = get_timezone({'lat': lat, 'lon': lon})

        content = discord.Embed(color=await util.get_color(ctx, '#e1e8ed'))
        #content.set_thumbnail(url=f"http://flagpedia.net/data/flags/w580/{country}.png")
        content.title = f":flag_{country}: {formatted_name}"
        content.add_field(
            name=f"{weather_icons.get(current['icon'], '')} {hourly['summary']}",
            value=f":thermometer: Currently **{current['temperature']} °C** "
            f"( {current['temperature'] * (9.0 / 5.0) + 32:.2f} °F )\n"
            f":neutral_face: Feels like **{current['apparentTemperature']} °C** "
            f"( {current['apparentTemperature'] * (9.0 / 5.0) + 32:.2f} °F )\n"
            f":dash: Wind speed **{current['windSpeed']} m/s** with gusts of **{current['windGust']} m/s**\n"
            f":sweat_drops: Humidity **{int(current['humidity'] * 100)}%**\n"
            f":map: [See on map](https://www.google.com/maps/search/?api=1&query={lat},{lon})"
        )

        content.set_footer(text=f"🕐 Local time {localtime}")
        await ctx.send(embed=content)

    @commands.command()
    async def define(self, ctx, *, word):
        """Search from oxford dictionary"""
        api_url = 'https://od-api.oxforddictionaries.com/api/v2/'
        
        headers = {
            'Accept': 'application/json',
            'app_id': OXFORD_APPID,
            'app_key': OXFORD_TOKEN,
        }

        response = requests.get(api_url + "lemmas/en/" + word, headers=headers)
        data = response.json()
       
        # searched for word id, now use the word id to get definition
        all_entries = []
        
        if data.get('results'):
            definitions_embed = discord.Embed(colour=discord.Colour.blue())
            definitions_embed.description = ""

            found_word = data['results'][0]['id']
            response = requests.get(api_url + "entries/en-gb/" + found_word, 
                                    params={'strictMatch': False}, headers=headers)
            data = json.loads(response.content.decode('utf-8'))
            for entry in data['results'][0]['lexicalEntries']:
                definitions_value = ""
                name = data['results'][0]['word']

                for i in range(len(entry['entries'][0]['senses'])):
                    for definition in entry['entries'][0]['senses'][i].get('definitions', []):
                        this_top_level_definition = f"\n**{i + 1}.** {definition}"
                        if len(definitions_value + this_top_level_definition) > 1024:
                            break
                        definitions_value += this_top_level_definition
                        try:
                            for y in range(len(entry['entries'][0]['senses'][i]['subsenses'])):
                                for subdef in entry['entries'][0]['senses'][i]['subsenses'][y]['definitions']:
                                    this_definition = f"\n**└ {i + 1}.{y + 1}.** {subdef}"
                                    if len(definitions_value + this_definition) > 1024:
                                        break
                                    definitions_value += this_definition

                            definitions_value += "\n"
                        except KeyError:
                            pass

                    for reference in entry['entries'][0]['senses'][i].get('crossReferenceMarkers', []):
                        definitions_value += reference

                word_type = entry['lexicalCategory']['text']
                this_entry = {"id": name, "definitions": definitions_value, "type": word_type}
                all_entries.append(this_entry)

            if not all_entries:
                return await ctx.send(f"No definitions found for `{word}`")

            definitions_embed.set_author(name=all_entries[0]['id'], icon_url="https://i.imgur.com/vDvSmF3.png")

            for entry in all_entries:
                definitions_embed.add_field(name=f"{entry['type']}", inline=False,
                                            value=entry["definitions"])

            await ctx.send(embed=definitions_embed)
        else:
            await ctx.send(f"```ERROR: {data['error']}```")
            
    @commands.command()
    async def urban(self, ctx, *, word):
        """Search from urban dictionary"""
        url = "https://api.urbandictionary.com/v0/define"
        response = requests.get(url, params={'term': word})
        if response.status_code == 200:
            data = response.json()
            pages = []

            if data['list']:
                for entry in data['list']:
                    definition = entry['definition'].replace("]", "**").replace("[", "**")
                    example = entry['example'].replace("]", "**").replace("[", "**")
                    timestamp = entry['written_on']
                    content = discord.Embed(colour=discord.Colour.orange())
                    content.description = f"{definition}"

                    if not example == "":
                        content.add_field(name="Example", value=example)

                    content.set_footer(text=f"by {entry['author']} • "
                                            f"{entry.get('thumbs_up')} 👍 {entry.get('thumbs_down')} 👎")
                    content.timestamp = arrow.get(timestamp).datetime
                    content.set_author(name=entry['word'], icon_url="https://i.imgur.com/yMwpnBe.png",
                                       url=entry.get('permalink'))
                    pages.append(content)

                await util.page_switcher(ctx, pages)

            else:
                await ctx.send(f"No definitions found for `{word}`")
        else:
            await ctx.send(f"ERROR `{response.status_code}`")

    @commands.command(aliases=['tr', 'trans'], rest_is_raw=True)
    async def translate(self, ctx, *, text):
        """Naver/Google translator"""
        text = text.strip(' ')
        languages = text.partition(" ")[0]
        if "/" in languages:
            source, target = languages.split("/")
            text = text.partition(" ")[2]
            if source == "":
                source = detect_language(text)
            if target == "":
                target = "en"
        else:
            source = detect_language(text)
            if source == "en":
                target = "ko"
            else:
                target = "en"
        language_pair = f"{source}/{target}"

        if text.strip() == '':
            return await ctx.send("Give me something to translate!")
        elif len(text) > 1000:
            return await ctx.send("Sorry, the maximum length is 1000 characters!")

        # we have language and query, now choose the appropriate translator

        if language_pair in papago_pairs:
            # use papago
            params = {'source': source, 'target': target, 'text': text}
            url = "https://openapi.naver.com/v1/papago/n2mt"
            headers = {'X-Naver-Client-Id': NAVER_APPID,
                       'X-Naver-Client-Secret': NAVER_TOKEN}

            response = requests.post(headers=headers, url=url, data=params)
            response.raise_for_status()
            translation = response.json()['message']['result']['translatedText']

        else:
            # use google
            url = "https://translation.googleapis.com/language/translate/v2"
            params = {
                'key': GOOGLE_API_KEY, 
                'model': 'nmt', 
                'target': target, 
                'source': source, 
                'q': text
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            try:
                translation = html.unescape(data['data']['translations'][0]['translatedText'])
            except KeyError:
                return await ctx.send("Sorry, I could not translate this :(")
       
        await ctx.send(f"`{source}->{target}` {translation}")

    @commands.command(aliases=['q', 'question'])
    async def wolfram(self, ctx, *, query):
        """Ask something from wolfram alpha"""
        url = "http://api.wolframalpha.com/v1/result"
        params = {
            'appid': WOLFRAM_APPID, 
            'i': query, 
            'output': 'json', 
            'units': 'metric'
        }

        response = requests.get(url, params=params)

        if response.status_code == 200:
            result = f":mag_right: {response.content.decode('utf-8')}"
        else:
            result = ":shrug:"

        await ctx.send(result)

    @commands.command()
    async def creategif(self, ctx, media_url):
        """Create a gfycat from video url"""
        starttimer = time()
        auth_headers = gfycat_oauth()
        response = requests.post(
            url="https://api.gfycat.com/v1/gfycats", 
            json={
                "fetchUrl": media_url.strip("`")
            },
            headers=auth_headers
        )

        response.raise_for_status()
        data = response.json()

        try:
            gfyname = data['gfyname']
        except KeyError:
            logger.error(data)
            return await ctx.send("Cannot create gif from this link!")

        message = await ctx.send("Encoding")

        i = 1
        while True:
            response = requests.get(f"https://api.gfycat.com/v1/gfycats/fetch/status/{gfyname}",
                                    headers=auth_headers).json()
            task = response['task']
            if task == 'encoding':
                await message.edit(content="Encoding" + '.' * (i % 4))

            elif task == 'complete':
                await message.edit(content=f"Gif created in **{util.stringfromtime(time() - starttimer, 2)}**\n"
                                           f"https://gfycat.com/{response['gfyname']}")
                break

            else:
                logger.error(response)
                await message.edit(content="There was an error creating your gif :(")
                break

            await asyncio.sleep(1 + int(i/8))
            i += 1

    @commands.command()
    async def streamable(self, ctx, media_url):
        """Create a streamable from video url"""
        starttimer = time()
        
        url = "https://api.streamable.com/import"
        
        params = {
            'url': media_url.strip('`')
        }

        response = requests.get(
            url=url, 
            params=params, 
            auth=(STREAMABLE_USER, STREAMABLE_PASSWORD)
        )

        if response.status_code != 200:
            try:
                data = response.json()
                messages = []
                for category in data['messages']:
                    for msg in data['messages'][category]:
                        messages.append(msg)
                messages = ' | '.join(messages)
                errormsg = f"ERROR {response.status_code}: {messages}"
            except (json.JSONDecodeError, KeyError):
                errormsg = response.content.decode('utf-8')

            logger.error(errormsg)
            return await ctx.send(f"```{errormsg.split(';')[0]}```")

        data = response.json()
        link = 'https://streamable.com/' + data.get('shortcode')

        message = await ctx.send("Processing Video")

        i = 1
        while True:
            status = requests.get(link)
            soup = BeautifulSoup(status.text, 'html.parser')
            meta = soup.find('meta', {'property': 'og:url'})            

            if meta:
                timestring = util.stringfromtime(time() - starttimer, 2)
                await message.edit(content=f"Streamable created in **{timestring}**\n{meta.get('content')}")
                break

            error = soup.find('h1').text + '.' * (i % 4)
            await message.edit(content=error)
            await asyncio.sleep(1 + int(i/8))
            i += 1

    @commands.command()
    async def host(self, ctx, image_url=None):
        """Upload an image to host on boring.host"""
        if image_url is None:
            if ctx.message.attachments:
                image_url = ctx.message.attachments[0].url
            else:
                await ctx.send("Give image url or attachment to upload!")

        data = boring_host(image_url)
        await ctx.send(f"{data.get('url') or data.get('status')}")


def boring_host(image_url):
    """Upload image to boring.host"""

    path = f'downloads/{os.path.basename(image_url)}'
    with open(path, 'wb') as f:
        resource = requests.get(image_url, stream=True)
        for block in resource.iter_content(1024):
            if not block:
                break

            f.write(block)

    with open(path, 'rb') as f:
        response = requests.post('https://api.boring.host/api/v1/upload',
                                 data={'api_token': BORING_TOKEN, 'file': f})

        os.remove(path)
        print(response.content)
        response.raise_for_status()
        data = response.json()
        print(data)
        response_dict = {
            'status': data.get('status'),
            'url': data['data'].get('direct_url')
        }

        return response_dict


def setup(client):
    client.add_cog(Utility(client))


def get_timezone(coord, clocktype='12hour'):
    url = "http://api.timezonedb.com/v2.1/get-time-zone"
    
    params = {
        'key': TIMEZONE_API_KEY, 
        'format': 'json', 
        'by': 'position', 
        'lat': coord['lat'], 
        'lng': coord['lon']
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        timestring = response.json().get('formatted').split(" ")
        hours, minutes = [int(x) for x in timestring[1].split(":")[:2]]
        if clocktype == '24hour':
            return f"{hours}:{minutes:02d}"
        elif clocktype == '12hour':
            if hours > 12:
                suffix = 'PM'
                hours -= 12
            else:
                suffix = 'AM'
                if hours == 0:
                    hours = 12
            return f"{hours}:{minutes:02d} {suffix}"
        else:
            return 'Invalid clocktype'
    else:
        return f"HTTP ERROR {response.status_code}"


def detect_language(string):
    url = "https://translation.googleapis.com/language/translate/v2/detect"
    
    params = {
        'key': GOOGLE_API_KEY, 
        'q': string[:1000]    
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data['data']['detections'][0][0]['language']


def gfycat_oauth():
    url = "https://api.gfycat.com/v1/oauth/token"

    params = {
        "grant_type": "client_credentials",
        "client_id": GFYCAT_CLIENT_ID,
        "client_secret": GFYCAT_SECRET
    }

    token = requests.post(url, json=params, timeout=3).json()
    access_token = token["access_token"]

    auth_headers = {
        "Authorization": f"Bearer {access_token}"
    }

    return auth_headers
