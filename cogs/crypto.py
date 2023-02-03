from decimal import Decimal

import discord
import orjson
from discord.ext import commands

from modules import emojis, exceptions, util
from modules.misobot import MisoBot


class Cryptocurrency(commands.Cog):
    """Cryptocurrency commands"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🪙"
        self.binance_icon = "https://i.imgur.com/i7vdQjQ.png"
        with open("html/candlestick_chart.html", "r", encoding="utf-8") as file:
            self.candlestick_chart_html = file.read()
        self.binance_intervals = [
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "3d",
            "1w",
            "1M",
        ]

    @commands.group()
    async def crypto(self, ctx: commands.Context):
        """Cryptocurrency price data"""
        await util.command_group_help(ctx)

    @crypto.command()
    async def chart(
        self, ctx: commands.Context, coin, pair="USDT", interval="1h", limit: int = 50
    ):
        """Generates candlestick chart for a given cryptocurrency pair"""
        if interval not in self.binance_intervals:
            raise exceptions.CommandError("Invalid interval.")

        if limit > 100:
            raise exceptions.CommandError("Limit must be 100 or less.")

        symbol = (coin + pair).upper()
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with self.bot.session.get(url, params=params) as response:
            data = await response.json(loads=orjson.loads)

        if isinstance(data, dict):
            raise exceptions.CommandError(data.get("msg"))

        candle_data = [str(ticker[:5]) for ticker in data]
        current_price = Decimal(data[-1][4]).normalize()

        replacements = {
            "HEIGHT": 512,
            "TITLE": f"{coin.upper()} / {pair.upper()} | {interval} | {current_price:,f}",
            "DATA": ",".join(candle_data),
        }

        payload = {
            "html": util.format_html(self.candlestick_chart_html, replacements),
            "width": 720,
            "height": 512,
            "imageFormat": "png",
        }
        buffer = await util.render_html(self.bot, payload)
        await ctx.send(file=discord.File(fp=buffer, filename=f"candlestick_{coin}_{pair}.png"))

    @crypto.command()
    async def price(self, ctx: commands.Context, coin, pair="USDT"):
        """See the current price and 24h statistics of cryptocurrency pair"""
        symbol = (coin + pair).upper()
        url = "https://api.binance.com/api/v3/ticker/24hr"
        params = {"symbol": symbol}
        async with self.bot.session.get(url, params=params) as response:
            data = await response.json(loads=orjson.loads)

        if error := data.get("msg"):
            raise exceptions.CommandError(error)

        content = discord.Embed(color=int("f3ba2e", 16))
        content.set_author(
            name=f"{data.get('symbol')} | Binance",
            icon_url=self.binance_icon,
            url=f"https://www.binance.com/en/trade/{data.get('symbol')}",
        )
        content.add_field(
            name="Current price",
            value=f"{Decimal(data.get('lastPrice')).normalize():,f}",
        )
        content.add_field(
            name="24h High", value=f"{Decimal(data.get('highPrice')).normalize():,f}"
        )
        content.add_field(name="24h Low", value=f"{Decimal(data.get('lowPrice')).normalize():,f}")
        pricechange = Decimal(data.get("priceChange")).normalize()
        if pricechange > 0:
            direction = emojis.GREEN_UP
        elif pricechange < 0:
            direction = emojis.RED_DOWN
        else:
            direction = ":white_small_square:"

        change_percent = Decimal(data.get("priceChangePercent")).normalize()

        content.add_field(
            name="24h Change",
            value=f"{direction} {pricechange:,f} ({change_percent:.2f}%)",
        )
        content.add_field(
            name=f"24h Volume ({coin.upper()})",
            value=f"{Decimal(data.get('volume')).normalize():,.2f}",
        )
        content.add_field(
            name=f"24h Volume ({pair.upper()})",
            value=f"{Decimal(data.get('quoteVolume')).normalize():,.2f}",
        )
        await ctx.send(embed=content)


async def setup(bot):
    await bot.add_cog(Cryptocurrency(bot))
