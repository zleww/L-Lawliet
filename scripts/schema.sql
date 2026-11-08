-- L-Lawliet Part II schema (Neon PostgreSQL)
-- Run once in the Neon SQL Editor as the project owner role (neondb_owner).
-- Creates laws, users and comments, their constraints and indexes.
-- The Part I test table republic_acts is not touched.

BEGIN;

CREATE TABLE laws (
    id                   SERIAL PRIMARY KEY,
    ra_number            VARCHAR(20)   NOT NULL UNIQUE CHECK (char_length(ra_number) >= 3),
    official_title       VARCHAR(300)  NOT NULL CHECK (char_length(official_title) >= 3),
    plain_title          VARCHAR(200)  NOT NULL CHECK (char_length(plain_title) >= 3),
    category             VARCHAR(30)   NOT NULL CHECK (category IN (
                             'Technology & Crime', 'Finance & Taxes', 'Governance & Business',
                             'Social & Welfare', 'Environment', 'Education & Civil Rights')),
    year                 SMALLINT      NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    status               VARCHAR(10)   NOT NULL DEFAULT 'Active'
                             CHECK (status IN ('Active', 'Amended', 'Repealed')),
    reading_time_minutes SMALLINT      NOT NULL CHECK (reading_time_minutes BETWEEN 1 AND 120),
    importance_rating    SMALLINT      NOT NULL CHECK (importance_rating BETWEEN 1 AND 5),
    tldr_summary         VARCHAR(500)  NOT NULL CHECK (char_length(tldr_summary) >= 10),
    full_breakdown       VARCHAR(2000) NOT NULL CHECK (char_length(full_breakdown) >= 10),
    why_it_matters       VARCHAR(1000) NOT NULL CHECK (char_length(why_it_matters) >= 5),
    example_scenario     VARCHAR(1000) NOT NULL CHECK (char_length(example_scenario) >= 10),
    penalties            VARCHAR(1000) NOT NULL CHECK (char_length(penalties) >= 5),
    min_fine_php         INTEGER       NOT NULL CHECK (min_fine_php >= 0),
    total_sections       SMALLINT      NOT NULL CHECK (total_sections BETWEEN 1 AND 1000),
    enacting_president   VARCHAR(100)  NOT NULL CHECK (char_length(enacting_president) >= 3),
    target_audience      VARCHAR(300)  NOT NULL CHECK (char_length(target_audience) >= 3),
    source_url           VARCHAR(500)  NOT NULL CHECK (source_url LIKE 'https://%'),
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE CHECK (char_length(username) >= 3),
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10)  NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE comments (
    id         SERIAL PRIMARY KEY,
    law_id     INTEGER       NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
    user_id    INTEGER       REFERENCES users(id) ON DELETE SET NULL,
    user_name  VARCHAR(100)  NOT NULL CHECK (char_length(user_name) >= 1),
    comment    VARCHAR(1000) NOT NULL CHECK (char_length(comment) >= 1),
    created_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- PostgreSQL does not index foreign keys automatically.
CREATE INDEX idx_laws_category   ON laws (category);
CREATE INDEX idx_comments_law_id ON comments (law_id);

COMMIT;
