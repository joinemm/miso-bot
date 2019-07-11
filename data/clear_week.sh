#!/bin/sh
sqlite3 database.db <<EOF
DELETE FROM activity_week;
VACUUM;
EOF