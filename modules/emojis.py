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


class Status(Enum):
    online = "<:online:783745533457203212>"
    idle = "<:idle:783745644559859783>"
    dnd = "<:dnd:783745671811039333>"
    offline = "<:offline:783745574138675221>"
    streaming = "<:streaming:783745506102476830>"
    mobile = "<:mobile:783745605423988786>"


class Badge(Enum):
    staff = "<:staff:783744718185693214>"
    partner = "<:partner:783744609138114560>"
    nitro = "<:nitro:783744676996841532>"
    hypesquad = "<:hypesquad:783744695074684946>"
    hypesquad_brilliance = "<:hypesquad_brilliance:783744824444190740>"
    hypesquad_bravery = "<:hypesquad_bravery:783744840928198736>"
    hypesquad_balance = "<:hypesquad_balance:783745461499592734>"
    verified_bot_developer = "<:verified_bot_developer:783744740301996042>"
    early_supporter = "<:early_supporter:783744759101390888>"
    bug_hunter = "<:bug_hunter:783744806815268914>"
    bug_hunter_level_2 = "<:bug_hunter_level_2:783744783670968331>"
    team_user = ""
    system = ""
    verified_bot = "<:verified_bot:813396139373101076>"
    boosting = "<:boosting:813395502439727165>"


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
