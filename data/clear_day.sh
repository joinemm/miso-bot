#!/bin/sh
sqlite3 database.db <<EOF
DELETE FROM activity_day;
VACUUM;
EOF