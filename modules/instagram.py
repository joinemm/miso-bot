from dataclasses import dataclass
from enum import Enum

import aiohttp
import orjson

from modules.misobot import MisoBot


class ExpiredCookie(Exception):
    pass


class ExpiredStory(Exception):
    pass


class InstagramError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class MediaType(Enum):
    PHOTO = 1
    VIDEO = 2
    ALBUM = 8


@dataclass
class IgMedia:
    media_type: MediaType
    url: str


@dataclass
class IgUser:
    id: int
    username: str
    avatar_url: str


@dataclass
class IgPost:
    user: IgUser
    media: list[IgMedia]
    timestamp: int


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


class Instagram:
    def __init__(
        self,
        bot: MisoBot,
        use_proxy: bool = False,
    ):
        self.bot = bot
        self.session = bot.session

        proxy_url: str = bot.keychain.PROXY_URL
        proxy_user: str = bot.keychain.PROXY_USER
        proxy_pass: str = bot.keychain.PROXY_PASS

        if use_proxy:
            self.proxy = proxy_url
            self.proxy_auth = aiohttp.BasicAuth(proxy_user, proxy_pass)
        else:
            self.proxy = None
            self.proxy_auth = None

    @property
    def emoji(self):
        return "<:ig:937425165162262528>"

    @property
    def color(self):
        return int("ce0071", 16)

    def parse_media(self, resource):
        resource_media_type = MediaType(int(resource["media_type"]))
        if resource_media_type == MediaType.PHOTO:
            res = resource["image_versions2"]["candidates"][0]
            return IgMedia(resource_media_type, res["url"])
        elif resource_media_type == MediaType.VIDEO:
            res = resource["video_versions"][0]
            return IgMedia(resource_media_type, res["url"])

    async def v1_api_request(self, endpoint: str, params: dict = None):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:98.0) Gecko/20100101 Firefox/98.0",
            "X-IG-App-ID": "936619743392459",
            "Cookie": self.bot.keychain.IG_COOKIE,
        }
        base_url = "https://i.instagram.com/api/v1/"
        async with self.session.get(
            base_url + endpoint,
            headers=headers,
            proxy=self.proxy,
            params=params,
            proxy_auth=self.proxy_auth,
        ) as response:
            try:
                data = await response.json(loads=orjson.loads)
            except aiohttp.ContentTypeError:
                raise ExpiredCookie

            if data["status"] != "ok":
                raise InstagramError(data.get("message"))

        return data

    async def get_story(self, username: str, story_pk: str) -> IgPost:
        user = await self.get_user(username)
        data = await self.v1_api_request("feed/reels_media/", {"reel_ids": user.id})
        stories = data["reels"][user.id]["items"]
        try:
            story = next(filter(lambda x: x["pk"] == story_pk, stories))
        except StopIteration:
            raise ExpiredStory

        return IgPost(user, [self.parse_media(story)], story["taken_at"])

    async def get_user(self, username) -> IgUser:
        data = await self.v1_api_request("users/web_profile_info/", {"username": username})
        user = data["data"]["user"]
        return IgUser(user["id"], user["username"], user["profile_pic_url"])

    async def get_post(self, shortcode: str) -> IgPost:
        """Extract all media from given Instagram post"""
        try:
            real_media_id = InstagramIdCodec.decode(shortcode[:11])
        except ValueError:
            raise InstagramError("Not a valid Instagram link")

        data = await self.v1_api_request(f"media/{real_media_id}/info/")
        data = data["items"][0]

        resources = []
        media = []

        media_type = MediaType(int(data["media_type"]))
        if media_type == MediaType.ALBUM:
            for carousel_media in data["carousel_media"]:
                resources.append(carousel_media)
        else:
            resources = [data]

        for resource in resources:
            media.append(self.parse_media(resource))

        timestamp = data["taken_at"]
        user = data["user"]
        user = IgUser(
            user["pk"],
            user["username"],
            user["profile_pic_url"],
        )
        return IgPost(user, media, timestamp)
