import pandas as pd
from pathlib import Path

INPUT_DIR = Path("../../data/구")
OUTPUT_DIR = Path("../../output")
OUTPUT_DIR.mkdir(exist_ok=True)

COLUMNS = ['공원명', '공원구분', '소재지지번주소', '위도', '경도', '공원면적', '데이터기준일자']

for csv_file in sorted(INPUT_DIR.glob("*.csv")):
    df = pd.read_csv(csv_file, encoding="utf-8")
    result = df[COLUMNS].copy()

    output_name = csv_file.stem + "ver2.csv"
    result.to_csv(OUTPUT_DIR / output_name, index=False, encoding="utf-8-sig")
    print(f"{output_name} 저장 완료 ({len(result)}행)")
