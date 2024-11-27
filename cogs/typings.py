# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import asyncio
import json
import random
from operator import itemgetter

import arrow
import discord
from discord.ext import commands

from modules import exceptions, util
from modules.misobot import MisoBot
from modules.ui import RowPaginator


class Typings(commands.Cog):
    """Test your typing speed"""

    def __init__(self, bot):
        self.bot: MisoBot = bot
        self.icon = "⌨️"
        self.separators = [" ", " ", " ", "  ", "  ", " "]
        self.font = "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"
        with open("data/wordlist.json") as f:
            self.languages = json.load(f)

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

    @commands.group(case_insensitive=True)
    async def typing(self, ctx: commands.Context):
        """Test your typing speed"""
        await util.command_group_help(ctx)

    @typing.command(name="test")
    async def typing_test(
        self, ctx: commands.Context, language=None, wordcount: int = 25
    ):
        """Take a typing test"""
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

        wordlist = self.get_wordlist(wordcount, language)
        if wordlist[0] is None:
            langs = ", ".join(wordlist[1])
            return await ctx.send(
                f"Unsupported language `{language}`.\n"
                f"Currently supported languages are:\n>>> {langs}"
            )

        words_message = await ctx.reply(
            f"```\n{self.obfuscate(' '.join(wordlist))}\n```"
        )

        def check(_message):
            return _message.author == ctx.author and _message.channel == ctx.channel

        try:
            message = await self.bot.wait_for("message", timeout=300.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send(f"{ctx.author.mention} Too slow.")

        wpm, accuracy, not_long_enough = calculate_entry(
            message, words_message, wordlist
        )
        if self.anticheat(message) or wpm > 300:
            return await message.reply("Stop cheating >:(")

        if not_long_enough:
            await message.reply(
                ":warning: `score not valid, you must type at least 90% of the words`"
            )
        else:
            await message.reply(f"**{int(wpm)} WPM / {int(accuracy)}% Accuracy**")
            await self.save_wpm(
                ctx.author, ctx.guild, wpm, accuracy, wordcount, language, False
            )

    @typing.command(name="race")
    async def typing_race(
        self, ctx: commands.Context, language=None, wordcount: int = 25
    ):
        """Challenge your friends into a typing race"""
        if ctx.guild is None:
            raise exceptions.CommandError("Unable to get current guild")

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

        wordlist = self.get_wordlist(wordcount, language)
        if wordlist[0] is None:
            langs = ", ".join(wordlist[1])
            return await ctx.send(
                f"Unsupported language `{language}`.\n"
                f"Currently supported languages are:\n>>> {langs}"
            )

        content = discord.Embed(
            title=f":rocket: Starting a new typing race | {wordcount} words",
            color=int("55acee", 16),
        )
        content.description = (
            "React with :notepad_spiral: to enter the race.\n"
            "React with :white_check_mark: to start the race."
        )

        content.add_field(
            name="Participants", value=f"**{util.displayname(ctx.author)}**"
        )
        enter_message = await ctx.send(embed=content)

        note_emoji = "🗒"
        check_emoji = "✅"

        players = {ctx.author}
        race_in_progress = False

        await enter_message.add_reaction(note_emoji)
        await enter_message.add_reaction(check_emoji)

        def check(_reaction, _user):
            return (
                _reaction.message.id == enter_message.id
                and _reaction.emoji in [note_emoji, check_emoji]
                and _user != ctx.bot.user
            )

        while not race_in_progress:
            try:
                reaction, user = await ctx.bot.wait_for(
                    "reaction_add", timeout=120.0, check=check
                )
            except asyncio.TimeoutError:
                try:
                    for emoji in [note_emoji, check_emoji]:
                        asyncio.ensure_future(
                            enter_message.remove_reaction(emoji, ctx.bot.user)
                        )
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    pass
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
                            await cant_race_alone.delete()
                            await enter_message.remove_reaction(check_emoji, user)
                        else:
                            race_in_progress = True
                    else:
                        await enter_message.remove_reaction(check_emoji, user)

        if not race_in_progress:
            content.remove_field(0)
            content.description = ""
            content.add_field(name="Race timed out", value="2 minutes passed")
            return await enter_message.edit(embed=content)

        words_message = await ctx.send("Starting race in 3...")
        i = 2
        while i > 0:
            await asyncio.sleep(1)
            await words_message.edit(content=f"Starting race in {i}...")
            i -= 1

        await asyncio.sleep(1)

        await words_message.delete()
        words_message = await ctx.send(
            f"```\n{self.obfuscate(' '.join(wordlist))}\n```"
        )

        tasks = []
        for player in players:
            tasks.append(
                self.race_user_results_waiter(
                    ctx, player, words_message, wordlist, wordcount, language
                )
            )

        results = await asyncio.gather(*tasks)

        content = discord.Embed(
            title=":checkered_flag: Race complete!", color=int("e1e8ed", 16)
        )
        rows = []
        values = []
        player: discord.Member
        for i, (player, wpm, accuracy) in enumerate(
            sorted(results, key=itemgetter(1), reverse=True), start=1
        ):
            values.append((ctx.guild.id, player.id, 1, 1 if i == 1 else 0))
            rows.append(
                f"{f'`#{i}`' if i > 1 else ':trophy:'} **{util.displayname(player)}** — "
                + (
                    f"**{int(wpm)} WPM / {int(accuracy)}% Accuracy**"
                    if wpm != 0
                    else ":x:"
                )
            )

        await self.bot.db.executemany(
            """
            INSERT INTO typing_race(guild_id, user_id, race_count, win_count)
                VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                race_count = race_count + 1,
                win_count = win_count + VALUES(win_count)
            """,
            values,
        )

        await RowPaginator(content, rows).run(ctx)

    async def race_user_results_waiter(
        self, ctx, player, words_message, wordlist, wordcount, language
    ):
        def progress_check(_message):
            return _message.author == player and _message.channel == ctx.channel

        try:
            message = await self.bot.wait_for(
                "message", timeout=300.0, check=progress_check
            )
        except asyncio.TimeoutError:
            await ctx.send(f"{player.mention} too slow!")
            return player, 0, 0

        wpm, accuracy, not_long_enough = calculate_entry(
            message, words_message, wordlist
        )
        if self.anticheat(message) or wpm > 300:
            await message.reply("Stop cheating >:(")
            return player, 0, 0

        if not_long_enough:
            await message.reply(
                ":warning: `score not valid, you must type at least 90% of the words`"
            )
            return player, 0, 0
        await message.add_reaction("✅")
        await self.save_wpm(
            message.author,
            ctx.guild,
            wpm,
            accuracy,
            wordcount,
            language,
            True,
        )
        return player, wpm, accuracy

    @typing.command(name="history")
    async def typing_history(
        self, ctx: commands.Context, member: discord.Member | discord.User | None = None
    ):
        """See your typing test history"""
        if member is None:
            member = ctx.author

        data = await self.bot.db.fetch(
            """
            SELECT test_date, wpm, accuracy, word_count, test_language FROM typing_stats
            WHERE user_id = %s ORDER BY test_date DESC
            """,
            member.id,
        )
        if not data:
            raise exceptions.CommandInfo(
                ("You haven't" if member is ctx.author else f"**{member.name}** hasn't")
                + " taken any typing tests yet!",
            )

        content = discord.Embed(
            title=f":stopwatch: {member.display_name} Typing test history",
            color=int("dd2e44", 16),
        )
        content.set_footer(text=f"Total {len(data)} typing tests taken")
        rows = [
            f"**{wpm}** WPM, **{int(accuracy)}%** ACC, **{word_count}** words, "
            f"*{test_language}* ({arrow.get(test_date).to('utc').humanize()})"
            for test_date, wpm, accuracy, word_count, test_language in data
        ]
        await RowPaginator(content, rows).run(ctx)

    @typing.command(name="cleardata")
    async def typing_clear(self, ctx: commands.Context):
        """Clear your typing data"""
        content = discord.Embed(
            title=":warning: Are you sure?", color=int("ffcc4d", 16)
        )
        content.description = "This action will delete *all* of your saved typing data and is **irreversible**."
        msg = await ctx.send(embed=content)

        async def confirm():
            await self.bot.db.execute(
                """
                DELETE FROM typing_stats WHERE user_id = %s
                """,
                ctx.author.id,
            )
            await self.bot.db.execute(
                """
                DELETE FROM typing_race WHERE user_id = %s
                """,
                ctx.author.id,
            )
            content.title = ":white_check_mark: Cleared your data"
            content.color = int("77b255", 16)
            content.description = ""
            await msg.edit(embed=content)

        async def cancel():
            content.title = ":x: Action cancelled"
            content.description = ""
            content.color = int("dd2e44", 16)
            await msg.edit(embed=content)

        functions = {"✅": confirm, "❌": cancel}
        asyncio.ensure_future(
            util.reaction_buttons(
                ctx, msg, functions, only_author=True, single_use=True
            )
        )

    @typing.command(name="stats")
    async def typing_stats(
        self, ctx: commands.Context, user: discord.Member | discord.User | None = None
    ):
        """See your typing statistics"""
        if user is None:
            user = ctx.author

        data = await self.bot.db.fetch_row(
            """
            SELECT COUNT(test_date), MAX(wpm), AVG(wpm), AVG(accuracy), race_count, win_count
                FROM typing_stats LEFT JOIN typing_race
                ON typing_stats.user_id = typing_race.user_id
            WHERE typing_stats.user_id = %s
            GROUP BY typing_stats.user_id
            """,
            user.id,
        )
        if not data:
            raise exceptions.CommandInfo(
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

    def get_wordlist(self, wordcount, language):
        all_words = self.languages.get(language.lower())
        if all_words is None:
            return None, [str(lang) for lang in self.languages]
        wordlist = []
        while len(wordlist) < wordcount:
            word = random.choice(all_words)
            if not wordlist or wordlist[-1] != word:
                wordlist.append(word)
        return wordlist


async def setup(bot):
    await bot.add_cog(Typings(bot))


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
                k = max(i - offset, 0)
                user_word = user_words[k]
                offset += 1

            if user_word == correct_word:
                corrent_keys += len(correct_word) + 1

    wpm = (corrent_keys / 5) / (time.total_seconds() / 60)
    accuracy = (corrent_keys / total_keys) * 100
    not_long_enough = len(user_words) / len(wordlist) < 0.9
    return wpm, accuracy, not_long_enough
