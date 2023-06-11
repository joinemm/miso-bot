# SPDX-FileCopyrightText: 2023 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

FROM python:3.11

WORKDIR /app

RUN wget --progress=dot:giga https://github.com/isis-project/isis-fonts/blob/master/NanumGothic.ttf?raw=true -O NanumGothic.ttf 
RUN apt-get update -y \
    && apt-get install --no-install-recommends -y ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-O", "main.py"]
