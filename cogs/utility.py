# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import html
import json
import random
from time import time
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import arrow
import discord
import orjson
from discord.ext import commands, tasks
from loguru import logger

from modules import emojis, exceptions, queries, util
from modules.misobot import MisoBot
from modules.shazam import Shazam
from modules.ui import BaseButtonPaginator, Compliance, RowPaginator

papago_pairs = [
    "ko/en",
    "ko/ja",
    "ko/zh-cn",
    "ko/zh-tw",
    "ko/vi",
    "ko/id",
    "ko/de",
    "ko/ru",
    "ko/es",
    "ko/it",
    "ko/fr",
    "en/ja",
    "ja/zh-cn",
    "ja/zh-tw",
    "zh-cn/zh-tw",
    "en/ko",
    "ja/ko",
    "zh-cn/ko",
    "zh-tw/ko",
    "vi/ko",
    "id/ko",
    "th/ko",
    "de/ko",
    "ru/ko",
    "es/ko",
    "it/ko",
    "fr/ko",
    "ja/en",
    "zh-cn/ja",
    "zh-tw/ja",
    "zh-tw/zh-tw",
]


class GifOptions(util.KeywordArguments):
    def __init__(self, start: float | None = None, end: float | None = None):
        if start and end is None:
            end = float(start) + 60
        elif end and start is None:
            start = 0.0

        if end and start:
            self.cut = {"start": float(start), "duration": float(end) - float(start)}
        else:
            self.cut = None

    def json(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


class Utility(commands.Cog):
    """Utility commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🔧"
        self.reminder_list = []
        self.cache_needs_refreshing = True
        self.shazam_client = Shazam(bot)
        with open("data/weather.json") as f:
            self.weather_constants = json.load(f)

    async def cog_load(self):
        self.reminder_loop.start()

    async def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(seconds=5.0)
    async def reminder_loop(self):
        try:
            await self.check_reminders()
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")

    @reminder_loop.before_loop
    async def task_waiter(self):
        await self.bot.wait_until_ready()

    async def check_reminders(self):
        """Check all current reminders"""
        if self.cache_needs_refreshing:
            self.cache_needs_refreshing = False
            self.reminder_list = await self.bot.db.fetch(
                """
                SELECT user_id, guild_id, created_on, reminder_date, content, original_message_url
                FROM reminder
                """
            )

        if not self.reminder_list:
            return

        now_ts = arrow.utcnow().timestamp()
        for (
            user_id,
            guild_id,
            created_on,
            reminder_date,
            content,
            original_message_url,
        ) in self.reminder_list:
            reminder_ts = reminder_date.timestamp()
            if reminder_ts > now_ts:
                continue

            user = self.bot.get_user(user_id)
            if user is not None:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    guild = "Unknown guild"

                date = arrow.get(created_on)
                if now_ts - reminder_ts > 21600:
                    logger.info(
                        f"Deleting reminder set for {date.format('DD/MM/YYYY HH:mm:ss')} for being over 6 hours late"
                    )
                else:
                    embed = discord.Embed(
                        color=int("d3a940", 16),
                        title=":alarm_clock: Reminder!",
                        description=content,
                    )
                    embed.add_field(
                        name="context",
                        value=f"[Jump to message]({original_message_url})",
                        inline=True,
                    )
                    embed.set_footer(text=f"{guild}")
                    embed.timestamp = created_on
                    try:
                        await user.send(embed=embed)
                        logger.info(f'Reminded {user} to "{content}"')
                    except discord.errors.Forbidden:
                        logger.warning(f"Unable to remind {user}, missing DM permissions!")
            else:
                logger.info(f"Deleted expired reminder by unknown user {user_id}")

            await self.bot.db.execute(
                """
                DELETE FROM reminder
                    WHERE user_id = %s AND guild_id = %s AND original_message_url = %s
                """,
                user_id,
                guild_id,
                original_message_url,
            )
            self.cache_needs_refreshing = True

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        """only for CommandNotFound"""
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound) and ctx.message.content.startswith(
            f"{ctx.prefix}!"
        ):
            # type ignores everywhere because this is so hacky
            ctx.timer = time()  # type: ignore
            ctx.iscallback = True  # type: ignore
            ctx.command = self.bot.get_command("!")
            if ctx.command:
                await ctx.command.callback(self, ctx)  # type: ignore

    async def resolve_bang(self, ctx: commands.Context, bang, args):
        params = {"q": f"!{bang} {args}", "format": "json", "no_redirect": 1}
        url = "https://api.duckduckgo.com"
        async with self.bot.session.get(url, params=params) as response:
            data = await response.json(content_type=None)
            location = data.get("Redirect")
            if location == "":
                return await ctx.send(":warning: Unknown bang or found nothing!")

            while True:
                async with self.bot.session.get(url, params=params) as deeper_response:
                    response = deeper_response
                    new_location = response.headers.get("location")
                    if not new_location:
                        break
                    location = new_location

        await ctx.send(location)

    @commands.command(name="!", usage="<bang> <query...>")
    async def bang(self, ctx: commands.Context):
        """
        DuckDuckGo bangs https://duckduckgo.com/bang

        Usage:
            >!<bang> <query...>

        Example:
            >!w horses
        """
        if not hasattr(ctx, "iscallback"):
            return await ctx.send_help(ctx.command)

        try:
            await ctx.typing()
        except discord.errors.Forbidden:
            pass

        logger.info(util.log_command_format(ctx))
        await queries.save_command_usage(ctx)
        try:
            bang, args = ctx.message.content[len(ctx.prefix or "") + 1 :].split(" ", 1)
            if len(bang) != 0:
                await self.resolve_bang(ctx, bang, args)
        except ValueError:
            await ctx.send("Please provide a query to search")

    @commands.command()
    async def shazam(self, ctx: commands.Context, url_or_attachment: Optional[str]):
        """Find song name from video or audio"""
        if url_or_attachment:
            result = await self.shazam_client.recognize_from_url(url_or_attachment)
        elif ctx.message.attachments:
            attachment = await ctx.message.attachments[0].to_file()
            result = await self.shazam_client.recognize_file(attachment.fp.read())
        elif (
            ctx.message.reference
            and ctx.message.reference.message_id
            and isinstance(ctx.channel, (discord.Thread, discord.TextChannel))
        ):
            reply_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if not reply_message.attachments:
                raise exceptions.CommandWarning("Referenced message has no attachments")
            attachment = await reply_message.attachments[0].to_file()
            result = await self.shazam_client.recognize_file(attachment.fp.read())
        else:
            return await util.send_command_help(ctx)

        if result is None:
            raise exceptions.CommandWarning("I was unable to recognize any music from this")

        metadata = "\n".join([f'`{m["title"]}:` {m["text"]}' for m in result.metadata])
        content = discord.Embed(
            description=f":notes: ***{result.song}*** by **{result.artist}**\n>>> {metadata}",
            color=int("1b64f7", 16),
        )
        content.set_author(
            name="Shazam result",
            url=result.url,
            icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/Shazam_icon.svg/84px-Shazam_icon.svg.png",
        )
        content.set_thumbnail(url=result.cover_art)
        await ctx.send(embed=content)

    @commands.command(usage="<'in' | 'on'> <time | YYYY/MM/DD [HH:mm:ss]> to <something>")
    async def remindme(self, ctx: commands.Context, pre, *, arguments):
        """
        Set a reminder

        Usage:
            >remindme in <some time> to <something>
            >remindme on <YYYY/MM/DD> [HH:mm:ss] to <something>
        """
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        try:
            reminder_time, content = arguments.split(" to ", 1)
        except ValueError:
            return await util.send_command_help(ctx)

        now = arrow.utcnow()

        if pre == "on":
            # user inputs date
            date = arrow.get(reminder_time)
            seconds = date.int_timestamp - now.int_timestamp

        elif pre == "in":
            # user inputs time delta
            seconds = util.timefromstring(reminder_time)
            date = now.shift(seconds=+seconds)

        else:
            return await ctx.send(
                f"Invalid operation `{pre}`\nUse `on` for date and `in` for time delta"
            )

        if seconds < 1:
            raise exceptions.CommandInfo(
                "You must give a valid time at least 1 second in the future!"
            )

        await self.bot.db.execute(
            """
            INSERT INTO reminder (user_id, guild_id, created_on, reminder_date, content, original_message_url)
                VALUES(%s, %s, %s, %s, %s, %s)
            """,
            ctx.author.id,
            ctx.guild.id,
            now.datetime,
            date.datetime,
            content,
            ctx.message.jump_url,
        )

        self.cache_needs_refreshing = True
        await ctx.send(
            embed=discord.Embed(
                color=int("ccd6dd", 16),
                description=(
                    f":pencil: I'll message you on **{date.to('utc').format('DD/MM/YYYY HH:mm:ss')}"
                    f" UTC** to remind you of:\n```{content}```"
                ),
            )
        )

    async def get_user_location(self, ctx: commands.Context):
        location = await self.bot.db.fetch_value(
            "SELECT location_string FROM user_settings WHERE user_id = %s",
            ctx.author.id,
        )
        if location is None:
            raise exceptions.CommandInfo(
                f"Please save your location using `{ctx.prefix}weather save <location...>`"
            )
        return location

    @commands.group()
    async def weather(self, ctx: commands.Context):
        """Show current weather in given location"""
        if ctx.invoked_subcommand is None:
            await util.command_group_help(ctx)

    @weather.command(name="now")
    async def weather_now(self, ctx: commands.Context, *, location: Optional[str] = None):
        location = await self.get_user_location(ctx)
        lat, lon, address = await self.geolocate(location)
        local_time, country_code = await self.get_country_information(lat, lon)

        params = {
            "apikey": self.bot.keychain.TOMORROWIO_TOKEN,
            "location": f"{lat},{lon}",
            "fields": ",".join(
                [
                    "precipitationProbability",
                    "precipitationType",
                    "windSpeed",
                    "windGust",
                    "windDirection",
                    "temperature",
                    "temperatureApparent",
                    "cloudCover",
                    "weatherCode",
                    "humidity",
                    "temperatureMin",
                    "temperatureMax",
                    "sunriseTime",
                    "sunsetTime",
                ]
            ),
            "units": "metric",
            "timesteps": ",".join(["current", "1d"]),
            "endTime": arrow.utcnow().shift(days=+1, minutes=+5).isoformat(),
        }

        if isinstance(local_time.tzinfo, ZoneInfo):
            params["timezone"] = str(local_time.tzinfo)
        else:
            logger.warning("Arrow object must be constructed with ZoneInfo timezone object")

        async with self.bot.session.get(
            "https://api.tomorrow.io/v4/timelines", params=params
        ) as response:
            if response.status != 200:
                logger.error(response.status)
                logger.error(response.headers)
                logger.error(await response.text())
                raise exceptions.CommandError(f"Weather api returned HTTP ERROR {response.status}")

            data = await response.json(loads=orjson.loads)

        current_data = next(filter(lambda t: t["timestep"] == "current", data["data"]["timelines"]))
        daily_data = next(filter(lambda t: t["timestep"] == "1d", data["data"]["timelines"]))
        values_current = current_data["intervals"][0]["values"]
        values_today = daily_data["intervals"][0]["values"]
        #  values_tomorrow = daily_data["intervals"][1]["values"]
        temperature = values_current["temperature"]
        temperature_apparent = values_current["temperatureApparent"]
        sunrise = arrow.get(values_current["sunriseTime"]).to(local_time.tzinfo).format("HH:mm")
        sunset = arrow.get(values_current["sunsetTime"]).to(local_time.tzinfo).format("HH:mm")

        icon = self.weather_constants["id_to_icon"][str(values_current["weatherCode"])]
        summary = self.weather_constants["id_to_description"][str(values_current["weatherCode"])]

        if values_today["precipitationType"] != 0 and values_today["precipitationProbability"] != 0:
            precipitation_type = self.weather_constants["precipitation"][
                str(values_today["precipitationType"])
            ]
            summary += (
                f", with {values_today['precipitationProbability']}% chance of {precipitation_type}"
            )

        content = discord.Embed(color=int("e1e8ed", 16))
        content.title = f":flag_{country_code.lower()}: {address}"
        content.set_footer(text=f"🕐 Local time {local_time.format('HH:mm')}")

        def render(F: bool):
            information_rows = [
                f":thermometer: Currently **{temp(temperature, F)}**, feels like **{temp(temperature_apparent, F)}**",
                f":calendar: Daily low **{temp(values_today['temperatureMin'], F)}**, high **{temp(values_today['temperatureMax'], F)}**",
                f":dash: Wind speed **{values_current['windSpeed']} m/s** with gusts of **{values_current['windGust']} m/s**",
                f":sunrise: Sunrise at **{sunrise}**, sunset at **{sunset}**",
                f":sweat_drops: Air humidity **{values_current['humidity']}%**",
                f":map: [See on map](https://www.google.com/maps/search/?api=1&query={lat},{lon})",
            ]

            content.clear_fields().add_field(
                name=f"{icon} {summary}",
                value="\n".join(information_rows),
            )

            return content

        await WeatherUnitToggler(render, False).run(ctx)

    @weather.command(name="forecast")
    async def weather_forecast(self, ctx: commands.Context, *, location: Optional[str] = None):
        location = await self.get_user_location(ctx)
        lat, lon, address = await self.geolocate(location)
        local_time, country_code = await self.get_country_information(lat, lon)
        body = {
            "location": f"{lat},{lon}",
            "fields": [  # ",".join(
                "precipitationProbability",
                "precipitationType",
                "windSpeed",
                "windGust",
                "windDirection",
                "temperature",
                "temperatureApparent",
                "cloudCover",
                "weatherCode",
                "humidity",
                "temperatureMin",
                "temperatureMax",
            ],  # ),
            "units": "metric",
            "timesteps": ["1d"],
            "startTime": "now",
            "endTime": "nowPlus5d",
        }

        if isinstance(local_time.tzinfo, ZoneInfo):
            body["timezone"] = str(local_time.tzinfo)
        else:
            logger.warning("Arrow object must be constructed with ZoneInfo timezone object")

        async with self.bot.session.post(
            "https://api.tomorrow.io/v4/timelines",
            json=body,
            params={
                "apikey": self.bot.keychain.TOMORROWIO_TOKEN,
            },
        ) as response:
            if response.status != 200:
                logger.error(response.status)
                logger.error(response.headers)
                logger.error(await response.text())
                raise exceptions.CommandError(f"Weather api returned HTTP ERROR {response.status}")
            data = await response.json(loads=orjson.loads)

        content = discord.Embed(
            title=f":flag_{country_code.lower()}: {address}",
            color=int("ffcc4d", 16),
        )

        def render(F: bool):
            days = []
            for day in data["data"]["timelines"][0]["intervals"]:
                date = arrow.get(day["startTime"]).format("**`ddd`** `D/M`")
                values = day["values"]
                minTemp = values["temperatureMin"]
                maxTemp = values["temperatureMax"]
                icon = self.weather_constants["id_to_icon"][str(values["weatherCode"])]
                description = self.weather_constants["id_to_description"][
                    str(values["weatherCode"])
                ]
                days.append(
                    f"{date} {icon} **{temp(maxTemp, F)}** / **{temp(minTemp, F)}** — {description}"
                )

            content.description = "\n".join(days)
            return content

        await WeatherUnitToggler(render, False).run(ctx)

    @weather.command(name="save")
    async def weather_save(self, ctx: commands.Context, *, location: str):
        await self.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, location_string)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                location_string = VALUES(location_string)
            """,
            ctx.author.id,
            location,
        )
        return await util.send_success(ctx, f"Saved your location as `{location}`")

    async def geolocate(self, location):
        GOOGLE_GEOCODING_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": location, "key": self.bot.keychain.GCS_DEVELOPER_KEY}
        async with self.bot.session.get(GOOGLE_GEOCODING_API_URL, params=params) as response:
            geocode_data = await response.json(loads=orjson.loads)
        try:
            geocode_data = geocode_data["results"][0]
        except IndexError:
            raise exceptions.CommandWarning("Could not find that location!")

        formatted_name = geocode_data["formatted_address"]
        lat = geocode_data["geometry"]["location"]["lat"]
        lon = geocode_data["geometry"]["location"]["lng"]

        return lat, lon, formatted_name

    async def get_country_information(self, lat, lon):
        TIMEZONE_API_URL = "http://api.timezonedb.com/v2.1/get-time-zone"
        params = {
            "key": self.bot.keychain.TIMEZONEDB_API_KEY,
            "format": "json",
            "by": "position",
            "lat": lat,
            "lng": lon,
        }
        async with self.bot.session.get(TIMEZONE_API_URL, params=params) as response:
            data = await response.json(loads=orjson.loads)
            country_code = data["countryCode"]
            try:
                local_time = arrow.now(ZoneInfo(data["zoneName"]))
            except ValueError:
                # does not have a time zone
                # most likely a special place such as antarctica
                # use UTC
                local_time = arrow.utcnow()
            return local_time, country_code

    @commands.command()
    async def define(self, ctx: commands.Context, *, word):
        """Get definitions for a given word"""
        API_BASE_URL = "wordsapiv1.p.rapidapi.com"
        COLORS = ["226699", "f4900c", "553788"]

        headers = {
            "X-RapidAPI-Key": self.bot.keychain.RAPIDAPI_KEY,
            "X-RapidAPI-Host": API_BASE_URL,
        }
        url = f"https://{API_BASE_URL}/words/{word}"
        async with self.bot.session.get(url, headers=headers) as response:
            data = await response.json(loads=orjson.loads)

        if data.get("results") is None:
            raise exceptions.CommandWarning(f"No definitions found for `{word}`")

        content = discord.Embed(
            title=f":books: {word.capitalize()}",
            color=int(random.choice(COLORS), 16),
        )

        if data.get("pronunciation") is not None:
            if isinstance(data["pronunciation"], str):
                content.description = f"`{data['pronunciation']}`"
            elif data["pronunciation"].get("all") is not None:
                content.description = f"`{data['pronunciation'].get('all')}`"
            else:
                content.description = "\n".join(
                    f"{wt}: `{pro}`" for wt, pro in data["pronunciation"].items()
                )

        results = {}
        for result in data["results"]:
            word_type = result["partOfSpeech"]
            try:
                results[word_type].append(result)
            except KeyError:
                results[word_type] = [result]

        for category, definitions in results.items():
            category_definitions = []
            for n, category_result in enumerate(definitions, start=1):
                parts = [f"**{n}.** {category_result['definition'].capitalize()}"]

                if category_result.get("examples") is not None:
                    parts.append(f'> *"{category_result.get("examples")[0]}"*')

                if category_result.get("synonyms") is not None:
                    quoted_synonyms = [f"`{x}`" for x in category_result["synonyms"]]
                    parts.append(f"> Similar: {' '.join(quoted_synonyms)}")

                category_definitions.append("\n".join(parts))

            content.add_field(
                name=category.upper(),
                value="\n".join(category_definitions)[:1024],
                inline=False,
            )

        await ctx.send(embed=content)

    @commands.command()
    async def urban(self, ctx: commands.Context, *, word):
        """Get Urban Dictionary entries for a given word"""
        API_BASE_URL = "https://api.urbandictionary.com/v0/define"
        async with self.bot.session.get(API_BASE_URL, params={"term": word}) as response:
            data = await response.json(loads=orjson.loads)

        if data["list"]:
            pages = []
            for entry in data["list"]:
                definition = entry["definition"].replace("]", "**").replace("[", "**")
                example = entry["example"].replace("]", "**").replace("[", "**")
                timestamp = entry["written_on"]
                content = discord.Embed(colour=discord.Colour.from_rgb(254, 78, 28))
                content.description = f"{definition}"

                if example != "":
                    content.add_field(name="Example", value=example)

                content.set_footer(
                    text=f"by {entry['author']} • "
                    f"{entry.get('thumbs_up')} 👍 {entry.get('thumbs_down')} 👎"
                )
                content.timestamp = arrow.get(timestamp).datetime
                content.set_author(
                    name=entry["word"],
                    icon_url="https://i.imgur.com/yMwpnBe.png",
                    url=entry.get("permalink"),
                )
                pages.append(content)

            await util.page_switcher(ctx, pages)

        else:
            await ctx.send(f"No definitions found for `{word}`")

    @commands.command(aliases=["tr", "trans"], usage="[source_lang]/[target_lang] <text>")
    async def translate(self, ctx: commands.Context, *, text):
        """
        Papago and Google translator

        You can specify language pairs or let them be automatically detected.
        Default target language is english.

        Usage:
            >translate <sentence>
            >translate xx/yy <sentence>
            >translate /yy <sentence>
            >translate xx/ <sentence>
        """
        if len(text) > 1000:
            raise exceptions.CommandWarning(
                "Sorry, the maximum length of text i can translate is 1000 characters!"
            )

        source = ""
        target = ""
        languages = text.partition(" ")[0]
        if "/" in languages or "->" in languages:
            source, target = languages.split("/") if "/" in languages else languages.split("->")
            text = text.partition(" ")[2]
            if source == "":
                source = await detect_language(self.bot, text)
            if target == "":
                target = "en"
        else:
            source = await detect_language(self.bot, text)
            target = "ko" if source == "en" else "en"
        language_pair = f"{source}/{target}"

        # we have language and query, now choose the appropriate translator

        if language_pair in papago_pairs:
            # use papago
            url = "https://openapi.naver.com/v1/papago/n2mt"
            params = {"source": source, "target": target, "text": text}
            headers = {
                "X-Naver-Client-Id": self.bot.keychain.NAVER_APPID,
                "X-Naver-Client-Secret": self.bot.keychain.NAVER_TOKEN,
            }

            async with self.bot.session.post(url, headers=headers, data=params) as response:
                translation = (await response.json(loads=orjson.loads))["message"]["result"][
                    "translatedText"
                ]

        else:
            # use google
            url = "https://translation.googleapis.com/language/translate/v2"
            params = {
                "key": self.bot.keychain.GCS_DEVELOPER_KEY,
                "model": "nmt",
                "target": target,
                "source": source,
                "q": text,
            }

            async with self.bot.session.get(url, params=params) as response:
                data = await response.json(loads=orjson.loads)

            try:
                translation = html.unescape(data["data"]["translations"][0]["translatedText"])
            except KeyError:
                return await ctx.send("Sorry, I could not translate this :(")

        await ctx.send(f"`{source}->{target}` {translation}")

    @commands.command(aliases=["wolf", "w"])
    async def wolfram(self, ctx: commands.Context, *, query):
        """Ask something from wolfram alpha"""
        url = "http://api.wolframalpha.com/v1/result"
        params = {
            "appid": self.bot.keychain.WOLFRAM_APPID,
            "i": query,
            "output": "json",
            "units": "metric",
        }

        async with self.bot.session.get(url, params=params) as response:
            if response.status == 200:
                content = await response.text()
                await ctx.send(f":mag_right: {content}")
            else:
                await ctx.send(":shrug:")

    @commands.command(enabled=False)
    async def mygifs(self, ctx: commands.Context):
        """See the gifs you have uploaded"""
        data = await self.bot.db.fetch(
            """
            SELECT gif_id, source_url, ts FROM user_uploaded_gif WHERE user_id = %s
            """,
            ctx.author.id,
        )
        if not data:
            raise exceptions.CommandWarning("You have not uploaded any gifs yet!")

        async with self.bot.session.get(
            "https://api.giphy.com/v1/gifs",
            params={
                "api_key": self.bot.keychain.GIPHY_API_KEY,
                "ids": ",".join(gif[0] for gif in data),
            },
        ) as response:
            response_data = await response.json()

        if not response_data["data"]:
            raise exceptions.CommandWarning("You don't have any gifs :(")

        gif_sources = {gif[0]: gif[1] for gif in data}

        rows = []
        for gif in response_data["data"]:
            source = gif_sources[gif["id"]]
            ts = arrow.get(gif["import_datetime"])
            rows.append(
                f"`{gif['id']}` [Source]({source}) | [Gif]({gif['url']}) <t:{int(ts.timestamp())}:R>"
            )

        await RowPaginator(
            discord.Embed(color=int("8b3cff", 16)).set_author(
                name="Your gifs", icon_url=ctx.author.display_avatar.url
            ),
            rows,
        ).run(ctx)

    @commands.command(enabled=False)
    async def creategif(self, ctx: commands.Context, media_url: str, *tags: str):
        """Create a gif and upload it to GIPHY"""
        has_seen_warning = await self.bot.db.fetch_value(
            """
            SELECT giphy_content_warning FROM popup_seen WHERE user_id = %s
            """,
            ctx.author.id,
        )
        if not has_seen_warning:
            view = Compliance(ctx.author)
            compliance_msg = await ctx.send(
                embed=discord.Embed(
                    color=int("5c68ee", 16),
                    title="IMPORTANT NOTICE",
                    description=(
                        "Uploading NSFW content on GIPHY is forbidden. "
                        "Failure to comply will get you banned from using Miso Bot. "
                        "Please also keep in mind everything you upload is public."
                    ),
                ).set_footer(text="ⓘ This notice is shown to everyone, not based on your content"),
                view=view,
            )
            await view.read_timer(3, compliance_msg)
            await view.wait()
            await compliance_msg.delete()

            if not view.agreed:
                return

            await self.bot.db.execute(
                """
                INSERT INTO popup_seen (user_id, giphy_content_warning)
                    VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    giphy_content_warning = VALUES(giphy_content_warning)
                """,
                ctx.author.id,
                True,
            )

        gif_already_created = await self.bot.db.fetch_value(
            """
            SELECT gif_id FROM user_uploaded_gif WHERE source_url = %s
            """,
            media_url,
        )
        if gif_already_created:
            gif_id = gif_already_created
            msg = None
        else:
            URL = "https://upload.giphy.com/v1/gifs"
            params = {
                "api_key": self.bot.keychain.GIPHY_API_KEY,
                "source_image_url": media_url,
                "tags": ["misobot"] + list(tags),
                "source_post_url": "https://misobot.xyz",
            }

            msg = await ctx.send(
                embed=discord.Embed(
                    description=f"{emojis.LOADING} **Creating your gif...**",
                    color=int("8a3cff", 16),
                ).set_footer(text="Powered by GIPHY")
            )

            async with self.bot.session.post(URL, json=params) as response:
                if response.status == 200:
                    data = await response.json(loads=orjson.loads)
                    gif_id = data["data"]["id"]
                else:
                    await msg.delete()
                    if response.status == 500:
                        raise exceptions.CommandWarning(
                            "Gif creation failed! Most likely the url provided is not a valid video source."
                        )
                    response.raise_for_status()
                    return

            await self.bot.db.execute(
                """
                INSERT INTO user_uploaded_gif
                    (user_id, guild_id, gif_id, source_url)
                    VALUES(%s, %s, %s, %s)
                """,
                ctx.author.id,
                ctx.guild.id if ctx.guild else None,
                gif_id,
                media_url,
            )

        async with self.bot.session.get(
            f"https://api.giphy.com/v1/gifs/{gif_id}",
            params={
                "api_key": self.bot.keychain.GIPHY_API_KEY,
            },
        ) as response:
            gif_data = await response.json(loads=orjson.loads)

            try:
                gif_url = gif_data["data"]["url"]
            except TypeError:
                error_message = gif_data["meta"]["msg"]
                raise exceptions.CommandError("GIPHY Error: " + error_message)

        if msg:
            await msg.edit(embed=None, content=gif_url)
        else:
            await ctx.send(gif_url)

    @commands.command()
    async def stock(self, ctx: commands.Context, *, symbol):
        """
        Get price data for the US stock market

        Example:
            >stock $TSLA
        """
        FINNHUB_API_QUOTE_URL = "https://finnhub.io/api/v1/quote"
        FINNHUB_API_PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"

        symbol = symbol.upper()
        params = {"symbol": symbol.strip("$"), "token": self.bot.keychain.FINNHUB_TOKEN}
        async with self.bot.session.get(FINNHUB_API_QUOTE_URL, params=params) as response:
            quote_data = await response.json(loads=orjson.loads)

        error = quote_data.get("error")
        if error:
            raise exceptions.CommandError(error)

        if quote_data["c"] == 0:
            raise exceptions.CommandWarning("Company not found")

        async with self.bot.session.get(FINNHUB_API_PROFILE_URL, params=params) as response:
            company_profile = await response.json(loads=orjson.loads)

        change = float(quote_data["c"]) - float(quote_data["pc"])
        GAINS = change > 0

        arrow_emoji = emojis.GREEN_UP if GAINS else emojis.RED_DOWN
        percentage = ((float(quote_data["c"]) / float(quote_data["pc"])) - 1) * 100
        market_cap = int(company_profile["marketCapitalization"])

        def get_money(key):
            return f"${quote_data[key]}"

        if company_profile.get("name") is not None:
            content = discord.Embed(
                title=f"${company_profile['ticker']} | {company_profile['name']}",
            )
            content.set_thumbnail(url=company_profile.get("logo"))
            content.set_footer(text=company_profile["exchange"])
        else:
            content = discord.Embed(title=f"${symbol}")

        content.add_field(
            name="Change",
            value=f"{'+' if GAINS else '-'}${abs(change):.2f}{arrow_emoji}\n({percentage:.2f}%)",
        )
        content.add_field(name="Open", value=get_money("o"))
        content.add_field(name="Previous close", value=get_money("pc"))
        content.add_field(name="Current price", value=get_money("c"))
        content.add_field(name="Today's high", value=get_money("h"))
        content.add_field(name="Today's low", value=get_money("l"))
        content.add_field(name="Market capitalization", value=f"${market_cap:,}", inline=False)

        content.colour = discord.Color.green() if GAINS else discord.Color.red()
        content.timestamp = arrow.get(quote_data["t"]).datetime

        await ctx.send(embed=content)

    @commands.group(aliases=["tz", "timezones"])
    async def timezone(self, ctx: commands.Context):
        """See the current time for your friends across the globe"""
        await util.command_group_help(ctx)

    @timezone.command(name="now")
    async def tz_now(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Get current time for a member"""
        if member is None:
            if isinstance(ctx.author, discord.Member):
                member = ctx.author
            else:
                raise exceptions.CommandWarning("Please give user to check")

        tz_str = await self.bot.db.fetch_value(
            "SELECT timezone FROM user_settings WHERE user_id = %s",
            member.id,
        )
        if not tz_str:
            raise exceptions.CommandWarning(f"{member} has not set their timezone yet!")
        dt = arrow.now(tz_str)
        await ctx.send(f":clock2: **{dt.format('MMM Do HH:mm')}**")

    @timezone.command(name="set")
    async def tz_set(self, ctx: commands.Context, your_timezone):
        """
        Set your timezone
        Give timezone as a tz database name (case sensitive):
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

        Example:
            >timezone set Europe/Helsinki
        """
        try:
            ts = arrow.now(your_timezone)
        except arrow.ParserError as e:
            raise exceptions.CommandWarning(str(e), help_footer=True)
        await ctx.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, timezone)
                VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                timezone = VALUES(timezone)
            """,
            ctx.author.id,
            your_timezone,
        )
        await util.send_success(
            ctx,
            f"Saved your timezone as **{your_timezone}**\n:clock2: Current time: **{ts.ctime()}**",
        )

    @timezone.command(name="unset")
    async def tz_unset(self, ctx: commands.Context):
        """Unset your timezone"""
        await ctx.bot.db.execute(
            """
            INSERT INTO user_settings (user_id, timezone)
                VALUES (%s, NULL)
            ON DUPLICATE KEY UPDATE
                timezone = VALUES(timezone)
            """,
            ctx.author.id,
        )
        await util.send_success(ctx, "Your timezone is no longer saved.")

    @timezone.command(name="list")
    async def tz_list(self, ctx: commands.Context):
        """List current time of all server members who have it saved"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

        content = discord.Embed(
            title=f":clock2: Current time in {ctx.guild}",
            color=int("3b88c3", 16),
        )
        rows = []
        user_ids = [user.id for user in ctx.guild.members]
        data = await self.bot.db.fetch(
            "SELECT user_id, timezone FROM user_settings WHERE user_id IN %s AND timezone IS NOT NULL",
            user_ids,
        )
        if not data:
            raise exceptions.CommandWarning("No one on this server has set their timezone yet!")

        dt_data = [(arrow.now(tz_str), ctx.guild.get_member(user_id)) for user_id, tz_str in data]
        rows.extend(
            f"{dt.format('MMM Do HH:mm')} - **{util.displayname(member)}**"
            for dt, member in sorted(dt_data, key=lambda x: int(x[0].format("Z")))
            if member is not None
        )
        await util.send_as_pages(ctx, content, rows)

    @commands.group()
    async def steam(self, ctx: commands.Context):
        """Steam commands"""
        await util.command_group_help(ctx)

    @steam.command()
    async def market(self, ctx: commands.Context, *, search_term: str):
        """Search the steam community market"""
        MARKET_SEARCH_URL = "https://steamcommunity.com/market/search/render"

        headers = {"User-Agent": util.random_user_agent()}
        params = {"norender": 1, "count": 99, "query": search_term}
        async with self.bot.session.get(
            MARKET_SEARCH_URL, params=params, headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.json()

        if not data["results"]:
            raise exceptions.CommandInfo(f"No steam market listings found for `{search_term}`")

        await MarketPaginator(data["results"]).run(ctx)


async def setup(bot):
    await bot.add_cog(Utility(bot))


class MarketPaginator(BaseButtonPaginator):
    MARKET_LISTING_URL = "https://steamcommunity.com/market/listings/"
    IMAGE_BASE_URL = "https://community.akamai.steamstatic.com/economy/image/"

    def __init__(self, entries: list[dict], **kwargs):
        super().__init__(entries=entries, per_page=1, **kwargs)

    async def format_page(self, entries: list[dict]):
        # entries should be a list with length of one so just grab the first element
        result = entries[0]
        asset = result["asset_description"]
        item_hash = quote(asset["market_hash_name"])
        market_link = f"{self.MARKET_LISTING_URL}{ asset['appid']}/{item_hash}"
        return (
            discord.Embed(
                description=asset["type"],
                color=int("68932f", 16),
            )
            .set_author(
                name=result["name"],
                url=market_link,
            )
            .set_thumbnail(url=self.IMAGE_BASE_URL + asset["icon_url"])
            .add_field(name="Starting at", value=result["sell_price_text"])
            .add_field(name="Listings", value=str(result["sell_listings"]))
            .set_footer(icon_url=result["app_icon"], text=result["app_name"])
        )


async def detect_language(bot, string):
    url = "https://translation.googleapis.com/language/translate/v2/detect"
    params = {"key": bot.keychain.GCS_DEVELOPER_KEY, "q": string[:1000]}

    async with bot.session.get(url, params=params) as response:
        data = await response.json(loads=orjson.loads)
        language = data["data"]["detections"][0][0]["language"]

    return language


def temp(celsius: float, convert_to_f: bool = False) -> str:
    if convert_to_f:
        return f"{int((celsius * 9.0 / 5.0) + 32)} °F"
    return f"{int(celsius)} °C"


class WeatherUnitToggler(discord.ui.View):
    def __init__(self, renderfunction, F):
        super().__init__()
        # renderfunction should be a function that takes boolean F,
        # denoting whether to use fahrenheit or not, and return a discord embed
        self.renderfunction = renderfunction
        self.message = None
        self.F = F

    async def run(self, ctx):
        self.update_label()
        content = self.renderfunction(self.F)
        self.message = await ctx.send(embed=content, view=self)

    def update_label(self):
        self.toggle.label = "°C" if self.F else "°F"

    @discord.ui.button(emoji="🌡️", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.F = not self.F
        self.update_label()

        content = self.renderfunction(self.F)
        await interaction.response.edit_message(embed=content, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True  # type: ignore

        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass
