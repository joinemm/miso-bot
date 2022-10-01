import os

from modules.log import get_logger

logger = get_logger(__name__)


class Keychain:

    KEYS = [
        "TWITTER_CONSUMER_KEY",
        "TWITTER_CONSUMER_SECRET",
        "NAVER_APPID",
        "NAVER_TOKEN",
        "LASTFM_API_KEY",
        "LASTFM_SECRET",
        "TIMEZONEDB_API_KEY",
        "GCS_DEVELOPER_KEY",
        "WOLFRAM_APPID",
        "GFYCAT_CLIENT_ID",
        "GFYCAT_SECRET",
        "STREAMABLE_USER",
        "STREAMABLE_PASSWORD",
        "THESAURUS_KEY",
        "THESAURUS_INTERMEDIATE_KEY",
        "FINNHUB_TOKEN",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "RAPIDAPI_KEY",
        "TOMORROWIO_TOKEN",
        "AWS_ACCESS_KEY",
        "AWS_ACCESS_SECRET",
        "PROXY_URL",
        "PROXY_USER",
        "PROXY_PASS",
        "IG_COOKIE",
        "DATALAMA_ACCESS_KEY",
    ]

    OPTIONAL = [
        "PROXY_URL",
        "PROXY_USER",
        "PROXY_PASS",
    ]

    def __init__(self):
        for name in self.KEYS:
            value = os.environ.get(name)
            if not value and name not in self.OPTIONAL:
                logger.warning(f'No value set for env variable "{name}"')

            setattr(self, name, value)
