# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot 

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

from modules.misobot import MisoBot


class MDText(MarkdownConverter):
    """Custom converter than doesn't render hyperlinks"""

    def convert_a(self, _el, text, _convert_as_inline):
        return text


class Genius:
    API_BASE_URL: str = "genius.p.rapidapi.com"

    def __init__(self, bot: MisoBot):
        self.bot: MisoBot = bot

    async def search(self, query: str):
        """Search Genius for songs"""
        url = f"https://{self.API_BASE_URL}/search"
        headers = {
            "X-RapidAPI-Key": self.bot.keychain.RAPIDAPI_KEY,
            "X-RapidAPI-Host": self.API_BASE_URL,
        }
        params = {"q": query}

        async with self.bot.session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            return [song["result"] for song in data["response"]["hits"]]

    async def scrape_lyrics(self, lyrics_path: str):
        """Scrape lyrics from the given relative path"""
        lyrics = []

        url = f"https://genius.com{lyrics_path}"
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:103.0) Gecko/20100101 Firefox/103.0"
        }
        async with self.bot.session.get(url, headers=headers) as response:
            content = await response.text()
            soup = BeautifulSoup(content, "lxml")
            lyric_containers = soup.find_all("div", {"data-lyrics-container": "true"})
            lyrics.extend(MDText().convert_soup(container) for container in lyric_containers)
        return lyrics
