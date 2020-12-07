# Miso Bot

![GitHub top language](https://img.shields.io/github/languages/top/joinemm/miso-bot?color=green)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/84479f7c0f4c44a6aa2ba435e0215436)](https://app.codacy.com/manual/joinemm/miso-bot?utm_source=github.com&utm_medium=referral&utm_content=joinemm/miso-bot&utm_campaign=Badge_Grade_Dashboard)
[![Discord](https://img.shields.io/discord/652904322706833409.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://discord.gg/RzDW3Ne)
[![Patreon](https://img.shields.io/badge/Patreon-donate-orange.svg)](https://www.patreon.com/joinemm)

---

A discord bot with almost 100 commands and features, including but not limited to:

-   LastFM Integration
-   Melon charts
-   Youtube search
-   Twitter image extractor
-   Instagram image extractor
-   Moderation (ban, mute, etc)
-   Logs bans, leaves, joins, messages
-   Server and user information
-   Levels and XP leaderboards
-   Customizable profiles
-   Server activity graph
-   Minecraft server status
-   Meme creation by inserting text
-   Starboard
-   Voting channels
-   Fishing
-   DuckDuckGo bangs
-   Colors and color palettes
-   Create Gfycats and Streamables 
-   Gfycat search
-   xkcd
-   Horoscope
-   Weather
-   Keyword notifications
-   Rolepicker
-   Typing tests and Typeracer
-   Papago Naver translator
-   Google Translate
-   Wolfram alpha
-   Wikipedia
-   Reminders
-   Custom commands
-   Changeable prefix
-   OPGG
-   Cryptocurrency data

...and much more. Visit <https://misobot.xyz> for more detailed overview of the features.

---

Invite to you server using this link!

<https://discordapp.com/oauth2/authorize?client_id=500385855072894982&scope=bot&permissions=1074654407>

---

#### Deployment

The python dependencies are managed using [poetry](https://python-poetry.org/).

```
sudo apt-get install python3 python3-pip mariadb-server
sudo mysql_secure_installation
git clone --recurse-submodules https://github.com/joinemm/miso-bot.git
cd miso-bot
poetry install
cp polls.yaml.example polls.yaml
cp .env.example .env
```
> fill `polls.yaml` and `.env` with your values.
```
sudo mysql
```
> mysql commands (replace user and password with your own preferred values)
```
CREATE DATABASE misobot;
GRANT ALL ON misobot.* TO 'miso'@'localhost' IDENTIFIED BY 'password' WITH GRANT OPTION;
connect misobot;
source sql/schema.sql
source sql/kpop_schema.sql
source sql/staticdata.sql
exit
```
> Start the image server (optional, but image generation will not work without it). Keep it running in the background.
```
./launch-image-server
```
> Finally, run the bot
```
poetry run python main.py
```
