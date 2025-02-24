# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional
from urllib import parse
from urllib.parse import urlencode

import aiohttp
import arrow
import orjson
import redis
from bs4 import BeautifulSoup
from loguru import logger

if TYPE_CHECKING:
    from modules.misobot import MisoBot


class InstagramError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class MediaType(Enum):
    PHOTO = 1
    VIDEO = 2
    ALBUM = 8
    NONE = 0

    @staticmethod
    def from_string(s: str):
        match s:
            case "photo":
                return MediaType.PHOTO
            case "video":
                return MediaType.VIDEO
            case _:
                raise ValueError(s)


@dataclass
class IgMedia:
    media_type: MediaType
    url: str
    expires: int | None = None


@dataclass
class IgUser:
    username: str
    name: str | None = None
    id: int | None = None
    avatar_url: str | None = None


@dataclass
class IgPost:
    url: str
    user: IgUser
    media: list[IgMedia]
    timestamp: int | None = None
    caption: str | None = None


class EmbedEz:
    def __init__(self, bot: "MisoBot"):
        self.bot = bot

    async def try_cache(self, cache_key: str) -> dict | None:
        cached_response = await self.bot.redis.get(cache_key)
        if cached_response is not None:
            logger.info(f"Instagram request was pulled from the cache: {cache_key}")
            return orjson.loads(cached_response)

    async def save_cache(self, cache_key: str, data: dict, lifetime: int):
        await self.bot.redis.set(cache_key, orjson.dumps(data), lifetime)
        logger.info(f"Instagram request was cached: {cache_key}")

    async def get_post(self, shortcode: str) -> IgPost:
        url = f"https://embedez.com/api/v1/providers/combined?q=https://instagram.com/p/{shortcode}"
        data = await self.try_cache(url)
        if data is None:
            cooldown = await self.bot.redis.get("ez_on_cooldown")
            if cooldown is not None:
                raise InstagramError("API Error: Rate limited (cached)")

            async with self.bot.session.get(
                url,
                headers={"Authorization": self.bot.keychain.EZ_API_KEY},
            ) as response:
                if not response.ok:
                    if response.status == 429:
                        # rate limited
                        await self.bot.redis.set("ez_on_cooldown", 1, 600)
                        logger.info("Stopping EZ requests for one hour")
                        raise InstagramError("API Error: Rate limited")
                    else:
                        raise InstagramError(f"API Error: {response.status}")
                data = await response.json()
                if not data["success"]:
                    raise InstagramError(f"API Error: {data['message']}")
                data = data["data"]

                # cache this response for a day
                await self.save_cache(url, data, 86400)

        media = [
            IgMedia(url=x["source"]["url"], media_type=MediaType.from_string(x["type"]))
            for x in data["content"]["media"]
        ]

        if not media:
            raise InstagramError("No media was found for this post")

        return IgPost(
            url=data["content"]["link"],
            user=IgUser(
                username=data["user"]["name"],
                name=data["user"]["displayName"],
                avatar_url=data["user"]["pictures"]["url"],
            ),
            caption=data["content"]["description"],
            media=media,
            timestamp=None,
        )


class InstaFix:
    BASE_URL = "https://www.ddinstagram.com"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def request(self, url: str) -> str:
        tries = 0
        while tries < 2:
            try:
                async with self.session.get(
                    url, allow_redirects=False, headers={"User-Agent": "bot"}
                ) as response:
                    if response.status != 200:
                        raise InstagramError(
                            f"Unable to scrape post: HTTP {response.status}"
                        )
                    data = await response.read()
                    # because the world is not perfect, and a server that
                    # promises utf-8 will not actually return utf-8
                    text = data.decode("utf-8", "ignore")
                return text

            except aiohttp.ClientConnectorError as e:
                logger.warning(e)
                tries += 1
                await asyncio.sleep(1)

        raise InstagramError("Could not connect to Instagram!")

    async def try_media(self, shortcode: str) -> list:
        media = []
        for i in range(1, 21):
            text = await self.request(f"{self.BASE_URL}/p/{shortcode}/{i}")
            soup = BeautifulSoup(text, "lxml")
            imagetag = soup.find("meta", {"property": "og:image"})
            videotag = soup.find("meta", {"property": "og:video"})

            if imagetag:
                media.append(
                    IgMedia(
                        url=self.BASE_URL + imagetag.attrs["content"],
                        media_type=MediaType.PHOTO,
                    )
                )
            elif videotag:
                media.append(
                    IgMedia(
                        url=self.BASE_URL + videotag.attrs["content"],
                        media_type=MediaType.VIDEO,
                    )
                )
            else:
                break

        return media

    async def get_post(self, shortcode: str):
        text = await self.request(f"{self.BASE_URL}/p/{shortcode}")
        soup = BeautifulSoup(text, "lxml")
        try:
            metadata = {
                "url": soup.find("a").attrs["href"],
                "description": soup.find("meta", {"property": "og:description"}).attrs[
                    "content"
                ],
                "username": soup.find("meta", {"name": "twitter:title"}).attrs[
                    "content"
                ],
            }
        except AttributeError as e:
            logger.error(e)
            raise InstagramError("There was a problem scraping this post!")

        media = await self.try_media(shortcode)

        if not media:
            raise InstagramError("There was a problem finding media for this post")

        return IgPost(
            url=metadata["url"],
            user=IgUser(username=metadata["username"].strip("@")),
            caption=metadata["description"],
            media=media,
            timestamp=None,
        )


class Datalama:
    BASE_URL = "https://api.datalikers.com"

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

        was_cached = False
        data = await self.try_cache(cache_key)
        if data is None:
            data = await self.api_request(endpoint, params)
        else:
            was_cached = True

        return data, was_cached, cache_key

    async def try_cache(self, cache_key: str) -> dict | None:
        try:
            cached_response = await self.bot.redis.get(cache_key)
        except redis.ConnectionError:
            logger.warning("Could not get cached content from redis (ConnectionError)")
            cached_response = None

        if cached_response:
            logger.info(f"Instagram request was pulled from the cache {cache_key}")
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

    async def get_post(self, shortcode: str) -> IgPost:
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

    async def get_story(self, username: str, story_pk: str) -> IgPost:
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
            id=user["pk"],
            username=(user["username"] or f"instagram_user_{user['pk']}"),
            avatar_url=user["profile_pic_url"],
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
