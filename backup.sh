#!/bin/sh

# SPDX-FileCopyrightText: 2024 Joonas Rautiola <joinemm@pm.me>
# SPDX-License-Identifier: MPL-2.0
# https://git.joinemm.dev/miso-bot

set -x
set -e

BACKUP_DIR="$HOME/backups"
CONTAINER_NAME="miso-db"
DATABASE_NAME="misobot"
USERLOGIN="--user=bot --password=botpw"
DUMP_OPTIONS="--quick --add-drop-table --add-locks --extended-insert --lock-tables"

# Get the current timestamp
TS=$(date +"%F-%s")

# Create our backup directory if not already there
mkdir -p "$BACKUP_DIR"
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Not a directory: $BACKUP_DIR"
    exit 1
fi

# Dump our database
echo "Dumping MySQL Database $DATABASE_NAME"
docker exec "$CONTAINER_NAME" /usr/bin/mysqldump $USERLOGIN $DUMP_OPTIONS "$DATABASE_NAME" >"$BACKUP_DIR"/"$TS"-"$DATABASE_NAME".sql
