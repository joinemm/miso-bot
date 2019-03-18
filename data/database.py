import sqlite3
from collections import namedtuple

FILE = 'data/database.db'


def query(command, parameters=(), maketuple=False):
    connection = sqlite3.connect(FILE)
    cursor = connection.cursor()
    cursor.execute(command, parameters)
    data = cursor.fetchall()
    if len(data) == 0:
        return None

    if maketuple:
        names = [description[0] for description in cursor.description]
        NT = namedtuple('Data', names)
        result = NT._make(data[0])
    else:
        result = data
    connection.close()
    return result


def execute(command, parameters=()):
    connection = sqlite3.connect(FILE)
    cursor = connection.cursor()
    cursor.execute(command, parameters)
    connection.commit()
    connection.close()


def userdata(userid):
    data = query("select * from users where discord_id = ?", (userid,), maketuple=True)
    return data


def fishdata(userid):
    data = query("select * from fishy where discord_id = ?", (userid,), maketuple=True)
    return data


def activitydata(guild_id, userid):
    data = query("select * from activity where guild_id = ? and user_id = ?", (guild_id, userid), maketuple=True)
    return data


def add_activity(guild_id, user_id, xp, hour):
    execute("insert or ignore into activity(guild_id, user_id) values(?, ?)", (guild_id, user_id))
    execute("update activity set h%s = h%s + ?, xp = xp + ?, messages = messages + 1 where guild_id = ? and user_id = ?"
            % (hour, hour), (xp, xp, guild_id, user_id))


def update_user(user_id, column, new_value):
    execute("insert or ignore into users(discord_id) values(?)", (user_id,))
    execute("update users set %s = ? where discord_id = ?" % column, (new_value, user_id))


def add_fishy(user_id, fishtype, amount, timestamp, fisher_id=None):
    execute("insert or ignore into fishy(discord_id) values(?)", (user_id,))
    if fisher_id is None:
        # fishing for self
        execute("update fishy set fishy = fishy + ?, %s = %s + 1, timestamp = ? where discord_id = ?"
                % (fishtype, fishtype), (amount, timestamp, user_id))
    else:
        execute("insert or ignore into fishy(discord_id) values(?)", (fisher_id,))
        execute("update fishy set fishy = fishy + ?, %s = %s + 1 where discord_id = ?"
                % (fishtype, fishtype), (amount, user_id))
        execute("update fishy set fishy_gifted = fishy_gifted + ?, timestamp = ? where discord_id = ?",
                (amount, timestamp, fisher_id))


def get_keywords(guild_id):
    data = query("select keyword, user_id from notifications where guild_id = ?", (guild_id,))
    return data


def update_setting(guild_id, setting, new_value):
    execute("insert or ignore into guilds(guild_id) values(?)", (guild_id,))
    execute("update guilds set %s = ?" % setting, (new_value,))


def get_setting(guild_id, setting, default=None):
    data = query("select %s from guilds where guild_id = ?" % setting, (guild_id,))
    if data is None:
        return default
    else:
        return data[0][0]
