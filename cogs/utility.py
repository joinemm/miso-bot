import discord
from discord.ext import commands
import data.database as db
import requests
import json
import os
import urllib.request
import html
import arrow
from helpers import utilityfunctions as util


GOOGLE_API_KEY = os.environ.get('GOOGLE_KEY')
DARKSKY_API_KEY = os.environ.get('DARK_SKY_KEY')
TIMEZONE_API_KEY = os.environ.get('TIMEZONEDB_API_KEY')
OXFORD_APPID = os.environ.get('OXFORD_APPID')
OXFORD_TOKEN = os.environ.get('OXFORD_TOKEN')
NAVER_APPID = os.environ.get('NAVER_APPID')
NAVER_TOKEN = os.environ.get('NAVER_TOKEN')
WOLFRAM_APPID = os.environ.get('WOLFRAM_APPID')


papago_pairs = ['ko/en', 'ko/ja', 'ko/zh-cn', 'ko/zh-tw', 'ko/vi', 'ko/id', 'ko/de', 'ko/ru', 'ko/es', 'ko/it',
                'ko/fr', 'en/ja', 'ja/zh-cn', 'ja/zh-tw', 'zh-cn/zh-tw', 'en/ko', 'ja/ko', 'zh-cn/ko', 'zh-tw/ko',
                'vi/ko', 'id/ko', 'th/ko', 'de/ko', 'ru/ko', 'es/ko', 'it/ko', 'fr/ko', 'ja/en', 'zh-cn/ja',
                'zh-tw/ja', 'zh-tw/zh-tw']


class Utility(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command()
    async def weather(self, ctx, *, address):
        """Get weather of a location"""
        if len(address) == 0:
            return await ctx.send(f"```{self.client.command_prefix}weather <location>\n"
                                  f"{self.client.command_prefix}weather save <location>\n\n"
                                  f"Get weather of a location```")

        address = address.replace(" ", "+")
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_API_KEY}"
        response = requests.get(url=url)
        response.raise_for_status()
        json_data = json.loads(response.content.decode('utf-8'))
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
        response = requests.get(url=f"https://api.darksky.net/forecast/{DARKSKY_API_KEY}/{lat},{lon}?units=si")
        response.raise_for_status()

        json_data = json.loads(response.content.decode('utf-8'))
        current = json_data['currently']
        hourly = json_data['hourly']
        daily = json_data['daily']
        time = get_timezone({'lat': lat, 'lon': lon})

        content = discord.Embed(color=discord.Color.dark_purple())
        content.set_thumbnail(url=f"http://flagpedia.net/data/flags/w580/{country}.png")
        content.set_author(name=formatted_name, icon_url=ctx.author.avatar_url)
        content.add_field(name=hourly['summary'],
                          value=f"**{current['temperature']} °C** "
                          f"({current['temperature'] * (9.0 / 5.0) + 32:.2f} °F) **|** Feels like "
                          f"**{current['apparentTemperature']} °C** "
                          f"({current['apparentTemperature'] * (9.0 / 5.0) + 32:.2f} °F)\n"
                          f"Wind speed: **{current['windSpeed']} m/s**")

        content.add_field(name="Weekly forecast:",
                          value=" ".join(f"**{x}**" if "°C" in x else x for x in daily['summary'].split(" ")))

        content.set_footer(text=f"Local time: {time}")
        await ctx.send(embed=content)

    @commands.command()
    async def define(self, ctx, *, word):
        """Search from oxford dictionary"""
        api_url = 'https://od-api.oxforddictionaries.com/api/v2/'
        response = requests.get(api_url + "lemmas/en/" + word, headers={
            'Accept': 'application/json',
            'app_id': OXFORD_APPID,
            'app_key': OXFORD_TOKEN,
        })
        if response.status_code == 200:
            data = json.loads(response.content.decode('utf-8'))
            await ctx.send(f"```{data}```")
            # searched for word id, now use the word id to get definition
            if data['results']:
                definitions_embed = discord.Embed(colour=discord.Colour.blue())
                definitions_embed.description = ""

                found_word = data['results'][0]['id']
                response = requests.get(api_url + f"entries/en-gb/{found_word}?strictMatch=false", headers={
                    'Accept': 'application/json',
                    'app_id': OXFORD_APPID,
                    'app_key': OXFORD_TOKEN,
                })
                data = json.loads(response.content.decode('utf-8'))
                all_entries = []
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
                                    for subdefinition in entry['entries'][0]['senses'][i]['subsenses'][y]['definitions']:
                                        this_definition = f"\n**└{i + 1}.{y + 1}.** {subdefinition}"
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
        else:
            data = json.loads(response.content.decode('utf-8'))
            await ctx.send(f"```ERROR: {data['error']}```")

    @commands.command()
    async def urban(self, ctx, *, word):
        """Search from urban dictionary"""
        url = "https://api.urbandictionary.com/v0/define?term="
        response = requests.get(url + word)
        if response.status_code == 200:
            data = json.loads(response.content.decode('utf-8'))
            pages = []
            if data['list']:
                for entry in data['list']:
                    definition = entry['definition'].replace("]", "**").replace("[", "**")
                    example = entry['example'].replace("]", "**").replace("[", "**")
                    time = entry['written_on']
                    content = discord.Embed(colour=discord.Colour.orange())
                    content.description = f"{definition}"

                    if not example == "":
                        content.add_field(name="Example", value=example)
                    content.set_footer(text=f"by {entry['author']} • "
                                            f"{entry.get('thumbs_up')} 👍 {entry.get('thumbs_down')} 👎")
                    content.timestamp = arrow.get(time).datetime
                    content.set_author(name=word.capitalize(), icon_url="https://i.imgur.com/yMwpnBe.png",
                                       url=entry.get('permalink'))
                    pages.append(content)
                await util.page_switcher(ctx, pages)
            else:
                await ctx.send(f"No definitions found for `{word}`")
        else:
            await ctx.send(f"ERROR `{response.status_code}`")

    @commands.command(aliases=['tr', 'trans'])
    async def translate(self, ctx, *, text):
        """Naver/Google translator"""
        languages = text.partition(" ")[0]
        if "/" in languages:
            source, target = languages.split("/")
            text = text.partition(" ")[1]
            if source == "":
                source = detect_language(text)
            if target == "":
                target = "en"
        else:
            source = detect_language(text)
            target = "en"
        language_pair = f"{source}/{target}"
        print(language_pair)
        # we have language and query, now choose the appropriate translator

        if language_pair in papago_pairs:
            # use papago
            query = f"source={source}&target={target}&text={text}"
            api_url = 'https://openapi.naver.com/v1/papago/n2mt'
            request = urllib.request.Request(api_url)
            request.add_header('X-Naver-Client-Id', NAVER_APPID)
            request.add_header('X-Naver-Client-Secret', NAVER_TOKEN)
            response = urllib.request.urlopen(request, data=query.encode('utf-8'))
            data = json.loads(response.read().decode('utf-8'))
            translation = data['message']['result']['translatedText']

        else:
            # use google
            url = f"https://translation.googleapis.com/language/translate/v2?key={GOOGLE_API_KEY}" \
                f"&model=nmt&target={target}&source={source}&q={text}"
            response = requests.get(url)
            data = json.loads(response.content.decode('utf-8'))
            try:
                translation = html.unescape(data['data']['translations'][0]['translatedText'])
            except KeyError:
                return await ctx.send("Sorry, I could not translate this :(")

        await ctx.send(f"`{source}->{target}` " + translation)

    @commands.command(aliases=['q', 'question'])
    async def wolfram(self, ctx, *, query):
        """Ask something from wolfram alpha"""
        url = f"http://api.wolframalpha.com/v1/result?appid={WOLFRAM_APPID}&i={query}&output=json"
        response = requests.get(url.replace("+", "%2B"))
        if response.status_code == 200:
            result = f"**{response.content.decode('utf-8')}**"
        else:
            result = "Sorry, I don't have an answer to that :("

        await ctx.send(result)


def setup(client):
    client.add_cog(Utility(client))


def get_timezone(coord):
    url = f"http://api.timezonedb.com/v2.1/get-time-zone?key={TIMEZONE_API_KEY}&format=json&by=position&" \
          f"lat={coord['lat']}&lng={coord['lon']}"
    response = requests.get(url)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        time = json_data['formatted'].split(" ")
        return ":".join(time[1].split(":")[:2])
    else:
        return f"[error_{response.status_code}]"


def detect_language(string):
    url = f"https://translation.googleapis.com/language/translate/v2/detect?key={GOOGLE_API_KEY}" \
          f"&q={string}"
    response = requests.get(url)
    response.raise_for_status()
    data = json.loads(response.content.decode('utf-8'))
    return data['data']['detections'][0][0]['language']
