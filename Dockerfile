# SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# install ffmpeg that is used in some commands
RUN apt-get update -y \
 && apt-get install --no-install-recommends -y ffmpeg wget \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# get font used for memes
RUN wget --progress=dot:giga https://github.com/isis-project/isis-fonts/blob/master/NanumGothic.ttf?raw=true -O NanumGothic.ttf 

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/usr/local/bin

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENTRYPOINT ["uv", "run", "main.py"]
