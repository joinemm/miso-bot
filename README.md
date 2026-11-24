[![noai](https://notbyai.fyi/img/written-by-human-not-by-ai-white.svg)](https://notbyai.fyi/)

[![License](https://img.shields.io/github/license/joinemm/miso-bot)](https://img.shields.io/github/license/joinemm/miso-bot)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/84479f7c0f4c44a6aa2ba435e0215436)](https://app.codacy.com/manual/joinemm/miso-bot?utm_source=github.com&utm_medium=referral&utm_content=joinemm/miso-bot&utm_campaign=Badge_Grade_Dashboard)
[![DeepSource](https://deepsource.io/gh/joinemm/miso-bot.svg/?label=active+issues&show_trend=true&token=0E1BBh1I4k_HkqRvfRy86yMc)](https://deepsource.io/gh/joinemm/miso-bot/?ref=repository-badge)
[![Discord](https://img.shields.io/discord/652904322706833409.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://discord.gg/RzDW3Ne)
[![Sponsor](https://img.shields.io/github/sponsors/joinemm?color=%23db61a2)](https://github.com/sponsors/joinemm)


* * *

# Miso Bot

Miso is a multipurpose Discord bot with over 100 commands and features.

For more information and command reference, visit <https://misobot.xyz>

## Development

A Nix development shell is included, using [devenv](https://github.com/cachix/devenv)

This environment installs poetry and some useful packages.

```sh
nix develop --impure
```

The dependencies are managed using [Poetry](https://python-poetry.org/)

```sh
poetry install
```

Copy/rename `.env.example` to `.env` and fill the api keys you need, most importantly the discord bot token.
The bot can then be run with

```sh
poetry run python main.py
# or in dev mode
poetry run python main.py dev

# if using the nix shell:

run
# or in dev mode
run dev
```

but it will not function without a MariaDB database.
The database can be bootstrapped with

```sh
docker compose up db -d
```

After which the bot can be ran and easily developed.
When you're done, remember to shut down the database container:

```sh
docker compose down
```

## Contributing

Your pull requests are welcome, as long as they meet the enforced code standards:

- [Black](https://github.com/psf/black) and [isort](https://pycqa.github.io/isort/) for formatting.
- [Ruff](https://github.com/astral-sh/ruff), for linting.
- [Reuse](https://reuse.software/), for licensing.

The nix shell installs these as pre-commit hook automatically.

## Deployment

First copy/rename `.env.example` to `.env` and fill it with your own keys.
Everything else should be handled by the dockerfile.

Production databases use the encryption configuration in
`docker-compose.production.yml`. The server's SOPS configuration provisions
`/run/secrets/mariadb_encryption_key` before the databases start. Its content is a
MariaDB file-key-management entry in the format `1;<64 hexadecimal characters>`.
The secret has UID/GID `999` and mode `0400`, matching the containers' `mysql` user,
and is mounted read-only into both databases. Keep the key in your password manager
separately from the database volume. When recovering an existing encrypted
database, restore the same key; generating a new key will not decrypt the
existing files.

Add the following to the production `.env` so subsequent Compose commands keep
encryption enabled:

```sh
COMPOSE_FILE=docker-compose.yml:docker-compose.production.yml
```

Local development uses `docker-compose.yml` without the production override.

The production override also enables
[`MARIADB_AUTO_UPGRADE`](https://mariadb.com/docs/server/server-management/automated-mariadb-deployment-and-administration/docker-and-mariadb/mariadb-server-docker-official-image-environment-variables)
for both databases. The image's entrypoint updates system tables when the MariaDB
version changes and backs up the system database before upgrading. Take a full
database backup before changing database versions, and keep the encryption key
with the recovery materials. An upgrade of system tables does not replace a full
backup.

```sh
docker compose --profile prod up
```

The docker compose file bootstraps the entire miso infrastructure,
including prometheus metrics, grafana dashboards and nginx reverse proxy.

You likely don't want these if you're just running the bot.

The compose file is using different profiles that start only a handful of containers: `dev`, `dev-extra` and `prod`.
`prod` starts everything, as you might have guessed. 
`dev` starts only the db and the bot in debug mode, for fast testing. 
`dev-extra` starts extra services used by some commands, but not the infra containers.

```sh
docker compose --profile dev up
docker compose --profile dev-extra up
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=joinemm/miso-bot&type=Date)](https://star-history.com/#joinemm/miso-bot&Date)

## Contributor wall

[![Contributors](https://contrib.rocks/image?repo=joinemm/miso-bot)](https://github.com/joinemm/miso-bot/graphs/contributors)
