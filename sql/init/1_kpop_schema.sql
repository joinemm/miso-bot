-- SPDX-FileCopyrightText: 2018-2025 Joonas Rautiola <mail@joinemm.dev>
-- SPDX-License-Identifier: MPL-2.0
-- https://git.joinemm.dev/miso-bot

CREATE TABLE IF NOT EXISTS kpop_group (
    group_id INT NOT NULL AUTO_INCREMENT,
    gender ENUM("F", "M"),
    profile_url VARCHAR(128),
    group_name VARCHAR(64) UNIQUE,
    short_name VARCHAR(64),
    korean_name VARCHAR(64),
    debut_date DATE,
    company VARCHAR(64),
    members INT,
    orig_members INT,
    fanclub VARCHAR(64),
    active ENUM('Yes', 'No', 'Hiatus'),
    image_url VARCHAR(1024),
    image_scrape_date DATETIME,
    PRIMARY KEY (group_id)
);

CREATE TABLE IF NOT EXISTS kpop_idol (
    idol_id INT NOT NULL AUTO_INCREMENT,
    gender ENUM("F", "M"),
    profile_url VARCHAR(128),
    stage_name VARCHAR(64),
    full_name VARCHAR(64),
    korean_name VARCHAR(64),
    korean_stage_name VARCHAR(64),
    date_of_birth DATE,
    group_name VARCHAR(64),
    country VARCHAR(32),
    second_country VARCHAR(32),
    height INT,
    weight INT,
    birthplace VARCHAR(32),
    other_group VARCHAR(64),
    former_group VARCHAR(64),
    position VARCHAR(64),
    instagram VARCHAR(64),
    twitter VARCHAR(64),
    image_url VARCHAR(1024),
    image_scrape_date DATETIME,
    UNIQUE(group_name, stage_name),
    PRIMARY KEY (idol_id)
);

CREATE TABLE IF NOT EXISTS group_membership (
    idol_id INT NOT NULL,
    group_id INT NOT NULL,
    current_member BOOLEAN,
    FOREIGN KEY (idol_id) REFERENCES kpop_idol(idol_id),
    FOREIGN KEY (group_id) REFERENCES kpop_group(group_id)
);

CREATE TABLE IF NOT EXISTS stannable_artist (
    id INT NOT NULL AUTO_INCREMENT,
    artist_name VARCHAR(128),
    category VARCHAR(64) NOT NULL,
    UNIQUE(artist_name),
    PRIMARY KEY (id)
);
