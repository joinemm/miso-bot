CREATE TABLE IF NOT EXISTS kpop_group (
    group_id INT NOT NULL AUTO_INCREMENT,
    profile_link VARCHAR(128),
    group_name VARCHAR(64) UNIQUE,
    other_name VARCHAR(64),
    korean_name VARCHAR(64),
    debut_date DATE,
    company VARCHAR(64),
    fanclub VARCHAR(64),
    gender ENUM("F", "M"),
    active ENUM('yes', 'no', 'hiatus'),
    PRIMARY KEY (group_id)
);

CREATE TABLE IF NOT EXISTS kpop_idol (
    idol_id INT NOT NULL AUTO_INCREMENT,
    profile_link VARCHAR(128),
    group_name VARCHAR(64),
    stage_name VARCHAR(64),
    full_name VARCHAR(64),
    korean_name VARCHAR(64),
    korean_stage_name VARCHAR(64),
    date_of_birth DATE,
    country VARCHAR(32),
    second_country VARCHAR(32),
    height INT,
    weight INT,
    birthplace VARCHAR(32),
    gender ENUM("F", "M"),
    position VARCHAR(64),
    instagram VARCHAR(128),
    twitter VARCHAR(128),
    image_url VARCHAR(256),
    UNIQUE(group_name, stage_name),
    PRIMARY KEY (idol_id)
);