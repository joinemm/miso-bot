from dataclasses import dataclass
from typing import Dict, Tuple

import aiohttp
from bs4 import BeautifulSoup


class InvalidVideo(Exception):
    pass


@dataclass
class TikTokVideo:
    video_url: str
    user: str
    description: str


class TikTok:
    BASE_URL: str = "https://musicaldown.com/"

    HEADERS: Dict[str, str] = {
        "Host": "musicaldown.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:103.0) Gecko/20100101 Firefox/103.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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

    async def warmup(self, session: aiohttp.ClientSession):
        self.request = await session.get(self.BASE_URL)
        soup = BeautifulSoup(await self.request.text(), "lxml")
        self.input_element = soup.findAll("input")

    def generate_post_data(self, url: str):
        return {
            index.get("name"): url
            if index.get("id") == "link_url"
            else index.get("value")
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

            text = await response.text()
            if response.status == 302:
                raise InvalidVideo
            for error_message in [
                "This video is currently not available",
                "Video is private or removed!",
                "Submitted Url is Invalid, Try Again",
            ]:
                if error_message in text:
                    raise InvalidVideo(error_message)

        soup = BeautifulSoup(text, "lxml")

        download_link = soup.findAll("a", attrs={"target": "_blank"})[0].get("href")
        username, description = [el.text for el in soup.select("h2.white-text")[:2]]
        return download_link, username, description

    async def get_video(self, url: str) -> TikTokVideo:
        async with aiohttp.ClientSession() as session:
            session.headers.update(self.HEADERS)
            await self.warmup(session)
            return TikTokVideo(*await self.download_video(url, session))
