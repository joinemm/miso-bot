import os

import aiohttp
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter


class MDText(MarkdownConverter):
    """Custom converter than doesn't render hyperlinks"""

    def convert_a(self, _el, text, _convert_as_inline):
        return text


class Genius:

    RAPIDAPI_KEY: str = os.environ.get("RAPIDAPI_KEY")
    API_BASE_URL: str = "genius.p.rapidapi.com"

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def search(self, query: str):
        """Search Genius for songs"""
        url = "https://" + self.API_BASE_URL + "/search"
        headers = {
            "X-RapidAPI-Key": self.RAPIDAPI_KEY,
            "X-RapidAPI-Host": self.API_BASE_URL,
        }
        params = {"q": query}

        async with self.session.get(url, params=params, headers=headers) as response:
            data = await response.json()
            return [song["result"] for song in data["response"]["hits"]]

    async def scrape_lyrics(self, lyrics_path: str):
        """Scrape lyrics from the given relative path"""
        lyrics = []

        url = "https://genius.com" + lyrics_path
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:103.0) Gecko/20100101 Firefox/103.0"
        }
        async with self.session.get(url, headers=headers) as response:
            content = await response.text()
            soup = BeautifulSoup(content, "html.parser")
            lyric_containers = soup.find_all("div", {"data-lyrics-container": "true"})
            for container in lyric_containers:
                lyrics.append(MDText().convert_soup(container))

        return lyrics
