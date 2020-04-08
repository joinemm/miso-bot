import sqlite3
import json
import random
from collections import namedtuple
from functools import reduce


SQLDATABASE = 'data/database.db'
SQLKPOPDB = 'data/kpop.db'
JSONDATABASE = 'data/data.json'


def query(command, parameters=(), maketuple=False, database=SQLDATABASE):
    connection = sqlite3.connect(database)
    cursor = connection.cursor()
    cursor.execute(command, parameters)
    data = cursor.fetchall()
    if len(data) == 0:
        return None

    if maketuple:
        names = [description[0].lower().replace(' ', '_').replace('.', '') for description in cursor.description]
        NT = namedtuple('Data', names)
        if len(data) > 1:
            result = [NT._make(row) for row in data]
        else:
            result = NT._make(data[0])
    else:
        result = data
    connection.close()
    return result


def execute(command, parameters=(), database=SQLDATABASE):
    connection = sqlite3.connect(database)
    cursor = connection.cursor()
    cursor.execute(command, parameters)
    connection.commit()
    connection.close()


def userdata(userid):
    data = query("select * from users where user_id = ?", (userid,), maketuple=True)
    return data


def fishdata(userid):
    data = query("select * from fishy where user_id = ?", (userid,), maketuple=True)
    return data


def activitydata(guild_id, user_id, tablename='activity'):
    data = query("select * from %s where guild_id = ? and user_id = ?" % tablename, (guild_id, user_id), maketuple=True)
    return data


def get_user_activity(guild_id, user_id, tablename='activity'):
    data = query("select * from %s where guild_id = ? and user_id = ?" % tablename, (guild_id, user_id))
    if data is None:
        return None
    activities = list(data[0][3:])
    return activities


def add_activity(guild_id, user_id, xp, hour):
    for activity_table in ['activity', 'activity_day', 'activity_week', 'activity_month']:
        execute("insert or ignore into %s(guild_id, user_id) values(?, ?)" % activity_table, (guild_id, user_id))
        execute("update %s set h%s = h%s + ?, messages = messages + 1 where guild_id = ? and user_id = ?"
                % (activity_table, hour, hour), (xp, guild_id, user_id))


def update_user(user_id, column, new_value):
    execute("insert or ignore into users(user_id) values(?)", (user_id,))
    execute("update users set %s = ? where user_id = ?" % column, (new_value, user_id))


def add_fishy(user_id, fishtype, amount, timestamp, fisher_id=None):
    execute("insert or ignore into fishy(user_id) values(?)", (user_id,))
    if fisher_id is None:
        # fishing for self
        execute("update fishy set fishy = fishy + ?, %s = %s + 1, timestamp = ? where user_id = ?"
                % (fishtype, fishtype), (amount, timestamp, user_id))
    else:
        execute("insert or ignore into fishy(user_id) values(?)", (fisher_id,))
        execute("update fishy set fishy = fishy + ?, %s = %s + 1 where user_id = ?"
                % (fishtype, fishtype), (amount, user_id))
        execute("update fishy set fishy_gifted = fishy_gifted + ?, timestamp = ? where user_id = ?",
                (amount, timestamp, fisher_id))

    if amount > 0:
        biggest = query("SELECT biggest FROM fishy WHERE user_id = ?", (user_id,))[0][0] or 0
        if amount > biggest:
            execute("UPDATE fishy SET biggest = ? WHERE user_id = ?", (amount, user_id))

        leaderboard = query("SELECT size FROM fishysize ORDER BY size")
        if leaderboard[0][0] is None or amount >= leaderboard[0][0] or len(leaderboard) < 15:
            execute("INSERT INTO fishysize VALUES (null, ?, ?, ?, ?)", (timestamp, fisher_id, user_id, amount))

            execute("delete from fishysize where id = (select * from ("
                    "select id from fishysize order by size desc limit 15,1) as t)")


def get_keywords(guild_id):
    data = query("select keyword, user_id from notifications where guild_id = ?", (guild_id,))
    return data


def update_setting(guild_id, setting, new_value):
    execute("insert or ignore into guilds(guild_id) values(?)", (guild_id,))
    execute("update guilds set %s = ? where guild_id = ?" % setting, (new_value, guild_id))


def get_setting(guild_id, setting, default=None):
    data = query("select %s from guilds where guild_id = ?" % setting, (guild_id,))
    if data is None:
        return default
    else:
        return data[0][0]


def add_crown(artist, guild_id, user_id, playcount):
    data = query("SELECT user_id FROM crowns WHERE artist = ? and guild_id = ?", (artist, guild_id))
    execute("REPLACE INTO crowns VALUES (?, ?, ?, ?)", (artist, guild_id, user_id, playcount))
    if data is None:
        return None
    else:
        return data[0][0]


def rolepicker_role(guild_id, rolename, caps=False):
    data = query("SELECT role_id FROM roles WHERE rolename = ? AND guild_id = ?", (rolename, guild_id))

    if data is None:
        return None
    else:
        if caps:
            if rolename != data[0][0]:
                return None

        return data[0][0]


def random_kpop_idol(gender=None):
    if gender is None:
        data = query("SELECT * FROM idols", database=SQLKPOPDB, maketuple=True)
    else:
        data = query("SELECT * FROM idols WHERE gender = ?", (gender,), database=SQLKPOPDB, maketuple=True)
    return random.choice(data)


def get_from_data_json(keys):
    with open(JSONDATABASE, 'r') as f:
        data = json.load(f)
    return reduce(getter, keys, data)


def save_into_data_json(keys, value):
    with open(JSONDATABASE, 'r') as f:
        data = json.load(f)
    with open(JSONDATABASE, 'w') as f:
        if len(keys) > 1:
            path_to = reduce(getter, keys[:-1], data)
            path_to[keys[-1]] = value
        else:
            data[keys[0]] = value
        json.dump(data, f, indent=4)


def getter(d, key):
    try:
        return d.get(key, None)
    except AttributeError:
        try:
            return d[int(key)]
        except (ValueError, IndexError):
            return None


def log_command_usage(ctx):
    execute("INSERT OR IGNORE INTO command_usage VALUES(?, ?, ?, ?)",
            ((ctx.guild.id if ctx.guild is not None else 'DM'), ctx.author.id, str(ctx.command), 0))
    execute("UPDATE command_usage SET count = count + 1 WHERE (guild_id = ? AND user_id = ? AND command = ?)",
            ((ctx.guild.id if ctx.guild is not None else 'DM'), ctx.author.id, str(ctx.command)))


def log_custom_command_usage(ctx, keyword):
    execute("INSERT OR IGNORE INTO custom_command_usage VALUES(?, ?, ?, ?)",
            ((ctx.guild.id if ctx.guild is not None else 'DM'), ctx.author.id, keyword, 0))
    execute("UPDATE custom_command_usage SET count = count + 1 WHERE (guild_id = ? AND user_id = ? AND command = ?)",
            ((ctx.guild.id if ctx.guild is not None else 'DM'), ctx.author.id, keyword))


def log_emoji_usage(message, custom_emoji, unicode_emoji):
    all_emoji = []
    for emoji in custom_emoji:
        all_emoji.append((emoji, 'custom'))
    
    for emoji in unicode_emoji:
        all_emoji.append((emoji, 'unicode'))

    for emoji, emojitype in all_emoji:
        execute("INSERT OR IGNORE INTO emoji_usage VALUES(?, ?, ?, ?, ?)", 
                (message.guild.id, message.author.id, emoji, emojitype, 0))
        execute("UPDATE emoji_usage SET count = count + 1 "
                "WHERE (guild_id = ? AND user_id = ? AND emoji = ? AND emojitype = ?)", 
                (message.guild.id, message.author.id, emoji, emojitype))


def pp(cursor, data=None, rowlens=0):
    d = cursor.description
    if not d:
        return "#### NO RESULTS ###"
    names = []
    lengths = []
    rules = []
    if not data:
        data = cursor.fetchall(  )
    for dd in d:    # iterate over description
        ll = dd[1]
        if not ll:
            ll = 12             # or default arg ...
        ll = max(ll, len(dd[0])) # Handle long names
        names.append(dd[0])
        lengths.append(ll)
    for col in range(len(lengths)):
        if rowlens:
            rls = [len(row[col]) for row in data if row[col]]
            lengths[col] = max([lengths[col]]+rls)
        rules.append("-"*lengths[col])
    print_format = " ".join("%%-%ss" % ll for ll in lengths)
    result = [print_format % tuple(names), print_format % tuple(rules)]
    for row in data:
        result.append(print_format % row)
    return "\n".join(result)
