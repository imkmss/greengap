import os
import glob
import unicodedata
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB = dict(
    dbname=os.environ.get("DB_NAME", "greengap"),
    user=os.environ.get("DB_USER", "myseo"),
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    port=os.environ.get("DB_PORT", "5432"),
)
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "../data"))
# pipeline 이 만든 중간 산출물 위치. housing_geocoded.csv 를 여기서 읽는다.
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "../output"))

GU_CODE_MAP = {
    "11110": "종로구",  "11140": "중구",     "11170": "용산구",
    "11200": "성동구",  "11215": "광진구",   "11230": "동대문구",
    "11260": "중랑구",  "11290": "성북구",   "11305": "강북구",
    "11320": "도봉구",  "11350": "노원구",   "11380": "은평구",
    "11410": "서대문구","11440": "마포구",   "11470": "양천구",
    "11500": "강서구",  "11530": "구로구",   "11545": "금천구",
    "11560": "영등포구","11590": "동작구",   "11620": "관악구",
    "11650": "서초구",  "11680": "강남구",   "11710": "송파구",
    "11740": "강동구",
}


def load_districts(cur):
    print("Loading districts...")
    rows = [(code, name) for code, name in GU_CODE_MAP.items()]
    execute_values(cur, "INSERT INTO districts (gu_code, gu_name) VALUES %s ON CONFLICT DO NOTHING", rows)
    print(f"  {len(rows)}개 구 삽입 완료")


def load_parks(cur):
    print("Loading parks...")
    all_rows = []
    for path in glob.glob(os.path.join(DATA_DIR, "구/*.csv")):
        gu_name = os.path.splitext(os.path.basename(path))[0]
        # macOS 는 한글 파일명을 자소 분리(NFD)로 저장한다. 브라우저로 내려받은
        # 파일과 기존 파일의 표현이 달라 문자열 비교가 실패하므로 NFC 로 맞춘다.
        gu_name = unicodedata.normalize("NFC", gu_name)
        gu_code = next((k for k, v in GU_CODE_MAP.items() if v == gu_name), None)
        if not gu_code:
            # 조용히 건너뛰면 데이터가 빠진 걸 알아채기 어렵다.
            print(f"  건너뜀 — 자치구를 알 수 없는 파일: {os.path.basename(path)}")
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", usecols=["공원명", "공원구분", "위도", "경도", "공원면적"])
        df = df.dropna(subset=["위도", "경도"])
        for _, row in df.iterrows():
            all_rows.append((gu_code, row["공원명"], row["공원구분"], float(row["위도"]), float(row["경도"]), row["공원면적"]))

    # 원본 CSV에 모든 값이 똑같은 행이 섞여 있다. 그대로 넣으면 반경 내 공원 수와
    # 총면적이 부풀려진다. 이름과 좌표가 같아도 면적이나 구분이 다르면 실제로 별개
    # 공원이므로(예: "개봉" 3023㎡ / 3684.6㎡) 전 컬럼이 일치할 때만 중복으로 본다.
    before = len(all_rows)
    all_rows = list(dict.fromkeys(all_rows))
    if before != len(all_rows):
        print(f"  완전중복 {before - len(all_rows)}행 제거")

    # parks 에는 자연키로 쓸 만한 컬럼이 없어 ON CONFLICT 를 걸 수 없다.
    # 매번 비우고 다시 넣어야 재실행 때 행이 누적되지 않는다.
    cur.execute("TRUNCATE parks RESTART IDENTITY CASCADE")
    execute_values(cur, """
        INSERT INTO parks (gu_code, park_name, park_type, lat, lng, area)
        VALUES %s
    """, all_rows)
    print(f"  {len(all_rows)}개 공원 삽입 완료")


def load_population(cur):
    print("Loading population... (시간이 걸릴 수 있어요)")
    df = pd.read_csv(
        os.path.join(DATA_DIR, "population.csv"),
        encoding="cp949",
        usecols=["일자", "시각", "행정동코드", "생활인구합계"]
    )
    df = df[df["시각"] == 0].copy()
    df["생활인구합계"] = pd.to_numeric(df["생활인구합계"], errors="coerce")
    df = df.dropna(subset=["생활인구합계"])
    df["gu_code"] = df["행정동코드"].astype(str).str[:5]
    df["date"] = pd.to_datetime(df["일자"].astype(str), format="%Y%m%d").dt.date

    rows = [
        (str(row["행정동코드"]), row["gu_code"], row["date"], float(row["생활인구합계"]))
        for _, row in df.iterrows()
    ]
    execute_values(cur, """
        INSERT INTO population (dong_code, gu_code, date, population_total)
        VALUES %s ON CONFLICT DO NOTHING
    """, rows)
    print(f"  {len(rows)}개 행 삽입 완료")


def load_housing(cur):
    print("Loading housing...")
    path = os.path.join(OUTPUT_DIR, "housing_geocoded.csv")
    if not os.path.exists(path):
        print(f"  건너뜀 — {path} 없음 "
              "(pipeline/preprocessing/housing_geocode.py 를 먼저 실행하세요)")
        return

    df = pd.read_csv(path, encoding="utf-8-sig")
    name_to_code = {name: code for code, name in GU_CODE_MAP.items()}

    unknown = sorted(set(df["gu_name"]) - set(name_to_code))
    if unknown:
        raise ValueError(f"districts 에 없는 자치구: {unknown}")

    rows = [
        (
            row["source"],
            row["complex_name"],
            name_to_code[row["gu_name"]],
            row["address_raw"],
            str(row["zipcode"]).zfill(5),          # 앞자리 0이 날아간 우편번호 복구
            row["lease_type"],
            int(row["households"]),
            row["move_in_date"],
            float(row["lat"]),
            float(row["lng"]),
            row["geocode_status"],
        )
        for _, row in df.iterrows()
    ]
    execute_values(cur, """
        INSERT INTO housing
            (source, complex_name, gu_code, address, zipcode, lease_type,
             households, move_in_date, lat, lng, geocode_status)
        VALUES %s
        ON CONFLICT (source, gu_code, complex_name) DO UPDATE
            SET address = EXCLUDED.address,
                zipcode = EXCLUDED.zipcode,
                lease_type = EXCLUDED.lease_type,
                households = EXCLUDED.households,
                move_in_date = EXCLUDED.move_in_date,
                lat = EXCLUDED.lat,
                lng = EXCLUDED.lng,
                geocode_status = EXCLUDED.geocode_status
    """, rows)
    checks = (df["geocode_status"] == "check").sum()
    print(f"  {len(rows)}개 단지 삽입 완료 (자치구 확인 필요 {checks}건)")


def load_walk(cur):
    print("Loading housing_park_walk...")
    path = os.path.join(OUTPUT_DIR, "housing_park_walk.csv")
    if not os.path.exists(path):
        print(f"  건너뜀 — {path} 없음 "
              "(pipeline/preprocessing/walk_distance.py 를 먼저 실행하세요)")
        return

    df = pd.read_csv(path, encoding="utf-8-sig")
    # 경로를 못 찾은 쌍(failed)은 넣지 않는다. 값이 비어 있는 행을 넣으면
    # API 쪽에서 "아직 안 받은 것"과 "받았는데 경로가 없는 것"이 구분되지 않는다.
    # onsite 는 공원이 단지 안이라 호출 없이 직선값을 쓴 쌍으로, 값은 유효하다.
    df = df[df["status"].isin(["ok", "onsite"])].dropna(subset=["walk_m", "walk_sec"])

    rows = [
        (int(r["housing_id"]), int(r["park_id"]),
         float(r["straight_m"]), float(r["walk_m"]), int(r["walk_sec"]))
        for _, r in df.iterrows()
    ]
    if not rows:
        print("  적재할 행이 없습니다")
        return

    execute_values(cur, """
        INSERT INTO housing_park_walk (housing_id, park_id, straight_m, walk_m, walk_sec)
        VALUES %s
        ON CONFLICT (housing_id, park_id) DO UPDATE
            SET straight_m = EXCLUDED.straight_m,
                walk_m = EXCLUDED.walk_m,
                walk_sec = EXCLUDED.walk_sec
    """, rows)
    print(f"  {len(rows)}쌍 삽입 완료")


def load_greengap_stats(cur):
    print("Loading greengap_stats...")
    cur.execute("""
        INSERT INTO greengap_stats (gu_code, total_park_area, population, green_per_capita)
        SELECT
            p.gu_code,
            SUM(pk.area) AS total_park_area,
            SUM(p.population_total) AS population,
            SUM(pk.area) / NULLIF(SUM(p.population_total), 0) AS green_per_capita
        FROM population p
        JOIN (
            SELECT gu_code, SUM(area) AS area FROM parks GROUP BY gu_code
        ) pk ON pk.gu_code = p.gu_code
        GROUP BY p.gu_code
        ON CONFLICT (gu_code) DO UPDATE
            SET total_park_area = EXCLUDED.total_park_area,
                population = EXCLUDED.population,
                green_per_capita = EXCLUDED.green_per_capita
    """)
    print("  greengap_stats 계산 완료")


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        load_districts(cur)
        load_parks(cur)
        load_population(cur)
        load_housing(cur)
        load_walk(cur)
        load_greengap_stats(cur)
        conn.commit()
        print("\n모든 데이터 로드 완료!")
    except Exception as e:
        conn.rollback()
        print(f"오류 발생: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
