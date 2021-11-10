-- blacklists
CREATE TABLE IF NOT EXISTS blacklisted_guild (
    guild_id BIGINT,
    reason VARCHAR(1024),
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS blacklisted_member (
    user_id BIGINT,
    guild_id BIGINT,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS blacklisted_user (
    user_id BIGINT,
    reason VARCHAR(1024),
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS blacklisted_channel (
    channel_id BIGINT,
    guild_id BIGINT,
    PRIMARY KEY (channel_id)
);

CREATE TABLE IF NOT EXISTS blacklisted_command (
    command_name VARCHAR(32),
    guild_id BIGINT,
    PRIMARY KEY (command_name, guild_id)
);

CREATE TABLE IF NOT EXISTS shadowbanned_user (
    user_id BIGINT,
    reason VARCHAR(1024),
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS lastfm_cheater (
    lastfm_username VARCHAR(32),
    flagged_on DATETIME,
    reason VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (lastfm_username)
);

-- user data
CREATE TABLE IF NOT EXISTS notification (
    guild_id BIGINT,
    user_id BIGINT,
    keyword VARCHAR(64),
    times_triggered INT DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, keyword)
);

CREATE TABLE IF NOT EXISTS custom_command (
    guild_id BIGINT,
    command_trigger VARCHAR(64),
    content VARCHAR(2000),
    added_on DATETIME,
    added_by BIGINT,
    PRIMARY KEY (guild_id, command_trigger)
);

CREATE TABLE IF NOT EXISTS rolepicker_role (
    guild_id BIGINT,
    role_name VARCHAR(64),
    role_id BIGINT,
    PRIMARY KEY (guild_id, role_name)
);

CREATE TABLE IF NOT EXISTS starboard_message (
    original_message_id BIGINT,
    starboard_message_id BIGINT UNIQUE,
    PRIMARY KEY (original_message_id)
);

CREATE TABLE IF NOT EXISTS starboard_blacklist (
    guild_id BIGINT,
    channel_id BIGINT,
    PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS fishy (
    user_id BIGINT,
    last_fishy DATETIME DEFAULT NULL,
    fishy_count INT DEFAULT 0,
    fishy_gifted_count INT DEFAULT 0,
    biggest_fish INT DEFAULT 0,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS fish_type (
    user_id BIGINT,
    trash INT DEFAULT 0,
    common INT DEFAULT 0,
    uncommon INT DEFAULT 0,
    rare INT DEFAULT 0,
    legendary INT DEFAULT 0,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS minecraft_server (
    guild_id BIGINT,
    server_address VARCHAR(128),
    port INT,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS artist_crown (
    guild_id BIGINT,
    user_id BIGINT,
    artist_name VARCHAR(256),
    cached_playcount INT,
    PRIMARY KEY (guild_id, artist_name)
);

CREATE TABLE IF NOT EXISTS donation_tier (
    id TINYINT,
    name VARCHAR(64),
    amount FLOAT,
    emoji VARCHAR(32),
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS donator (
    user_id BIGINT,
    platform ENUM('patreon', 'github', 'ko-fi'),
    external_username VARCHAR(64),
    donation_tier TINYINT,
    total_donated FLOAT DEFAULT 0.0,
    donating_since DATETIME,
    currently_active BOOLEAN DEFAULT 1,
    PRIMARY KEY (user_id, platform),
    FOREIGN KEY (donation_tier) REFERENCES donation_tier (id)
);

CREATE TABLE IF NOT EXISTS lastfm_vote_setting (
    user_id BIGINT,
    is_enabled BOOLEAN DEFAULT TRUE,
    upvote_emoji VARCHAR(128) DEFAULT NULL,
    downvote_emoji VARCHAR(128) DEFAULT NULL,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS donation (
    user_id BIGINT,
    platform ENUM('patreon', 'github', 'ko-fi', 'paypal'),
    amount FLOAT,
    donated_on DATETIME
);

CREATE TABLE IF NOT EXISTS command_usage (
    guild_id BIGINT,
    user_id BIGINT,
    command_name VARCHAR(64),
    command_type ENUM('internal', 'custom'),
    uses INT DEFAULT 1,
    PRIMARY KEY (guild_id, user_id, command_name, command_type)
);

CREATE TABLE IF NOT EXISTS custom_emoji_usage (
    guild_id BIGINT,
    user_id BIGINT,
    emoji_id BIGINT,
    emoji_name VARCHAR(32),
    uses INT DEFAULT 1,
    PRIMARY KEY (guild_id, user_id, emoji_id)
);

CREATE TABLE IF NOT EXISTS unicode_emoji_usage (
    guild_id BIGINT,
    user_id BIGINT,
    emoji_name VARCHAR(128),
    uses INT DEFAULT 1,
    PRIMARY KEY (guild_id, user_id, emoji_name)
);

CREATE TABLE IF NOT EXISTS typing_stats (
    user_id BIGINT,
    guild_id BIGINT,
    test_date DATETIME,
    wpm INT,
    accuracy FLOAT,
    word_count INT,
    test_language VARCHAR(32),
    was_race BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS typing_race (
    guild_id BIGINT,
    user_id BIGINT,
    race_count INT DEFAULT 0,
    win_count INT DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id BIGINT,
    description VARCHAR(500) DEFAULT NULL,
    background_url VARCHAR(255) DEFAULT NULL,
    background_color VARCHAR(6) DEFAULT NULL,
    show_graph BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS guild_prefix (
    guild_id BIGINT,
    prefix VARCHAR(32) NOT NULL,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS reminder (
    user_id BIGINT,
    guild_id BIGINT,
    created_on DATETIME,
    reminder_date DATETIME,
    content VARCHAR(255),
    original_message_url VARCHAR(128)
);

-- settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT,
    lastfm_username VARCHAR(64) DEFAULT NULL,
    sunsign VARCHAR(32) DEFAULT NULL,
    location_string VARCHAR(128) DEFAULT NULL,
    timezone VARCHAR(32) DEFAULT NULL,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT,
    mute_role_id BIGINT DEFAULT NULL,
    levelup_messages BOOLEAN DEFAULT FALSE,
    autoresponses BOOLEAN DEFAULT TRUE,
    restrict_custom_commands BOOLEAN DEFAULT FALSE,
    delete_blacklisted_usage BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS starboard_settings (
    guild_id BIGINT,
    channel_id BIGINT DEFAULT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    reaction_count INT DEFAULT 3,
    emoji_name VARCHAR(64) DEFAULT ':star:' NOT NULL,
    emoji_id BIGINT DEFAULT NULL,
    emoji_type ENUM('unicode', 'custom') DEFAULT 'unicode' NOT NULL,
    log_channel_id BIGINT DEFAULT NULL,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS rolepicker_settings (
    guild_id BIGINT,
    channel_id BIGINT DEFAULT NULL,
    is_enabled BOOLEAN DEFAULT FALSE,
    case_sensitive BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS greeter_settings (
    guild_id BIGINT,
    channel_id BIGINT DEFAULT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    message_format VARCHAR(1024) DEFAULT NULL,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS goodbye_settings (
    guild_id BIGINT,
    channel_id BIGINT DEFAULT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    message_format VARCHAR(1024) DEFAULT NULL,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS logging_settings (
    guild_id BIGINT,
    member_log_channel_id BIGINT DEFAULT NULL,
    ban_log_channel_id BIGINT DEFAULT NULL,
    message_log_channel_id BIGINT DEFAULT NULL,
    error_log_channel_id BIGINT DEFAULT NULL,
    PRIMARY KEY (guild_id)
);

CREATE TABLE IF NOT EXISTS message_log_ignore (
    guild_id BIGINT,
    channel_id BIGINT,
    PRIMARY KEY (channel_id)
);

CREATE TABLE IF NOT EXISTS autorole (
    guild_id BIGINT,
    role_id BIGINT,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS voting_channel (
    guild_id BIGINT,
    channel_id BIGINT,
    voting_type ENUM('rating', 'voting'),
    PRIMARY KEY (channel_id)
);

CREATE TABLE IF NOT EXISTS muted_user (
    guild_id BIGINT,
    user_id BIGINT,
    channel_id BIGINT,
    unmute_on DATETIME DEFAULT NULL,
    PRIMARY KEY (guild_id, user_id)
);

-- caches
CREATE TABLE IF NOT EXISTS image_color_cache (
    image_hash VARCHAR(32),
    r TINYINT UNSIGNED NOT NULL,
    g TINYINT UNSIGNED NOT NULL,
    b TINYINT UNSIGNED NOT NULL,
    hex VARCHAR(6) NOT NULL,
    PRIMARY KEY (image_hash)
);

CREATE TABLE IF NOT EXISTS artist_image_cache (
    artist_name VARCHAR(255),
    image_hash VARCHAR(32),
    scrape_date DATETIME,
    PRIMARY KEY (artist_name)
);

CREATE TABLE IF NOT EXISTS album_image_cache (
    artist_name VARCHAR(255),
    album_name VARCHAR(255),
    image_hash VARCHAR(32),
    scrape_date DATETIME,
    PRIMARY KEY (artist_name, album_name)
);

CREATE TABLE IF NOT EXISTS marriage (
    first_user_id BIGINT UNIQUE,
    second_user_id BIGINT UNIQUE,
    marriage_date DATETIME,
    PRIMARY KEY (first_user_id, second_user_id)
);

CREATE TABLE IF NOT EXISTS stats (
    ts DATETIME,
    messages INT NOT NULL DEFAULT 0,
    reactions INT NOT NULL DEFAULT 0,
    commands_used INT NOT NULL DEFAULT 0,
    guild_count INT NOT NULL DEFAULT 0,
    member_count INT NOT NULL DEFAULT 0,
    notifications_sent INT NOT NULL DEFAULT 0,
    lastfm_api_requests INT NOT NULL DEFAULT 0,
    html_rendered INT NOT NULL DEFAULT 0,
    PRIMARY KEY (ts)
);

-- activity
CREATE TABLE IF NOT EXISTS user_activity (
    guild_id BIGINT,
    user_id BIGINT,
    is_bot BOOLEAN,
    message_count INT DEFAULT 1,
    h0 INT NOT NULL DEFAULT 0,
    h1 INT NOT NULL DEFAULT 0,
    h2 INT NOT NULL DEFAULT 0,
    h3 INT NOT NULL DEFAULT 0,
    h4 INT NOT NULL DEFAULT 0,
    h5 INT NOT NULL DEFAULT 0,
    h6 INT NOT NULL DEFAULT 0,
    h7 INT NOT NULL DEFAULT 0,
    h8 INT NOT NULL DEFAULT 0,
    h9 INT NOT NULL DEFAULT 0,
    h10 INT NOT NULL DEFAULT 0,
    h11 INT NOT NULL DEFAULT 0,
    h12 INT NOT NULL DEFAULT 0,
    h13 INT NOT NULL DEFAULT 0,
    h14 INT NOT NULL DEFAULT 0,
    h15 INT NOT NULL DEFAULT 0,
    h16 INT NOT NULL DEFAULT 0,
    h17 INT NOT NULL DEFAULT 0,
    h18 INT NOT NULL DEFAULT 0,
    h19 INT NOT NULL DEFAULT 0,
    h20 INT NOT NULL DEFAULT 0,
    h21 INT NOT NULL DEFAULT 0,
    h22 INT NOT NULL DEFAULT 0,
    h23 INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_activity_day (
    guild_id BIGINT,
    user_id BIGINT,
    is_bot BOOLEAN NOT NULL,
    message_count INT DEFAULT 1,
    h0 INT NOT NULL DEFAULT 0,
    h1 INT NOT NULL DEFAULT 0,
    h2 INT NOT NULL DEFAULT 0,
    h3 INT NOT NULL DEFAULT 0,
    h4 INT NOT NULL DEFAULT 0,
    h5 INT NOT NULL DEFAULT 0,
    h6 INT NOT NULL DEFAULT 0,
    h7 INT NOT NULL DEFAULT 0,
    h8 INT NOT NULL DEFAULT 0,
    h9 INT NOT NULL DEFAULT 0,
    h10 INT NOT NULL DEFAULT 0,
    h11 INT NOT NULL DEFAULT 0,
    h12 INT NOT NULL DEFAULT 0,
    h13 INT NOT NULL DEFAULT 0,
    h14 INT NOT NULL DEFAULT 0,
    h15 INT NOT NULL DEFAULT 0,
    h16 INT NOT NULL DEFAULT 0,
    h17 INT NOT NULL DEFAULT 0,
    h18 INT NOT NULL DEFAULT 0,
    h19 INT NOT NULL DEFAULT 0,
    h20 INT NOT NULL DEFAULT 0,
    h21 INT NOT NULL DEFAULT 0,
    h22 INT NOT NULL DEFAULT 0,
    h23 INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_activity_week (
    guild_id BIGINT,
    user_id BIGINT,
    is_bot BOOLEAN,
    message_count INT DEFAULT 1,
    h0 INT NOT NULL DEFAULT 0,
    h1 INT NOT NULL DEFAULT 0,
    h2 INT NOT NULL DEFAULT 0,
    h3 INT NOT NULL DEFAULT 0,
    h4 INT NOT NULL DEFAULT 0,
    h5 INT NOT NULL DEFAULT 0,
    h6 INT NOT NULL DEFAULT 0,
    h7 INT NOT NULL DEFAULT 0,
    h8 INT NOT NULL DEFAULT 0,
    h9 INT NOT NULL DEFAULT 0,
    h10 INT NOT NULL DEFAULT 0,
    h11 INT NOT NULL DEFAULT 0,
    h12 INT NOT NULL DEFAULT 0,
    h13 INT NOT NULL DEFAULT 0,
    h14 INT NOT NULL DEFAULT 0,
    h15 INT NOT NULL DEFAULT 0,
    h16 INT NOT NULL DEFAULT 0,
    h17 INT NOT NULL DEFAULT 0,
    h18 INT NOT NULL DEFAULT 0,
    h19 INT NOT NULL DEFAULT 0,
    h20 INT NOT NULL DEFAULT 0,
    h21 INT NOT NULL DEFAULT 0,
    h22 INT NOT NULL DEFAULT 0,
    h23 INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_activity_month (
    guild_id BIGINT,
    user_id BIGINT,
    is_bot BOOLEAN,
    message_count INT DEFAULT 1,
    h0 INT NOT NULL DEFAULT 0,
    h1 INT NOT NULL DEFAULT 0,
    h2 INT NOT NULL DEFAULT 0,
    h3 INT NOT NULL DEFAULT 0,
    h4 INT NOT NULL DEFAULT 0,
    h5 INT NOT NULL DEFAULT 0,
    h6 INT NOT NULL DEFAULT 0,
    h7 INT NOT NULL DEFAULT 0,
    h8 INT NOT NULL DEFAULT 0,
    h9 INT NOT NULL DEFAULT 0,
    h10 INT NOT NULL DEFAULT 0,
    h11 INT NOT NULL DEFAULT 0,
    h12 INT NOT NULL DEFAULT 0,
    h13 INT NOT NULL DEFAULT 0,
    h14 INT NOT NULL DEFAULT 0,
    h15 INT NOT NULL DEFAULT 0,
    h16 INT NOT NULL DEFAULT 0,
    h17 INT NOT NULL DEFAULT 0,
    h18 INT NOT NULL DEFAULT 0,
    h19 INT NOT NULL DEFAULT 0,
    h20 INT NOT NULL DEFAULT 0,
    h21 INT NOT NULL DEFAULT 0,
    h22 INT NOT NULL DEFAULT 0,
    h23 INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_activity_year (
    guild_id BIGINT,
    user_id BIGINT,
    is_bot BOOLEAN,
    message_count INT DEFAULT 1,
    h0 INT NOT NULL DEFAULT 0,
    h1 INT NOT NULL DEFAULT 0,
    h2 INT NOT NULL DEFAULT 0,
    h3 INT NOT NULL DEFAULT 0,
    h4 INT NOT NULL DEFAULT 0,
    h5 INT NOT NULL DEFAULT 0,
    h6 INT NOT NULL DEFAULT 0,
    h7 INT NOT NULL DEFAULT 0,
    h8 INT NOT NULL DEFAULT 0,
    h9 INT NOT NULL DEFAULT 0,
    h10 INT NOT NULL DEFAULT 0,
    h11 INT NOT NULL DEFAULT 0,
    h12 INT NOT NULL DEFAULT 0,
    h13 INT NOT NULL DEFAULT 0,
    h14 INT NOT NULL DEFAULT 0,
    h15 INT NOT NULL DEFAULT 0,
    h16 INT NOT NULL DEFAULT 0,
    h17 INT NOT NULL DEFAULT 0,
    h18 INT NOT NULL DEFAULT 0,
    h19 INT NOT NULL DEFAULT 0,
    h20 INT NOT NULL DEFAULT 0,
    h21 INT NOT NULL DEFAULT 0,
    h22 INT NOT NULL DEFAULT 0,
    h23 INT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);