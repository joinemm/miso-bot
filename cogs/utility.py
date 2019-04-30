import discord
from discord.ext import commands
import data.database as db
import requests
from bs4 import BeautifulSoup
import json
import os
import urllib.request
import html

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
    async def weather(self, ctx, *args):
        """Get weather of a location"""
        await ctx.message.channel.trigger_typing()
        address = "+".join(args)
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_API_KEY}"
        response = requests.get(url=url)
        if response.status_code == 200:
            json_data = json.loads(response.content.decode('utf-8'))['results'][0]
            # print(json.dumps(json_data, indent=4))
            formatted_name = json_data['formatted_address']
            lat = json_data['geometry']['location']['lat']
            lon = json_data['geometry']['location']['lng']
            country = "N/A"
            for comp in json_data['address_components']:
                if 'country' in comp['types']:
                    country = comp['short_name'].lower()

            # we have lat and lon now, plug them into dark sky
            response = requests.get(url=f"https://api.darksky.net/forecast/{DARKSKY_API_KEY}/{lat},{lon}?units=si")
            if response.status_code == 200:
                json_data = json.loads(response.content.decode('utf-8'))
                # print(json.dumps(json_data, indent=4))
                current = json_data['currently']
                hourly = json_data['hourly']
                daily = json_data['daily']
                time = get_timezone({'lat': lat, 'lon': lon})

                message = discord.Embed(color=discord.Color.dark_purple())
                message.set_thumbnail(url=f"http://flagpedia.net/data/flags/w580/{country}.png")
                message.set_author(name=formatted_name, icon_url=ctx.author.avatar_url)
                message.add_field(name=hourly['summary'],
                                  value=f"**{current['temperature']} °C** "
                                  f"({current['temperature'] * (9.0 / 5.0) + 32:.2f} °F) **|** Feels like "
                                  f"**{current['apparentTemperature']} °C** "
                                  f"({current['apparentTemperature'] * (9.0 / 5.0) + 32:.2f} °F)\n"
                                  f"Wind speed: **{current['windSpeed']} m/s**")

                message.add_field(name="Weekly forecast:",
                                  value=" ".join(f"**{x}**" if "°C" in x else x for x in daily['summary'].split(" ")))

                message.set_footer(text=f"Local time: {time}")

                await ctx.send(embed=message)

    @commands.command()
    async def define(self, ctx, *args):
        """Search from oxford dictionary"""
        await ctx.message.channel.trigger_typing()
        search_string = ' '.join(args)
        api_url = 'https://od-api.oxforddictionaries.com:443/api/v1'
        query = f'''/search/en?q={search_string}&prefix=false'''
        response = requests.get(api_url + query, headers={
            'Accept': 'application/json',
            'app_id': OXFORD_APPID,
            'app_key': OXFORD_TOKEN,
        })
        if response.status_code == 200:
            data = json.loads(response.content.decode('utf-8'))
            # searched for word id, now use the word id to get definition
            if data['results']:
                word_id = data['results'][0]['id']
                word_string = data['results'][0]['word']
                response = requests.get(api_url + f"/entries/en/{word_id}", headers={
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
                        for definition in entry['entries'][0]['senses'][i]['definitions']:
                            definitions_value += f"\n**{i + 1}.** {definition}"
                        try:
                            for y in range(len(entry['entries'][0]['senses'][i]['subsenses'])):
                                for definition in entry['entries'][0]['senses'][i]['subsenses'][y]['definitions']:
                                    definitions_value += f"\n**└{i + 1}.{y + 1}.** {definition}"
                            definitions_value += "\n"
                        except KeyError:
                            pass

                    word_type = entry['lexicalCategory']
                    this_entry = {"id": name, "definitions": definitions_value, "type": word_type}
                    all_entries.append(this_entry)

                definitions_embed = discord.Embed(colour=discord.Colour.blue())
                definitions_embed.set_author(name=word_string.capitalize(), icon_url="https://i.imgur.com/vDvSmF3.png")

                for entry in all_entries:
                    definitions_embed.add_field(name=entry["type"], inline=False,
                                                value=entry["definitions"])

                await ctx.send(embed=definitions_embed)
            else:
                await ctx.send(f"ERROR: no definition found for `{search_string}`")
        else:
            await ctx.send(f"ERROR: status code `{response.status_code}`")

    @commands.command()
    async def urban(self, ctx, *args):
        """Search from urban dictionary"""
        await ctx.message.channel.trigger_typing()
        search_string = " ".join(args)
        url = "https://mashape-community-urban-dictionary.p.mashape.com/define?term="
        response = requests.get(url + search_string,
                                headers={"X-Mashape-Key": "w3TR0XTmB3mshcxWHQNKxiVWSuUtp1nqnlzjsnoZ6d0yZ1MJAT",
                                         "Accept": "text/plain"})
        if response.status_code == 200:
            message = discord.Embed(colour=discord.Colour.orange())
            message.set_author(name=search_string.capitalize(), icon_url="https://i.imgur.com/yMwpnBe.png")

            json_data = json.loads(response.content.decode('utf-8'))
            # print(json.dumps(json_data, indent=4))

            if json_data['list']:
                word = json_data['list'][0]
                definition = word['definition'].replace("]", "").replace("[", "")
                example = word['example'].replace("]", "").replace("[", "")
                time = word['written_on'][:9].replace("-", "/")
                message.description = f"{definition}"
                message.add_field(name="Example", value=example)
                message.set_footer(text=f"by {word['author']} on {time}")
                await ctx.send(embed=message)
            else:
                await ctx.send("No definition found for " + search_string)
        else:
            await ctx.send("Error: " + str(response.status_code))

    @commands.command(aliases=['tr', 'trans'])
    async def translate(self, ctx, *text):
        """Translator that uses naver papago when possible, using google translator otherwise"""
        await ctx.message.channel.trigger_typing()
        if text[0] == "help":
            await ctx.send('Format: `>translate source/target "text"`\n'
                           'Example: `>translate ko/en 안녕하세요`\n\n'
                           'Leave source empty to detect language automatically.\n'
                           'Example: `>translate /en こんにちは`\n\n'
                           'When no language codes given, defaults to detected -> english.\n'
                           'Example: `>translate ㅋㅋㅋ`')
            return
        if "/" in text[0]:
            source, target = text[0].split("/")
            text = text[1:]
            if source == "":
                source = detect_language(" ".join(text))
            if target == "":
                target = "en"
        else:
            source = detect_language(" ".join(text))
            target = "en"
        query_text = " ".join(text)
        language_pair = f"{source}/{target}"
        # we have language and query, now choose the appropriate translator

        if language_pair in papago_pairs:
            # use papago
            query = f"source={source}&target={target}&text={query_text}"
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
                f"&model=nmt&target={target}&source={source}&q={query_text}"
            response = requests.get(url)
            data = json.loads(response.content.decode('utf-8'))
            translation = html.unescape(data['data']['translations'][0]['translatedText'])

        await ctx.send(f"`{source}->{target}` " + translation)

    @commands.command()
    async def question(self, ctx, *, query):
        """Ask something from wolfram alpha"""
        url = f"http://api.wolframalpha.com/v1/result?appid={WOLFRAM_APPID}&i={query}&output=json"
        response = requests.get(url.replace("+", "%2B"))
        if response.status_code == 200:
            result = response.content.decode('utf-8')
        else:
            result = "Sorry I did not understand your question."

        await ctx.send(f"**{result}**")


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
        return f"<error{response.status_code}>"


def detect_language(string):
    url = f"https://translation.googleapis.com/language/translate/v2/detect?key={GOOGLE_API_KEY}" \
          f"&q={string}"
    response = requests.get(url)
    if response.status_code == 200:
        data = json.loads(response.content.decode('utf-8'))
        return data['data']['detections'][0][0]['language']
    else:
        return None
