# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import re
from dataclasses import dataclass
from typing import Dict, Tuple

import aiohttp
from bs4 import BeautifulSoup


class TiktokError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


@dataclass
class TikTokVideo:
    video_url: str
    user: str
    description: str


def error_code_to_message(error_code):
    match error_code:
        case "tiktok":
            return "URL redirected to tiktok home page."
        case "Video is private!":
            return "Video is private or unavailable"
        case _:
            return error_code


class TikTok:
    BASE_URL: str = "https://musicaldown.com/"

    HEADERS: Dict[str, str] = {
        "Host": "musicaldown.com",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:103.0) Gecko/20100101 Firefox/103.0"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "TE": "trailers",
    }
    EMOJI = "<:tiktok:1050401570090647582>"

    def __init__(self) -> None:
        self.input_element = None

    async def warmup(self, session: aiohttp.ClientSession):
        response = await session.get(self.BASE_URL)
        soup = BeautifulSoup(await response.text(), "lxml")
        self.input_element = soup.findAll("input")

    def generate_post_data(self, url: str):
        if self.input_element is None:
            raise Exception("TikTok downloader was not warmed up!")

        return {
            index.get("name"): url if index.get("id") == "link_url" else index.get("value")
            for index in self.input_element
        }

    async def download_video(
        self, url: str, session: aiohttp.ClientSession
    ) -> Tuple[str, str, str]:
        async with session.post(
            f"{self.BASE_URL}id/download",
            data=self.generate_post_data(url),
            allow_redirects=True,
        ) as response:
            if response.status == 302:
                raise TiktokError("302 Not Found")

            error_code = response.url.query.get("err")
            if error_code:
                raise TiktokError(error_code_to_message(error_code))

            text = await response.text()

        soup = BeautifulSoup(text, "lxml")

        error_message = re.search(r"html: 'Error: (.*)'", soup.findAll("script")[-1].text)
        if error_message:
            raise TiktokError(error_message)

        download_link = soup.findAll(
            "a",
            attrs={
                "target": "_blank",
                "class": "btn",
            },
        )
        if not download_link:
            # probably a slideshow with music
            script = soup.findAll("script")[-2].text
            data = re.search(r"data: {\s*data:\s*'(.*?)'", script, flags=re.MULTILINE)
            if data is None:
                raise TiktokError("Internal Error: Unable to scrape POST data")

            async with session.post(
                "https://muscdn.xyz/slider", data={"data": data.group(1)}, headers=self.HEADERS
            ) as response:
                converted_data = await response.json()
                username = soup.select_one("h2.white-text")
                if username:
                    username = username.text.strip("Download Now: Check out ").strip(
                        "’s video! #TikTok >"
                    )
                else:
                    username = ""
                return converted_data["url"], username, ""

        else:
            username, description = [el.text for el in soup.select("h2.white-text")[:2]]
            return download_link[0].get("href"), username, description

    async def get_video(self, url: str) -> TikTokVideo:
        async with aiohttp.ClientSession() as session:
            session.headers.update(self.HEADERS)
            await self.warmup(session)
            return TikTokVideo(*await self.download_video(url, session))
