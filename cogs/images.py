import os

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from modules import util


class ImageObject:
    def __init__(self, filename):
        self.filename = filename
        self.image = Image.open(self.filename)
        self.draw = ImageDraw.Draw(self.image)
        self.font = "NanumGothic.ttf"

    def get_text_size(self, font_size, text):
        font = ImageFont.truetype(self.font, font_size)
        return font.getsize(text)

    def save(self, filename=None):
        self.image.save(filename or self.filename)

    def write_watermark(self, size, color):
        font = ImageFont.truetype(self.font, size)
        self.draw.text((5, 5), "Created with Miso Bot", font=font, fill=color)

    def write_box(self, x, y, width, height, color, text, angle=0):
        font_size = 300

        while True:
            lines = []
            line = []
            line_height = 0
            words = text.split(" ")
            for word in words:
                if "\n" in word:
                    newline_words = word.split("\n")
                    new_line = " ".join(line + [newline_words[0]])
                    size = self.get_text_size(font_size, new_line)
                    line_height = size[1]
                    if size[0] <= width:
                        line.append(newline_words[0])
                    else:
                        lines.append(line)
                        line = [newline_words[0]]
                    lines.append(line)
                    if len(word.split("\n")) > 2:
                        for i in range(1, len(word.split("\n")) - 1):
                            lines.append([newline_words[i]])
                    line = [newline_words[-1]]
                else:
                    new_line = " ".join(line + [word])
                    size = self.get_text_size(font_size, new_line)
                    line_height = size[1]
                    if size[0] <= width:
                        line.append(word)
                    else:
                        lines.append(line)
                        line = [word]

                # check after every word to exit prematurely
                size = self.get_text_size(font_size, " ".join(line))
                text_height = len(lines) * line_height
                if text_height > height or size[0] > width:
                    break

            # add leftover line to total
            if line:
                lines.append(line)

            text_height = len(lines) * line_height
            if text_height <= height and size[0] <= width:
                break

            font_size -= 1

        lines = [" ".join(line) for line in lines]
        font = ImageFont.truetype(self.font, font_size)

        if angle != 0:
            txt = Image.new("RGBA", (self.image.size))
            txtd = ImageDraw.Draw(txt)
        else:
            txtd = self.draw
        height = y
        for i, line in enumerate(lines):
            total_size = self.get_text_size(font_size, line)
            x_left = int(x + ((width - total_size[0]) / 2))
            txtd.text((x_left, height), line, font=font, fill=color)
            height += line_height

        if angle != 0:
            txt = txt.rotate(angle, resample=Image.BILINEAR)
            self.image.paste(txt, mask=txt)


class Images(commands.Cog):
    """Make memes"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🖼️"

    @commands.group(case_insensitive=True, enabled=False)
    async def meme(self, ctx):
        """Input text into images."""
        await util.command_group_help(ctx)

    @meme.command()
    async def olivia(self, ctx, *, text):
        """Olivia hye has something to say."""
        filename = "images/hye.jpg"
        await self.image_sender(ctx, filename, (206, 480, 530, 400), text, angle=2)

    @meme.command()
    async def yyxy(self, ctx, *, text):
        """YYXY has something to say."""
        filename = "images/yyxy.png"
        await self.image_sender(ctx, filename, (500, 92, 315, 467), text, angle=1)

    @meme.command()
    async def haseul(self, ctx, *, text):
        """Haseul has something to say."""
        filename = "images/haseul.jpg"
        await self.image_sender(
            ctx,
            filename,
            (212, 395, 275, 279),
            text,
            wm_size=20,
            wm_color=(50, 50, 50, 100),
            angle=4,
        )

    @meme.command()
    async def trump(self, ctx, *, text):
        """Donald Trump has signed a new order."""
        filename = "images/trump.jpg"
        await self.image_sender(
            ctx, filename, (761, 579, 406, 600), text, wm_color=(255, 255, 255, 255)
        )

    @meme.command()
    async def jihyo(self, ctx, *, text):
        """Jihyo has something to say."""
        filename = "images/jihyo.jpg"
        await self.image_sender(
            ctx,
            filename,
            (272, 441, 518, 353),
            text,
            wm_color=(255, 255, 255, 255),
            angle=-7,
        )

    @meme.command()
    async def dubu(self, ctx, *, text):
        """Dahyun has something to say."""
        filename = "images/dubu.jpg"
        await self.image_sender(
            ctx,
            filename,
            (287, 454, 512, 347),
            text,
            wm_color=(255, 255, 255, 255),
            angle=-3,
        )

    @meme.command(aliases=["chae"])
    async def chaeyoung(self, ctx, *, text):
        """Chae has something to say."""
        filename = "images/chae.jpg"
        await self.image_sender(
            ctx,
            filename,
            (109, 466, 467, 320),
            text,
            wm_color=(255, 255, 255, 255),
            angle=3,
        )

    @meme.command()
    async def nayeon(self, ctx, *, text):
        """Nayeon has something to say."""
        filename = "images/nayeon.jpg"
        await self.image_sender(
            ctx,
            filename,
            (247, 457, 531, 353),
            text,
            wm_color=(255, 255, 255, 255),
            angle=5,
        )

    async def image_sender(
        self,
        ctx,
        filename,
        boxdimensions,
        text,
        color=(40, 40, 40),
        wm_size=30,
        wm_color=(150, 150, 150, 100),
        angle=0,
    ):
        image = ImageObject(filename)

        await self.bot.loop.run_in_executor(
            None, lambda: image.write_box(*boxdimensions, color, text, angle=angle)
        )
        await self.bot.loop.run_in_executor(None, lambda: image.write_watermark(wm_size, wm_color))

        save_location = f"downloads/{ctx.message.id}_output_{filename.split('/')[-1]}"
        image.save(save_location)
        with open(save_location, "rb") as img:
            await ctx.send(file=discord.File(img))

        os.remove(save_location)


def setup(bot):
    bot.add_cog(Images(bot))
