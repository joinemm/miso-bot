#!/bin/sh

# SPDX-FileCopyrightText: 2024 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

set -e

BACKUP_DIR="$HOME/backups"
CONTAINER_NAME="miso-db"
DATABASES="misobot shlink"
USERLOGIN="--user=bot --password=botpw"
DUMP_OPTIONS="--force --quick --single-transaction --compact --extended-insert --order-by-primary"
BUCKET="s3:s3.us-west-004.backblazeb2.com/misobot-database"

# Create our backup directory if not already there
mkdir -p "$BACKUP_DIR"
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Not a directory: $BACKUP_DIR"
    exit 1
fi

# back up the backups because why not
cp -r "$BACKUP_DIR" "$BACKUP_DIR"-yesterday

# Dump our databases
for DATABASE_NAME in $DATABASES; do
    echo "Dumping MySQL Database $DATABASE_NAME"
    # shellcheck disable=SC2086
    docker exec "$CONTAINER_NAME" \
        /usr/bin/mysqldump $USERLOGIN $DUMP_OPTIONS \
        --ignore-table="$DATABASE_NAME".sessions \
        "$DATABASE_NAME" >"$BACKUP_DIR"/"$DATABASE_NAME".sql
done

echo "Uploading dumps to B2"
# shellcheck source=./.restic.env.example
. "$HOME"/miso-bot/.restic.env
restic -r "$BUCKET" backup "$BACKUP_DIR"
