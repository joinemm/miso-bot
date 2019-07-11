#!/bin/sh
sqlite3 database.db <<EOF
DELETE FROM activity_month;
VACUUM;
EOF