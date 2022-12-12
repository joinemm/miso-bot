import io
from dataclasses import dataclass

from shazamio import Shazam as ShazamClient

from modules.misobot import MisoBot


@dataclass
class ShazamTrack:
    song: str
    artist: str
    metadata: list
    cover_art: str
    url: str


class Shazam:
    def __init__(self, bot: MisoBot):
        self.client = ShazamClient()
        self.bot = bot

    async def recognize_file(self, file: bytes) -> ShazamTrack | None:
        try:
            data = await self.client.recognize_song(file)
            track = data["track"]
        except (IndexError, KeyError):
            return None
        return ShazamTrack(
            track["title"],
            track["subtitle"],
            track["sections"][0]["metadata"],
            track["images"]["coverart"],
            track["url"],
        )

    async def recognize_from_url(self, url: str) -> ShazamTrack | None:
        async with self.bot.session.get(url) as response:
            buffer = io.BytesIO(await response.read())
            return await self.recognize_file(buffer.read())
