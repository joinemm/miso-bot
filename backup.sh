#!/bin/sh

set -x
set -e

BACKUP_DIR="$HOME/backups"
CONTAINER_NAME="miso-db"
DATABASE_NAME="misobot"
USERLOGIN="--user=bot --password=botpw"
DUMP_OPTIONS="--quick --add-drop-table --add-locks --extended-insert --lock-tables"

# Get the current timestamp
TS=$(date +%Y%m%d%H%M%S)

# Create our backup directory if not already there
mkdir -p "$BACKUP_DIR"
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Not a directory: $BACKUP_DIR"
    exit 1
fi

# Dump our database
echo "Dumping MySQL Database $DATABASE_NAME"
docker exec "$CONTAINER_NAME" /usr/bin/mysqldump $USERLOGIN $DUMP_OPTIONS "$DATABASE_NAME" >"$BACKUP_DIR"/"$TS"-"$DATABASE_NAME".sql
