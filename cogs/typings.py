import discord
import random
import asyncio
import arrow
import json
from discord.ext import commands
from operator import itemgetter
from modules import util, exceptions


class Typings(commands.Cog):
    """Typing speed tests"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "⌨️"
        self.separators = [" ", " ", " ", "  ", "  ", " "]
        self.font = "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"

    def obfuscate(self, text):
        while " " in text:
            text = text.replace(" ", random.choice(self.separators), 1)
        letter_dict = dict(zip("abcdefghijklmnopqrstuvwxyz", self.font))
        return "".join(letter_dict.get(letter, letter) for letter in text)

    def anticheat(self, message):
        remainder = "".join(
            set(message.content).intersection(self.font + "".join(self.separators))
        )
        return remainder != ""

    @commands.group()
    async def typing(self, ctx):
        """Test your typing speed."""
        await util.command_group_help(ctx)

    @typing.command(name="test")
    async def typing_test(self, ctx, language=None, wordcount: int = 25):
        """Take a typing test and see your typing speed."""
        if language is None:
            language = wordcount
        try:
            wordcount = int(language)
            language = "english"
        except ValueError:
            pass

        if wordcount < 10:
            return await ctx.send("Minimum word count is 10!")
        if wordcount > 250:
            return await ctx.send("Maximum word count is 250!")

        wordlist = get_wordlist(wordcount, language)
        if wordlist[0] is None:
            langs = "\n".join(wordlist[1])
            return await ctx.send(
                f"Unsupported language `{language}`.\n"
                f"Currently supported languages are:\n>>> {langs}"
            )

        og_msg = await ctx.send(f"```\n{self.obfuscate(' '.join(wordlist))}\n```")

        def check(_message):
            return _message.author == ctx.author and _message.channel == ctx.channel

        try:
            message = await self.bot.wait_for("message", timeout=300.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Too slow.")

        else:
            wpm, accuracy, not_long_enough = calculate_entry(message, og_msg, wordlist)
            if self.anticheat(message) or wpm > 216:
                return await ctx.send(f"{ctx.author.mention} Stop cheating >:(")

            if not_long_enough:
                await ctx.send(
                    ":warning: `score not valid, you must type at least 90% of the words`"
                )
            else:
                await ctx.send(f"{ctx.author.mention} **{int(wpm)} WPM / {int(accuracy)}% ACC**")
                await self.save_wpm(
                    ctx.author, ctx.guild, wpm, accuracy, wordcount, language, False
                )

    @typing.command(name="race")
    async def typing_race(self, ctx, language=None, wordcount: int = 25):
        """Race against other people."""
        if language is None:
            language = wordcount
        try:
            wordcount = int(language)
            language = "english"
        except ValueError:
            pass

        if wordcount < 10:
            return await ctx.send("Minimum word count is 10!")
        if wordcount > 250:
            return await ctx.send("Maximum word count is 250!")

        content = discord.Embed(
            title=f":keyboard:  Starting a new typing race | {wordcount} words",
            color=discord.Color.gold(),
        )
        content.description = (
            "React with :notepad_spiral: to enter the race.\n"
            "React with :white_check_mark: to start the race."
        )

        content.add_field(name="Participants", value=f"**{ctx.author}**")
        enter_message = await ctx.send(embed=content)

        note_emoji = "🗒"
        check_emoji = "✅"

        players = set()
        players.add(ctx.author)
        race_in_progress = False

        await enter_message.add_reaction(note_emoji)
        await enter_message.add_reaction(check_emoji)

        def check(_reaction, _user):
            return (
                _reaction.message.id == enter_message.id
                and _reaction.emoji in [note_emoji, check_emoji]
                and not _user == ctx.bot.user
            )

        while not race_in_progress:
            try:
                reaction, user = await ctx.bot.wait_for("reaction_add", timeout=300.0, check=check)
            except asyncio.TimeoutError:
                try:
                    for emoji in [note_emoji, check_emoji]:
                        await enter_message.remove_reaction(emoji, ctx.bot.user)
                except discord.errors.NotFound:
                    pass
                except discord.errors.Forbidden:
                    await ctx.send(
                        "`error: i'm missing required discord permission [ manage messages ]`"
                    )
                break
            else:
                if reaction.emoji == note_emoji:
                    if user in players:
                        continue
                    players.add(user)
                    content.remove_field(0)
                    content.add_field(
                        name="Participants",
                        value="\n".join(f"**{util.displayname(x)}**" for x in players),
                    )
                    await enter_message.edit(embed=content)
                elif reaction.emoji == check_emoji:
                    if user == ctx.author:
                        if len(players) < 2:
                            cant_race_alone = await ctx.send("You can't race alone!")
                            await asyncio.sleep(1)
                            try:
                                await cant_race_alone.delete()
                                await enter_message.remove_reaction(check_emoji, user)
                            except discord.errors.Forbidden:
                                await ctx.send(
                                    "`error: i'm missing required discord permission [ manage messages ]`"
                                )
                        else:
                            race_in_progress = True
                    else:
                        await enter_message.remove_reaction(check_emoji, user)

        if not race_in_progress:
            content.remove_field(0)
            content.add_field(name="Race timed out", value="Not enough players")
            return await enter_message.edit(embed=content)

        words_message = await ctx.send("Starting race in 3...")
        i = 2
        while i > 0:
            await asyncio.sleep(1)
            await words_message.edit(content=f"Starting race in {i}...")
            i -= 1

        await asyncio.sleep(1)

        wordlist = get_wordlist(wordcount, language)
        if wordlist[0] is None:
            langs = "\n".join(wordlist[1])
            return await ctx.send(
                f"Unsupported language `{language}`.\n"
                f"Currently supported languages are:\n>>> {langs}"
            )

        await words_message.edit(content=f"```\n{self.obfuscate(' '.join(wordlist))}\n```")

        tasks = []
        for player in players:
            tasks.append(
                self.race_user_results_waiter(
                    ctx, player, words_message, wordlist, wordcount, language
                )
            )

        results = await asyncio.gather(*tasks)

        content = discord.Embed(
            title=":checkered_flag: Race complete!", color=discord.Color.green()
        )
        rows = []
        values = []
        for i, (player, score) in enumerate(
            sorted(results, key=itemgetter(1), reverse=True), start=1
        ):
            values.append((ctx.guild.id, player.id, 1, 1 if i == 1 else 0))
            rows.append(
                f"{f'`#{i:2}`' if i > 1 else ':crown:'} {util.displayname(player)} — "
                + (f"**{int(score)} WPM**" if score != 0 else ":o:")
            )

        await self.bot.db.executemany(
            """
            INSERT INTO typing_race(guild_id, user_id, race_count, win_count)
                VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                race_count = race_count + 1,
                win_count = win_count + VALUES(win_count)
            """,
            tuple(values),
        )

        await util.send_as_pages(ctx, content, rows)

    async def race_user_results_waiter(
        self, ctx, player, words_message, wordlist, wordcount, language
    ):
        def progress_check(_message):
            return _message.author == player and _message.channel == ctx.channel

        try:
            message = await self.bot.wait_for("message", timeout=300.0, check=progress_check)
        except asyncio.TimeoutError:
            ctx.send(f"{player.mention} too slow!")
            return player, 0
        else:
            wpm, accuracy, not_long_enough = calculate_entry(message, words_message, wordlist)
            if self.anticheat(message) or wpm > 216:
                await ctx.send(f"{message.author.mention} Stop cheating >:(")
                return player, 0

            if not_long_enough:
                await ctx.send(
                    f"{message.author.mention} :warning: `score not valid, you must type at least 90% of the words`"
                )
                return player, 0
            else:
                await ctx.send(
                    f"{message.author.mention} **{int(wpm)} WPM / {int(accuracy)}% ACC**"
                )
                await self.save_wpm(
                    message.author, ctx.guild, wpm, accuracy, wordcount, language, True
                )
                return player, wpm

    @typing.command(name="history")
    async def typing_history(self, ctx, user: discord.Member = None):
        """See your typing test history."""
        if user is None:
            user = ctx.author

        data = await self.bot.db.execute(
            """
            SELECT test_date, wpm, accuracy, word_count, test_language FROM typing_stats
            WHERE user_id = %s ORDER BY test_date DESC
            """,
            user.id,
        )
        if not data:
            raise exceptions.Info(
                ("You haven't" if user is ctx.author else f"**{user.name}** hasn't")
                + " taken any typing tests yet!",
            )

        content = discord.Embed(
            title=f":stopwatch: Typing history for {user.name}",
            color=int("dd2e44", 16),
        )
        content.set_footer(text=f"Total {len(data)} typing tests taken")
        rows = []
        for test_date, wpm, accuracy, word_count, test_language in data:
            rows.append(
                f"**{wpm}** WPM, **{int(accuracy)}%** ACC, "
                f"**{word_count}** words, *{test_language}* ({arrow.get(test_date).to('utc').humanize()})"
            )

        await util.send_as_pages(ctx, content, rows)

    @typing.command(name="cleardata")
    async def typing_clear(self, ctx):
        """Clear your typing data."""
        content = discord.Embed(title=":warning: Are you sure?", color=int("ffcc4d", 16))
        content.description = (
            "This action will delete *all* of your saved typing data and is **irreversible**."
        )
        msg = await ctx.send(embed=content)

        async def confirm():
            await self.bot.db.execute("DELETE FROM typing_stats WHERE user_id = %s", ctx.author.id)
            await self.bot.db.execute("DELETE FROM typing_race WHERE user_id = %s", ctx.author.id)
            content.title = ":white_check_mark: Cleared your data"
            content.description = ""
            await msg.edit(embed=content)

        async def cancel():
            content.title = ":x: Action cancelled"
            content.description = ""
            await msg.edit(embed=content)

        functions = {"✅": confirm, "❌": cancel}
        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, functions, only_author=True, single_use=True)
        )

    @typing.command(name="stats")
    async def typing_stats(self, ctx, user: discord.Member = None):
        """See your typing test statistics."""
        if user is None:
            user = ctx.author

        data = await self.bot.db.execute(
            """
            SELECT COUNT(test_date), MAX(wpm), AVG(wpm), AVG(accuracy), race_count, win_count
            FROM typing_stats LEFT JOIN typing_race ON typing_stats.user_id = typing_race.user_id
            WHERE typing_stats.user_id = %s GROUP BY typing_stats.user_id
            """,
            user.id,
            one_row=True,
        )
        if not data:
            raise exceptions.Info(
                ("You haven't" if user is ctx.author else f"**{user.name}** hasn't")
                + " taken any typing tests yet!",
            )

        test_count, max_wpm, avg_wpm, avg_acc, race_count, win_count = data
        content = discord.Embed(
            title=f":bar_chart: Typing stats for {user.name}", color=int("3b94d9", 16)
        )
        content.description = (
            f"Best WPM: **{max_wpm}**\n"
            f"Average WPM: **{int(avg_wpm)}**\n"
            f"Average Accuracy: **{avg_acc:.2f}%**\n"
            f"Tests taken: **{test_count}** of which **{race_count}** were races\n"
            f"Races won: **{win_count or 0}** "
            + (
                f"(**{(win_count/race_count)*100:.1f}%** win rate)"
                if race_count is not None
                else ""
            )
        )

        await ctx.send(embed=content)

    async def save_wpm(self, user, guild, wpm, accuracy, wordcount, language, was_race):
        if wpm == 0:
            return

        await self.bot.db.execute(
            """
            INSERT INTO typing_stats (
                user_id, guild_id, test_date, wpm,
                accuracy, word_count, test_language, was_race
            )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            user.id,
            guild.id if guild is not None else None,
            arrow.utcnow().datetime,
            int(wpm),
            accuracy,
            wordcount,
            language,
            was_race,
        )


def setup(bot):
    bot.add_cog(Typings(bot))


def get_wordlist(wordcount, language):
    with open("data/wordlist.json") as f:
        data = json.load(f)
        all_words = data.get(language.lower())
        if all_words is None:
            return None, [str(lang) for lang in data]
    wordlist = []
    while len(wordlist) < wordcount:
        word = random.choice(all_words)
        if not wordlist or not wordlist[-1] == word:
            wordlist.append(word)
    return wordlist


def calculate_entry(message, words_message, wordlist):
    time = message.created_at - words_message.created_at
    user_words = message.content.lower().split()
    total_keys = 0
    corrent_keys = 0
    for i, correct_word in enumerate(wordlist):
        correct_word = correct_word.lower()
        total_keys += len(correct_word) + 1
        offset = 0 if i == len(user_words) - 1 else -1

        try:
            user_word = user_words[i]
        except IndexError:
            # user message out of words, but still keep looping correct words for total key count
            continue
        else:
            while user_word != correct_word and offset < 3:
                k = i - offset
                print(k)
                if k < 0:
                    k = 0
                user_word = user_words[k]
                offset += 1

            if user_word == correct_word:
                corrent_keys += len(correct_word) + 1

    wpm = (corrent_keys / 5) / (time.total_seconds() / 60)
    accuracy = (corrent_keys / total_keys) * 100
    not_long_enough = len(user_words) / len(wordlist) < 0.9
    return wpm, accuracy, not_long_enough
