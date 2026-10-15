# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import ipaddress
import socket
from dataclasses import dataclass

import aiohttp
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver
from shazamio import Shazam as ShazamClient
from yarl import URL

from modules import exceptions
from modules.misobot import MisoBot


def require_public_address(host: str) -> None:
    address = ipaddress.ip_address(host)
    if (
        not address.is_global
        or address.is_multicast
        or address.is_reserved
        or (
            isinstance(address, ipaddress.IPv6Address)
            and (
                address.is_site_local
                or address.sixtofour is not None
                or address.teredo is not None
            )
        )
    ):
        raise exceptions.CommandWarning("Only public internet addresses are allowed.")


class PublicResolver(ThreadedResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        addresses = await super().resolve(host, port, family)
        # Validate the addresses the connector actually uses, avoiding DNS rebinding.
        for address in addresses:
            require_public_address(address["host"])
        return addresses


def validate_download_url(value: str | URL) -> URL:
    try:
        url = URL(value)
        host = url.host
        url.port  # Validate the port before making a request.
    except ValueError:
        raise exceptions.CommandWarning("Invalid download URL.") from None

    if (
        url.scheme not in {"http", "https"}
        or not host
        or url.user is not None
        or url.password is not None
        or "%" in host
    ):
        raise exceptions.CommandWarning(
            "Use a public HTTP or HTTPS URL without credentials."
        )

    try:
        ipaddress.ip_address(host)
    except ValueError:
        # Older aiohttp versions treat legacy numeric IPv4 forms as literals,
        # skipping the resolver even though ipaddress rejects them.
        if ":" in host or host.replace(".", "").isdigit():
            raise exceptions.CommandWarning("Invalid IP address.") from None
        # Other hostnames are validated by PublicResolver when connecting.
    else:
        # aiohttp skips DNS resolution for IP literals, so check these here.
        require_public_address(host)
    return url


@dataclass
class ShazamTrack:
    song: str
    artist: str
    metadata: list
    cover_art: str
    url: str


class Shazam:
    MAX_FILE_SIZE = 25 * 1024 * 1024
    MAX_REDIRECTS = 5

    def __init__(self, bot: MisoBot):
        self.client = ShazamClient()
        self.bot = bot
        self.download_limit = asyncio.Semaphore(2)

    async def recognize_file(self, file: bytes) -> ShazamTrack | None:
        if len(file) > self.MAX_FILE_SIZE:
            raise exceptions.CommandWarning("Shazam files must be at most 25 MiB.")
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
        async with self.download_limit:
            file = await self.download_file(url)
            return await self.recognize_file(file)

    async def download_file(self, url: str) -> bytes:
        current_url = validate_download_url(url)
        try:
            # An isolated session cannot leak the bot's cookies to supplied URLs.
            async with (
                asyncio.timeout(30),
                aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(
                        resolver=PublicResolver(), use_dns_cache=False
                    ),
                    cookie_jar=aiohttp.DummyCookieJar(),
                    timeout=aiohttp.ClientTimeout(total=30, sock_connect=10),
                    headers={"Accept-Encoding": "identity"},
                    auto_decompress=False,
                    trust_env=False,
                ) as session,
            ):
                for _ in range(self.MAX_REDIRECTS + 1):
                    async with session.get(
                        current_url, allow_redirects=False
                    ) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise exceptions.CommandWarning(
                                    "The download returned an invalid redirect."
                                )
                            current_url = validate_download_url(
                                current_url.join(URL(location))
                            )
                            continue

                        response.raise_for_status()
                        if not 200 <= response.status < 300:
                            raise exceptions.CommandWarning(
                                "The URL did not return a file."
                            )
                        if (
                            response.headers.get("Content-Encoding", "identity").lower()
                            != "identity"
                        ):
                            raise exceptions.CommandWarning(
                                "Compressed HTTP responses are not supported."
                            )
                        if (
                            response.content_length is not None
                            and response.content_length > self.MAX_FILE_SIZE
                        ):
                            raise exceptions.CommandWarning(
                                "Shazam files must be at most 25 MiB."
                            )

                        buffer = bytearray()
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            if len(buffer) + len(chunk) > self.MAX_FILE_SIZE:
                                raise exceptions.CommandWarning(
                                    "Shazam files must be at most 25 MiB."
                                )
                            buffer.extend(chunk)
                        return bytes(buffer)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise exceptions.CommandWarning("Unable to download that file.") from None

        raise exceptions.CommandWarning("The download returned too many redirects.")
