import pandas as pd

df = pd.read_csv("../../data/250_LOCAL_RESD.csv", encoding="utf-8-sig")

result = df[['일자', '행정동코드', '250M격자', '생활인구합계']].copy()

# 250M격자에서 숫자 8자리 추출 후 앞 4자리 X코드, 뒤 4자리 Y코드로 분리
nums = result['250M격자'].str.extract(r'(\d{8})')
result['X코드'] = nums[0].str[:4]
result['Y코드'] = nums[0].str[4:]

# 숫자 변환
result['생활인구합계'] = pd.to_numeric(result['생활인구합계'], errors='coerce')

# X코드, Y코드 기준 생활인구합계 평균 계산
avg = result.groupby(['X코드', 'Y코드'], as_index=False)['생활인구합계'].mean()
avg.rename(columns={'생활인구합계': '생활인구합계avg'}, inplace=True)
avg['생활인구합계avg'] = avg['생활인구합계avg'].round(2)

result = result.merge(avg, on=['X코드', 'Y코드'], how='left')

result.to_csv("../../output/population_per250.csv", index=False, encoding="utf-8-sig")
print(f"저장 완료: {len(result)}행")
print(result[['X코드', 'Y코드', '생활인구합계', '생활인구합계avg']].head(10).to_string())
