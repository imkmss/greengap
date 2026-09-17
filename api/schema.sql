-- GGF greengap DB 스키마
-- api/load_data.py 가 채우고 api/main.py 가 읽는 테이블 정의

-- 두 좌표 사이의 거리를 미터로 반환한다 (하버사인).
--
-- 위경도는 각도이지 거리가 아니다. 위도 1도는 어디서나 약 111km지만 경도 1도는
-- 서울(북위 37.5도)에서 약 88km라, 평면처럼 빼서 계산하면 동서 거리가 26% 부풀려진다.
-- 기준선이 800m인 이 프로젝트에서는 그 오차가 정책 충족 판정을 뒤집는다.
--
-- 이름의 _m 은 반환 단위가 미터라는 뜻이다. km 와 헷갈리면 800배가 어긋난다.
-- LANGUAGE sql + IMMUTABLE 이라 쿼리에 인라인 확장되므로, 같은 호출이 WHERE 와
-- ORDER BY 에 두 번 있어도 한 번만 계산된다.
CREATE OR REPLACE FUNCTION haversine_m(
    lat1 DOUBLE PRECISION, lng1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION, lng2 DOUBLE PRECISION
) RETURNS DOUBLE PRECISION AS $$
    SELECT 6371000 * 2 * asin(sqrt(
        power(sin(radians(lat2 - lat1) / 2), 2)
        + cos(radians(lat1)) * cos(radians(lat2))
        * power(sin(radians(lng2 - lng1) / 2), 2)
    ));
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

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
