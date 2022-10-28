import arrow
import asyncpraw
import asyncpraw.exceptions
import asyncprawcore
import discord
from asyncpraw.models import Submission, Subreddit
from discord.ext import commands

from modules import emojis, util
from modules.misobot import MisoBot


class RedditError(commands.CommandError):
    pass


class Reddit(commands.Cog):
    """Get reddit content"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "🪧"
        self.timespans = ["all", "day", "hour", "week", "month", "year"]
        self.human_ts = {
            "all": "all-time",
            "day": "daily",
            "hour": "hourly",
            "week": "weekly",
            "month": "monthly",
            "year": "yearly",
        }
        self.client = asyncpraw.Reddit(
            client_id=self.bot.keychain.REDDIT_CLIENT_ID,
            client_secret=self.bot.keychain.REDDIT_CLIENT_SECRET,
            user_agent="discord:miso_bot",
        )

    # COMMANDS

    @commands.group(name="reddit")
    async def reddit(self, ctx: commands.Context):
        """Get content from reddit"""
        await util.command_group_help(ctx)

    @reddit.command(name="random", aliases=["r"])
    async def reddit_random(self, ctx: commands.Context, subreddit, *, options):
        """Get random post from given subreddit"""
        images = "-i" in options
        subreddit = await self.client.subreddit(subreddit.lower())
        try:
            post = await subreddit.random()
        except asyncprawcore.exceptions.NotFound as e:
            if e.response.status == 404:
                return await ctx.send(
                    f":warning: `r/{subreddit}` is either banned or doesn't exist!"
                )
            if e.response.status == 403:
                return await ctx.send(
                    f":warning: `r/{subreddit}` is either quarantined or private!"
                )
            raise e

        if post is None:
            return await ctx.send(
                "Sorry, this subreddit does not support the random post feature!"
            )

        if images:
            i = 0
            while i < 25 or not is_image_post(post):
                post = await subreddit.random()
                i += 1

            if not is_image_post(post):
                return await ctx.send(
                    ":warning: Could not find any image post from this subreddit after 25 tries."
                )

        await self.send_post(ctx, subreddit, post, f"Random post from r/{subreddit}")

    @reddit.command(name="hot", aliases=["h"])
    async def reddit_hot(self, ctx: commands.Context, subreddit, number="1"):
        """Get hot post from given subreddit"""
        if not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit.lower())
        post = await get_n_post(subreddit.hot(), number)

        await self.send_post(ctx, subreddit, post, f"#{number} hottest post from r/{subreddit}")

    @reddit.command(name="controversial", aliases=["c"])
    async def reddit_controversial(
        self, ctx: commands.Context, subreddit, number="1", timespan="all"
    ):
        """Get controversial post from given subreddit"""
        timespan = await self.check_ts(ctx, timespan)
        if timespan is None or not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit.lower())
        post = await get_n_post(subreddit.controversial(timespan), number)

        await self.send_post(
            ctx,
            subreddit,
            post,
            f"#{number} most controversial {self.human_ts[timespan]} post from r/{subreddit}",
        )

    @reddit.command(name="top", aliases=["t"])
    async def reddit_top(self, ctx: commands.Context, subreddit, number="1", timespan="all"):
        """Get top post from given subreddit"""
        timespan = await self.check_ts(ctx, timespan)
        if timespan is None or not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit.lower())
        post = await get_n_post(subreddit.top(timespan), number)

        await self.send_post(
            ctx,
            subreddit,
            post,
            f"#{number} top {self.human_ts[str(timespan)]} post from r/{subreddit}",
        )

    @reddit.command(name="new", aliases=["n"])
    async def reddit_new(self, ctx: commands.Context, subreddit, number="1"):
        """Get new post from given subreddit"""
        if not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit.lower())
        post = await get_n_post(subreddit.new(), number)

        await self.send_post(ctx, subreddit, post, f"#{number} newest post from r/{subreddit}")

    # FUNCTIONS

    async def send_post(self, ctx: commands.Context, subreddit, post, footer=""):
        """Checks for eligibility for sending submission and sends it"""
        try:
            await subreddit.load()
        except asyncpraw.exceptions.AsyncPRAWException as e:
            if str(subreddit) != "all":
                raise e

        if not can_send_nsfw(ctx, subreddit):
            return await ctx.send(
                ":underage: NSFW subreddits can only be viewed in an NSFW channel!"
            )

        censor = (
            ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.abc.GuildChannel) else False
        )
        content, message_content = await self.render_submission(post, censor)
        content.set_footer(text=footer)
        await ctx.send(embed=content)
        if message_content is not None:
            await ctx.send(message_content)

    @staticmethod
    async def render_submission(submission, censor=True):
        """Turns reddit submission into a discord embed"""
        message_text = None
        content = discord.Embed()
        content.title = (
            f"`[{submission.link_flair_text}]` "
            if hasattr(submission, "link_flair_text") and submission.link_flair_text is not None
            else ""
        )
        content.title += submission.title[:256]
        content.timestamp = arrow.get(submission.created_utc).datetime

        redditor = submission.author
        if redditor is None:
            # deleted user
            content.set_author(name="[deleted]")
        else:
            await redditor.load()
            content.set_author(
                name=f"u/{redditor.name}",
                url=f"https://old.reddit.com/u/{redditor.name}",
                icon_url=(redditor.icon_img if hasattr(redditor, "icon_img") else None),
            )

        suffix_elements = [
            f"{emojis.UPVOTE} {submission.score} ({int(submission.upvote_ratio*100)}%)",
            f"{submission.num_comments} comment" + ("s" if submission.num_comments > 1 else ""),
            f"[Permalink](https://old.reddit.com{submission.permalink})",
        ]
        suffix = "\n\n**" + " | ".join(suffix_elements) + "**"

        if submission.is_self:
            submission.selftext = submission.selftext.replace("&#x200B;", "")
            if len(submission.selftext + suffix) > 2044:
                content.description = submission.selftext[: (2044 - len(suffix) - 3)] + "..."
            else:
                content.description = submission.selftext
        else:
            hide = submission.spoiler or (submission.over_18 and censor)
            content.description = ""
            if not hide and is_image_post(submission):
                content.set_image(url=submission.url)
            else:
                url = submission.url
                if hide:
                    url = "||" + url + "||"
                if self_embeds(submission.url):
                    message_text = url
                else:
                    content.description = url

        content.description.strip()
        if submission.over_18:
            content.title = "`[NSFW]` " + content.title

        elif submission.spoiler:
            content.title = "`[SPOILER]` " + content.title

        if submission.is_self and ((censor and submission.over_18) or submission.spoiler):
            content.description = "||" + content.description + "||"

        content.description = (content.description or "") + suffix
        return content, message_text

    async def check_ts(self, ctx: commands.Context, timespan):
        """Validates timespan argument"""
        timespan = timespan.lower()
        if timespan not in self.timespans:
            await ctx.send(
                f":warning: Invalid timespan `{timespan}` please use one of: `{self.timespans}`"
            )
            return None
        return timespan

    @staticmethod
    async def check_n(ctx: commands.Context, number):
        """Validates number argument"""
        try:
            number = int(number)
        except ValueError:
            await ctx.send(f":warning: `number` must be an integer, not `{number}`")
            return False

        if number < 1 or number > 50:
            await ctx.send(":warning: `number` must be between `1` and `50`")
            return False
        return True


async def get_n_post(gen, n, ignore_sticky=True):
    """Gets the n:th submission from given PRAW ListingGenerator"""
    n = int(n)
    i = 1
    try:
        async for post in gen:
            if post.stickied and ignore_sticky:
                n += 1
            if i >= n:
                return post
            i += 1
    except asyncprawcore.exceptions.Redirect:
        raise RedditError("this subreddit doesn't seem to exist!")


def is_image_post(submission):
    """is submission content embedable image"""
    return (not submission.is_self) and submission.url.endswith((".png", ".jpg", ".jpeg", ".gif"))


def self_embeds(url):
    """Does this url generate a usable embed on it's own when sent on discord?"""
    return (
        url.startswith("https://www.youtube.com")
        or url.startswith("https://youtu.be")
        or url.startswith("https://imgur.com")
        or url.startswith("https://www.imgur.com")
        or url.startswith("https://gfycat.com")
        or url.startswith("https://www.gfycat.com")
        or url.startswith("https://redgifs.com")
        or url.startswith("https://www.redgifs.com")
    )


def can_send_nsfw(ctx, content):
    """Checks whether content is NSFW and if so whether it can be sent in current channel"""
    if isinstance(content, Submission):
        is_nsfw = content.over_18
    elif isinstance(content, Subreddit):
        is_nsfw = content.over18
    else:
        return True

    if is_nsfw:
        return ctx.channel.is_nsfw()
    return True


async def setup(bot):
    await bot.add_cog(Reddit(bot))
