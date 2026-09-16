import { useEffect, useRef, useState, useCallback, useMemo, memo } from 'react';
import { Map, MapMarker, Circle, MarkerClusterer, useKakaoLoader } from 'react-kakao-maps-sdk';
import Navbar from './Navbar';
import AboutSection from './AboutSection';
import './App.css';

const SEOUL_CENTER = { lat: 37.5665, lng: 126.9780 };
const mapContainerStyle = { width: '100%', height: '100%' };
// 카카오 지도 레벨은 숫자가 클수록 축소된다. 9가 서울 전역에 해당
const SEOUL_LEVEL = 9;
// 구글의 strictBounds 대체 — 서울 밖으로 과하게 축소되는 것만 막는다.
// 주의: react-kakao-maps-sdk의 prop 이름은 카카오 원본 API와 반대로 매핑된다.
//   minLevel prop -> kakao setMaxLevel() (축소 한계)  ← 우리가 쓰는 쪽
//   maxLevel prop -> kakao setMinLevel() (확대 한계)
const ZOOM_OUT_LIMIT = 11;
// 클러스터링 시작 레벨 (이 레벨 이상으로 축소되면 묶는다)
const CLUSTER_MIN_LEVEL = 6;

// 구별 색칠은 카카오 Polygon으로 재현할지 결정 전까지 보류.
// 되살릴 때는 이 값을 true로 바꾸고 App 안의 choropleth useEffect 주석을 해제한다.
const ENABLE_CHOROPLETH = false;

// 형광 계열 팔레트. 색상환을 23등분해 구마다 하나씩 배정한다.
// 선택 마커(#ffff00)와 겹치지 않도록 순수 노랑 근처는 비워뒀다.
const DISTRICT_COLORS = [
  '#ff073a', '#ff2d00', '#ff6b00', '#ff9e00', '#ffc800',
  '#c6ff00', '#7cff00', '#39ff14', '#00ff6a', '#00ffb3',
  '#00fff0', '#00d4ff', '#00a3ff', '#2979ff', '#3d4eff',
  '#6a2bff', '#9b30ff', '#c21fff', '#e619ff', '#ff00d4',
  '#ff0080', '#ff2e63', '#ff5c8a',
];

function getGreenGapColor(value, min, max) {
  const ratio = (value - min) / (max - min);
  const r = Math.round(180 * (1 - ratio));
  const g = Math.round(80 + 140 * ratio);
  return `rgb(${r}, ${g}, 40)`;
}

// 카카오 마커는 구글의 SymbolPath 같은 내장 도형이 없어서 원을 SVG로 직접 만든다
function parkMarkerImage(color, isSelected) {
  const radius = isSelected ? 7 : 4;
  const strokeColor = isSelected ? '#ffffff' : '#000000';
  const strokeWeight = isSelected ? 1.5 : 0.5;
  const size = Math.ceil((radius + strokeWeight) * 2);
  const center = size / 2;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">` +
    `<circle cx="${center}" cy="${center}" r="${radius}" fill="${color}" fill-opacity="0.95" ` +
    `stroke="${strokeColor}" stroke-width="${strokeWeight}" /></svg>`;

  return {
    src: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,
    size: { width: size, height: size },
  };
}

const ParkMarker = memo(function ParkMarker({ park, isSelected, color, onSelect }) {
  const image = useMemo(
    () => parkMarkerImage(isSelected ? '#ffff00' : color, isSelected),
    [isSelected, color]
  );

  return (
    <MapMarker
      position={{ lat: park['위도'], lng: park['경도'] }}
      title={park['공원명']}
      image={image}
      zIndex={isSelected ? 999 : 1}
      onClick={() => onSelect(park)}
    />
  );
});

function LayerControls({ showParks, onToggleParks, showChoropleth, onToggleChoropleth }) {
  return (
    <div className="sidebar-layer-section">
      <span className="sidebar-label">레이어</span>
      {ENABLE_CHOROPLETH && (
        <button
          className={`layer-toggle ${showChoropleth ? 'active' : ''}`}
          onClick={onToggleChoropleth}
        >
          <span className="layer-toggle-dot" style={{ background: showChoropleth ? '#2a9d8f' : '#ccc' }} />
          녹지 비율
        </button>
      )}
      <button
        className={`layer-toggle ${showParks ? 'active' : ''}`}
        onClick={onToggleParks}
      >
        <span className="layer-toggle-dot" />
        공원 레이어
      </button>
    </div>
  );
}

function Sidebar({ district, park, onClose, showParks, onToggleParks, showChoropleth, onToggleChoropleth }) {
  const layerControls = (
    <LayerControls
      showParks={showParks}
      onToggleParks={onToggleParks}
      showChoropleth={showChoropleth}
      onToggleChoropleth={onToggleChoropleth}
    />
  );

  if (!district && !park) {
    return (
      <div className="sidebar">
        <p className="sidebar-hint">구 또는 공원을 클릭하면<br />정보를 확인할 수 있어요</p>
        {layerControls}
      </div>
    );
  }

  if (district?.noData) {
    return (
      <div className="sidebar">
        <button className="sidebar-close" onClick={onClose}>✕</button>
        <div className="sidebar-badge">구</div>
        <div className="sidebar-title">{district['구']}</div>
        <p className="sidebar-hint">데이터가 없습니다</p>
        {layerControls}
      </div>
    );
  }

  if (park) {
    const apiKey = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
    // Street View Static도 구글 결제가 켜져 있어야 뜬다. 실패하면 이미지를 숨긴다.
    const streetViewUrl = `https://maps.googleapis.com/maps/api/streetview?size=280x160&location=${park['위도']},${park['경도']}&fov=90&key=${apiKey}`;
    const mapsUrl = `https://map.kakao.com/link/map/${encodeURIComponent(park['공원명'])},${park['위도']},${park['경도']}`;

    return (
      <div className="sidebar">
        <button className="sidebar-close" onClick={onClose}>✕</button>
        <div className="sidebar-badge">공원</div>
        <div className="sidebar-title">{park['공원명']}</div>
        <img
          className="sidebar-streetview"
          src={streetViewUrl}
          alt={park['공원명']}
          onError={(e) => { e.currentTarget.style.display = 'none'; }}
        />
        <div className="sidebar-section">
          <div className="sidebar-stat">
            <span className="sidebar-label">공원 구분</span>
            <span className="sidebar-value small">{park['공원구분']}</span>
          </div>
          <hr className="sidebar-divider" />
          <div className="sidebar-stat">
            <span className="sidebar-label">면적</span>
            <span className="sidebar-value">
              {Number(park['공원면적']).toLocaleString()}
              <span className="sidebar-unit">m²</span>
            </span>
          </div>
          <div className="sidebar-stat">
            <span className="sidebar-label">위치</span>
            <span className="sidebar-value small">{park['구']}</span>
          </div>
          <a className="sidebar-map-link" href={mapsUrl} target="_blank" rel="noreferrer">
            카카오맵에서 보기 →
          </a>
        </div>
        {layerControls}
      </div>
    );
  }

  return (
    <div className="sidebar">
      <button className="sidebar-close" onClick={onClose}>✕</button>
      <div className="sidebar-badge">구</div>
      <div className="sidebar-title">{district['구']}</div>
      <div className="sidebar-section">
        <div className="sidebar-stat">
          <span className="sidebar-label">1인당 녹지 면적</span>
          <span className="sidebar-value">
            {Number(district.green_per_capita).toFixed(2)}
            <span className="sidebar-unit">m²/인</span>
          </span>
        </div>
        <hr className="sidebar-divider" />
        <div className="sidebar-stat">
          <span className="sidebar-label">총 공원 면적</span>
          <span className="sidebar-value">
            {(Number(district.total_park_area) / 1_000_000).toFixed(2)}
            <span className="sidebar-unit">km²</span>
          </span>
        </div>
        <div className="sidebar-stat">
          <span className="sidebar-label">생활인구</span>
          <span className="sidebar-value">
            {Math.round(Number(district.population) / 10000).toLocaleString()}
            <span className="sidebar-unit">만 명</span>
          </span>
        </div>
      </div>
      {layerControls}
    </div>
  );
}

function App() {
  const [, mapError] = useKakaoLoader({
    appkey: process.env.REACT_APP_KAKAO_MAP_KEY,
    libraries: ['clusterer'],
  });

  const mapRef = useRef(null);
  const geojsonRef = useRef(null);
  const gapMapRef = useRef({});
  const minRef = useRef(0);
  const maxRef = useRef(1);

  const [parks, setParks] = useState([]);
  const [greengap, setGreengap] = useState([]);
  const [selected, setSelected] = useState(null);
  const [selectedPark, setSelectedPark] = useState(null);
  const [showParks, setShowParks] = useState(true);
  const [showChoropleth, setShowChoropleth] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/parks')
      .then(res => res.json())
      .then(setParks);
    fetch('http://localhost:8000/api/greengap')
      .then(res => res.json())
      .then(setGreengap);
    fetch('/seoul_districts.json')
      .then(res => res.json())
      .then(data => { geojsonRef.current = data; });
  }, []);

  const colorMap = useMemo(() => {
    const names = [...new Set(parks.map(p => p['구']))].sort();
    const map = {};
    names.forEach((name, i) => { map[name] = DISTRICT_COLORS[i % DISTRICT_COLORS.length]; });
    return map;
  }, [parks]);

  const onMapLoad = useCallback((map) => {
    mapRef.current = map;
  }, []);

  /*
   * 구별 색칠(choropleth) — 보류 중.
   *
   * 아래 코드는 구글 지도의 Data Layer(map.data)에 의존한다. GeoJSON을 통째로
   * 넘기면 폴리곤 생성·일괄 스타일링·클릭 이벤트를 알아서 처리해주는 기능인데,
   * 카카오에는 대응물이 없다. 되살리려면 seoul_districts.json을 직접 파싱해서
   * 구 25개를 kakao.maps.Polygon으로 만들고 각각에 스타일과 클릭 핸들러를
   * 붙여야 한다 (약 60~80줄).
   *
   * 되살릴 때는 파일 상단의 ENABLE_CHOROPLETH도 true로 바꿀 것.
   *
  useEffect(() => {
    if (!mapRef.current || greengap.length === 0) return;
    const map = mapRef.current;

    const values = greengap.map(d => d.green_per_capita);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const gapMap = {};
    greengap.forEach(d => { gapMap[d['구']] = d; });

    gapMapRef.current = gapMap;
    minRef.current = min;
    maxRef.current = max;

    const applyStyle = (geojson) => {
      map.data.forEach(f => map.data.remove(f));
      map.data.addGeoJson(geojson);
      map.data.setStyle(feature => {
        const name = feature.getProperty('name');
        const val = gapMapRef.current[name]?.green_per_capita ?? minRef.current;
        return {
          fillColor: getGreenGapColor(val, minRef.current, maxRef.current),
          fillOpacity: 0.55,
          strokeColor: '#ffffff',
          strokeWeight: 1,
        };
      });
      map.data.addListener('click', (e) => {
        const name = e.feature.getProperty('name');
        setSelectedPark(null);
        setSelected(gapMapRef.current[name] ?? { '구': name, noData: true });
      });
    };

    if (geojsonRef.current) {
      applyStyle(geojsonRef.current);
    } else {
      fetch('/seoul_districts.json')
        .then(res => res.json())
        .then(data => {
          geojsonRef.current = data;
          applyStyle(data);
        });
    }
  }, [greengap]);

  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.data.setStyle(feature => {
      if (!showChoropleth) return { fillOpacity: 0, strokeWeight: 0 };
      const name = feature.getProperty('name');
      const val = gapMapRef.current[name]?.green_per_capita ?? minRef.current;
      return {
        fillColor: getGreenGapColor(val, minRef.current, maxRef.current),
        fillOpacity: 0.55,
        strokeColor: '#ffffff',
        strokeWeight: 1,
      };
    });
  }, [showChoropleth]);
  */

  const handleSelectPark = useCallback((park) => {
    setSelected(null);
    setSelectedPark(park);
  }, []);

  const handleToggleParks = () => {
    setShowParks(v => {
      if (v) setSelectedPark(null);
      return !v;
    });
  };

  const handleToggleChoropleth = () => {
    setShowChoropleth(v => {
      if (v) setSelected(null);
      return !v;
    });
  };

  const [activeSection, setActiveSection] = useState(null);
  const aboutRef = useRef(null);
  const dataRef = useRef(null);
  const emptyRef = useRef(null);
  const contactRef = useRef(null);

  useEffect(() => {
    const sections = [
      { ref: aboutRef, name: 'about' },
      { ref: dataRef, name: 'data' },
      { ref: emptyRef, name: 'empty' },
      { ref: contactRef, name: 'contact' },
    ];
    const intersecting = new Set();
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            intersecting.add(entry.target.dataset.section);
          } else {
            intersecting.delete(entry.target.dataset.section);
          }
        });
        setActiveSection(intersecting.size > 0 ? [...intersecting].at(-1) : null);
      },
      { rootMargin: '-45% 0px -45% 0px', threshold: 0 }
    );
    sections.forEach(({ ref }) => { if (ref.current) observer.observe(ref.current); });
    return () => observer.disconnect();
  }, []);

  return (
    <div
        className="App"
        style={{
          backgroundImage: `url(${process.env.PUBLIC_URL}/background.png)`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundAttachment: 'fixed',
        }}
      >
      <Navbar activeSection={activeSection} />

      <div className="map-section">
        <div className="map-embed">
          {mapError ? (
            <p className="sidebar-hint">지도를 불러오지 못했습니다</p>
          ) : (
            <Map
              style={mapContainerStyle}
              center={SEOUL_CENTER}
              level={SEOUL_LEVEL}
              minLevel={ZOOM_OUT_LIMIT}
              onCreate={onMapLoad}
            >
              {showParks && selectedPark && (
                <Circle
                  center={{ lat: selectedPark['위도'], lng: selectedPark['경도'] }}
                  radius={800}
                  fillColor="#13f229"
                  fillOpacity={0.15}
                  strokeColor="#13f229"
                  strokeOpacity={0.6}
                  strokeWeight={1.5}
                />
              )}
              {showParks && (
                <MarkerClusterer averageCenter={true} minLevel={CLUSTER_MIN_LEVEL}>
                  {parks.map((park, i) => {
                    const isSelected = !!selectedPark && selectedPark['공원명'] === park['공원명']
                      && selectedPark['위도'] === park['위도'];
                    return (
                      <ParkMarker
                        key={i}
                        park={park}
                        isSelected={isSelected}
                        color={colorMap[park['구']] || '#cccccc'}
                        onSelect={handleSelectPark}
                      />
                    );
                  })}
                </MarkerClusterer>
              )}
            </Map>
          )}
        </div>

        <Sidebar
          district={selected}
          park={selectedPark}
          onClose={() => { setSelected(null); setSelectedPark(null); }}
          showParks={showParks}
          onToggleParks={handleToggleParks}
          showChoropleth={showChoropleth}
          onToggleChoropleth={handleToggleChoropleth}
        />
      </div>

      <div ref={aboutRef} data-section="about" className="scroll-section scroll-about">
        <AboutSection />
      </div>

      <div ref={dataRef} data-section="data" className="scroll-section scroll-data">
        <div className="about-content">
          <section className="about-hero">
            <h1 className="about-hero-title">Data</h1>
            <p className="about-hero-sub">준비 중입니다</p>
          </section>
        </div>
      </div>

      <div ref={emptyRef} data-section="empty" className="scroll-section scroll-empty">
        <div className="about-content">
          <section className="about-hero">
            <h1 className="about-hero-title">Empty</h1>
            <p className="about-hero-sub">준비 중입니다</p>
          </section>
        </div>
      </div>

      <div ref={contactRef} data-section="contact" className="scroll-section scroll-contact">
        <div className="about-content">
          <section className="about-hero">
            <h1 className="about-hero-title">Contact</h1>
            <p className="about-hero-sub">준비 중입니다</p>
          </section>
        </div>
      </div>
    </div>
  );
}

export default App;
