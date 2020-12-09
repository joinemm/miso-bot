from discord.ext import commands
import arrow
import sqlite3
from libraries import emoji_literals


SQLDATABASE = "data/database.db"


def query(command, parameters=(), maketuple=False, database=SQLDATABASE):
    connection = sqlite3.connect(database, timeout=10)
    cursor = connection.cursor()
    cursor.execute(command, parameters)
    data = cursor.fetchall()
    connection.close()
    if len(data) == 0:
        return []
    else:
        return data


class Migrate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        """Check if command author is Owner."""
        return await self.bot.is_owner(ctx.author)

    @commands.command()
    async def mblacklists(self, ctx):
        guild_values = []
        member_values = []
        user_values = []
        channel_values = []
        command_values = []
        lastfm_cheater_values = []

        for row in query("SELECT guild_id FROM blacklist_guilds"):
            guild_values.append(row)

        for guild_id, user_id in query("SELECT guild_id, user_id FROM blacklisted_users"):
            member_values.append((guild_id, user_id))

        for row in query("SELECT user_id FROM blacklist_global_users"):
            user_values.append(row)

        for guild_id, channel_id in query("SELECT guild_id, channel_id FROM blacklisted_channels"):
            channel_values.append((channel_id, guild_id))

        for guild_id, command_name in query("SELECT guild_id, command FROM blacklisted_commands"):
            command_values.append((command_name, guild_id))

        for row in query("SELECT username FROM lastfm_blacklist"):
            lastfm_cheater_values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE blacklisted_guild (guild_id) VALUES (%s)",
            guild_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE blacklisted_member (guild_id, user_id) VALUES (%s, %s)",
            member_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE blacklisted_user (user_id) VALUES (%s)",
            user_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE blacklisted_channel (channel_id, guild_id) VALUES (%s, %s)",
            channel_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE blacklisted_command (command_name, guild_id) VALUES (%s, %s)",
            command_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE lastfm_cheater (lastfm_username) VALUES (%s)",
            lastfm_cheater_values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mnotifications(self, ctx):
        values = []
        for row in query("SELECT guild_id, user_id, keyword FROM notifications"):
            if len(row[2]) > 64:
                continue
            values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE notification (guild_id, user_id, keyword) VALUES (%s, %s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mcc(self, ctx):
        values = []
        for guild_id, command, response, added_on, added_by in query(
            "SELECT guild_id, command, response, added_on, added_by FROM customcommands"
        ):
            added_on_datetime = arrow.get(added_on).datetime
            if len(command) > 64:
                continue
            values.append((guild_id, command, response, added_on_datetime, added_by))

        await self.bot.db.executemany(
            """INSERT IGNORE custom_command (guild_id, command_trigger, content, added_on, added_by)
            VALUES (%s, %s, %s, %s, %s)""",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mroles(self, ctx):
        values = []
        for row in query("SELECT guild_id, rolename, role_id FROM roles"):
            if len(row[1]) > 64:
                continue
            values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE rolepicker_role (guild_id, role_name, role_id) VALUES (%s, %s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mstarb(self, ctx):
        values = []
        for row in query("SELECT message_id, starboard_message_id FROM starboard"):
            values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE starboard_message (original_message_id, starboard_message_id) VALUES (%s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mfishy(self, ctx):
        fishy_values = []
        fishtype_values = []
        for (
            user_id,
            timestamp,
            fishy,
            fishy_gifted,
            trash,
            common,
            uncommon,
            rare,
            legendary,
            biggest,
        ) in query("SELECT * FROM fishy"):
            last_fishy = arrow.get(timestamp).datetime
            fishy_values.append((user_id, last_fishy, fishy, fishy_gifted, biggest))
            fishtype_values.append((user_id, trash, common, uncommon, rare, legendary))

        await self.bot.db.executemany(
            "INSERT IGNORE fishy VALUES (%s, %s, %s, %s, %s)",
            fishy_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE fish_type VALUES (%s, %s, %s, %s, %s, %s)",
            fishtype_values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mminecraft(self, ctx):
        values = []
        for row in query("SELECT * FROM minecraft"):
            if len(row[1]) > 128:
                continue
            values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE minecraft_server (guild_id, server_address, port) VALUES (%s, %s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mprefix(self, ctx):
        values = []
        for row in query("SELECT * FROM prefixes"):
            if len(row[1]) > 32:
                continue
            values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE guild_prefix VALUES (%s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mreminders(self, ctx):
        values = []
        for user_id, guild_id, created_on, timestamp, thing, message_link in query(
            "SELECT * FROM reminders"
        ):
            created_on_dt = arrow.get(created_on).datetime
            reminder_date_dt = arrow.get(timestamp).datetime
            values.append(
                (user_id, guild_id, created_on_dt, reminder_date_dt, thing, message_link)
            )

        await self.bot.db.executemany(
            "INSERT IGNORE reminder VALUES (%s, %s, %s, %s, %s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mvotes(self, ctx):
        values = []
        for guild_id, channel_id, channel_type in query("SELECT * FROM votechannels"):
            if channel_type == "rating":
                voting_type = "rating"
            else:
                voting_type = "voting"

            values.append((guild_id, channel_id, voting_type))

        await self.bot.db.executemany(
            "INSERT IGNORE voting_channel VALUES (%s, %s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mcrowns(self, ctx):
        values = []
        for row in query("SELECT guild_id, user_id, artist, playcount FROM crowns"):
            values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE artist_crown VALUES (%s, %s, %s, %s)",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mxp(self, ctx):
        total_values = []
        day_values = []
        week_values = []
        month_values = []
        skipped = 0

        def make_new_row(row):
            row = list(row)
            user = self.bot.get_user(row[1])
            if user is None:
                return None

            new_row = row[:2] + [user.bot] + row[2:]
            return tuple(new_row)

        for row in query("SELECT * FROM activity"):
            new_row = make_new_row(row)
            if new_row is not None:
                total_values.append(new_row)
            else:
                skipped += 1

        for row in query("SELECT * FROM activity_day"):
            new_row = make_new_row(row)
            if new_row is not None:
                day_values.append(new_row)

        for row in query("SELECT * FROM activity_week"):
            new_row = make_new_row(row)
            if new_row is not None:
                week_values.append(new_row)

        for row in query("SELECT * FROM activity_month"):
            new_row = make_new_row(row)
            if new_row is not None:
                month_values.append(new_row)

        await self.bot.db.executemany(
            """INSERT IGNORE user_activity VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            total_values,
        )

        await self.bot.db.executemany(
            """INSERT IGNORE user_activity_day VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            day_values,
        )

        await self.bot.db.executemany(
            """INSERT IGNORE user_activity_week VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            week_values,
        )

        await self.bot.db.executemany(
            """INSERT IGNORE user_activity_month VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            month_values,
        )

        await ctx.send(f":ok_hand: skipped {skipped} unknown users")

    @commands.command()
    async def mcommanduse(self, ctx):
        values = []
        custom_values = []
        for guild_id, user_id, command, count in query(
            "SELECT guild_id, user_id, command, count FROM command_usage"
        ):
            if len(command) > 64 or guild_id == "DM":
                continue
            values.append((guild_id, user_id, command, "internal", count))

        for guild_id, user_id, command, count in query(
            "SELECT guild_id, user_id, command, count FROM custom_command_usage"
        ):
            if len(command) > 64 or guild_id == "DM":
                continue
            custom_values.append((guild_id, user_id, command, "custom", count))

        await self.bot.db.executemany(
            "INSERT IGNORE command_usage VALUES (%s, %s, %s, %s, %s)",
            values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE command_usage VALUES (%s, %s, %s, %s, %s)",
            custom_values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def musers(self, ctx):
        profile_values = []
        settings_values = []
        for user_id, description, background_url, _ in query("SELECT * FROM profiles"):
            profile_values.append((user_id, description, background_url))

        for row in query("SELECT * FROM users"):
            settings_values.append(row)

        await self.bot.db.executemany(
            "INSERT IGNORE user_profile (user_id, description, background_url) VALUES (%s, %s, %s)",
            profile_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE user_settings VALUES (%s, %s, %s, %s)",
            settings_values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mguilds(self, ctx):
        guild_setting_values = []
        starboard_values = []
        rolepicker_values = []
        greeter_values = []
        goodbye_values = []
        logging_values = []
        autorole_values = []

        for (
            guild_id,
            muterole,
            autorole,
            levelup_toggle,
            welcome_toggle,
            welcome_channel,
            welcome_message,
            starboard_toggle,
            starboard_channel,
            starboard_amount,
            rolepicker_channel,
            rolepicker_case,
            rolepicker_enabled,
            goodbye_channel,
            goodbye_message,
            bans_channel,
            deleted_messages_channel,
            delete_blacklisted,
            custom_commands_everyone,
            autoresponses,
            welcome_embed,
            starboard_emoji,
            starboard_emoji_is_custom,
        ) in query("SELECT * FROM guilds"):
            guild_setting_values.append(
                (
                    guild_id,
                    muterole,
                    levelup_toggle,
                    autoresponses,
                    not (custom_commands_everyone == 1),
                    delete_blacklisted,
                )
            )

            if starboard_emoji_is_custom == 1:
                starboard_emoji_id = int(starboard_emoji)
                emoji_obj = self.bot.get_emoji(starboard_emoji_id)
                if emoji_obj is None:
                    starboard_emoji_id = None
                    starboard_emoji_name = ":star:"
                else:
                    starboard_emoji_name = emoji_obj.name
            else:
                starboard_emoji_id = None
                starboard_emoji_name = emoji_literals.UNICODE_TO_NAME.get(starboard_emoji)
            starboard_values.append(
                (
                    guild_id,
                    starboard_channel,
                    starboard_toggle,
                    starboard_amount,
                    starboard_emoji_name,
                    starboard_emoji_id,
                    "custom" if starboard_emoji_is_custom == 1 else "unicode",
                )
            )

            rolepicker_values.append(
                (guild_id, rolepicker_channel, rolepicker_enabled, rolepicker_case)
            )
            greeter_values.append((guild_id, welcome_channel, welcome_toggle, welcome_message))
            goodbye_values.append((guild_id, goodbye_channel, True, goodbye_message))
            logging_values.append((guild_id, bans_channel, deleted_messages_channel))
            if autorole is not None:
                autorole_values.append((guild_id, autorole))

        await self.bot.db.executemany(
            "INSERT IGNORE guild_settings VALUES (%s, %s, %s, %s, %s, %s)",
            guild_setting_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE starboard_settings VALUES (%s, %s, %s, %s, %s, %s, %s)",
            starboard_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE rolepicker_settings VALUES (%s, %s, %s, %s)",
            rolepicker_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE greeter_settings VALUES (%s, %s, %s, %s)",
            greeter_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE goodbye_settings VALUES (%s, %s, %s, %s)",
            goodbye_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE logging_settings (guild_id, ban_log_channel_id, message_log_channel_id) VALUES (%s, %s, %s)",
            logging_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE autorole VALUES (%s, %s)",
            autorole_values,
        )

        message_ignore_values = []
        for guild_id, channel_id in query("SELECT * FROM deleted_messages_mask"):
            message_ignore_values.append((guild_id, channel_id))

        await self.bot.db.executemany(
            "INSERT IGNORE message_log_ignore VALUES (%s, %s)",
            message_ignore_values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def mtyping(self, ctx):
        values = []
        for timestamp, user_id, wpm, accuracy, wordcount, race, language in query(
            "SELECT * FROM typingdata"
        ):
            test_date = arrow.get(timestamp).datetime
            values.append((user_id, test_date, wpm, accuracy, wordcount, language, race == 1))

        await self.bot.db.executemany(
            """INSERT IGNORE typing_stats (user_id, test_date, wpm, accuracy, word_count, test_language, was_race)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            values,
        )

        await ctx.send(":ok_hand:")

    @commands.command()
    async def memojis(self, ctx):
        custom_values = []
        unicode_values = []
        for guild_id, user_id, emoji, emojitype, count in query(
            "SELECT guild_id, user_id, emoji, emojitype, count FROM emoji_usage"
        ):
            if emojitype == "unicode":
                unicode_values.append((guild_id, user_id, emoji, count))
            else:
                emoji_id = int(emoji.split(":")[-1].strip(">"))
                emoji_name = emoji.split(":")[0].strip("<")
                if len(emoji_name) < 2:
                    emoji_name = emoji.split(":")[1]

                if len(emoji_name) > 32:
                    print("how", emoji_name)

                custom_values.append((guild_id, user_id, emoji_id, emoji_name, count))

        print("inserting now")
        await self.bot.db.executemany(
            "INSERT INTO custom_emoji_usage VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE uses = uses + VALUES(uses)",
            custom_values,
        )

        await self.bot.db.executemany(
            "INSERT IGNORE unicode_emoji_usage VALUES (%s, %s, %s, %s)",
            unicode_values,
        )

        await ctx.send(":ok_hand:")


def setup(bot):
    bot.add_cog(Migrate(bot))
