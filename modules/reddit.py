# SPDX-FileCopyrightText: 2024 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import arrow
from aiohttp import BasicAuth

from modules import exceptions
from modules.media_embedders import Options

if TYPE_CHECKING:
    from modules.misobot import MisoBot


class RedditError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


@dataclass
class RedditPost:
    videos: list[str]
    caption: str
    media: list[str]
    timestamp: int
    url: str
    subreddit: str


class Reddit:
    API_V1_URL: str = "https://www.reddit.com/api/v1"
    API_OAUTH_URL: str = "https://oauth.reddit.com/api"
    EMOJI = "<:reddit:1184484866520264724>"
    USER_AGENT = "Miso Bot (by Joinemm)"

    def __init__(self, bot: "MisoBot"):
        self.bot = bot
        self.access_token = {
            "expiry": 0,
            "token": None,
        }

    async def autheticate(self):
        now = arrow.utcnow().timestamp()
        async with self.bot.session.post(
            self.API_V1_URL + "/access_token",
            headers={
                "User-Agent": self.USER_AGENT,
            },
            data={
                "grant_type": "client_credentials",
            },
            auth=BasicAuth(
                self.bot.keychain.REDDIT_CLIENT_ID,
                self.bot.keychain.REDDIT_CLIENT_SECRET,
            ),
        ) as response:
            data = await response.json()
            self.access_token = {
                "expiry": now + data["expires_in"],
                "token": data["access_token"],
            }

    async def api_request(self, path: str):
        if self.access_token["expiry"] < arrow.utcnow().timestamp():
            await self.autheticate()

        async with self.bot.session.get(
            self.API_OAUTH_URL + path,
            headers={
                "User-Agent": self.USER_AGENT,
                "Authorization": f"Bearer {self.access_token['token']}",
            },
        ) as response:
            data = await response.json()
            post = data["data"]["children"][0]["data"]

        return post

    async def get_post(
        self,
        reddit_post_id: str,
        options: Options | None = None,
    ):
        post = await self.api_request(f"/info/?id=t3_{reddit_post_id}")

        timestamp = int(post["created"])
        caption = f"{self.EMOJI} `{post['subreddit_name_prefixed']}` <t:{timestamp}:d>"
        if options and options.captions:
            caption += f"\n>>> {post['title']}"

        pictures = []
        videos = []
        if post.get("is_gallery"):
            for item in post["gallery_data"]["items"]:
                meta = post["media_metadata"][item["media_id"]]
                pictures.append(
                    f"https://i.redd.it/{meta['id']}.{meta['m'].split('/')[-1]}"
                )
        elif post["is_reddit_media_domain"]:
            hint = post["post_hint"]
            if hint == "image":
                pictures = [post["url_overridden_by_dest"]]

            elif hint == "hosted:video":
                video_url = post["media"]["reddit_video"]["dash_url"]
                video_path = f"downloads/{reddit_post_id}.mp4"
                Path("downloads").mkdir(exist_ok=True)
                ffmpeg = subprocess.call(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        video_url,
                        "-c",
                        "copy",
                        video_path,
                    ]
                )
                if ffmpeg != 0:
                    raise exceptions.CommandError(
                        "There was an error encoding your video!"
                    )
                videos.append(video_path)

        elif post["is_self"]:
            raise exceptions.CommandWarning(
                f"This is a text post! [`{reddit_post_id}`]"
            )
        elif post["post_hint"] == "link":
            caption += "\n" + post["url"]
        else:
            raise exceptions.CommandWarning(
                f"I don't know what to do with this post! [`{reddit_post_id}`]"
            )

        return RedditPost(
            media=pictures,
            videos=videos,
            caption=caption,
            timestamp=timestamp,
            url=post["permalink"],
            subreddit=post["subreddit"],
        )
