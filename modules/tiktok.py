# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp


class TiktokError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


@dataclass
class TikTokVideo:
    video_url: str
    description: str


class TikTok:
    BASE_URL = f"http://{os.environ['EMBEDDER_HOST']}:{os.environ['EMBEDDER_PORT']}"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_video(self, url: str) -> TikTokVideo:
        try:
            async with self.session.get(
                f"{self.BASE_URL}/embed", params={"url": url}
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except aiohttp.ClientError:
            raise TiktokError("Network error in embedder connection")

        if not data["success"]:
            raise TiktokError(data["message"])

        media = data["data"]["media"]
        if not media:
            raise TiktokError("No media found!")
        if len(media) != 1 or media[0]["type"] != "video":
            raise TiktokError("TikTok slideshows are not supported")

        video_url = media[0].get("url") or ""
        parsed_url = urlsplit(video_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise TiktokError("Embedder returned an invalid video URL")

        return TikTokVideo(
            video_url=video_url, description=data["data"].get("description") or ""
        )
