import asyncio
import os
from dataclasses import dataclass
from enum import Enum

import aiohttp


class ExpiredCookie(Exception):
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
        self, session, cookie, use_proxy=False, proxy_url=None, proxy_user=None, proxy_pass=None
    ):
        self.cookie = cookie
        self.session = session
        if use_proxy:
            self.proxy = proxy_url
            self.proxy_auth = aiohttp.BasicAuth(proxy_user, proxy_pass)
        else:
            self.proxy = None
            self.proxy_auth = None

    async def extract(self, shortcode: str) -> IgPost:
        """Extract all media from given Instagram post"""
        real_media_id = InstagramIdCodec.decode(shortcode[:11])
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:98.0) Gecko/20100101 Firefox/98.0",
            "Cookie": self.cookie,
            "X-IG-App-ID": "936619743392459",
        }
        url = f"https://i.instagram.com/api/v1/media/{real_media_id}/info/"

        async with self.session.get(
            url,
            headers=headers,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        ) as response:
            try:
                data = await response.json()
            except aiohttp.ContentTypeError:
                raise ExpiredCookie

            try:
                data = data["items"][0]
            except KeyError:
                raise InstagramError(data["message"])

            resources = []
            media = []

            media_type = MediaType(int(data["media_type"]))
            if media_type == MediaType.ALBUM:
                for carousel_media in data["carousel_media"]:
                    resources.append(carousel_media)
            else:
                resources = [data]

            for resource in resources:
                resource_media_type = MediaType(int(resource["media_type"]))
                if resource_media_type == MediaType.PHOTO:
                    res = resource["image_versions2"]["candidates"][0]
                    media.append(IgMedia(resource_media_type, res["url"]))
                elif resource_media_type == MediaType.VIDEO:
                    res = resource["video_versions"][0]
                    media.append(IgMedia(resource_media_type, res["url"]))

            timestamp = data["taken_at"]
            user = IgUser(data["user"]["username"], data["user"]["profile_pic_url"])
            return IgPost(user, media, timestamp)

    async def test(self):
        """Test that every kind of post works"""
        one_image = "CdxAbDbrUGs"
        one_video = "CefwLP0KgSO"
        image_carousel = "CdxHB09rE9m"
        video_and_image_carousel = "Cei0fGmLlZd"
        reel = "CeeDK8XgPCP"

        results = await asyncio.gather(
            self.extract(one_image),
            self.extract(one_video),
            self.extract(reel),
            self.extract(image_carousel),
            self.extract(video_and_image_carousel),
        )
        print(results)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    IG_COOKIE = os.environ.get("IG_COOKIE")
    PROXY_URL = os.environ.get("PROXY_URL")
    PROXY_USER = os.environ.get("PROXY_USER")
    PROXY_PASS = os.environ.get("PROXY_PASS")

    ig = Instagram(IG_COOKIE, True, PROXY_URL, PROXY_USER, PROXY_PASS)
    asyncio.run(ig.test())
