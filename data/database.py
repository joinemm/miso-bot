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


def add_activity(guild_id, user_id, xp, hour):
    execute("update activity set h%s = h%s + ?, messages = messages + 1 where guild_id = ? and user_id = ?"
            % (hour, hour), (xp, guild_id, user_id))


def update_user(user_id, column, new_value):
    execute("update users set %s = ? where discord_id = ?" % column, (new_value, user_id))


def add_fishy(user_id, fishtype, amount, timestamp):
    execute("update fishy set fishy = fishy + ?, %s = %s + 1, timestamp = ? where discord_id = ?"
            % (fishtype, fishtype), (amount, timestamp, user_id))
