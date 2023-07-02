# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import json
import os

LITERALS = {}
with open(os.path.join(os.path.dirname(__file__), "../data/emoji_map.json")) as f:
    LITERALS = json.load(f)

NAME_TO_UNICODE = {f":{k}:": v for k, v in LITERALS.items()}
UNICODE_TO_NAME = {v: k for k, v in NAME_TO_UNICODE.items()}
