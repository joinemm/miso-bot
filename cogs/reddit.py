import discord
import arrow
import asyncpraw
import os
from discord.ext import commands
from helpers import emojis, utilityfunctions as util


CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")


class Reddit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
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
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, user_agent="discord:miso_bot"
        )

    # COMMANDS

    @commands.group(name="reddit")
    async def reddit(self, ctx):
        """Reddit commands."""
        await util.command_group_help(ctx)

    @reddit.command(name="random", aliases=["r"])
    async def reddit_random(self, ctx, subreddit):
        """Get random post from given subreddit."""
        subreddit = await self.client.subreddit(subreddit)
        post = await subreddit.random()
        if post is None:
            return await ctx.send(
                "Sorry, this subreddit does not support the random post feature!"
            )

        await self.send_post(ctx, subreddit, post)

    @reddit.command(name="hot", aliases=["h"])
    async def reddit_hot(self, ctx, subreddit, number="1"):
        """Get hot post from given subreddit."""
        if not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit)
        post = await get_n_post(subreddit.hot(), number)

        await self.send_post(ctx, subreddit, post, f"#{number} hottest post from r/{subreddit}")

    @reddit.command(name="controversial", aliases=["c"])
    async def reddit_controversial(self, ctx, subreddit, number="1", timespan="all"):
        """Get controversial post from given subreddit."""
        timespan = await self.check_ts(ctx, timespan)
        if timespan is None or not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit)
        post = await get_n_post(subreddit.controversial(timespan), number)

        await self.send_post(
            ctx,
            subreddit,
            post,
            f"#{number} most controversial {self.human_ts[timespan]} post from r/{subreddit}",
        )

    @reddit.command(name="top", aliases=["t"])
    async def reddit_top(self, ctx, subreddit, number="1", timespan="all"):
        """Get top post from given subreddit."""
        timespan = await self.check_ts(ctx, timespan)
        if timespan is None or not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit)
        post = await get_n_post(subreddit.top(timespan), number)

        await self.send_post(
            ctx,
            subreddit,
            post,
            f"#{number} top {self.human_ts[timespan]} post from r/{subreddit}",
        )

    @reddit.command(name="new", aliases=["n"])
    async def reddit_new(self, ctx, subreddit, number="1"):
        """Get new post from given subreddit."""
        if not await self.check_n(ctx, number):
            return

        subreddit = await self.client.subreddit(subreddit)
        post = await get_n_post(subreddit.new(), number)

        await self.send_post(ctx, subreddit, post, f"#{number} newest post from r/{subreddit}")

    # FUNCTIONS

    async def send_post(self, ctx, subreddit, post, footer=""):
        """Checks for eligibility for sending submission and sends it."""
        try:
            await subreddit.load()
            if not can_send_nsfw(ctx, subreddit):
                return await ctx.send(
                    ":underage: NSFW subreddits can only be viewed in an NSFW channel!"
                )
        except Exception:
            pass

        content = await self.render_submission(post, not ctx.channel.is_nsfw())
        content.set_footer(text=footer)
        await ctx.send(embed=content)

    async def render_submission(self, submission, censor=True):
        """Turns reddit submission into a discord embed."""
        content = discord.Embed()
        content.title = (
            f"`[{submission.link_flair_text}]` " if submission.link_flair_text is not None else ""
        )
        content.title += submission.title
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
                icon_url=redditor.icon_img,
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
            if submission.spoiler or (submission.over_18 and censor):
                content.description = "||" + submission.url + "||"
            elif submission.url.endswith((".png", ".jpg", ".jpeg", ".gif")):
                content.set_image(url=submission.url)
                content.description = ""
            else:
                content.description = submission.url

        content.description.strip()
        if submission.over_18:
            content.title = "`[NSFW]` " + content.title
            if submission.is_self and censor:
                content.description = "||" + content.description + "||"

        elif submission.spoiler:
            content.title = "`[SPOILER]` " + content.title
            if submission.is_self:
                content.description = "||" + content.description + "||"

        content.description += suffix
        return content

    async def check_ts(self, ctx, timespan):
        """Validates timespan argument."""
        timespan = timespan.lower()
        if timespan not in self.timespans:
            await ctx.send(
                f":warning: Invalid timespan `{timespan}` please use one of: `{self.timespans}`"
            )
            return None
        return timespan

    async def check_n(self, ctx, number):
        """Validates number argument."""
        try:
            number = int(number)
        except ValueError:
            await ctx.send(f":warning: `number` must be an integer, not `{number}`")
            return False

        if number < 1 or number > 50:
            await ctx.send(":warning: `number` must be between `1` and `50`")
            return False
        else:
            return True


async def get_n_post(gen, n, ignore_sticky=True):
    """Gets the n:th submission from given PRAW ListingGenerator."""
    n = int(n)
    i = 1
    async for post in gen:
        if post.stickied and ignore_sticky:
            n += 1
        if i >= n:
            return post
        else:
            i += 1


def can_send_nsfw(ctx, content):
    """Checks whether content is NSFW and if so whether it can be sent in current channel."""
    if isinstance(content, asyncpraw.models.Submission):
        is_nsfw = content.over_18
    elif isinstance(content, asyncpraw.models.Subreddit):
        is_nsfw = content.over18
    else:
        return True

    if is_nsfw:
        return ctx.channel.is_nsfw()
    else:
        return True


def setup(bot):
    bot.add_cog(Reddit(bot))
