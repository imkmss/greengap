import pandas as pd

df = pd.read_csv("../../data/population.csv", encoding="cp949")

# 필요한 컬럼만 추출
result = df[['행정동코드', '생활인구합계']]

# 컬럼 이름 정리 및 숫자 변환
result = result.rename(columns={'생활인구합계': 'population'})
result['population'] = pd.to_numeric(result['population'], errors='coerce')

# 행정동 단위 합산
result = result.groupby('행정동코드', as_index=False)['population'].sum()
result['population'] = result['population'].round(2)

result.to_csv("../../output/population_clean.csv", index=False, encoding="utf-8-sig")

output = pd.read_csv("../../output/population_clean.csv", encoding="utf-8-sig")
print(output.head(20).to_string())