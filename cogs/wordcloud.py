import discord
from discord.ext import commands
from wordcloud import WordCloud, STOPWORDS
import numpy as np
from PIL import Image
import helpers.utilityfunctions as util


class Wordcloud(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.mask = np.array(Image.open("html/cloud.png"))

    @commands.command()
    async def wordcloud(self, ctx, user, messages=1000):
        """Create a word cloud of messages in the channel used in"""
        if int(messages) > 10000:
            return await ctx.send("For performance reasons the amount of messages is limited to 10000 for now!")
        if user in ['all', 'channel']:
            user_limiter = None
        else:
            member = await util.get_member(ctx, user)
            user_limiter = member.id if member is not None else None

        all_words = []
        async for message in ctx.channel.history(limit=int(messages)):
            if message.author.bot:
                continue
            if user_limiter is None or message.author.id == user_limiter:
                all_words += message.content.split(" ")

        stopwords = set(STOPWORDS)

        # create wordcloud object
        wc = WordCloud(background_color="#36393F",
                       max_words=500,
                       mask=self.mask,
                       stopwords=stopwords)

        # generate wordcloud
        wc.generate(" ".join(all_words))

        # save wordcloud
        wc.to_file("downloads/wordcloud.png")

        with open("downloads/wordcloud.png", "rb") as img:
            await ctx.send(file=discord.File(img))


def setup(client):
    client.add_cog(Wordcloud(client))
