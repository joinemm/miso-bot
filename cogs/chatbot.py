import discord
from discord.ext import commands
from lxml.html import fromstring
import requests
from itertools import cycle
import json
import re
import urllib.parse
import helpers.log as log
import helpers.utilityfunctions as util

logger = log.get_logger(__name__)

misomisc
class Chatbot(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.sessions = {}
        self.proxies = get_proxies()

    async def conversation(self, ctx, user, sentence):

        sentence = sentence.replace(str(self.client.user.mention), "Mitsuku")
        sentence = await commands.clean_content(use_nicknames=False, escape_markdown=True).convert(ctx, sentence)

        sentence = (sentence
                    .replace("miso", "mitsuku")
                    .replace("Miso", "Mitsuku")
                    .replace("@", "")
                    )

        sessionid = self.sessions.get(str(user.id), "")
        data = self.process_talk(user.id, sentence, sessionid)
        if data is None:
            return
        for response in data['responses']:
            buttons = re.findall(r'<button>(.*?)</button>', response)
            for button in buttons:
                url = re.findall(r'<url>(.*?)</url>', button)[0].replace(" ", "-")
                response = re.sub(r'<button>.*?</button>', url + "\n", response, 1)

            images = re.findall(r'<image>(.*?)</image>', response)
            if images:
                url = images[0]
                embed = discord.Embed()
                embed.set_image(url=url)
                response = re.sub(r'<image>.*?</image>[.|]', "", response)
            else:
                embed = None

            response = (response
                        .replace("Mitsuku", "Miso")
                        .replace("mitsuku", "miso")
                        ).strip()

            if embed:
                await ctx.send(response, embed=embed)
            else:
                await ctx.send(response)

            logger.info(f'[CHAT] {user} : "{sentence}"\nMiso : "{response}"')

        self.sessions[str(user.id)] = data['sessionid']

    @commands.command(is_hidden=True)
    @commands.is_owner()
    async def refreshproxies(self, ctx):
        self.proxies = get_proxies()
        await ctx.send(f"Done. **{len(self.proxies)}** IP proxies available")

    @commands.command()
    async def talk(self, ctx, *, sentence):
        """Use this command, or @mention miso to talk with her"""
        await self.conversation(ctx, ctx.author, sentence)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot and self.client.user in message.mentions:
            sentence = message.content

            if message.content.startswith(str(self.client.user.mention)):
                sentence = sentence.replace(str(self.client.user.mention), "").strip()

            elif message.content.startswith(f"<@!{self.client.user.id}>"):
                sentence = sentence.replace(f"<@!{self.client.user.id}>", "").strip()

            if len(sentence) > 0:
                ctx = await self.client.get_context(message)
                async with ctx.typing():
                    await self.conversation(ctx, message.author, sentence)

    def process_talk(self, user_id, sentence, sessionid):
        input_string = urllib.parse.quote(sentence, safe='')

        proxy_pool = cycle(self.proxies)
        proxy = next(proxy_pool)

        url = ("https://miapi.pandorabots.com/talk"
               "?botkey=n0M6dW2XZacnOgCWTp0FRYUuMjSfCkJGgobNpgPv9060_72eKnu3Yl-o1v2nFGtSXqfwJBG2Ros~"
               f"&input={input_string}"
               f"&client_name={user_id}"
               f"&sessionid={sessionid}"
               )

        headers = {"Host": "miapi.pandorabots.com",
                   "User-Agent": util.useragent(),
                   "Accept": "*/*",
                   "Accept-Language": "en,en-US;q=0.5",
                   "Accept-Encoding": "gzip, deflate, br",
                   "Origin": "https://www.pandorabots.com",
                   "DNT": "1",
                   "Connection": "keep-alive",
                   "Referer": "https://www.pandorabots.com/mitsuku/",
                   "Content-Length": "0"}
        while True:
            try:
                response = requests.post(url, headers=headers, proxies={"http": proxy, "https": proxy}, timeout=10)
                break
            except Exception:
                continue
        try:
            data = json.loads(response.content.decode('utf-8'))
            return data
        except Exception as e:
            print(e)
            print(user_id, "<", sentence, ">", sessionid)
            print(response.status_code, response.content)
            return None


def get_proxies():
    url = 'https://free-proxy-list.net/'
    response = requests.get(url)
    parser = fromstring(response.text)
    proxies = set()
    for i in parser.xpath('//tbody/tr')[:10]:
        if i.xpath('.//td[7][contains(text(),"yes")]'):
            proxy = ":".join([i.xpath('.//td[1]/text()')[0], i.xpath('.//td[2]/text()')[0]])
            proxies.add(proxy)
    return proxies


def setup(client):
    client.add_cog(Chatbot(client))
