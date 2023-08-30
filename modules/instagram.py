# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional
from urllib import parse
from urllib.parse import urlencode

import aiohttp
import arrow
import orjson
import redis
from loguru import logger

from modules import exceptions

if TYPE_CHECKING:
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
    NONE = 0


@dataclass
class IgMedia:
    media_type: MediaType
    url: str
    expires: int | None = None


@dataclass
class IgUser:
    id: int
    username: str
    avatar_url: str


@dataclass
class IgPost:
    url: str
    user: IgUser
    media: list[IgMedia]
    timestamp: int
    caption: str = ""


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
        return sum(
            alphabet.index(char) * base ** (strlen - (idx + 1))
            for idx, char in enumerate(shortcode)
        )


class Datalama:
    BASE_URL = "https://api.datalama.io"

    def __init__(self, bot: "MisoBot"):
        self.bot: "MisoBot" = bot

    def make_cache_key(self, endpoint: str, params: dict):
        return self.BASE_URL + endpoint + "?" + urlencode(params)

    @staticmethod
    def get_url_expiry(media_url: str):
        return int(parse.parse_qs(parse.urlparse(media_url).query)["oe"][0], 16)

    @staticmethod
    def calculate_post_lifetime(media: list) -> int:
        return min(m.expires for m in media) - arrow.utcnow().int_timestamp

    async def api_request_with_cache(
        self, endpoint: str, params: dict
    ) -> tuple[dict, bool, str]:
        cache_key = self.make_cache_key(endpoint, params)

        data = await self.try_cache(cache_key)
        was_cached = data is not None
        if not was_cached:
            data = await self.api_request(endpoint, params)

        return data, was_cached, cache_key

    async def try_cache(self, cache_key: str) -> dict | None:
        try:
            cached_response = await self.bot.redis.get(cache_key)
        except redis.ConnectionError:
            logger.warning("Could not get cached content from redis (ConnectionError)")
            cached_response = None

        if cached_response:
            logger.info(f"Instagram request was pulled from the cache {cache_key}")
            if prom := self.bot.get_cog("Prometheus"):
                await prom.increment_instagram_cache_hits()  # type: ignore
            return orjson.loads(cached_response)
        return None

    async def save_cache(self, cache_key: str, data: dict, lifetime: int):
        try:
            await self.bot.redis.set(cache_key, orjson.dumps(data), lifetime)
            logger.info(
                f"Instagram request was cached (expires in {lifetime}) {cache_key}"
            )
        except redis.ConnectionError:
            logger.warning("Could not save content into redis cache (ConnectionError)")

    async def api_request(self, endpoint: str, params: dict) -> dict:
        raise exceptions.CommandWarning(
            "The Instagram scraper was taken down by Meta Inc :("
        )
        headers = {
            "accept": "application/json",
            "x-access-key": self.bot.keychain.DATALAMA_ACCESS_KEY,
        }
        async with self.bot.session.get(
            self.BASE_URL + endpoint,
            params=params,
            headers=headers,
        ) as response:
            try:
                data = await response.json()
                if (
                    not response.ok
                    or data.get("exc_type") is not None
                    or data.get("detail") is not None
                ):
                    raise InstagramError(
                        f"API returned **{response.status} {data.get('detail')}**"
                        f"```json\n{params}```"
                    )

                return data

            except aiohttp.ContentTypeError:
                response.raise_for_status()
                text = await response.text()
                raise InstagramError(f"{response.status} | {text}")

    async def get_post_v1(self, shortcode: str) -> IgPost:
        data, was_cached, cache_key = await self.api_request_with_cache(
            "/v1/media/by/code",
            {"code": shortcode},
        )

        media = self.parse_resource_v1(data)

        if not was_cached and media:
            lifetime = self.calculate_post_lifetime(media)
            await self.save_cache(cache_key, data, lifetime)

        return IgPost(
            f"https://www.instagram.com/p/{shortcode}",
            self.parse_user(data),
            media,
            data["taken_at_ts"],
            data["caption_text"],
        )

    async def get_story_v1(self, username: str, story_pk: str) -> IgPost:
        data, was_cached, cache_key = await self.api_request_with_cache(
            "/v1/story/by/id",
            {"id": story_pk},
        )

        media = []

        match MediaType(data["media_type"]):
            case MediaType.VIDEO:
                media.append(
                    IgMedia(
                        MediaType.VIDEO,
                        data["video_url"],
                        self.get_url_expiry(data["video_url"]),
                    )
                )
            case MediaType.PHOTO:
                media.append(
                    IgMedia(
                        MediaType.PHOTO,
                        data["thumbnail_url"],
                        self.get_url_expiry(data["thumbnail_url"]),
                    )
                )
            case _:
                raise TypeError(f"Unknown IG media type {data['media_type']}")

        if not was_cached and media:
            lifetime = self.calculate_post_lifetime(media)
            await self.save_cache(cache_key, data, lifetime)

        timestamp = int(arrow.get(data["taken_at"]).timestamp())

        return IgPost(
            f"https://www.instagram.com/stories/{username}/{story_pk}",
            self.parse_user(data),
            media,
            timestamp,
        )

    @staticmethod
    def parse_user(data: dict):
        """Pass a dict which has user as a key to make it IgUser"""
        user = data["user"]
        return IgUser(
            user["pk"],
            user["username"] or f"instagram_user_{user['pk']}",
            user["profile_pic_url"],
        )

    def parse_resource_v1(self, resource: dict) -> list[IgMedia]:
        media = []
        match MediaType(resource["media_type"]):
            case MediaType.ALBUM:
                for album_resource in resource["resources"]:
                    media += self.parse_resource_v1(album_resource)

            case MediaType.VIDEO:
                media_url = get_best_candidate(resource["video_versions"])
                media.append(
                    IgMedia(
                        MediaType.VIDEO,
                        media_url,
                        self.get_url_expiry(media_url),
                    )
                )

            case MediaType.PHOTO:
                media_url = get_best_candidate(resource["image_versions"])
                media.append(
                    IgMedia(
                        MediaType.PHOTO,
                        media_url,
                        self.get_url_expiry(media_url),
                    )
                )

            case _:
                raise TypeError(f"Unknown IG media type {resource['media_type']}")

        return media

    def parse_resource_a1(self, resource: dict) -> list[IgMedia]:
        media = []
        match MediaType(resource["media_type"]):
            case MediaType.ALBUM:
                for album_resource in resource["carousel_media"]:
                    media += self.parse_resource_v1(album_resource)

            case MediaType.VIDEO:
                media_url = get_best_candidate(resource["video_versions"])
                media.append(
                    IgMedia(
                        MediaType.VIDEO,
                        media_url,
                        self.get_url_expiry(media_url),
                    )
                )

            case MediaType.PHOTO:
                media_url = get_best_candidate(
                    resource["image_versions2"]["candidates"]
                )
                media.append(
                    IgMedia(
                        MediaType.PHOTO,
                        media_url,
                        self.get_url_expiry(media_url),
                    )
                )

            case _:
                raise TypeError(f"Unknown IG media type {resource['media_type']}")

        return media

    async def get_post_a1(self, shortcode: str) -> IgPost:
        data = await self.api_request("/a1/media/by/code", {"code": shortcode})
        post = data["items"][0]

        return IgPost(
            f"https://www.instagram.com/p/{shortcode}",
            self.parse_user(post),
            self.parse_resource_a1(post),
            post["taken_at"],
        )


class Instagram:
    def __init__(
        self,
        bot: "MisoBot",
        use_proxy: bool = False,
    ):
        self.bot: "MisoBot" = bot
        self.jar = aiohttp.CookieJar(unsafe=True)
        self.session = aiohttp.ClientSession(cookie_jar=self.jar)

        if use_proxy:
            proxy_url: str = bot.keychain.PROXY_URL
            self.proxy = proxy_url
            proxy_user: str = bot.keychain.PROXY_USER
            proxy_pass: str = bot.keychain.PROXY_PASS

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

    async def close(self):
        await self.session.close()

    @staticmethod
    def parse_media(resource):
        resource_media_type = MediaType(int(resource["media_type"]))
        if resource_media_type == MediaType.PHOTO:
            res = resource["image_versions2"]["candidates"][0]
            return IgMedia(resource_media_type, res["url"])
        if resource_media_type == MediaType.VIDEO:
            res = resource["video_versions"][0]
            return IgMedia(resource_media_type, res["url"])
        return IgMedia(resource_media_type, "")

    async def graphql_request(self, shortcode: str):
        url = "https://www.instagram.com/graphql/query/"
        params = {
            "query_hash": "9f8827793ef34641b2fb195d4d41151c",
            "variables": '{"shortcode": "'
            + shortcode
            + '", "child_comment_count": 3, "fetch_comment_count": 40, '
            + '"parent_comment_count": 24, "has_threaded_comments": "true"}',
        }
        headers = {
            "Host": "www.instagram.com",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:104.0) Gecko/20100101 Firefox/104.0",
            "Accept": "*/*",
            "Accept-Language": "en,en-US;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Instagram-AJAX": "1006292718",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "198387",
            "X-IG-WWW-Claim": "0",
            "X-Requested-With": "XMLHttpRequest",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://www.instagram.com/p/Ci3_9mnrK9z/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers",
            "Cookie": self.bot.keychain.IG_COOKIE,
        }
        async with self.session.get(
            url,
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
                logger.warning(data)
                raise InstagramError(f'[HTTP {response.status}] {data.get("message")}')

        return data

    async def v1_api_request(self, endpoint: str, params: Optional[dict] = None):
        headers = {
            "Cookie": self.bot.keychain.IG_COOKIE,
            "Host": "i.instagram.com",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:104.0) Gecko/20100101 Firefox/104.0",
            "Accept": "*/*",
            "Accept-Language": "en,en-US;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Instagram-AJAX": "1006164448",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "198387",
            "Origin": "https://www.instagram.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://www.instagram.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers",
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

        return IgPost(
            f"https://www.instagram.com/stories/{username}/{story_pk}",
            user,
            [self.parse_media(story)],
            story["taken_at"],
        )

    async def get_user(self, username) -> IgUser:
        data = await self.v1_api_request(
            "users/web_profile_info/", {"username": username}
        )
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
        media_type = MediaType(int(data["media_type"]))
        if media_type == MediaType.ALBUM:
            resources.extend(iter(data["carousel_media"]))
        else:
            resources = [data]

        media = [self.parse_media(resource) for resource in resources]
        timestamp = data["taken_at"]
        user = data["user"]
        user = IgUser(
            user["pk"],
            user["username"],
            user["profile_pic_url"],
        )
        return IgPost(
            f"https://www.instagram.com/p/{shortcode}", user, media, timestamp
        )

    async def get_post_graphql(self, shortcode: str) -> IgPost:
        data = await self.graphql_request(shortcode)
        data = data["data"]["shortcode_media"]
        mediatype = to_mediatype(data["__typename"])

        media = []
        if mediatype == MediaType.ALBUM:
            for node in data["edge_sidecar_to_children"]["edges"]:
                node = node["node"]
                node_mediatype = to_mediatype(node["__typename"])
                display_url = node["display_resources"][-1]["src"]
                media.append(IgMedia(node_mediatype, display_url))
        else:
            display_url = data["display_resources"][-1]["src"]
            media.append(IgMedia(mediatype, display_url))

        timestamp = data["taken_at_timestamp"]
        user = data["owner"]
        user = IgUser(
            user["id"],
            user["username"],
            user["profile_pic_url"],
        )
        return IgPost(
            f"https://www.instagram.com/p/{shortcode}", user, media, timestamp
        )


def to_mediatype(typename: str) -> MediaType:
    match typename:
        case "GraphVideo":
            return MediaType.VIDEO
        case "GraphImage":
            return MediaType.PHOTO
        case "GraphSidecar":
            return MediaType.ALBUM
        case _:
            return MediaType.NONE


def get_best_candidate(
    candidates: list[dict],
    og_width: Optional[int] = None,
    og_height: Optional[int] = None,
) -> str:
    """Filter out the best image candidate, based on resolution. Returns media url"""
    if og_height and og_width:
        best = next(
            filter(
                lambda img: img["width"] == og_width and img["height"] == og_height,
                candidates,
            )
        )
    else:
        best = sorted(
            candidates, key=lambda img: img["width"] * img["height"], reverse=True
        )[0]

    return best["url"]
