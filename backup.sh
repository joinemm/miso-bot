#!/bin/sh

# SPDX-FileCopyrightText: 2024 Joonas Rautiola <mail@joinemm.dev>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

set -e

BACKUP_DIR="$HOME/backups"
DUMP_OPTIONS="--force --quick --single-transaction --extended-insert --order-by-primary"
BUCKET="s3:s3.us-west-004.backblazeb2.com/misobot"

# shellcheck source=./.backup.env.example
. "$HOME"/miso-bot/.backup.env

if [ "$1" = init ]; then
    echo "Initialising repository and exiting"
    restic -r "$BUCKET" init
    exit 0
fi

# Signal healthcheck.io that the backup run started
curl -m 10 --retry 5 "https://hc-ping.com/$HC_PING_KEY/db-backup/start"

# Create our backup directory if not already there
mkdir -p "$BACKUP_DIR"
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Not a directory: $BACKUP_DIR"
    exit 1
fi

# back up the backups because why not
echo "Copying old backups to $BACKUP_DIR-yesterday"
cp -r "$BACKUP_DIR" "$BACKUP_DIR"-yesterday

# Dump our databases
DATABASE_NAME=misobot
echo "Dumping MySQL Database $DATABASE_NAME"
# shellcheck disable=SC2086
docker exec miso-bot-db \
    /usr/bin/mysqldump --user=bot --password=botpw $DUMP_OPTIONS \
    --ignore-table="$DATABASE_NAME".sessions \
    "$DATABASE_NAME" >"$BACKUP_DIR"/"$DATABASE_NAME".sql

DATABASE_NAME=shlink
echo "Dumping MySQL Database $DATABASE_NAME"
# shellcheck disable=SC2086
docker exec miso-bot-db \
    /usr/bin/mysqldump --user=shlink --password=shlinkpw $DUMP_OPTIONS \
    --ignore-table="$DATABASE_NAME".sessions \
    "$DATABASE_NAME" >"$BACKUP_DIR"/"$DATABASE_NAME".sql

echo "Uploading dumps to B2"

restic -r "$BUCKET" backup "$BACKUP_DIR"

echo "Forgetting old backups based on policy"
RETENTION_POLICY="--keep-daily 7 --keep-weekly 5 --keep-monthly 12"
# shellcheck disable=SC2086
restic -r "$BUCKET" forget $RETENTION_POLICY

echo "Pruning the bucket"
restic -r "$BUCKET" prune

# signal healthcheck.io that the backup ran fine
curl -m 10 --retry 5 "https://hc-ping.com/$HC_PING_KEY/db-backup"
