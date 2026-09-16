-- GGF greengap DB 스키마
-- api/load_data.py 가 채우고 api/main.py 가 읽는 테이블 정의

CREATE TABLE IF NOT EXISTS districts (
    gu_code  VARCHAR(5) PRIMARY KEY,
    gu_name  VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS parks (
    id         SERIAL PRIMARY KEY,
    gu_code    VARCHAR(5) NOT NULL REFERENCES districts(gu_code),
    park_name  TEXT,
    park_type  TEXT,
    lat        DOUBLE PRECISION,
    lng        DOUBLE PRECISION,
    area       DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS population (
    id                SERIAL PRIMARY KEY,
    dong_code         VARCHAR(10) NOT NULL,
    gu_code           VARCHAR(5) NOT NULL REFERENCES districts(gu_code),
    date              DATE NOT NULL,
    population_total  DOUBLE PRECISION,
    UNIQUE (dong_code, date)
);

-- 공공임대 단지. pipeline/preprocessing/housing_geocode.py 가 만든
-- output/housing_geocoded.csv 를 그대로 받는 원본 계층이다.
-- 계산된 녹지 점수는 housing_green_score 에 따로 둔다. 점수 산식이 바뀌어도
-- 지오코딩(외부 API 호출)을 다시 하지 않기 위해서다.
CREATE TABLE IF NOT EXISTS housing (
    id              SERIAL PRIMARY KEY,
    source          VARCHAR(10) NOT NULL,          -- SH / LH
    complex_name    TEXT NOT NULL,
    gu_code         VARCHAR(5) NOT NULL REFERENCES districts(gu_code),
    address         TEXT,
    zipcode         VARCHAR(10),
    lease_type      TEXT,                          -- 원문 유지 ("국민,장기" 등 복합 표기가 많다)
    households      INTEGER,
    move_in_date    DATE,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    -- ok    : 서울 안 + 자치구 일치
    -- check : 좌표는 나왔으나 자치구가 다름 (노원구 관할이지만 실제로는 의정부 등)
    geocode_status  VARCHAR(10),
    UNIQUE (source, gu_code, complex_name)
);

CREATE INDEX IF NOT EXISTS idx_housing_gu ON housing (gu_code);

CREATE TABLE IF NOT EXISTS greengap_stats (
    gu_code           VARCHAR(5) PRIMARY KEY REFERENCES districts(gu_code),
    total_park_area   DOUBLE PRECISION,
    population        DOUBLE PRECISION,
    green_per_capita  DOUBLE PRECISION
);
