"""단지에서 가까운 공원까지의 실제 도보거리를 TMAP으로 구한다.

    API /api/housing/{id}/nearby  ->  TMAP 보행자 경로  ->  output/housing_park_walk.csv

    TMAP_APP_KEY=xxxx python3 walk_distance.py [--limit 950] [--parks 3]

하버사인 직선거리는 하천·철도·대로를 무시한다. 직선 84m인 공원이 실제로는
412m를 걸어야 하는 경우가 있어, 정책 기준(보행 800m)을 직선거리로 판정하면
틀린다. 그 차이를 메우는 단계다.

대상 선정은 우리 API에 맡긴다. /api/housing/{id}/nearby 가 이미 거리순 정렬을
해주고 공원 id까지 주므로 계산을 중복할 이유가 없다.

TMAP 무료 한도가 일 1,000건인데 825단지 x 3공원 = 2,475콜이라 하루에 다 못 돈다.
결과를 계속 기록하고 이미 처리한 쌍은 건너뛰므로, 며칠에 나눠 실행하면 된다.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_PATH = BASE_DIR / "output" / "housing_park_walk.csv"

API_BASE = os.environ.get("GGF_API", "http://localhost:8000")
APP_KEY = os.environ.get("TMAP_APP_KEY", "").strip()
TMAP_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"

# 후보를 고르는 반경. 정책 기준 800m 밖의 공원도 최근접이면 쓸모가 있어 넉넉히 잡는다.
CANDIDATE_RADIUS_M = 2000
REQUEST_INTERVAL = 0.2

# 2040 서울도시기본계획의 보행 접근권 기준. unmet 모드가 이 값으로 판정한다.
POLICY_M = 800

# 이 거리 안이면 공원이 단지 안에 있다고 본다. 공원 지번이 단지 지번과 같으면
# 두 좌표가 소수점까지 겹쳐 TMAP에 출발=도착으로 들어가고 경로가 나오지 않는다.
# 불러봐야 실패하므로 직선값을 그대로 쓴다.
ONSITE_M = 20

FIELDS = [
    "housing_id", "housing_name", "park_id", "park_name", "park_type",
    "straight_m", "walk_m", "walk_sec", "status",
]


def get_json(url):
    with urllib.request.urlopen(url, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def tmap_walk(start, end, start_name, end_name):
    """보행자 경로를 호출해 (거리 m, 시간 초)를 반환한다. 실패하면 (None, None)."""
    payload = json.dumps({
        # TMAP은 X가 경도, Y가 위도다. lat/lng 순서로 넣으면 엉뚱한 경로가 나온다.
        "startX": start["lng"], "startY": start["lat"],
        "endX": end["lng"], "endY": end["lat"],
        # 둘 다 필수 파라미터라 비우면 오류가 난다.
        "startName": start_name or "출발",
        "endName": end_name or "도착",
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
    }).encode("utf-8")

    request = urllib.request.Request(TMAP_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "appKey": APP_KEY,
    })

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as res:
                body = json.loads(res.read().decode("utf-8"))
            props = body["features"][0]["properties"]
            return props.get("totalDistance"), props.get("totalTime")
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:200]
            if err.code == 429 or "QUOTA" in detail.upper():
                raise SystemExit(f"\n일일 쿼터를 소진했습니다. 내일 다시 실행하세요.\n{detail}")
            if err.code == 403:
                raise SystemExit(
                    "\n인증 실패. TMAP_APP_KEY 와, 대시보드 > 앱 > 상품 관리에서 "
                    f"TMAP 상품이 '사용중'인지 확인하세요.\n{detail}"
                )
            # 경로를 못 찾는 지점이 있다(섬, 보행 불가 구역 등). 재시도해도 같다.
            if err.code == 400:
                return None, None
            print(f"    HTTP {err.code}: {detail}")
            time.sleep(1)
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as err:
            print(f"    재시도 {attempt + 1}/3: {err}")
            time.sleep(1)
    return None, None


def load_done():
    if not OUTPUT_PATH.exists():
        return set(), []
    with OUTPUT_PATH.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # 좌표가 겹쳐 실패했던 쌍은 이제 호출 없이 처리한다. 기록에 남겨두면
    # 건너뛰기에 걸려 영영 값이 안 채워지므로 뺀다.
    kept = [r for r in rows
            if not (r["status"] == "failed" and float(r["straight_m"] or 0) < ONSITE_M)]
    if len(kept) != len(rows):
        print(f"좌표가 겹쳐 실패했던 {len(rows) - len(kept)}쌍을 다시 처리합니다.")
    return {(r["housing_id"], r["park_id"]) for r in kept}, kept


def pick_targets(complex_row, args):
    """이번 단지에서 도보거리를 구할 공원을 고른다.

    nearest — 가까운 순 N개. 전체를 고르게 채울 때 쓴다.
    unmet   — 도보 800m 충족이 아직 확인되지 않은 단지의, 안 재본 공원만.
              최근접 공원 하나가 800m를 넘었다고 미달로 단정할 수 없다. 직선으로
              더 먼 공원이 길이 곧아 실제로는 더 가까운 경우가 있어 판정이 뒤집힌다.
    """
    hid = complex_row["id"]

    if args.targets == "unmet":
        items = get_json(f"{API_BASE}/api/housing/{hid}/nearby?radius={POLICY_M}")["items"]
        # 이미 800m 안에 드는 공원이 확인됐으면 더 잴 이유가 없다.
        if any(p["walk_m"] is not None and p["walk_m"] <= POLICY_M for p in items):
            return []
        return [p for p in items if p["walk_m"] is None]

    nearby = get_json(f"{API_BASE}/api/housing/{hid}/nearby?radius={CANDIDATE_RADIUS_M}")
    # 반경 안에 하나도 없는 단지가 있다. 그때는 최근접 하나만이라도 구해둔다.
    return nearby["items"][:args.parks] or ([nearby["nearest"]] if nearby["nearest"] else [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=950,
                        help="이번 실행에서 호출할 최대 건수 (무료 한도 1000건에서 여유분을 뺀 값)")
    parser.add_argument("--parks", type=int, default=3,
                        help="단지당 도보거리를 구할 공원 수 (nearest 모드에서만)")
    parser.add_argument("--targets", choices=["nearest", "unmet"], default="nearest",
                        help="nearest=가까운 순 --parks개 / unmet=800m 충족 미확인 단지만")
    args = parser.parse_args()

    if not APP_KEY:
        raise SystemExit(
            "TMAP_APP_KEY가 비어 있습니다.\n"
            "  TMAP_APP_KEY=발급받은_앱키 python3 walk_distance.py"
        )

    housing = get_json(f"{API_BASE}/api/housing")
    print(f"단지 {len(housing)}건")

    done, results = load_done()
    if done:
        print(f"이미 처리한 {len(done)}쌍은 건너뜁니다.")
    if args.targets == "unmet":
        print(f"이번 실행 상한 {args.limit}콜 · 대상: 도보 {POLICY_M}m 충족 미확인 단지\n")
    else:
        print(f"이번 실행 상한 {args.limit}콜 · 단지당 공원 {args.parks}개\n")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    def flush():
        with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(results)

    calls = 0
    for idx, complex_row in enumerate(housing, 1):
        if calls >= args.limit:
            print(f"\n상한 {args.limit}콜에 도달했습니다. 다시 실행하면 이어서 진행합니다.")
            break

        targets = pick_targets(complex_row, args)

        for park in targets:
            key = (str(complex_row["id"]), str(park["id"]))
            if key in done:
                continue
            if calls >= args.limit:
                break

            straight = park["distance_m"]
            if straight < ONSITE_M:
                walk_m, walk_sec, status = round(straight), 0, "onsite"
            else:
                walk_m, walk_sec = tmap_walk(
                    complex_row, park, complex_row["complex_name"], park["name"]
                )
                calls += 1
                time.sleep(REQUEST_INTERVAL)
                status = "ok" if walk_m is not None else "failed"

            results.append({
                "housing_id": complex_row["id"],
                "housing_name": complex_row["complex_name"],
                "park_id": park["id"],
                "park_name": park["name"],
                "park_type": park["subtype"],
                "straight_m": round(straight),
                "walk_m": walk_m if walk_m is not None else "",
                "walk_sec": walk_sec if walk_sec is not None else "",
                "status": status,
            })
            done.add(key)

            head = (f"[{idx:3}/{len(housing)}] {complex_row['complex_name'][:14]:14} "
                    f"-> {park['name'][:14]:14}")
            if status == "onsite":
                print(f"{head} 단지 내 공원 (호출 생략)")
            elif walk_m is not None:
                ratio = walk_m / straight if straight else 0
                print(f"{head} 직선 {round(straight):4}m "
                      f"도보 {walk_m:4}m ({ratio:.1f}배, {round(walk_sec/60)}분)")
            else:
                print(f"{head} 경로 없음")

            if calls % 25 == 0:
                flush()

            # unmet 모드는 충족 여부만 가리면 된다. 800m 안에 드는 공원이 하나
            # 나온 순간 판정이 끝나므로 남은 후보에 콜을 더 쓰지 않는다.
            if args.targets == "unmet" and walk_m is not None and walk_m <= POLICY_M:
                break

    flush()
    report(results, calls)


def report(results, calls):
    ok = [r for r in results if r["status"] == "ok"]
    onsite = [r for r in results if r["status"] == "onsite"]
    failed = [r for r in results if r["status"] == "failed"]
    print("\n" + "=" * 64)
    print(f"이번 실행 {calls}콜 · 누적 {len(results)}쌍 "
          f"(측정 {len(ok)} / 단지 내 {len(onsite)} / 실패 {len(failed)})")

    if ok:
        ratios = []
        for r in ok:
            straight = float(r["straight_m"])
            if straight > 0:
                ratios.append((float(r["walk_m"]) / straight, r))
        if ratios:
            # 비율만 기준으로 정렬한다. 튜플째 비교하면 동률일 때 dict 를 비교하려다 터진다.
            ratios.sort(key=lambda pair: pair[0], reverse=True)
            avg = sum(x for x, _ in ratios) / len(ratios)
            print(f"\n도보/직선 비율 평균 {avg:.2f}배")
            print("\n차이가 가장 큰 사례 (직선거리만 보면 놓치는 것들)")
            for ratio, r in ratios[:5]:
                print(f"  {ratio:5.1f}배  {r['housing_name'][:18]:18} -> {r['park_name'][:16]:16} "
                      f"직선 {r['straight_m']:>4}m / 도보 {r['walk_m']:>5}m "
                      f"({round(int(r['walk_sec']) / 60)}분)")

            # 직선으로는 정책을 충족하는데 실제로 걸으면 미달인 경우
            flipped = [r for _, r in ratios
                       if float(r["straight_m"]) <= 800 < float(r["walk_m"])]
            print(f"\n직선 800m 이내지만 실제 도보로는 800m 초과: {len(flipped)}쌍")

    print("=" * 64)
    print(f"저장: {OUTPUT_PATH.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    sys.exit(main())
