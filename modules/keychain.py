import os

from modules.log import get_logger

logger = get_logger(__name__)


class Keychain:
    def __init__(self):

        self.TWITTER_BEARER_TOKEN: str = ""
        self.NAVER_APPID: str = ""
        self.NAVER_TOKEN: str = ""
        self.LASTFM_API_KEY: str = ""
        self.LASTFM_SECRET: str = ""
        self.TIMEZONEDB_API_KEY: str = ""
        self.GCS_DEVELOPER_KEY: str = ""
        self.WOLFRAM_APPID: str = ""
        self.GFYCAT_CLIENT_ID: str = ""
        self.GFYCAT_SECRET: str = ""
        self.STREAMABLE_USER: str = ""
        self.STREAMABLE_PASSWORD: str = ""
        self.THESAURUS_KEY: str = ""
        self.THESAURUS_INTERMEDIATE_KEY: str = ""
        self.FINNHUB_TOKEN: str = ""
        self.REDDIT_CLIENT_ID: str = ""
        self.REDDIT_CLIENT_SECRET: str = ""
        self.RAPIDAPI_KEY: str = ""
        self.TOMORROWIO_TOKEN: str = ""
        self.AWS_ACCESS_KEY: str = ""
        self.AWS_ACCESS_SECRET: str = ""
        self.DATALAMA_ACCESS_KEY: str = ""
        self.PROXY_URL: str = ""
        self.PROXY_USER: str = ""
        self.PROXY_PASS: str = ""
        self.IG_COOKIE: str = ""

        for name in self.__dict__.keys():
            value = os.environ.get(name)
            optional = [
                "PROXY_URL",
                "PROXY_USER",
                "PROXY_PASS",
                "IG_COOKIE",
            ]
            if not value and name not in optional:
                logger.warning(f'No value set for env variable "{name}"')

            setattr(self, name, value)
