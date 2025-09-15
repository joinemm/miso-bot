# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

import json
import math
import random
import re
from itertools import chain, repeat

from modules.misobot import MisoBot

COMMON_WORDS = [
    "a",
    "an",
    "as",
    "is",
    "if",
    "of",
    "the",
    "it",
    "its",
    "or",
    "are",
    "this",
    "with",
    "so",
    "to",
    "at",
    "was",
    "and",
]


class Emojifier:
    def __init__(self, bot: MisoBot):
        self.bot = bot
        with open("data/emoji-word-association.json") as f:
            self.emoji_data = json.load(f)

    def convert(self, text: str) -> str:
        words = text.split()
        results = []

        for word_raw in words:
            word = re.sub(r"[^0-9a-zA-Z]", "", word_raw).lower()

            emoji_candidates = []
            word_data = self.emoji_data.get(word)
            if word_data is not None:
                emoji_candidates = list(
                    chain.from_iterable(
                        repeat(option, freq) for option, freq in word_data.items()
                    )
                )

            if word in COMMON_WORDS or not emoji_candidates:
                results.append(word_raw)
                continue

            emojis = emoji_candidates[
                math.floor(random.random() * len(emoji_candidates))
            ]

            results.append(f"{word_raw} {emojis}")

        return " ".join(results)
