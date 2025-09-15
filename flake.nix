# SPDX-FileCopyrightText: 2024 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    devenv = {
      url = "github:cachix/devenv";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
  };

  outputs =
    { nixpkgs, devenv, ... }@inputs:
    let
      pkgs = nixpkgs.legacyPackages."x86_64-linux";
      binary-deps = with pkgs; [ ffmpeg ];
    in
    {
      devShells.x86_64-linux.default = devenv.lib.mkShell {
        inherit inputs pkgs;
        modules = [
          (
            { pkgs, ... }:
            {
              dotenv.disableHint = true;

              packages =
                with pkgs;
                [
                  reuse
                  mariadb
                ]
                ++ binary-deps;

              git-hooks.hooks = {
                isort.enable = true;
                ruff-format.enable = true;
                ruff.enable = true;
              };

              languages.python = {
                enable = true;
                uv.enable = true;
              };

              services.mysql = {
                enable = true;
                ensureUsers = [
                  {
                    name = "bot";
                    password = "botpw";
                    ensurePermissions = {
                      "misobot.*" = "ALL PRIVILEGES";
                    };
                  }
                ];
                initialDatabases = [
                  {
                    name = "misobot";
                    schema = ./sql/init/0_schema.sql;
                  }
                ];
              };

              scripts = {
                "run".exec = ''
                  uv run main.py $1
                '';
                "grepr".exec = ''
                  grep -r --exclude-dir=".git" --exclude-dir=".ruff_cache" --exclude-dir=".venv" --exclude-dir=".devenv" --exclude=\*.pyc --color $1
                '';
                "db".exec = ''
                  mysql --host=localhost --port=3306 --user=bot --password=botpw misobot
                '';
              };
            }
          )
        ];
      };
    };
}
