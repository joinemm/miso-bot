from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
import discord


class ImageObject:

    def __init__(self, filename):
        self.filename = filename
        self.image = Image.open(self.filename)
        self.draw = ImageDraw.Draw(self.image)
        self.font = 'NanumGothic.ttf'

    def get_text_size(self, font_size, text):
        font = ImageFont.truetype(self.font, font_size)
        return font.getsize(text)

    def save(self, filename=None):
        self.image.save(filename or self.filename)

    def write_watermark(self):
        font = ImageFont.truetype(self.font, 30)
        self.draw.text((5, 5), "Created with Miso Bot", font=font, fill=(150, 150, 150, 100))

    def write_box(self, x, y, width, height, color, text):

        font_size = 300

        while True:
            lines = []
            line = []
            line_height = 0
            words = text.split(' ')
            for w, word in enumerate(words):
                if '\n' in word:
                    newline_words = word.split('\n')
                    new_line = ' '.join(line + [newline_words[0]])
                    size = self.get_text_size(font_size, new_line)
                    line_height = size[1]
                    if size[0] <= width:
                        line.append(newline_words[0])
                    else:
                        lines.append(line)
                        line = [newline_words[0]]
                    lines.append(line)
                    if len(word.split('\n')) > 2:
                        for i in range(1, len(word.split('\n')) - 1):
                            lines.append([newline_words[i]])
                    line = [newline_words[-1]]
                else:
                    new_line = ' '.join(line + [word])
                    size = self.get_text_size(font_size, new_line)
                    line_height = size[1]
                    if size[0] <= width:
                        line.append(word)
                    else:
                        lines.append(line)
                        line = [word]

                # check after every word to exit prematurely
                size = self.get_text_size(font_size, ' '.join(line))
                text_height = len(lines) * line_height
                if text_height > height or size[0] > width:
                    # print(f"Font_size {font_size} too big at {w+1}/{len(words)} words")
                    break

            # add leftover line to total
            if line:
                lines.append(line)

            text_height = len(lines) * line_height
            if text_height <= height and size[0] <= width:
                # print(f"Selected font_size {font_size}")
                break
            else:
                # print(f"Font_size {font_size} too big")
                font_size -= 1

        lines = [' '.join(line) for line in lines]
        font = ImageFont.truetype(self.font, font_size)
        # print(lines)

        height = y
        for i, line in enumerate(lines):
            total_size = self.get_text_size(font_size, line)
            x_left = int(x + ((width - total_size[0]) / 2))
            self.draw.text((x_left, height), line, font=font, fill=color)
            # print(f"Drawing line {i} : {line}")
            height += line_height

        self.write_watermark()


class Images(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command()
    async def olivia(self, ctx, *, text):
        """Olivia hye has something to say"""
        filename = "images/hye.jpg"
        color = (40, 40, 40)
        image = ImageObject(filename)
        image.write_box(206, 480, 530, 400, color, text)
        image.save("downloads/hye_out.jpg")
        with open("downloads/hye_out.jpg", "rb") as img:
            await ctx.send(file=discord.File(img))


def setup(client):
    client.add_cog(Images(client))
