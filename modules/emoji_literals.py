import json

LITERALS = {}
with open("data/emoji_map.json") as f:
    LITERALS = json.load(f)

NAME_TO_UNICODE = {f":{k}:": v for k, v in LITERALS.items()}
UNICODE_TO_NAME = {v: k for k, v in NAME_TO_UNICODE.items()}
