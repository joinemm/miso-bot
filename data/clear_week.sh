#!/bin/sh
sqlite3 /home/join/misobot2/data/database.db <<EOF
DELETE FROM activity_week;
VACUUM;
EOF