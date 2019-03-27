import sqlite3
from collections import namedtuple
import json
from functools import reduce


SQLDATABASE = 'data/database.db'
JSONDATABASE = 'data/data.json'


def query(command, parameters=(), maketuple=False):
    connection = sqlite3.connect(SQLDATABASE)
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
    connection = sqlite3.connect(SQLDATABASE)
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


def activitydata(guild_id, user_id):
    data = query("select * from activity where guild_id = ? and user_id = ?", (guild_id, user_id), maketuple=True)
    return data


def get_user_activity(guild_id, user_id):
    data = query("select * from activity where guild_id = ? and user_id = ?", (guild_id, user_id))
    activities = list(data[0][3:])
    return activities


def add_activity(guild_id, user_id, xp, hour):
    execute("insert or ignore into activity(guild_id, user_id) values(?, ?)", (guild_id, user_id))
    execute("update activity set h%s = h%s + ?, messages = messages + 1 where guild_id = ? and user_id = ?"
            % (hour, hour), (xp, guild_id, user_id))


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


def rolepicker_role(rolename):
    data = query("select role_id from roles where rolename = ?", (rolename,))
    if data is None:
        return None
    else:
        return data[0][0]


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
