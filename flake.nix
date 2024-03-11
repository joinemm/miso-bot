# SPDX-FileCopyrightText: 2024 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";
    devenv.url = "github:cachix/devenv";
  };

  nixConfig = {
    extra-trusted-public-keys = "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw=";
    extra-substituters = "https://devenv.cachix.org";
  };

  outputs = {
    nixpkgs,
    devenv,
    ...
  } @ inputs: let
    pkgs = nixpkgs.legacyPackages."x86_64-linux";
  in {
    devShell.x86_64-linux = devenv.lib.mkShell {
      inherit inputs pkgs;
      modules = [
        ({
          pkgs,
          lib,
          ...
        }: {
          dotenv.disableHint = true;

          packages = with pkgs; [
            ffmpeg
            isort
            black
            ruff
            reuse
          ];

          pre-commit.hooks = {
            isort.enable = true;
            black.enable = true;
            ruff = {
              enable = true;
              entry = lib.mkForce "${pkgs.ruff}/bin/ruff --fix --ignore=E501";
            };
          };

          languages.python = {
            enable = true;
            poetry.enable = true;
          };

          scripts."run".exec = ''
            poetry run python main.py $1
          '';
        })
      ];
    };
  };
}
