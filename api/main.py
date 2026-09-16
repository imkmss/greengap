import os

import psycopg2
import psycopg2.extras
from fastapi import FastAPI
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


def query(sql):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


@app.on_event("startup")
def load_cache():
    _cache["parks"] = query("""
        SELECT p.park_name AS "공원명", p.park_type AS "공원구분",
               p.lat AS "위도", p.lng AS "경도", p.area AS "공원면적",
               d.gu_name AS "구"
        FROM parks p
        JOIN districts d ON d.gu_code = p.gu_code
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
def get_parks():
    return _cache["parks"]


@app.get("/api/districts/summary")
def get_district_summary():
    return _cache["districts_summary"]


@app.get("/api/greengap")
def get_greengap():
    return _cache["greengap"]
