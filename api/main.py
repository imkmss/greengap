import os

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DB = dict(
    dbname=os.environ.get("DB_NAME", "greengap"),
    user=os.environ.get("DB_USER", "myseo"),
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    port=os.environ.get("DB_PORT", "5432"),
)

# 서버 시작 시 한 번만 DB에서 읽어 메모리에 캐시
_cache = {}


def get_conn():
    return psycopg2.connect(**DB)


def query(sql, params=None):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


@app.on_event("startup")
def load_cache():
    # 기존 프론트가 쓰는 한글 키는 그대로 두고 id 만 추가했다.
    # 공원 기준 조회(/api/parks/{id}/nearby)를 하려면 마커에서 id 를 알아야 한다.
    _cache["parks"] = query("""
        SELECT p.id, p.park_name AS "공원명", p.park_type AS "공원구분",
               p.lat AS "위도", p.lng AS "경도", p.area AS "공원면적",
               d.gu_name AS "구"
        FROM parks p
        JOIN districts d ON d.gu_code = p.gu_code
    """)
    _cache["housing"] = query("""
        SELECT h.id, h.complex_name, h.lease_type, h.households,
               h.move_in_date, h.address, h.lat, h.lng, h.geocode_status,
               d.gu_name
        FROM housing h
        JOIN districts d ON d.gu_code = h.gu_code
        ORDER BY d.gu_name, h.complex_name
    """)
    _cache["greengap"] = query("""
        SELECT d.gu_name AS "구",
               g.total_park_area,
               g.population,
               g.green_per_capita
        FROM greengap_stats g
        JOIN districts d ON d.gu_code = g.gu_code
        ORDER BY d.gu_name
    """)
    _cache["districts_summary"] = query("""
        SELECT d.gu_name AS "구",
               SUM(p.area) AS total_area,
               COUNT(*) AS park_count
        FROM parks p
        JOIN districts d ON d.gu_code = p.gu_code
        GROUP BY d.gu_name
        ORDER BY d.gu_name
    """)


@app.get("/api/parks")
def get_parks(gu: str | None = None, type: str | None = None):
    rows = _cache["parks"]
    if gu:
        rows = [r for r in rows if r["구"] == gu]
    if type:
        wanted = set(type.split(","))
        rows = [r for r in rows if r["공원구분"] in wanted]
    return rows


@app.get("/api/housing")
def get_housing(gu: str | None = None):
    rows = _cache["housing"]
    if gu:
        rows = [r for r in rows if r["gu_name"] == gu]
    return rows


@app.get("/api/districts/summary")
def get_district_summary():
    return _cache["districts_summary"]


@app.get("/api/greengap")
def get_greengap():
    return _cache["greengap"]


# --------------------------------------------------------------------------
# 주변 조회
#
# 단지에서 보면 공원이, 공원에서 보면 단지가 대상이 된다. 두 방향이 같은 형태를
# 반환하므로 프론트는 사이드바를 하나만 만들면 된다.
#
# 825 x 1723 = 142만 쌍이지만 한 지점 기준 조회는 0.6ms 라 미리 구워두지 않는다.
# 전체를 점수순으로 정렬해야 하는 시점(검색 기능)에 사전 계산 테이블을 도입한다.
# --------------------------------------------------------------------------

DEFAULT_RADIUS_M = 800  # 2040 서울도시기본계획의 보행 10분 접근권 기준

_ORIGIN_SQL = {
    "housing": """
        SELECT h.id, h.complex_name AS name, h.lat, h.lng, d.gu_name,
               h.lease_type, h.households, h.move_in_date, h.address,
               h.geocode_status
        FROM housing h JOIN districts d ON d.gu_code = h.gu_code
        WHERE h.id = %(id)s
    """,
    "park": """
        SELECT p.id, p.park_name AS name, p.lat, p.lng, d.gu_name,
               p.park_type AS subtype, p.area
        FROM parks p JOIN districts d ON d.gu_code = p.gu_code
        WHERE p.id = %(id)s
    """,
}

_TARGET_SQL = {
    "park": """
        SELECT p.id, p.park_name AS name, p.park_type AS subtype, p.area,
               d.gu_name, p.lat, p.lng, w.walk_m, w.walk_sec,
               haversine_m(%(lat)s, %(lng)s, p.lat, p.lng) AS distance_m
        FROM parks p
        JOIN districts d ON d.gu_code = p.gu_code
        LEFT JOIN housing_park_walk w
               ON w.park_id = p.id AND w.housing_id = %(origin_id)s
    """,
    "housing": """
        SELECT h.id, h.complex_name AS name, h.lease_type AS subtype,
               h.households, d.gu_name, h.lat, h.lng, w.walk_m, w.walk_sec,
               haversine_m(%(lat)s, %(lng)s, h.lat, h.lng) AS distance_m
        FROM housing h
        JOIN districts d ON d.gu_code = h.gu_code
        LEFT JOIN housing_park_walk w
               ON w.housing_id = h.id AND w.park_id = %(origin_id)s
    """,
}


def _nearby(origin_kind, target_kind, item_id, radius):
    found = query(_ORIGIN_SQL[origin_kind], {"id": item_id})
    if not found:
        raise HTTPException(status_code=404, detail=f"{origin_kind} id={item_id} 없음")
    origin = found[0]

    base = _TARGET_SQL[target_kind]
    # 도보거리는 (단지, 공원) 쌍으로 저장돼 있어 조인하려면 기준 쪽 id가 필요하다.
    params = {"lat": origin["lat"], "lng": origin["lng"],
              "radius": radius, "origin_id": origin["id"]}

    items = query(
        f"{base} WHERE haversine_m(%(lat)s, %(lng)s, "
        f"{'p' if target_kind == 'park' else 'h'}.lat, "
        f"{'p' if target_kind == 'park' else 'h'}.lng) <= %(radius)s "
        f"ORDER BY distance_m",
        params,
    )

    # 반경 안에 아무것도 없어도 "가장 가까운 것"은 알려준다. 800m 내 공원이 없는
    # 단지가 39곳인데, 빈 목록만 주면 데이터가 없는 건지 진짜 먼 건지 구분되지 않는다.
    nearest = query(f"{base} ORDER BY distance_m LIMIT 1", params)

    summary = {
        "count": len(items),
        "types": sorted({i["subtype"] for i in items if i["subtype"]}),
        "walk_known": sum(1 for i in items if i["walk_sec"] is not None),
    }
    if target_kind == "park":
        summary["total_area"] = sum(i["area"] or 0 for i in items)
    else:
        summary["total_households"] = sum(i["households"] or 0 for i in items)

    return {
        "origin": {"kind": origin_kind, **origin},
        "radius": radius,
        "policy_met": len(items) > 0,
        "nearest": nearest[0] if nearest else None,
        "items": items,
        "summary": summary,
    }


@app.get("/api/housing/{housing_id}/nearby")
def get_housing_nearby(housing_id: int, radius: int = DEFAULT_RADIUS_M):
    return _nearby("housing", "park", housing_id, radius)


@app.get("/api/parks/{park_id}/nearby")
def get_park_nearby(park_id: int, radius: int = DEFAULT_RADIUS_M):
    return _nearby("park", "housing", park_id, radius)
