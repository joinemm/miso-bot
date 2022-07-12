import random

import arrow
import discord
import orjson
from discord.ext import commands

from libraries import emoji_literals, minestat
from modules import exceptions, util
from modules.misobot import MisoBot


class Miscellaneous(commands.Cog):
    """Miscellaneous commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🔮"
        self.hs = {
            "aquarius": {
                "name": "Aquarius",
                "emoji": ":aquarius:",
                "date_range": "Jan 20 - Feb 18",
            },
            "pisces": {
                "name": "Pisces",
                "emoji": ":pisces:",
                "date_range": "Feb 19 - Mar 20",
            },
            "aries": {
                "name": "Aries",
                "emoji": ":aries:",
                "date_range": "Mar 21 - Apr 19",
            },
            "taurus": {
                "name": "Taurus",
                "emoji": ":taurus:",
                "date_range": "Apr 20 - May 20",
            },
            "gemini": {
                "name": "Gemini",
                "emoji": ":gemini:",
                "date_range": "May 21 - Jun 20",
            },
            "cancer": {
                "name": "Cancer",
                "emoji": ":cancer:",
                "date_range": "Jun 21 - Jul 22",
            },
            "leo": {
                "name": "Leo",
                "emoji": ":leo:",
                "date_range": "Jul 23 - Aug 22",
            },
            "virgo": {
                "name": "Virgo",
                "emoji": ":virgo:",
                "date_range": "Aug 23 - Sep 22",
            },
            "libra": {
                "name": "Libra",
                "emoji": ":libra:",
                "date_range": "Sep 23 - Oct 22",
            },
            "scorpio": {
                "name": "Scorpio",
                "emoji": ":scorpius:",
                "date_range": "Oct 23 - Nov 21",
            },
            "sagittarius": {
                "name": "Sagittarius",
                "emoji": ":sagittarius:",
                "date_range": "Nov 22 - Dec 21",
            },
            "capricorn": {
                "name": "Capricorn",
                "emoji": ":capricorn:",
                "date_range": "Dec 22 - Jan 19",
            },
        }

    @commands.command(aliases=["random"], usage="<n>-[m]")
    async def rng(self, ctx: commands.Context, *, number_range):
        """Random number generator

        Usage:
            >rng <n>
            >rng <n-m>
        """
        try:
            values = [int(x) for x in number_range.split("-")]
        except ValueError:
            return await ctx.send(":warning: Please give a valid number range to choose from")
        if len(values) == 2:
            start, end = values
        else:
            start = 0
            end = values[0]
        choice = random.randint(start, end)
        await ctx.send(f"Random range `{start}-{end}`\n> **{choice}**")

    @commands.command()
    async def advice(self, ctx: commands.Context):
        """Get some life advice"""
        # for some reason the api is missing content for these ids
        missing_ids = {0, 22, 48, 67}
        slip_id = 0
        while slip_id in missing_ids:
            slip_id = random.randint(1, 224)
        url = f"https://api.adviceslip.com/advice/{slip_id}"
        async with self.bot.session.get(url) as response:
            data = orjson.loads(await response.text())
        try:
            await ctx.send(f"*{data['slip']['advice']}*")
        except KeyError:
            raise exceptions.CommandError(f"slip_id={slip_id} :: {data}")

    @commands.command()
    async def affirmation(self, ctx: commands.Context):
        """Get some affirmation"""
        async with self.bot.session.get("https://www.affirmations.dev") as response:
            data = await response.json(loads=orjson.loads)
        await ctx.send(f"*{data['affirmation']}*")

    @commands.command(aliases=["imbored"])
    async def iambored(self, ctx: commands.Context):
        """Get something to do"""
        async with self.bot.session.get("http://www.boredapi.com/api/activity/") as response:
            data = await response.json(loads=orjson.loads)

        # https://www.boredapi.com/documentation
        activity_emoji = {
            "education": ":books:",
            "recreational": ":carousel_horse:",
            "social": ":champagne_glass:",
            "diy": ":tools:",
            "charity": ":juggling:",
            "cooking": ":cook:",
            "relaxation": ":beach:",
            "music": ":saxophone:",
            "busywork": ":broom:",
        }
        await ctx.send(f"{activity_emoji.get(data['type'], '')} {data['activity']}")

    @commands.command(name="ascii")
    async def ascii_text(self, ctx: commands.Context, *, text):
        """Turn text into fancy ascii art"""
        font = "small"
        async with self.bot.session.get(
            f"https://artii.herokuapp.com/make?text={text}&font={font}"
        ) as response:
            content = await response.text()

        await ctx.send(f"```\n{content}\n```")

    @commands.command(aliases=["8ball"])
    async def eightball(self, ctx: commands.Context, *, question):
        """Ask a yes/no question"""
        choices = [
            # yes
            "Yes, definitely",
            "Yes",
            "Yass",
            "Most likely yes",
            "I think so, yes",
            "Absolutely!",
            # indecisive
            "Maybe",
            "Perhaps",
            "Possibly",
            # no
            "I don't think so",
            "No",
            "Most likely not",
            "Absolutely not!",
            "In your dreams",
            "Naur",
        ]
        answer = random.choice(choices)
        question = question + ("?" if not question.endswith("?") else "")
        await ctx.send(f"> {question}\n**{answer}**")

    @commands.command()
    async def choose(self, ctx: commands.Context, *, choices):
        """Choose from given options.

        Usage:
            >choose <thing_1> or <thing_2> or ... or <thing_n>
        """
        choices = choices.split(" or ")
        if len(choices) < 2:
            return await ctx.send(
                "Give me at least 2 options to choose from! (separate options with `or`)"
            )
        choice = random.choice(choices).strip()
        await ctx.send(f"I choose **{choice}**")

    @commands.command()
    async def ship(self, ctx: commands.Context, *, names):
        """Ship two names and get your chance for succesful love.

        Usage:
            >ship <name> and <name>
        """
        nameslist = names.split(" and ")
        if not len(nameslist) == 2:
            nameslist = names.split(" ", 1)
            if len(nameslist) < 2:
                return await ctx.send("Please give two names separated with `and`")

        lovenums = [0, 0, 0, 0, 0]
        for c in names:
            c = c.lower()
            if c == "l":
                lovenums[0] += 1
            elif c == "o":
                lovenums[1] += 1
            elif c == "v":
                lovenums[2] += 1
            elif c == "e":
                lovenums[3] += 1
            elif c == "s":
                lovenums[4] += 1

        while max(lovenums) > 9:
            newnums = []
            for n in lovenums:
                if n > 9:
                    newnums.append(n // 10)
                    newnums.append(n % 10)
                else:
                    newnums.append(n)
            lovenums = newnums

        it = 0
        maxit = 100  # Maximum iterations allowed in below algorithm to attempt convergence
        maxlen = 100  # Maximum length of generated list allowed (some cases grow list infinitely)
        while len(lovenums) > 2 and it < maxit and len(lovenums) < maxlen:
            newnums = []
            it += 1
            for i in range(0, len(lovenums) - 1):
                pairsum = lovenums[i] + lovenums[i + 1]
                if pairsum < 10:
                    newnums.append(pairsum)
                else:
                    newnums.append(1)
                    newnums.append(pairsum % 10)
            lovenums = newnums

        # This if-else matches with original site alg handling of non-convergent result. (i.e. defaulting to 1%)
        # Technically, you can leave this section as it was previously and still get a non-trivial outputtable result since the length is always at least 2.
        if len(lovenums) == 2:
            percentage = lovenums[0] * 10 + lovenums[1]
        else:
            percentage = 1  # Same default that original site algorithm used

        if percentage < 25:
            emoji = ":broken_heart:"
            text = "Dr. Love thinks a relationship might work out between {} and {}, but the chance is very small. A successful relationship is possible, but you both have to work on it. Do not sit back and think that it will all work out fine, because it might not be working out the way you wanted it to. Spend as much time with each other as possible. Again, the chance of this relationship working out is very small, so even when you do work hard on it, it still might not work out.".format(
                nameslist[0], nameslist[1]
            )
        elif percentage < 50:
            emoji = ":heart:"
            text = "The chance of a relationship working out between {} and {} is not very big, but a relationship is very well possible, if the two of you really want it to, and are prepared to make some sacrifices for it. You'll have to spend a lot of quality time together. You must be aware of the fact that this relationship might not work out at all, no matter how much time you invest in it.".format(
                nameslist[0], nameslist[1]
            )
        elif percentage < 75:
            emoji = ":heart:"
            text = "Dr. Love thinks that a relationship between {} and {} has a reasonable chance of working out, but on the other hand, it might not. Your relationship may suffer good and bad times. If things might not be working out as you would like them to, do not hesitate to talk about it with the person involved. Spend time together, talk with each other.".format(
                nameslist[0], nameslist[1]
            )
        else:
            emoji = ":sparkling_heart:"
            text = "Dr. Love thinks that a relationship between {} and {} has a very good chance of being successful, but this doesn't mean that you don't have to work on the relationship. Remember that every relationship needs spending time together, talking with each other etc.".format(
                nameslist[0], nameslist[1]
            )

        content = discord.Embed(
            title=f"{nameslist[0]} {emoji} {nameslist[1]} - {percentage}%",
            colour=discord.Colour.magenta(),
        )
        content.description = text
        await ctx.send(embed=content)

    @commands.command(aliases=["mc"])
    @commands.guild_only()
    async def minecraft(self, ctx: commands.Context, address=None, port=None):
        """Get the status of a minecraft server"""
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

            await self.bot.db.execute(
                """
                INSERT INTO minecraft_server (guild_id, server_address, port)
                    VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    server_address = VALUES(server_address),
                    port = VALUES(port)
                """,
                ctx.guild.id,
                address,
                port,
            )
            return await util.send_success(
                ctx,
                f"Default Minecraft server of this discord saved as `{address}:{port}`",
            )

        if address is None:
            data = await self.bot.db.execute(
                "SELECT server_address, port FROM minecraft_server WHERE guild_id = %s",
                ctx.guild.id,
                one_row=True,
            )
            if not data:
                raise exceptions.CommandInfo(
                    "No default Minecraft server saved for this discord server!"
                    f"Use `{ctx.prefix}minecraft set` to save one or"
                    f"`{ctx.prefix}minecraft <address> <port>` to see any server"
                )

            address, port = data

        if port is None:
            port = 25565

        server = await self.bot.loop.run_in_executor(
            None, lambda: minestat.MineStat(address, int(port))
        )
        content = discord.Embed(color=discord.Color.green())
        if server.online:
            content.add_field(name="Server Address", value=f"`{server.address}`")
            content.add_field(name="Version", value=server.version)
            content.add_field(
                name="Players", value=f"{server.current_players}/{server.max_players}"
            )
            content.add_field(name="Latency", value=f"{server.latency}ms")
            content.set_footer(text=f"Message of the day: {server.motd}")
        else:
            content.title = f"{address}:{port}"
            content.description = ":warning: **Server is offline**"
        content.set_thumbnail(url="https://i.imgur.com/P1IxD0Q.png")
        await ctx.send(embed=content)

    @commands.command()
    async def clap(self, ctx: commands.Context, *sentence):
        """Add a clap emoji between words"""
        await ctx.send(" 👏 ".join(sentence) + " 👏")

    @commands.group(aliases=["hs"])
    async def horoscope(self, ctx: commands.Context):
        """Get your daily horoscope"""
        if ctx.invoked_subcommand is None:
            await self.send_hs(ctx, "today")

    @horoscope.command(name="tomorrow")
    async def horoscope_tomorrow(self, ctx: commands.Context):
        """Get tomorrow's horoscope"""
        await self.send_hs(ctx, "tomorrow")

    @horoscope.command(name="yesterday")
    async def horoscope_yesterday(self, ctx: commands.Context):
        """Get yesterday's horoscope"""
        await self.send_hs(ctx, "yesterday")

    async def send_hs(self, ctx: commands.Context, day):
        sunsign = await self.bot.db.execute(
            "SELECT sunsign FROM user_settings WHERE user_id = %s",
            ctx.author.id,
            one_value=True,
        )
        if not sunsign or sunsign is None:
            raise exceptions.CommandInfo(
                "Please save your zodiac sign using `>horoscope set <sign>`\n"
                "Use `>horoscope list` if you don't know which one you are."
            )
        params = {"sign": sunsign, "day": day}
        async with self.bot.session.post(
            "https://aztro.sameerkumar.website/", params=params
        ) as response:
            data = await response.json(loads=orjson.loads)

        sign = self.hs.get(sunsign)
        content = discord.Embed(
            color=int("9266cc", 16),
            title=f"{sign['emoji']} {sign['name']} - {data['current_date']}",
            description=data["description"],
        )

        content.add_field(name="Mood", value=data["mood"], inline=True)
        content.add_field(name="Compatibility", value=data["compatibility"], inline=True)
        content.add_field(name="Color", value=data["color"], inline=True)
        content.add_field(name="Lucky number", value=data["lucky_number"], inline=True)
        content.add_field(name="Lucky time", value=data["lucky_time"], inline=True)
        content.add_field(name="Date range", value=data["date_range"], inline=True)

        await ctx.send(embed=content)

    @horoscope.command(name="set")
    async def horoscope_set(self, ctx: commands.Context, sign):
        """Save your zodiac sign"""
        sign = sign.lower()
        if self.hs.get(sign) is None:
            raise exceptions.CommandInfo(
                f"`{sign}` is not a valid zodiac! Use `>horoscope list` for a list of zodiacs."
            )

        await ctx.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, sunsign)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                sunsign = VALUES(sunsign)
            """,
            ctx.author.id,
            sign,
        )
        await ctx.send(f"Zodiac saved as **{sign.capitalize()}** {self.hs.get(sign)['emoji']}")

    @horoscope.command(name="list")
    async def horoscope_list(self, ctx: commands.Context):
        """Get list of all zodiac signs"""
        content = discord.Embed(
            color=int("9266cc", 16),
            title=":crystal_ball: Zodiac signs",
            description="\n".join(
                f"{sign['emoji']} **{sign['name']}**: {sign['date_range']}"
                for sign in self.hs.values()
            ),
        )
        return await ctx.send(embed=content)

    @commands.command(aliases=["colour"], usage="<hex | @member | @role | 'random' | url> ...")
    async def color(self, ctx: commands.Context, *sources):
        """
        Visualise colors

        Different color sources can be chained together to create patterns.

        Usage:
            >color <hex>
            >color <@member>
            >color <@role>
            >color random [amount]
            >color <image url>
        """
        if not sources:
            return await util.send_command_help(ctx)

        colors = []
        i = 0
        while i < len(sources):
            source = sources[i]
            i += 1
            if source.lower() == "random":
                try:
                    amount = int(sources[i])
                    i += 1
                except (IndexError, ValueError):
                    amount = 1

                for _ in range(min(amount, 50)):
                    colors.append("{:06x}".format(random.randint(0, 0xFFFFFF)))
                continue

            role_or_user = await util.get_member(ctx, source) or await util.get_role(ctx, source)
            if role_or_user is not None:
                colors.append(str(role_or_user.color).strip("#"))
                continue

            if source.startswith("http") or source.startswith("https"):
                url_color = await util.color_from_image_url(self.bot.session, source)
                if url_color is not None:
                    colors.append(url_color)
                    continue

            color = await util.get_color(ctx, "#" + source.strip("#"))
            if color is not None:
                colors.append(str(color))
                continue

            await ctx.send(f"Error parsing `{source}`")

        if not colors:
            return await ctx.send("No valid colors to show")

        content = discord.Embed(colour=await util.get_color(ctx, "#" + colors[0].strip("#")))

        if len(colors) > 50:
            await ctx.send("Maximum amount of colors is 50, ignoring rest...")
            colors = colors[:50]

        colors = [x.strip("#") for x in colors]
        url = "https://api.color.pizza/v1/" + ",".join(colors)
        async with self.bot.session.get(url) as response:
            colordata = (await response.json(loads=orjson.loads)).get("colors")

        if len(colors) == 1:
            discord_color = await util.get_color(ctx, "#" + colors[0].strip("#"))
            hexvalue = colordata[0]["requestedHex"]
            rgbvalue = discord_color.to_rgb()
            name = colordata[0]["name"]
            luminance = colordata[0]["luminance"]
            image_url = f"http://www.colourlovers.com/img/{colors[0]}/200/200/color.png"
            content.title = name
            content.description = (
                f"**HEX:** `{hexvalue}`\n"
                f"**RGB:** {rgbvalue}\n"
                f"**Luminance:** {luminance:.4f}"
            )
        else:
            content.description = ""
            palette = ""
            for i, color in enumerate(colors):
                hexvalue = colordata[i]["requestedHex"]
                name = colordata[i]["name"]
                content.description += f"`{hexvalue}` **| {name}**\n"
                palette += color.strip("#") + "/"

            image_url = f"https://www.colourlovers.com/paletteImg/{palette}palette.png"

        content.set_image(url=image_url)
        await ctx.send(embed=content)

    @commands.command(name="emoji", aliases=["emote"])
    async def big_emoji(self, ctx: commands.Context, emoji):
        """
        Get source image and stats of an emoji

        Will display additional info if Miso is in the server where the emoji is located in.
        Displaying who added the emoji requires Miso to have manage emojis permission!

        Usage:
            >emoji :emoji:
        """
        if emoji[0] == "<":
            emoji = await util.get_emoji(ctx, emoji)
            if emoji is None:
                raise exceptions.CommandWarning("I don't know this emoji!")

            emoji_url = emoji.url
            emoji_name = emoji.name
        else:
            # unicode emoji
            emoji_name = emoji_literals.UNICODE_TO_NAME.get(emoji)
            if emoji_name is None:
                raise exceptions.CommandWarning("I don't know this emoji!")

            codepoint = "-".join(
                f"{ord(e):x}" for e in emoji_literals.NAME_TO_UNICODE.get(emoji_name)
            )
            emoji_name = emoji_name.strip(":")
            emoji_url = f"https://twemoji.maxcdn.com/v/13.0.1/72x72/{codepoint}.png"

        content = discord.Embed(title=f"`:{emoji_name}:`")
        content.set_image(url=emoji_url)
        stats = await util.image_info_from_url(self.bot.session, emoji_url)
        content.set_footer(text=f"Type: {stats['filetype']}")

        if isinstance(emoji, discord.Emoji):
            emoji = await emoji.guild.fetch_emoji(emoji.id)
            desc = [f"Uploaded {arrow.get(emoji.created_at).format('D/M/YYYY')}"]
            if emoji.user:
                desc.append(f"by **{emoji.user}**")
            if ctx.guild != emoji.guild:
                desc.append(f"in **{emoji.guild}**")

            content.description = "\n".join(desc)

        content.set_footer(
            text=f"{stats['filetype']} | {stats['filesize']} | {stats['dimensions']}"
        )
        await ctx.send(embed=content)

    @commands.command()
    async def emojify(self, ctx: commands.Context, *, text):
        """Emojify your message"""
        request_data = {"density": 100, "input": text, "shouldFilterEmojis": False}
        async with self.bot.session.post(
            "https://api.emojify.net/convert",
            json=request_data,
            headers={"Content-Type": "application/json"},
        ) as response:
            data = await response.json(loads=orjson.loads)
            result = data.get("result")

            try:
                await ctx.send(result)
            except discord.errors.HTTPException:
                raise exceptions.CommandWarning("Your text when emojified is too long to send!")


async def setup(bot):
    await bot.add_cog(Miscellaneous(bot))
