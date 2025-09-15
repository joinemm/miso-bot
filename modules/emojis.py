# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import random
from enum import Enum

VIVISMIRK = "<:vivismirk:749950217218162719>"

UPVOTE = "<:miso_upvote:748235458571534508>"
DOWNVOTE = "<:miso_downvote:748235446231891998>"

GREEN_UP = "<:green_triangle_up:749966847788449822>"
RED_DOWN = "<:red_triangle_down:749966805908455526>"

LOADING = "<a:loading:749966819514777690>"
TYPING = "<a:typing:749966793480732694>"

LASTFM = "<:lastfm:785230336014811139>"

REMOVE = "<:delete:1092405453754994718>"
REPEAT = "<:repeat:1092404557600002168>"
CONFIRM = "<:confirm:997952848677589074>"


class Status(Enum):
    online = "<:online:783745533457203212>"
    idle = "<:idle:783745644559859783>"
    dnd = "<:dnd:783745671811039333>"
    offline = "<:offline:783745574138675221>"
    streaming = "<:streaming:783745506102476830>"
    mobile = "<:mobile:783745605423988786>"


class Badge(Enum):
    staff = "<a:discord_staff:1083026664444919890>"
    partner = "<a:partnered_server_owner:1083026854178476202>"
    nitro = "<a:nitro_subscriber:1083026661961900112>"
    hypesquad = "<:hypesquad:783744695074684946>"
    hypesquad_brilliance = "<:hypesquad_brilliance:1083029882470137886>"
    hypesquad_bravery = "<:hypesquad_bravery:1083029880347840544>"
    hypesquad_balance = "<:hypesquad_balance:1083029878330368142>"
    verified_bot_developer = "<a:early_verified_bot_developer:1083026866178359356>"
    discord_certified_moderator = "<a:certified_moderator:1083026863468847154>"
    early_supporter = "<:early_supporter:1083027046923517964>"
    bug_hunter = "<a:bug_hunter:1083026666076520598>"
    bug_hunter_level_2 = "<a:gold_bug_hunter:1083026670748979235>"
    team_user = ""
    system = ""
    verified_bot = "<a:verified:1083026856669876286>"
    boosting = "<a:nitro_boost:1083027795250262056>"
    spammer = ":triangular_flag_on_post:"
    active_developer = "<a:active_developer:1083026858813177908>"


HUGS = [
    "<:miso_hug_muses:749948266006839346>",
    "<:miso_hug_gugu:749948228681597008>",
    "<:miso_hug_gidle_2:749948199271268432>",
    "<:miso_hug_gidle:749948173430161449>",
    "<:miso_hug_fromis:749948142467678268>",
    "<:miso_hug_dc:749948105335636010>",
    "<:miso_hug_clc:749948066399780915>",
    "<:miso_hug_chungha:749948024469585972>",
]

ANIMATED_HUGS = [
    "<a:miso_a_hug_loona_3:749948536853889024>",
    "<a:miso_a_hug_loona_2:749948506780729344>",
    "<a:miso_a_hug_itzy_2:749949471449940039>",
    "<a:miso_a_hug_loona:749949983351898143>",
    "<a:miso_a_hug_itzy:749949194835460138>",
    "<a:miso_a_hug_gidle:749949555558055966>",
    "<a:miso_a_hug_twice:749951935490293810>",
]


def random_hug(a=True):
    return random.choice(HUGS + ANIMATED_HUGS if a else [])
