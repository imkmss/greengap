import './About.css';

function AboutSection() {
  return (
    <div className="about-content">
      <section className="about-hero">
        <h1 className="about-hero-title">Green Gap Finder</h1>
        <p className="about-hero-sub">
          서울시 녹지 부족 구역 탐지 및 친환경 도시 설계 의사결정 지원 시스템
        </p>
      </section>

      <section className="about-section">
        <h2>프로젝트 개요</h2>
        <p>
          GGF는 서울시를 대상으로 토지피복도, 공원, 인구 데이터를 통합하여
          <strong> 녹지 부족 구역을 정량적으로 탐지</strong>하고,
          2040 서울도시기본계획의 공간·환경 목표에 부합하는
          <strong> 친환경 도시 설계 대안을 우선순위 형태로 제안</strong>하는
          데이터 기반 의사결정 지원 시스템입니다.
        </p>
      </section>

      <section className="about-section">
        <h2>문제 정의</h2>
      </section>

      <section className="about-section">
        <h2>데이터 파이프라인</h2>
      </section>

      <section className="about-section">
        <h2>기능 로드맵</h2>
      </section>

      <section className="about-section">
        <h2>기술 스택</h2>
        <div className="about-stack">
          {[
            { label: '언어', value: 'Python' },
            { label: '공간 분석', value: 'GIS · GeoPandas · Shapely' },
            { label: '머신러닝', value: 'U-Net (딥러닝 세그멘테이션)' },
            { label: '백엔드', value: 'FastAPI · PostgreSQL' },
            { label: '프론트엔드', value: 'React · Google Maps API' },
            { label: '데이터', value: 'GeoJSON · CSV · Raster' },
          ].map((item, i) => (
            <div key={i} className="about-stack-row">
              <span className="about-stack-label">{item.label}</span>
              <span className="about-stack-value">{item.value}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="about-section">
        <h2>활용 데이터</h2>
        <div className="about-stack">
          {[
            { label: '토지피복도', value: '환경부' },
            { label: '공원 데이터', value: '서울시 공공데이터' },
            { label: '인구 데이터', value: '통계청' },
            { label: '행정동 경계', value: '서울시 공공데이터' },
            { label: '대기질 데이터', value: '환경부 에어코리아' },
          ].map((item, i) => (
            <div key={i} className="about-stack-row">
              <span className="about-stack-label">{item.label}</span>
              <span className="about-stack-value">{item.value}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default AboutSection;
