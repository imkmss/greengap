"""SH 주택관리현황 xlsx를 읽어 단지 주소를 좌표로 변환한다.

    data/housing/*.xlsx  ->  output/housing_geocoded.csv

카카오 로컬 API를 쓰며, 키는 환경변수로 받는다.

    KAKAO_REST_API_KEY=xxxx python3 housing_geocode.py

표준 라이브러리만 사용한다. xlsx는 zip이라 zipfile + xml로 직접 읽고,
API 호출은 urllib로 한다. 별도 설치가 필요 없다.

중간 결과를 계속 기록하므로 중단 후 다시 실행하면 남은 단지부터 이어서 한다.
"""

import csv
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

BASE_DIR = Path(__file__).resolve().parents[2]
INPUT_DIR = BASE_DIR / "data" / "housing"
OUTPUT_PATH = BASE_DIR / "output" / "housing_geocoded.csv"

API_KEY = os.environ.get("KAKAO_REST_API_KEY", "").strip()
ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 호출 간격(초). 카카오 일 쿼터는 10만이라 여유롭지만 순간 QPS는 지켜준다.
REQUEST_INTERVAL = 0.1

# 서울 경계. 이 안에 들어오고 자치구까지 맞으면 ok로 본다.
SEOUL_BOUNDS = {"lat": (37.40, 37.72), "lng": (126.73, 127.20)}

# 수도권 경계. SH 단지 중에는 노원구 관할이지만 실제 위치가 의정부인 곳처럼
# 서울 밖에 있는 정상 단지가 있다. 이 범위 안이면 좌표를 채택하되 check로 표시한다.
# 이 밖이면 다른 지역을 잘못 잡은 것으로 보고 다음 후보로 넘어간다.
METRO_BOUNDS = {"lat": (37.20, 37.95), "lng": (126.50, 127.45)}

XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

FIELDS = [
    "source", "gu_name", "complex_name", "lease_type", "households",
    "move_in_date", "address_raw", "zipcode",
    "lat", "lng", "geocode_status", "geocode_method",
    "matched_address", "gu_match", "query_used",
]


# --------------------------------------------------------------------------
# xlsx 읽기
# --------------------------------------------------------------------------

def _column_index(cell_ref):
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    index = 0
    for ch in letters:
        index = index * 26 + ord(ch) - 64
    return index - 1


def read_xlsx(path):
    """첫 번째 시트를 행 리스트로 읽는다."""
    archive = zipfile.ZipFile(path)

    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in root.iter(XLSX_NS + "si"):
            shared.append("".join(t.text or "" for t in item.iter(XLSX_NS + "t")))

    sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(XLSX_NS + "row"):
        cells = {}
        for cell in row.iter(XLSX_NS + "c"):
            value_node = cell.find(XLSX_NS + "v")
            if value_node is None:
                inline = cell.find(XLSX_NS + "is")
                value = "".join(t.text or "" for t in inline.iter(XLSX_NS + "t")) if inline is not None else ""
            elif cell.get("t") == "s":
                value = shared[int(value_node.text)]
            else:
                value = value_node.text or ""
            cells[_column_index(cell.get("r"))] = value
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "").strip() for i in range(width)])
    return rows


def excel_serial_to_date(value):
    """엑셀 날짜 일련번호를 ISO 문자열로. 1900 윤년 버그 때문에 기준일이 12-30이다."""
    try:
        serial = int(float(value))
    except (TypeError, ValueError):
        return ""
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=serial)).isoformat()


# --------------------------------------------------------------------------
# 주소 정제
# --------------------------------------------------------------------------

# "서울시립대로"가 "서울시"로 시작하므로 반드시 공백까지 확인하고 떼야 한다.
_CITY_PREFIX = re.compile(r"^(서울특별시|서울시|서울)\s+")
_PARENS = re.compile(r"\(([^)]*)\)")
_JIBUN_IN_TEXT = re.compile(r"([가-힣]+동)\s*(\d+(?:-\d+)?)\s*(?:번지)?")


def strip_prefix(address, gu_name):
    """주소 앞에 이미 붙어 있는 시/구 표기를 떼어낸다. 나중에 일괄로 다시 붙인다."""
    cleaned = _CITY_PREFIX.sub("", address.strip())
    cleaned = re.sub(r"^" + re.escape(gu_name) + r"\s+", "", cleaned)
    return cleaned.strip()


def extract_jibun(address):
    """괄호 안 또는 본문에서 지번(동 + 번지)을 뽑는다."""
    match = _PARENS.search(address)
    if match:
        head = match.group(1).split(",")[0].strip()
        if _JIBUN_IN_TEXT.search(head):
            found = _JIBUN_IN_TEXT.search(head)
            return f"{found.group(1)} {found.group(2)}"
    found = _JIBUN_IN_TEXT.search(address)
    if found:
        return f"{found.group(1)} {found.group(2)}"
    return ""


def build_queries(gu_name, complex_name, address):
    """시도할 질의를 우선순위대로 만든다.

    원본 주소에 시/구가 빠져 있어 도로명이 전국에서 중복될 수 있다.
    그래서 어떤 질의든 "서울 {자치구}"를 앞에 붙인다.
    """
    prefix = f"서울 {gu_name}"
    queries = []

    road = _PARENS.sub("", strip_prefix(address, gu_name)).strip(" ,")
    if road:
        queries.append(("road", f"{prefix} {road}"))
        # "한천로 592-8, 592-6" 처럼 한 칸에 두 주소가 병기된 경우가 있다.
        if "," in road:
            queries.append(("road", f"{prefix} {road.split(',')[0].strip()}"))

    jibun = extract_jibun(address)
    if jibun:
        queries.append(("jibun", f"{prefix} {jibun}"))

    # "청계로벤하임(숭인동 240-1)" 처럼 단지명 괄호에만 지번이 있는 경우가 있다.
    name_jibun = extract_jibun(complex_name)
    if name_jibun:
        queries.append(("jibun_name", f"{prefix} {name_jibun}"))

    if complex_name:
        # 괄호를 떼야 장소 검색이 걸린다. "더푸름(성북1)" -> "더푸름"
        bare_name = _PARENS.sub("", complex_name).strip()
        queries.append(("keyword_gu", f"{prefix} {bare_name or complex_name}"))
        queries.append(("keyword", bare_name or complex_name))

    # 마지막 수단: 접두어 없이 질의한다.
    # 노원구 관할이지만 실제로는 의정부 장암동에 있는 단지처럼, 자치구를 붙이면
    # 오히려 결과가 안 나오는 경우가 있다. 엉뚱한 지역이 잡히는 건 METRO_BOUNDS가
    # 거르고, 자치구가 안 맞으므로 결과는 check로 남아 사람이 확인하게 된다.
    if road:
        queries.append(("no_prefix", road))
    if jibun:
        queries.append(("no_prefix", jibun))

    seen = set()
    unique = []
    for method, query in queries:
        if query not in seen:
            seen.add(query)
            unique.append((method, query))
    return unique


# --------------------------------------------------------------------------
# 카카오 로컬 API
# --------------------------------------------------------------------------

def call_api(url, query):
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode({'query': query, 'size': 5})}",
        headers={"Authorization": f"KakaoAK {API_KEY}"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8")).get("documents", [])
        except urllib.error.HTTPError as err:
            if err.code == 429:          # 쿼터/속도 제한
                time.sleep(2 ** attempt)
                continue
            if err.code in (400, 404):   # 질의 형식 문제 — 재시도해도 같다
                return []
            body = err.read().decode("utf-8", "replace")[:200]
            print(f"    HTTP {err.code}: {body}")
            if err.code in (401, 403):   # 키/권한 문제 — 더 진행해도 의미 없다
                raise SystemExit(
                    "\n인증에 실패했습니다. KAKAO_REST_API_KEY를 확인하고, "
                    "카카오 개발자 콘솔에서 [제품 설정] > [카카오맵]이 켜져 있는지 보세요."
                )
            time.sleep(1)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            print(f"    재시도 {attempt + 1}/3: {err}")
            time.sleep(1)
    return []


def _within(lat, lng, bounds):
    lat_lo, lat_hi = bounds["lat"]
    lng_lo, lng_hi = bounds["lng"]
    return lat_lo <= lat <= lat_hi and lng_lo <= lng <= lng_hi


def pick_document(documents, gu_name):
    """서울 안이면서 자치구가 일치하는 결과를 우선 고른다.

    자치구가 다르거나 서울 밖(수도권 이내)이면 좌표는 채택하되 fallback으로 남겨
    호출부가 check 상태로 기록하게 한다. 수도권 밖은 오매칭으로 보고 버린다.
    """
    fallback = None
    for doc in documents:
        try:
            lng, lat = float(doc["x"]), float(doc["y"])
        except (KeyError, TypeError, ValueError):
            continue

        if not _within(lat, lng, METRO_BOUNDS):
            continue

        matched = (
            doc.get("address_name")
            or doc.get("road_address_name")
            or (doc.get("road_address") or {}).get("address_name", "")
        )
        confident = gu_name in matched and _within(lat, lng, SEOUL_BOUNDS)
        result = {"lat": lat, "lng": lng, "matched": matched, "gu_match": confident}
        if confident:
            return result
        if fallback is None:
            fallback = result
    return fallback


def geocode(gu_name, complex_name, address):
    for method, query in build_queries(gu_name, complex_name, address):
        url = KEYWORD_URL if method.startswith("keyword") else ADDRESS_URL
        documents = call_api(url, query)
        time.sleep(REQUEST_INTERVAL)
        picked = pick_document(documents, gu_name)
        if picked:
            return {
                "lat": picked["lat"],
                "lng": picked["lng"],
                "geocode_status": "ok" if picked["gu_match"] else "check",
                "geocode_method": method,
                "matched_address": picked["matched"],
                "gu_match": "Y" if picked["gu_match"] else "N",
                "query_used": query,
            }
    return {
        "lat": "", "lng": "", "geocode_status": "failed", "geocode_method": "",
        "matched_address": "", "gu_match": "", "query_used": "",
    }


# --------------------------------------------------------------------------

def load_done():
    """이미 처리한 단지를 (자치구, 단지명)으로 기억해 재실행 시 건너뛴다."""
    if not OUTPUT_PATH.exists():
        return {}, []
    with OUTPUT_PATH.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {(r["gu_name"], r["complex_name"]) for r in rows}, rows


def main():
    if not API_KEY:
        raise SystemExit(
            "KAKAO_REST_API_KEY가 비어 있습니다.\n"
            "  KAKAO_REST_API_KEY=발급받은_REST_키 python3 housing_geocode.py"
        )

    sources = sorted(INPUT_DIR.glob("*.xlsx"))
    if not sources:
        raise SystemExit(f"{INPUT_DIR} 에 xlsx 파일이 없습니다.")

    rows = read_xlsx(sources[0])
    header, records = rows[0], rows[1:]
    print(f"입력: {sources[0].name}")
    print(f"컬럼: {header}")
    print(f"단지: {len(records)}건\n")

    done_keys, existing = load_done()
    if done_keys:
        print(f"이미 처리된 {len(done_keys)}건은 건너뜁니다.\n")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = list(existing)

    def flush():
        with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(results)

    for i, record in enumerate(records, 1):
        gu_name, complex_name, lease_type = record[0], record[1], record[2]
        households, move_in, address, zipcode = record[3], record[4], record[5], record[6]

        if (gu_name, complex_name) in done_keys:
            continue

        result = geocode(gu_name, complex_name, address)
        results.append({
            "source": "SH",
            "gu_name": gu_name,
            "complex_name": complex_name,
            "lease_type": lease_type,
            "households": households,
            "move_in_date": excel_serial_to_date(move_in),
            "address_raw": address,
            "zipcode": zipcode,
            **result,
        })

        mark = {"ok": "OK", "check": "??", "failed": "XX"}[result["geocode_status"]]
        print(f"[{i:3}/{len(records)}] {mark} {gu_name} {complex_name}"
              f"{'' if result['geocode_status'] == 'failed' else '  <- ' + result['matched_address']}")

        if i % 25 == 0:
            flush()

    flush()
    report(results)


def report(results):
    status = Counter(r["geocode_status"] for r in results)
    total = len(results)
    ok, check, failed = status["ok"], status["check"], status["failed"]

    print("\n" + "=" * 60)
    print(f"전체 {total}건")
    print(f"  성공        {ok:4}  ({ok / total * 100:.1f}%)")
    print(f"  확인 필요   {check:4}  (좌표는 나왔으나 자치구 불일치)")
    print(f"  실패        {failed:4}")

    print("\n단계별 성공 분포")
    labels = {
        "road": "1. 도로명", "jibun": "2. 지번",
        "jibun_name": "3. 단지명 속 지번", "keyword_gu": "4. 단지명+자치구", "keyword": "5. 단지명", "no_prefix": "6. 접두어 없음",
    }
    methods = Counter(r["geocode_method"] for r in results if r["geocode_method"])
    for key, label in labels.items():
        if methods.get(key):
            print(f"  {label:20} {methods[key]:4}건")

    if check:
        print("\n확인 필요 (자치구 불일치)")
        for r in results:
            if r["geocode_status"] == "check":
                print(f"  [{r['gu_name']}] {r['complex_name']}")
                print(f"      원본: {r['address_raw']}")
                print(f"      매칭: {r['matched_address']}")

    if failed:
        print("\n실패 목록")
        for r in results:
            if r["geocode_status"] == "failed":
                print(f"  [{r['gu_name']}] {r['complex_name']} — {r['address_raw']}")

    print("=" * 60)
    print(f"저장: {OUTPUT_PATH.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    sys.exit(main())
