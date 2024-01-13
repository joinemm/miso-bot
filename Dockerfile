# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

# The builder image, used to build the virtual environment
FROM python:3.11-buster as builder

RUN pip install --no-cache-dir poetry==1.4.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# poetry complains if there is no readme for some reason
RUN touch README.md

RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# The runtime image, used to just run the code provided its virtual environment
FROM python:3.11-slim-buster as runtime

WORKDIR /app

# install ffmpeg that is used in some commands
RUN apt-get update -y \
 && apt-get install --no-install-recommends -y ffmpeg wget \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# get font used for memes
RUN wget --progress=dot:giga https://github.com/isis-project/isis-fonts/blob/master/NanumGothic.ttf?raw=true -O NanumGothic.ttf 

# copy over just the virtualenv from our builder image
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# copy over the source code
COPY . .

# don't buffer stdout, just show it normally
ENV PYTHONUNBUFFERED=1

CMD ["python", "-O", "main.py"]
