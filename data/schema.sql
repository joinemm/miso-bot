CREATE TABLE `notifications`(
  `guild_id`	INTEGER NOT NULL,
  `user_id`	INTEGER NOT NULL,
  `keyword`	TEXT NOT NULL,
  UNIQUE(`guild_id`,`user_id`,`keyword`)
);
CREATE TABLE customcommands(
  `guild_id`	INTEGER NOT NULL,
  `command`	TEXT NOT NULL,
  `response`	TEXT NOT NULL,
  added_on REAL,
  added_by INTEGER,
  UNIQUE(`guild_id`,`command`)
);
CREATE TABLE `roles`(
  `guild_id`	INTEGER NOT NULL,
  `rolename`	TEXT NOT NULL,
  `role_id`	INTEGER NOT NULL,
  UNIQUE(`guild_id`,`rolename`)
);
CREATE TABLE `votechannels`(
  `guild_id`	INTEGER,
  `channel_id`	INTEGER,
  UNIQUE(`guild_id`,`channel_id`)
);
CREATE TABLE `starboard`(
  `message_id`	INTEGER NOT NULL UNIQUE,
  `starboard_message_id`	INTEGER NOT NULL UNIQUE
);
CREATE TABLE users(
  user_id INTEGER,
  lastfm_username TEXT,
  sunsign TEXT,
  location TEXT,
  PRIMARY KEY(user_id)
);
CREATE TABLE `fishy`(
  `user_id`	INTEGER,
  `timestamp`	FLOAT,
  `fishy`	INTEGER DEFAULT 0 NOT NULL,
  `fishy_gifted`	INTEGER DEFAULT 0 NOT NULL,
  `trash`	INTEGER DEFAULT 0 NOT NULL,
  `common`	INTEGER DEFAULT 0 NOT NULL,
  `uncommon`	INTEGER DEFAULT 0 NOT NULL,
  `rare`	INTEGER DEFAULT 0 NOT NULL,
  `legendary`	INTEGER DEFAULT 0 NOT NULL,
  biggest integer,
  PRIMARY KEY(`user_id`)
);
CREATE TABLE badges(
  discord_id INTEGER PRIMARY KEY,
  developer INTEGER,
  patron INTEGER,
  super_hugger INTEGER,
  best_friend INTEGER,
  master_fisher INTEGER,
  lucky_fisher INTEGER,
  generous_fisher INTEGER
);
CREATE TABLE IF NOT EXISTS "sorterpresets"(
  "guild_id"	INTEGER,
  "user_id"	INTEGER,
  "name"	TEXT,
  "items"	TEXT,
  PRIMARY KEY("name")
);
CREATE TABLE IF NOT EXISTS "emojis"(
  "id"	INTEGER,
  "name"	TEXT,
  "type"	TEXT,
  PRIMARY KEY("name","id")
);
CREATE TABLE IF NOT EXISTS "minecraft"(
  "guild_id" INTEGER NOT NULL,
  "address" TEXT,
  "port" INTEGER,
  PRIMARY KEY("guild_id")
);
CREATE TABLE IF NOT EXISTS "guilds"(
  "guild_id"	INTEGER NOT NULL,
  "muterole"	INTEGER,
  "autorole"	INTEGER,
  "levelup_toggle"	INTEGER NOT NULL DEFAULT 1,
  "welcome_toggle"	INTEGER NOT NULL DEFAULT 1,
  "welcome_channel"	INTEGER,
  "welcome_message"	TEXT,
  "welcome_embed" INTEGER DEFAULT 1,
  "starboard_toggle"	INTEGER NOT NULL DEFAULT 0,
  "starboard_channel"	INTEGER,
  "starboard_amount"	INTEGER NOT NULL DEFAULT 3,
  "rolepicker_channel"	INTEGER,
  "rolepicker_case"	INTEGER NOT NULL DEFAULT 1,
  rolepicker_enabled INTEGER,
  goodbye_channel INTEGER,
  goodbye_message TEXT,
  bans_channel INTEGER,
  deleted_messages_channel INTEGER,
  delete_blacklisted INTEGER DEFAULT 0,
  custom_commands_everyone INTEGER DEFAULT 1,
  autoresponses INTEGER DEFAULT 1,
  PRIMARY KEY("guild_id")
);
CREATE TABLE IF NOT EXISTS "activity"(
  "guild_id"	INTEGER NOT NULL,
  "user_id"	INTEGER NOT NULL,
  "messages"	INTEGER NOT NULL DEFAULT 0,
  "h0"	INTEGER NOT NULL DEFAULT 0,
  "h1"	INTEGER NOT NULL DEFAULT 0,
  "h2"	INTEGER NOT NULL DEFAULT 0,
  "h3"	INTEGER NOT NULL DEFAULT 0,
  "h4"	INTEGER NOT NULL DEFAULT 0,
  "h5"	INTEGER NOT NULL DEFAULT 0,
  "h6"	INTEGER NOT NULL DEFAULT 0,
  "h7"	INTEGER NOT NULL DEFAULT 0,
  "h8"	INTEGER NOT NULL DEFAULT 0,
  "h9"	INTEGER NOT NULL DEFAULT 0,
  "h10"	INTEGER NOT NULL DEFAULT 0,
  "h11"	INTEGER NOT NULL DEFAULT 0,
  "h12"	INTEGER NOT NULL DEFAULT 0,
  "h13"	INTEGER NOT NULL DEFAULT 0,
  "h14"	INTEGER NOT NULL DEFAULT 0,
  "h15"	INTEGER NOT NULL DEFAULT 0,
  "h16"	INTEGER NOT NULL DEFAULT 0,
  "h17"	INTEGER NOT NULL DEFAULT 0,
  "h18"	INTEGER NOT NULL DEFAULT 0,
  "h19"	INTEGER NOT NULL DEFAULT 0,
  "h20"	INTEGER NOT NULL DEFAULT 0,
  "h21"	INTEGER NOT NULL DEFAULT 0,
  "h22"	INTEGER NOT NULL DEFAULT 0,
  "h23"	INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("guild_id","user_id")
);
CREATE TABLE IF NOT EXISTS "crowns"(
  "artist"	TEXT,
  "guild_id"	INTEGER,
  "user_id"	INTEGER NOT NULL,
  "playcount"	INTEGER NOT NULL,
  PRIMARY KEY("artist","guild_id")
);
CREATE TABLE IF NOT EXISTS "activity_day"(
  "guild_id"INTEGER NOT NULL,
  "user_id"INTEGER NOT NULL,
  "messages"INTEGER NOT NULL DEFAULT 0,
  "h0"INTEGER NOT NULL DEFAULT 0,
  "h1"INTEGER NOT NULL DEFAULT 0,
  "h2"INTEGER NOT NULL DEFAULT 0,
  "h3"INTEGER NOT NULL DEFAULT 0,
  "h4"INTEGER NOT NULL DEFAULT 0,
  "h5"INTEGER NOT NULL DEFAULT 0,
  "h6"INTEGER NOT NULL DEFAULT 0,
  "h7"INTEGER NOT NULL DEFAULT 0,
  "h8"INTEGER NOT NULL DEFAULT 0,
  "h9"INTEGER NOT NULL DEFAULT 0,
  "h10"INTEGER NOT NULL DEFAULT 0,
  "h11"INTEGER NOT NULL DEFAULT 0,
  "h12"INTEGER NOT NULL DEFAULT 0,
  "h13"INTEGER NOT NULL DEFAULT 0,
  "h14"INTEGER NOT NULL DEFAULT 0,
  "h15"INTEGER NOT NULL DEFAULT 0,
  "h16"INTEGER NOT NULL DEFAULT 0,
  "h17"INTEGER NOT NULL DEFAULT 0,
  "h18"INTEGER NOT NULL DEFAULT 0,
  "h19"INTEGER NOT NULL DEFAULT 0,
  "h20"INTEGER NOT NULL DEFAULT 0,
  "h21"INTEGER NOT NULL DEFAULT 0,
  "h22"INTEGER NOT NULL DEFAULT 0,
  "h23"INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("guild_id","user_id")
);
CREATE TABLE IF NOT EXISTS "activity_month"(
  "guild_id"INTEGER NOT NULL,
  "user_id"INTEGER NOT NULL,
  "messages"INTEGER NOT NULL DEFAULT 0,
  "h0"INTEGER NOT NULL DEFAULT 0,
  "h1"INTEGER NOT NULL DEFAULT 0,
  "h2"INTEGER NOT NULL DEFAULT 0,
  "h3"INTEGER NOT NULL DEFAULT 0,
  "h4"INTEGER NOT NULL DEFAULT 0,
  "h5"INTEGER NOT NULL DEFAULT 0,
  "h6"INTEGER NOT NULL DEFAULT 0,
  "h7"INTEGER NOT NULL DEFAULT 0,
  "h8"INTEGER NOT NULL DEFAULT 0,
  "h9"INTEGER NOT NULL DEFAULT 0,
  "h10"INTEGER NOT NULL DEFAULT 0,
  "h11"INTEGER NOT NULL DEFAULT 0,
  "h12"INTEGER NOT NULL DEFAULT 0,
  "h13"INTEGER NOT NULL DEFAULT 0,
  "h14"INTEGER NOT NULL DEFAULT 0,
  "h15"INTEGER NOT NULL DEFAULT 0,
  "h16"INTEGER NOT NULL DEFAULT 0,
  "h17"INTEGER NOT NULL DEFAULT 0,
  "h18"INTEGER NOT NULL DEFAULT 0,
  "h19"INTEGER NOT NULL DEFAULT 0,
  "h20"INTEGER NOT NULL DEFAULT 0,
  "h21"INTEGER NOT NULL DEFAULT 0,
  "h22"INTEGER NOT NULL DEFAULT 0,
  "h23"INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("guild_id","user_id")
);
CREATE TABLE IF NOT EXISTS "activity_week"(
  "guild_id"INTEGER NOT NULL,
  "user_id"INTEGER NOT NULL,
  "messages"INTEGER NOT NULL DEFAULT 0,
  "h0"INTEGER NOT NULL DEFAULT 0,
  "h1"INTEGER NOT NULL DEFAULT 0,
  "h2"INTEGER NOT NULL DEFAULT 0,
  "h3"INTEGER NOT NULL DEFAULT 0,
  "h4"INTEGER NOT NULL DEFAULT 0,
  "h5"INTEGER NOT NULL DEFAULT 0,
  "h6"INTEGER NOT NULL DEFAULT 0,
  "h7"INTEGER NOT NULL DEFAULT 0,
  "h8"INTEGER NOT NULL DEFAULT 0,
  "h9"INTEGER NOT NULL DEFAULT 0,
  "h10"INTEGER NOT NULL DEFAULT 0,
  "h11"INTEGER NOT NULL DEFAULT 0,
  "h12"INTEGER NOT NULL DEFAULT 0,
  "h13"INTEGER NOT NULL DEFAULT 0,
  "h14"INTEGER NOT NULL DEFAULT 0,
  "h15"INTEGER NOT NULL DEFAULT 0,
  "h16"INTEGER NOT NULL DEFAULT 0,
  "h17"INTEGER NOT NULL DEFAULT 0,
  "h18"INTEGER NOT NULL DEFAULT 0,
  "h19"INTEGER NOT NULL DEFAULT 0,
  "h20"INTEGER NOT NULL DEFAULT 0,
  "h21"INTEGER NOT NULL DEFAULT 0,
  "h22"INTEGER NOT NULL DEFAULT 0,
  "h23"INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("guild_id","user_id")
);
CREATE TABLE IF NOT EXISTS "patrons"(
  "user_id" INTEGER,
  "tier" INTEGER NOT NULL,
  "patron_since" INTEGER,
  "currently_active" INTEGER,
  PRIMARY KEY("user_id")
);
CREATE TABLE IF NOT EXISTS "command_usage"(
  "guild_id" INTEGER,
  "user_id" INTEGER,
  "command" TEXT,
  "count" INTEGER NOT NULL,
  PRIMARY KEY("guild_id", "user_id", "command")
);
CREATE TABLE IF NOT EXISTS "fishysize"(
  "id"INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
  "timestamp"INTEGER NOT NULL,
  "user_id_catcher"INTEGER,
  "user_id_receiver"INTEGER NOT NULL,
  "size"INTEGER NOT NULL
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE IF NOT EXISTS "typingdata"(
  "timestamp"REAL NOT NULL,
  "user_id"INTEGER NOT NULL,
  "wpm"REAL NOT NULL,
  "accuracy"REAL NOT NULL,
  "wordcount"INTEGER NOT NULL,
  "race"INTEGER NOT NULL DEFAULT 0,
  language TEXT,
  PRIMARY KEY("timestamp","user_id")
);
CREATE TABLE IF NOT EXISTS "typeracer"(
  "guild_id"INTEGER NOT NULL,
  "user_id"INTEGER NOT NULL,
  "wins"INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("guild_id","user_id")
);
CREATE TABLE IF NOT EXISTS "profiles"(
  "user_id"INTEGER,
  "description"TEXT,
  "background_url"TEXT,
  "background_color"TEXT,
  PRIMARY KEY("user_id")
);
CREATE TABLE IF NOT EXISTS "reminders"(
  "user_id"INTEGER NOT NULL,
  "guild_id"INTEGER NOT NULL,
  "created_on"INTEGER,
  "timestamp"INTEGER NOT NULL,
  "thing"TEXT NOT NULL,
  message_link TEXT,
  PRIMARY KEY("user_id","timestamp")
);
CREATE TABLE IF NOT EXISTS "emoji_usage"(
  "guild_id"INTEGER,
  "user_id"INTEGER,
  "emoji"TEXT,
  "emojitype"TEXT NOT NULL,
  "count"INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("guild_id","user_id","emoji")
);
CREATE TABLE IF NOT EXISTS "custom_command_usage"(
  "guild_id"INTEGER,
  "user_id"INTEGER,
  "command"TEXT,
  "count"INTEGER NOT NULL,
  PRIMARY KEY("guild_id","user_id","command")
);
CREATE TABLE IF NOT EXISTS "prefixes"(
  "guild_id"INTEGER NOT NULL,
  "prefix"TEXT NOT NULL DEFAULT '>',
  PRIMARY KEY("guild_id")
);
CREATE TABLE IF NOT EXISTS "blacklist_global_users"(
  "user_id"INTEGER NOT NULL,
  PRIMARY KEY("user_id")
);
CREATE TABLE IF NOT EXISTS "blacklisted_channels"(
  "guild_id" INTEGER NOT NULL,
  "channel_id" INTEGER NOT NULL,
  PRIMARY KEY("guild_id", "channel_id")
);
CREATE TABLE IF NOT EXISTS "blacklisted_commands"(
  "guild_id"INTEGER NOT NULL,
  "command"TEXT NOT NULL,
  PRIMARY KEY("guild_id","command")
);
CREATE TABLE IF NOT EXISTS "blacklisted_users"(
  "guild_id"INTEGER NOT NULL,
  "user_id"INTEGER NOT NULL,
  PRIMARY KEY("guild_id","user_id")
);
CREATE TABLE IF NOT EXISTS "album_color_cache"(
  "image_id"TEXT,
  "rgb"TEXT NOT NULL,
  PRIMARY KEY("image_id")
);
CREATE TABLE IF NOT EXISTS "lastfm_blacklist"("username"	TEXT,
PRIMARY KEY("username"));
CREATE TABLE IF NOT EXISTS "api_usage"(
  "api_name"	TEXT,
  "month"	INTEGER,
  "count"	INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY("api_name","month")
);
CREATE TABLE IF NOT EXISTS "rate_limits"(
  "api_name"	TEXT,
  "usage_limit"	INTEGER,
  PRIMARY KEY("api_name")
);
