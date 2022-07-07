import discord

from modules.misobot import MisoBot


class ProxiedBot(MisoBot):
    # def __init__(self, **kwargs):
    #     # self.cluster_name = kwargs.pop("cluster_name")
    #     self.cluster_id = kwargs.pop("cluster_id")
    #     super().__init__(**kwargs)

    #     self.run(kwargs["token"])

    # async def on_ready(self):
    #     self.log.info(f"Cluster {self.cluster_id} ready")

    # async def on_shard_ready(self, shard_id):
    #     self.log.info(f"Shard {shard_id} ready")

    async def before_identify_hook(self, shard_id, *, initial):
        pass

    def is_ws_ratelimited(self):
        return False


def patch_with_gateway(gateway_url):
    class ProxyHTTPClient(discord.http.HTTPClient):
        async def get_gateway(self, **_):
            return f"{gateway_url}?encoding=json&v=9"

        async def get_bot_gateway(self, **_):
            try:
                data = await self.request(discord.http.Route("GET", "/gateway/bot"))
            except discord.HTTPException as exc:
                raise discord.GatewayNotFound() from exc
            return data["shards"], f"{gateway_url}?encoding=json&v=9"

    class ProxyDiscordWebSocket(discord.gateway.DiscordWebSocket):
        def is_ratelimited(self):
            return False

    class ProxyReconnectWebSocket(Exception):
        def __init__(self, shard_id, *, resume=False):
            self.shard_id = shard_id
            self.resume = False
            self.op = "IDENTIFY"

    discord.http.HTTPClient.get_gateway = ProxyHTTPClient.get_gateway
    discord.http.HTTPClient.get_bot_gateway = ProxyHTTPClient.get_bot_gateway
    discord.http._set_api_version(9)
    discord.gateway.DiscordWebSocket.is_ratelimited = ProxyDiscordWebSocket.is_ratelimited
    discord.gateway.ReconnectWebSocket.__init__ = ProxyReconnectWebSocket.__init__
