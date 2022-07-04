import asyncio
import io
import os
import random
import re

import arrow
import discord
import orjson
import regex
import tweepy
import yarl
from bs4 import BeautifulSoup
from discord.ext import commands
from tweepy import OAuthHandler

from modules import exceptions, instagram, log, util

logger = log.get_logger(__name__)

TWITTER_CKEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CSECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
IG_COOKIE = os.environ.get("IG_COOKIE")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
PROXY_URL = os.environ.get("PROXY_URL")
PROXY_USER = os.environ.get("PROXY_USER")
PROXY_PASS = os.environ.get("PROXY_PASS")
IG_COOKIE = os.environ.get("IG_COOKIE")


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🌐"
        self.twitter_api = tweepy.API(OAuthHandler(TWITTER_CKEY, TWITTER_CSECRET))
        self.ig = instagram.Instagram(
            self.bot.session,
            IG_COOKIE,
            use_proxy=True,
            proxy_url=PROXY_URL,
            proxy_user=PROXY_USER,
            proxy_pass=PROXY_PASS,
        )
        self.ig_colors = [
            int("405de6", 16),
            int("5851db", 16),
            int("833ab4", 16),
            int("c13584", 16),
            int("e1306c", 16),
            int("fd1d1d", 16),
            int("f56040", 16),
            int("f77737", 16),
            int("fcaf45", 16),
        ]
        self.regions = {
            "kr": "www",
            "korea": "www",
            "eune": "eune",
            "euw": "euw",
            "jp": "jp",
            "japan": "jp",
            "na": "na",
            "oceania": "oce",
            "oce": "oce",
            "brazil": "br",
            "las": "las",
            "russia": "ru",
            "ru": "ru",
            "turkey": "tr",
            "tr": "tr",
        }

    @commands.group(aliases=["league"], case_insensitive=True, enabled=False)
    async def opgg(self, ctx: commands.Context):
        """League of legends stats"""
        await util.command_group_help(ctx)

    @opgg.command()
    async def profile(self, ctx: commands.Context, region, *, summoner_name):
        """See your op.gg profile"""
        parsed_region = self.regions.get(region.lower())
        if parsed_region is None:
            return await ctx.send(f":warning: Unknown region `{region}`")

        region = parsed_region

        ggsoup = GGSoup()
        await ggsoup.create(region, summoner_name)

        if ggsoup.soup.find("div", {"class": "SummonerNotFoundLayout"}):
            raise exceptions.CommandWarning("Summoner not found!")

        content = discord.Embed()
        content.set_author(
            name=f"{ggsoup.text('span', 'Name')} [{region.upper()}]",
            icon_url=ggsoup.src("img", "ProfileImage"),
        )

        rank = ggsoup.text("div", "TierRank")
        lp = ""
        wins_losses = ""
        if rank != "Unranked":
            lp = ggsoup.text("span", "LeaguePoints")
            wins_losses = (
                f"{ggsoup.text('span', 'wins')} {ggsoup.text('span', 'losses')} "
                f"({ggsoup.text('span', 'winratio').split()[-1]})"
            )

        content.add_field(
            name="Rank",
            value=f"**{rank}**" + (f" {lp} **|** {wins_losses}" if rank != "Unranked" else ""),
            inline=False,
        )

        rank_image = "https:" + ggsoup.soup.find("div", {"class": "Medal"}).find("img").get("src")
        content.set_thumbnail(url=rank_image)
        content.colour = int("5383e8", 16)

        champions = []
        for championbox in ggsoup.soup.findAll("div", {"class": "ChampionBox"}):
            name = championbox.find("div", {"class": "ChampionName"}).get("title")
            played_div = championbox.find("div", {"class": "Played"})
            played_count = played_div.find("div", {"class": "Title"}).text.strip()
            winrate = played_div.find("div", {"class": "WinRatio"}).text.strip()
            champions.append(
                f"**{played_count.replace(' Played', '** Played')} **{name}** ({winrate})"
            )

        content.add_field(name="Champions", value="\n".join(champions) if champions else "None")

        match_history = []
        for match in ggsoup.soup.findAll("div", {"class": "GameItem"}):
            gametype = ggsoup.text("div", "GameType", match)
            champion = match.find("div", {"class": "ChampionName"}).find("a").text.strip()
            win = match.get("data-game-result") == "win"
            kda = "".join(ggsoup.text("div", "KDA", match.find("div", {"class": "KDA"})).split())
            emoji = ":blue_square:" if win else ":red_square:"
            match_history.append(f"{emoji} **{gametype}** as **{champion}** `{kda}`")

        content.add_field(
            name="Match History",
            value="\n".join(match_history) if match_history else "No matches found",
        )

        await ctx.send(embed=content)

    @opgg.command()
    async def nowplaying(self, ctx: commands.Context, region, *, summoner_name):
        """Show your current game"""
        parsed_region = self.regions.get(region.lower())
        if parsed_region is None:
            return await ctx.send(f":warning: Unknown region `{region}`")

        region = parsed_region

        content = discord.Embed(title=f"{summoner_name} current game")

        ggsoup = GGSoup()
        await ggsoup.create(region, summoner_name, sub_url="spectator/")

        error = ggsoup.soup.find("div", {"class": "SpectatorError"})
        if error:
            raise exceptions.CommandWarning(error.find("h2").text)

        blue_team = ggsoup.soup.find("table", {"class": "Team-100"})
        red_team = ggsoup.soup.find("table", {"class": "Team-200"})
        for title, team in [("Blue Team", blue_team), ("Red Team", red_team)]:
            rows = []
            players = team.find("tbody").findAll("tr")
            for player in players:
                champion = (
                    player.find("td", {"class": "ChampionImage"})
                    .find("a")
                    .get("href")
                    .split("/")[2]
                )
                summoner = ggsoup.text("a", "SummonerName", player)
                url = f"https://{region}.op.gg/summoner/userName={summoner.replace(' ', '%20')}"
                rank = ggsoup.text("div", "TierRank", player)
                rows.append(f"`{rank:20} |` [{summoner}]({url}) as **{champion}**")

            content.add_field(name=title, value="\n".join(rows), inline=False)

        await ctx.send(embed=content)

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx: commands.Context, *, query):
        """Search for videos from youtube"""
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": GOOGLE_API_KEY,
            "part": "snippet",
            "type": "video",
            "maxResults": 25,
            "q": query,
        }
        async with self.bot.session.get(url, params=params) as response:
            if response.status == 403:
                raise exceptions.CommandError("Daily youtube api quota reached.")

            data = await response.json()

        if not data.get("items"):
            return await ctx.send("No results found!")

        await util.paginate_list(
            ctx,
            [f"https://youtube.com/watch?v={item['id']['videoId']}" for item in data.get("items")],
            use_locking=True,
            only_author=True,
            index_entries=True,
        )

    @commands.command(aliases=["ig", "insta"], usage="<links...> '-d'")
    async def instagram(self, ctx: commands.Context, *links):
        """Retrieve images from one or more instagram posts"""
        urls = []
        download = False

        for link in links:
            if link.lower() in ["-d", "--download"]:
                download = True
            else:
                urls.append(link)

        if len(urls) > 5:
            raise exceptions.CommandWarning("Only 5 links at a time please!")

        for post_url in urls:
            result = regex.findall("/(p|reel|tv)/(.*?)(/|\\Z)", post_url)
            if result:
                shortcode = result[0][1]
            else:
                shortcode = post_url.strip("/").split("/")[0]

            post_url = f"https://www.instagram.com/p/{shortcode}"
            try:
                post = await self.ig.extract(shortcode)
            except instagram.ExpiredCookie:
                raise exceptions.CommandError(
                    "The Instagram login cookie has expired, please ask my developer to reauthenticate!"
                )
            except instagram.InstagramError as e:
                raise exceptions.CommandError(e.message)

            if download:
                # send as files
                caption = "\n".join(
                    [
                        f":bust_in_silhouette: **@{post.user.username}**",
                        f":calendar: <t:{post.timestamp}:d>",
                        f":link: <{post_url}>",
                    ]
                )
                files = []
                # discord normally has 8MB file size limit, but it can be increased in some guilds
                max_filesize = getattr(ctx.guild, "filesize_limit", 8388608)
                for n, media in enumerate(post.media, start=1):
                    ext = "mp4" if media.media_type == instagram.MediaType.VIDEO else "jpg"
                    dateformat = arrow.get(post.timestamp).format("YYMMDD")
                    filename = f"{dateformat}-@{post.user.username}-{shortcode}-{n}.{ext}"

                    # The url params are unescaped by aiohttp's built-in yarl
                    # This causes problems with the hash-based request signing that instagram uses
                    # Thankfully you can plug your own yarl.URL into session.get(), with encoded=True
                    async with self.bot.session.get(yarl.URL(media.url, encoded=True)) as response:
                        if (
                            int(response.headers.get("content-length", max_filesize))
                            > max_filesize
                        ):
                            caption += f"\n{media.url}"
                        else:
                            buffer = io.BytesIO(await response.read())
                            files.append(discord.File(fp=buffer, filename=filename))

                # send files to discord
                await ctx.send(caption, files=files)

            else:
                # send as embeds
                content = discord.Embed(color=random.choice(self.ig_colors))
                content.set_author(
                    name=f"@{post.user.username}", icon_url=post.user.avatar_url, url=post_url
                )
                for n, media in enumerate(post.media, start=1):
                    if n == len(post.media):
                        content.timestamp = arrow.get(post.timestamp).datetime
                    if media.media_type == instagram.MediaType.VIDEO:
                        await ctx.send(media.url)
                    else:
                        content.set_image(url=media.url)
                        await ctx.send(embed=content)
                    content._author = None

        # finally delete discord automatic embed
        try:
            await ctx.message.edit(suppress=True)
        except (discord.Forbidden, discord.NotFound):
            pass

    @commands.command(aliases=["twt"], usage="<links...> '-d'")
    async def twitter(self, ctx: commands.Context, *links):
        """Retrieve images from one or more tweets"""
        urls = []
        download = False
        if len(links) > 5:
            raise exceptions.CommandWarning("Only 5 links at a time please!")
        for link in links:
            if link.lower() in ["-d", "--download"]:
                download = True
            else:
                urls.append(link)
        for tweet_url in urls:
            if "status" in tweet_url:
                tweet_id = re.search(r"status/(\d+)", tweet_url).group(1)
            else:
                tweet_id = tweet_url

            try:
                tweet = await ctx.bot.loop.run_in_executor(
                    None,
                    lambda: self.twitter_api.get_status(str(tweet_id), tweet_mode="extended"),
                )

            except Exception:
                await ctx.send(f":warning: Could not get tweet `{tweet_url}`")
                continue

            media_files = []
            try:
                media = tweet.extended_entities.get("media", [])
            except AttributeError:
                media = []

            if not media:
                await ctx.send(f":warning: Could not find any images from tweet id `{tweet_id}`")
                continue

            for resource in media:
                media_url = resource["media_url"]
                video_url = None
                if not resource["type"] == "photo":
                    video_variants = resource["video_info"]["variants"]
                    largest_rate = -1
                    for video in video_variants:
                        if (
                            video["content_type"] == "video/mp4"
                            and video["bitrate"] > largest_rate
                        ):
                            largest_rate = video["bitrate"]
                            video_url = video["url"]
                            media_url = video["url"]

                media_files.append((media_url, video_url))

            content = discord.Embed(colour=int(tweet.user.profile_link_color, 16))
            content.set_author(
                icon_url=tweet.user.profile_image_url,
                name=f"@{tweet.user.screen_name}",
                url=f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}",
            )

            if download:
                # download file and rename, upload to discord
                tweet_link = "https://" + tweet.full_text.split(" ")[-1].split("https://")[-1]
                timestamp = arrow.get(tweet.created_at).format("YYMMDD")
                caption = (
                    f":bust_in_silhouette: **@{tweet.user.screen_name}**\n"
                    f":calendar: {timestamp}\n"
                    f":link: <{tweet_link}>"
                )
                files = []
                for n, (media_url, video_url) in enumerate(media_files, start=1):
                    # is image not video
                    if video_url is None:
                        extension = "jpeg"
                    else:
                        extension = "mp4"

                    filename = f"{timestamp}-@{tweet.user.screen_name}-{tweet.id}-{n}.{extension}"
                    # discord normally has 8MB file size limit, but it can be increased in some guilds
                    max_filesize = getattr(ctx.guild, "filesize_limit", 8388608)
                    url = media_url.replace(".jpg", "?format=jpg&name=orig")
                    async with self.bot.session.get(url) as response:
                        if (
                            int(response.headers.get("content-length", max_filesize))
                            > max_filesize
                        ):
                            caption += f"\n{url}"
                        else:
                            buffer = io.BytesIO(await response.read())
                            files.append(discord.File(fp=buffer, filename=filename))

                    await ctx.send(caption, files=files)

            else:
                # just send link in embed
                for n, (media_url, video_url) in enumerate(media_files, start=1):
                    url = media_url.replace(".jpg", "?format=jpg&name=orig")
                    content.set_image(url=url)
                    if n == len(media_files):
                        content.timestamp = tweet.created_at
                    await ctx.send(embed=content)

                    if video_url is not None:
                        # contains a video/gif, send it separately
                        await ctx.send(video_url)

                    content._author = None

        try:
            # delete discord automatic embed
            await ctx.message.edit(suppress=True)
        except (discord.Forbidden, discord.NotFound):
            pass

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx: commands.Context, *, query):
        """Search for a gfycat gif"""
        scripts = []
        tasks = []
        if len(query.split(" ")) == 1:
            tasks.append(extract_scripts(self.bot.session, f"https://gfycat.com/gifs/tag/{query}"))

        tasks.append(extract_scripts(self.bot.session, f"https://gfycat.com/gifs/search/{query}"))
        scripts = sum(await asyncio.gather(*tasks), [])

        urls = []
        for script in scripts:
            try:
                data = orjson.loads(str(script.contents[0]))
                for x in data["itemListElement"]:
                    if "url" in x:
                        urls.append(x["url"])
            except orjson.JSONDecodeError:
                continue

        if not urls:
            return await ctx.send("Found nothing!")

        msg = await ctx.send(f"**{query}** {random.choice(urls)}")

        async def randomize():
            await msg.edit(content=f"**{query}** {random.choice(urls)}")

        async def done():
            return True

        buttons = {"❌": msg.delete, "🔁": randomize, "🔒": done}
        asyncio.ensure_future(util.reaction_buttons(ctx, msg, buttons, only_author=True))

    @commands.command(usage="<day | month | realtime | rising>")
    async def melon(self, ctx: commands.Context, timeframe):
        """Melon music charts"""
        if timeframe not in ["day", "month"]:
            if timeframe == "realtime":
                timeframe = ""
            elif timeframe == "rising":
                timeframe = "rise"
            else:
                raise exceptions.CommandInfo(
                    "Available timeframes: `[ day | month | realtime | rising ]`"
                )

        url = f"https://www.melon.com/chart/{timeframe}/index.htm"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
        }
        async with self.bot.session.get(url, headers=headers) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        song_titles = [
            util.escape_md(x.find("span").find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank01"})
        ]
        artists = [
            util.escape_md(x.find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank02"})
        ]
        # albums = [
        #     util.escape_md(x.find("a").text)
        #     for x in soup.find_all("div", {"class": "ellipsis rank03"})
        # ]
        image = soup.find("img", {"onerror": "WEBPOCIMG.defaultAlbumImg(this);"}).get("src")

        content = discord.Embed(color=discord.Color.from_rgb(0, 205, 60))
        content.set_author(
            name=f"Melon top {len(song_titles)}"
            + ("" if timeframe == "" else f" - {timeframe.capitalize()}"),
            url=url,
            icon_url="https://i.imgur.com/hm9xzPz.png",
        )
        content.set_thumbnail(url=image)
        content.timestamp = ctx.message.created_at

        rows = []
        for i, (song, artist) in enumerate(zip(song_titles, artists), start=1):
            rows.append(f"`#{i:2}` **{artist}** — ***{song}***")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def xkcd(self, ctx: commands.Context, comic_id=None):
        """Get a random xkcd comic"""
        if comic_id is None:
            url = "https://c.xkcd.com/random/comic"
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Connection": "keep-alive",
                "Referer": "https://xkcd.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0",
            }
            async with self.bot.session.get(url, headers=headers) as response:
                location = response.url
        else:
            location = f"https://xkcd.com/{comic_id}/"
        await ctx.send(location)


async def setup(bot):
    await bot.add_cog(Media(bot))


async def extract_scripts(session, url):
    async with session.get(url) as response:
        data = await response.text()
        soup = BeautifulSoup(data, "html.parser")
        return soup.find_all("script", {"type": "application/ld+json"})


class GGSoup:
    def __init__(self):
        self.soup = None

    async def create(self, region, summoner_name, sub_url=""):
        async with self.bot.session.get(
            f"https://{region}.op.gg/summoner/{sub_url}userName={summoner_name}"
        ) as response:
            data = await response.text()
            self.soup = BeautifulSoup(data, "html.parser")

    def text(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        a = source.find(obj, {"class": classname})
        return a.text.strip() if a else a

    def src(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        a = source.find(obj, {"class": classname})
        return "https:" + a.get("src") if a else a


class InstagramIdCodec:
    ENCODING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

    @staticmethod
    def encode(num, alphabet=ENCODING_CHARS):
        """Covert a numeric value to a shortcode."""
        num = int(num)
        if num == 0:
            return alphabet[0]
        arr = []
        base = len(alphabet)
        while num:
            rem = num % base
            num //= base
            arr.append(alphabet[rem])
        arr.reverse()
        return "".join(arr)

    @staticmethod
    def decode(shortcode, alphabet=ENCODING_CHARS):
        """Covert a shortcode to a numeric value."""
        base = len(alphabet)
        strlen = len(shortcode)
        num = 0
        idx = 0
        for char in shortcode:
            power = strlen - (idx + 1)
            num += alphabet.index(char) * (base**power)
            idx += 1
        return num
