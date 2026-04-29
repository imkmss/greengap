import pandas as pd

df = pd.read_csv("../../data/population.csv", encoding="cp949")

# 필요한 컬럼만 추출
result = df[['행정동코드', '생활인구합계']]

# 컬럼 이름 정리
result.rename(columns={'생활인구합계': 'population'}, inplace=True)

result.to_csv("../../output/population_clean.csv", index=False, encoding="utf-8-sig")

output = pd.read_csv("../../output/population_clean.csv", encoding="utf-8-sig")
print(output.head(20).to_string())