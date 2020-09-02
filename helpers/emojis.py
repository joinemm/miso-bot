import random
from enum import Enum


VIVISMIRK = "<:vivismirk:749950217218162719>"

UPVOTE = "<:miso_upvote:748235458571534508>"
DOWNVOTE = "<:miso_downvote:748235446231891998>"

GREEN_UP = "<:green_triangle_up:749966847788449822>"
RED_DOWN = "<:red_triangle_down:749966805908455526>"

LOADING = "<a:loading:749966819514777690>"
TYPING = "<a:typing:749966793480732694>"


class Status(Enum):
    ONLINE = "<:online:749966779840856094>"
    IDLE = "<:away:749966876284813363>"
    DND = "<:dnd:749966861549961277>"
    OFFLINE = "<:offline:749966834031394886>"


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
