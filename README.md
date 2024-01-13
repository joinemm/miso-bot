[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/84479f7c0f4c44a6aa2ba435e0215436)](https://app.codacy.com/manual/joinemm/miso-bot?utm_source=github.com&utm_medium=referral&utm_content=joinemm/miso-bot&utm_campaign=Badge_Grade_Dashboard)
[![DeepSource](https://deepsource.io/gh/joinemm/miso-bot.svg/?label=active+issues&show_trend=true&token=0E1BBh1I4k_HkqRvfRy86yMc)](https://deepsource.io/gh/joinemm/miso-bot/?ref=repository-badge)
[![License](https://img.shields.io/github/license/joinemm/miso-bot)](https://img.shields.io/github/license/joinemm/miso-bot)

[![Discord](https://img.shields.io/discord/652904322706833409.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://discord.gg/RzDW3Ne)
[![Patreon](https://img.shields.io/badge/Patreon-donate-orange.svg)](https://www.patreon.com/joinemm)
[![Sponsor](https://img.shields.io/github/sponsors/joinemm?color=%23db61a2)](https://github.com/sponsors/joinemm)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/B0B824LWC)

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

The bot can then be run with

```sh
poetry run python main.py
```

but it will not function without a MariaDB database.
This makes using docker compose the easiest way to run the bot.

## Contributing

Your pull requests are welcome, as long as they meet the code standards enforced by the [pre-commit](https://pre-commit.com/) hooks.

- [Black](https://github.com/psf/black) and [isort](https://pycqa.github.io/isort/) for formatting.
- [Ruff](https://github.com/astral-sh/ruff), for linting.
- [Reuse](https://reuse.software/), for licensing.

To install the hooks, run this command:

```sh
pre-commit install
```

Now your code should be automatically checked for issues when you commit.

## Deployment

First copy/rename `.env.example` to `.env` and fill it with your own keys.
Everything else should be handled by the dockerfile.

```sh
docker-compose up
```

The docker compose file bootstraps the entire miso infrastructure,
including prometheus metrics, grafana dashboards and nginx reverse proxy.

You likely don't want these if you're just running the bot.

To run only the containers needed for the functionality of the bot, you can specify the service names:

```sh
docker-compose up db image-server emojifier bot
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=joinemm/miso-bot&type=Date)](https://star-history.com/#joinemm/miso-bot&Date)

## Contributor wall

[![Contributors](https://contrib.rocks/image?repo=joinemm/miso-bot)](https://github.com/joinemm/miso-bot/graphs/contributors)
