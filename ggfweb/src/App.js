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
// 클러스터링 시작 레벨. 6이면 축척 250m까지 확대해야 개별 마커가 보여서
// 대부분의 구간에서 클러스터만 보였다. 8이면 1km 축척부터 마커가 드러난다.
const CLUSTER_MIN_LEVEL = 8;

const API_BASE = 'http://localhost:8000';

// 2040 서울도시기본계획의 보행 10분 접근권 기준
const RADIUS_M = 800;

// 사이드바 너비. 기본값이 곧 최소값이고 두 배까지 넓힐 수 있다.
const SIDEBAR_MIN_W = 300;
const SIDEBAR_MAX_W = SIDEBAR_MIN_W * 2;

// 단지 마커. 소공원이 민트 네모라 겹치지 않게 진한 남색에 흰 테두리를 주고
// 공원보다 크게 그린다. 이 도구의 주인공이 단지라 시각적 위계도 그쪽이 위다.
const HOUSING_MARKER = { color: '#12309b', shape: 'square', stroke: '#ffffff', radius: 7 };

// 공원 구분은 원본에 14종이 있는데 뒤쪽 6종은 다 합쳐도 10개뿐이라 7그룹으로 묶는다.
// 색으로 자치구를 나타내던 것을 공원 성격으로 바꿨다. 자치구는 지도에 이미 지명이
// 표시되는 데다 23색은 범례를 만들어도 눈으로 매칭이 안 됐다.
const PARK_GROUPS = {
  neighborhood: { label: '근린공원',   color: '#39ff14', shape: 'circle'   },
  children:     { label: '어린이공원', color: '#ffc800', shape: 'circle'   },
  pocket:       { label: '소공원',     color: '#00ffb3', shape: 'square'   },
  culture:      { label: '문화·역사',  color: '#c21fff', shape: 'circle'   },
  active:       { label: '수변·체육',  color: '#00d4ff', shape: 'circle'   },
  large:        { label: '대형·특수',  color: '#ff6b00', shape: 'circle'   },
  etc:          { label: '기타',       color: '#ff2ec4', shape: 'triangle' },
};

const PARK_TYPE_TO_GROUP = {
  '근린공원': 'neighborhood',
  '어린이공원': 'children',
  '소공원': 'pocket',
  '문화공원': 'culture', '역사공원': 'culture',
  '수변공원': 'active', '체육공원': 'active',
  // "기타"는 이름과 달리 평균 16만 제곱미터로 가장 큰 공원들이다. 회색에 묻히면 안 된다.
  '기타': 'large', '도시농업공원': 'large', '묘지공원': 'large', '주제공원': 'large',
};

function parkGroup(parkType) {
  return PARK_GROUPS[PARK_TYPE_TO_GROUP[parkType] || 'etc'];
}

// 카카오 마커는 구글의 SymbolPath 같은 내장 도형이 없어서 SVG로 직접 그린다.
// 지름 8px일 때는 모양이 구분되지 않아 12px(선택 시 18px)로 키웠다. 단지 모드로
// 가면 화면에 공원이 5~15개만 뜨므로 크게 그려도 부담이 없다.
function markerImage({ color, shape, selected = false, radius: baseRadius = 6, stroke = '#000000' }) {
  const radius = selected ? baseRadius + 3 : baseRadius;
  const strokeColor = selected ? '#ffffff' : stroke;
  const strokeWeight = selected ? 2 : 0.8;
  const size = Math.ceil((radius + strokeWeight) * 2);
  const c = size / 2;

  let body;
  if (shape === 'triangle') {
    // 정삼각형은 같은 반지름의 원보다 작아 보여서 조금 키운다.
    const r = radius * 1.15;
    const points = [
      `${c},${c - r}`,
      `${c - r * 0.866},${c + r * 0.5}`,
      `${c + r * 0.866},${c + r * 0.5}`,
    ].join(' ');
    body = `<polygon points="${points}" fill="${color}" fill-opacity="0.95" ` +
           `stroke="${strokeColor}" stroke-width="${strokeWeight}" stroke-linejoin="round" />`;
  } else if (shape === 'square') {
    // 같은 반지름이면 정사각형이 원보다 넓어 보인다(4r² 대 3.14r²).
    // 0.9를 곱해 면적을 맞추고, 작은 크기에서 뭉개지지 않게 모서리를 살짝 둥글린다.
    const half = radius * 0.9;
    body = `<rect x="${c - half}" y="${c - half}" width="${half * 2}" height="${half * 2}" ` +
           `rx="${radius * 0.18}" fill="${color}" fill-opacity="0.95" ` +
           `stroke="${strokeColor}" stroke-width="${strokeWeight}" stroke-linejoin="round" />`;
  } else {
    body = `<circle cx="${c}" cy="${c}" r="${radius}" fill="${color}" fill-opacity="0.95" ` +
           `stroke="${strokeColor}" stroke-width="${strokeWeight}" />`;
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">${body}</svg>`;
  return {
    src: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,
    size: { width: size, height: size },
  };
}

const ParkMarker = memo(function ParkMarker({ park, isSelected, onSelect }) {
  const group = parkGroup(park['공원구분']);
  const image = useMemo(
    () => markerImage({
      color: isSelected ? '#ff0026' : group.color,
      shape: group.shape,
      selected: isSelected,
    }),
    [isSelected, group.color, group.shape]
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

const HousingMarker = memo(function HousingMarker({ item, isSelected, onSelect }) {
  const image = useMemo(
    () => markerImage({
      ...HOUSING_MARKER,
      // 단지는 노랑, 공원은 빨강으로 강조색을 나눈다. 같은 색이면 지도에서
      // 고른 단지와 강조된 공원이 구분되지 않는다.
      color: isSelected ? '#ffff00' : HOUSING_MARKER.color,
      selected: isSelected,
    }),
    [isSelected]
  );

  return (
    <MapMarker
      position={{ lat: item.lat, lng: item.lng }}
      title={item.complex_name || item.name}
      image={image}
      zIndex={isSelected ? 999 : 2}
      onClick={() => onSelect(item)}
    />
  );
});

// 사이드바와 지도 사이의 드래그 핸들. 사이드바가 오른쪽에 있으므로 창 너비에서
// 커서 위치를 빼면 그대로 너비가 된다. 더블클릭하면 기본값으로 돌아간다.
function SidebarResizer({ onResize }) {
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    const move = (ev) => onResize(window.innerWidth - ev.clientX);
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    // 드래그 중 지도나 텍스트가 선택되는 걸 막는다.
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [onResize]);

  return (
    <div
      className="sidebar-resizer"
      onMouseDown={handleMouseDown}
      onDoubleClick={() => onResize(SIDEBAR_MIN_W)}
      title="드래그하여 너비 조절"
    />
  );
}

function ModeToggle({ mode, onChange }) {
  return (
    <div className="sidebar-layer-section">
      <span className="sidebar-label">기준</span>
      {[['housing', '단지'], ['park', '공원']].map(([value, label]) => (
        <button
          key={value}
          className={`layer-toggle ${mode === value ? 'active' : ''}`}
          onClick={() => onChange(value)}
        >
          <span
            className="layer-toggle-dot"
            style={{ background: mode === value ? '#12309b' : '#ccc' }}
          />
          {label}
        </button>
      ))}
    </div>
  );
}

// 범례이자 조작부. 모드에 따라 역할이 바뀐다.
//   filter — 공원 모드. 어린이공원 1,010개를 빼야 클릭으로 고를 만한 수가 된다.
//   focus  — 단지 모드에서 단지를 고른 뒤. 반경 안의 해당 그룹 공원을 강조한다.
//            목록에 커서를 올렸을 때와 같은 강조를 그룹 단위로 켜는 것이다.
//   static — 단지 모드지만 아직 고른 단지가 없을 때. 강조할 대상이 없다.
function Legend({ variant, hidden, focus, onToggle, onFocus }) {
  return (
    <div className="legend">
      {Object.entries(PARK_GROUPS).map(([key, g]) => {
        const off = variant === 'filter' && hidden.has(key);
        const on = variant === 'focus' && focus === key;
        return (
          <button
            key={key}
            className={`legend-item ${off ? 'off' : ''}${on ? ' on' : ''}`}
            onClick={
              variant === 'filter' ? () => onToggle(key)
                : variant === 'focus' ? () => onFocus(key)
                  : undefined
            }
            disabled={variant === 'static'}
          >
            <span
              className={`legend-swatch legend-${g.shape}`}
              style={{ background: off ? '#ccc' : g.color }}
            />
            {g.label}
          </button>
        );
      })}
    </div>
  );
}

function formatDistance(m) {
  return m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`;
}

// 도보 시간. TMAP 결과가 아직 없는 쌍은 빈 값을 돌려준다.
function formatWalk(sec) {
  if (sec == null) return '';
  const min = Math.max(1, Math.round(sec / 60));
  return `도보 ${min}분`;
}

// 단지 기준이든 공원 기준이든 응답 형태가 같아서 이 컴포넌트 하나를 공유한다.
function NearbyPanel({ detail, onHover, focus }) {
  const { items, summary, nearest, policy_met: policyMet, radius } = detail;
  const targetIsPark = detail.origin.kind === 'housing';

  return (
    <>
      <div className={`policy-badge ${policyMet ? 'met' : 'unmet'}`}>
        {targetIsPark
          ? (policyMet ? '도보 10분 내 공원 접근권 충족' : '도보 10분 내 공원 없음')
          : (policyMet ? `반경 내 공공임대 ${summary.count}곳` : '반경 내 공공임대 없음')}
      </div>

      {nearest && (
        <div className="sidebar-stat">
          <span className="sidebar-label">가장 가까운 {targetIsPark ? '공원' : '단지'}</span>
          <span className="sidebar-value small">
            {nearest.name} · {formatDistance(nearest.distance_m)}
            {nearest.walk_sec != null && ` · ${formatWalk(nearest.walk_sec)}`}
          </span>
        </div>
      )}

      <hr className="sidebar-divider" />

      <div className="sidebar-stat">
        <span className="sidebar-label">반경 {radius}m 내</span>
        <span className="sidebar-value">
          {summary.count}
          <span className="sidebar-unit">{targetIsPark ? '곳' : '단지'}</span>
        </span>
      </div>
      {targetIsPark && summary.count > 0 && (
        <div className="sidebar-stat">
          <span className="sidebar-label">공원 총면적</span>
          <span className="sidebar-value">
            {Math.round(summary.total_area).toLocaleString()}
            <span className="sidebar-unit">m²</span>
          </span>
        </div>
      )}
      {!targetIsPark && summary.count > 0 && (
        <div className="sidebar-stat">
          <span className="sidebar-label">총 세대수</span>
          <span className="sidebar-value">
            {summary.total_households.toLocaleString()}
            <span className="sidebar-unit">세대</span>
          </span>
        </div>
      )}

      <ul className="nearby-list">
        {items.map(item => (
          <li
            key={item.id}
            className={`nearby-item${
              focus && (PARK_TYPE_TO_GROUP[item.subtype] || 'etc') === focus ? ' focus' : ''
            }`}
            onMouseEnter={() => onHover(item.id)}
            onMouseLeave={() => onHover(null)}
          >
            <span className="nearby-dist">
              {formatDistance(item.distance_m)}
              {item.walk_sec != null && (
                <em className="nearby-walk">{formatWalk(item.walk_sec)}</em>
              )}
            </span>
            <span className="nearby-name">{item.name}</span>
            <span className="nearby-sub">{item.subtype}</span>
          </li>
        ))}
        {items.length === 0 && (
          <li className="sidebar-hint">
            반경 {radius}m 안에 {targetIsPark ? '공원이' : '단지가'} 없습니다
          </li>
        )}
      </ul>
    </>
  );
}

function Sidebar({ mode, onModeChange, origin, detail, loading, onClose, onHover,
                  hidden, onToggleGroup, focusGroup, onFocusGroup }) {
  // 공원 모드의 반경 안 대상은 단지라 공원 그룹으로 강조할 것이 없다.
  const canFocus = mode === 'housing' && !!detail;
  const controls = (
    <>
      <ModeToggle mode={mode} onChange={onModeChange} />
      <Legend
        variant={mode === 'park' ? 'filter' : canFocus ? 'focus' : 'static'}
        hidden={hidden}
        focus={focusGroup}
        onToggle={onToggleGroup}
        onFocus={onFocusGroup}
      />
    </>
  );

  if (!origin) {
    return (
      <div className="sidebar">
        <p className="sidebar-hint">
          {mode === 'housing'
            ? '공공임대 단지를 클릭하면\n주변 공원과의 거리를 확인할 수 있어요'
            : '공원을 클릭하면\n주변 공공임대 단지를 확인할 수 있어요'}
        </p>
        {controls}
      </div>
    );
  }

  const isHousing = mode === 'housing';
  const mapUrl = `https://map.kakao.com/link/map/${encodeURIComponent(origin.name)},${origin.lat},${origin.lng}`;

  return (
    <div className="sidebar">
      <button className="sidebar-close" onClick={onClose}>✕</button>
      <div className="sidebar-badge">{isHousing ? '공공임대 단지' : '공원'}</div>
      <div className="sidebar-title">{origin.name}</div>

      <div className="sidebar-section">
        {isHousing ? (
          <>
            <div className="sidebar-stat">
              <span className="sidebar-label">임대유형</span>
              <span className="sidebar-value small">{origin.lease_type}</span>
            </div>
            <div className="sidebar-stat">
              <span className="sidebar-label">세대수</span>
              <span className="sidebar-value">
                {Number(origin.households).toLocaleString()}
                <span className="sidebar-unit">세대</span>
              </span>
            </div>
            <div className="sidebar-stat">
              <span className="sidebar-label">입주</span>
              <span className="sidebar-value small">{String(origin.move_in_date).slice(0, 7)}</span>
            </div>
          </>
        ) : (
          <>
            <div className="sidebar-stat">
              <span className="sidebar-label">공원 구분</span>
              <span className="sidebar-value small">{origin.subtype}</span>
            </div>
            <div className="sidebar-stat">
              <span className="sidebar-label">면적</span>
              <span className="sidebar-value">
                {Number(origin.area).toLocaleString()}
                <span className="sidebar-unit">m²</span>
              </span>
            </div>
          </>
        )}
        <div className="sidebar-stat">
          <span className="sidebar-label">위치</span>
          <span className="sidebar-value small">{origin.gu_name}</span>
        </div>
      </div>

      <div className="sidebar-section">
        {loading && <p className="sidebar-hint">주변 정보를 불러오는 중…</p>}
        {!loading && detail && (
          <NearbyPanel
            detail={detail}
            onHover={onHover}
            focus={canFocus ? focusGroup : null}
          />
        )}
      </div>

      <div className="sidebar-section">
        {isHousing && (
          <>
            <a className="sidebar-map-link" href="https://www.i-sh.co.kr" target="_blank" rel="noreferrer">
              SH 청약정보 →
            </a>
            <a className="sidebar-map-link" href="https://www.myhome.go.kr" target="_blank" rel="noreferrer">
              마이홈포털 →
            </a>
          </>
        )}
        <a className="sidebar-map-link" href={mapUrl} target="_blank" rel="noreferrer">
          카카오맵에서 보기 →
        </a>
      </div>

      {controls}
    </div>
  );
}


function App() {
  const [, mapError] = useKakaoLoader({
    appkey: process.env.REACT_APP_KAKAO_MAP_KEY,
    libraries: ['clusterer'],
  });

  const [mode, setMode] = useState('housing');
  const [housing, setHousing] = useState([]);
  const [parks, setParks] = useState([]);
  const [origin, setOrigin] = useState(null);      // 선택한 단지 또는 공원
  const [detail, setDetail] = useState(null);      // nearby 응답
  const [loading, setLoading] = useState(false);
  const [hovered, setHovered] = useState(null);    // 목록 hover -> 지도 강조
  const [hiddenGroups, setHiddenGroups] = useState(() => new Set(['children']));
  const [focusGroup, setFocusGroup] = useState(null);  // 범례 클릭 -> 반경 안 해당 그룹 강조
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_MIN_W);

  const handleResize = useCallback((w) => {
    setSidebarWidth(Math.min(SIDEBAR_MAX_W, Math.max(SIDEBAR_MIN_W, w)));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/housing`).then(r => r.json()).then(setHousing);
    fetch(`${API_BASE}/api/parks`).then(r => r.json()).then(setParks);
  }, []);

  const onMapLoad = useCallback(() => {}, []);

  // 선택이 바뀌면 주변을 조회한다. 응답 형태가 양쪽 동일해서 분기가 kind 하나뿐이다.
  useEffect(() => {
    if (!origin) { setDetail(null); return; }
    let cancelled = false;
    setLoading(true);
    const path = mode === 'housing' ? 'housing' : 'parks';
    fetch(`${API_BASE}/api/${path}/${origin.id}/nearby?radius=${RADIUS_M}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) { setDetail(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [origin, mode]);

  const handleModeChange = useCallback((next) => {
    setMode(next);
    setOrigin(null);
    setDetail(null);
    setHovered(null);
    setFocusGroup(null);
  }, []);

  const handleFocusGroup = useCallback((key) => {
    setFocusGroup(prev => (prev === key ? null : key));
  }, []);

  const handleToggleGroup = useCallback((key) => {
    setHiddenGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }, []);

  const handleSelectHousing = useCallback((item) => {
    setFocusGroup(null);
    setOrigin({ id: item.id, name: item.complex_name, lat: item.lat, lng: item.lng,
                gu_name: item.gu_name, lease_type: item.lease_type,
                households: item.households, move_in_date: item.move_in_date });
  }, []);

  const handleSelectPark = useCallback((park) => {
    setFocusGroup(null);
    setOrigin({ id: park.id, name: park['공원명'], lat: park['위도'], lng: park['경도'],
                gu_name: park['구'], subtype: park['공원구분'], area: park['공원면적'] });
  }, []);

  // 공원 모드의 진입점은 1,723개라 그대로 뿌리면 고를 수가 없다. 범례에서 끈
  // 그룹(기본: 어린이공원 1,010개)을 빼서 클릭 가능한 수로 줄인다.
  const visibleParks = useMemo(() => {
    if (mode !== 'park') return [];
    return parks.filter(p => !hiddenGroups.has(PARK_TYPE_TO_GROUP[p['공원구분']] || 'etc'));
  }, [mode, parks, hiddenGroups]);

  // 선택 후에는 반경 안의 대상만 그린다. 공원을 서울 전역에 뿌릴 이유가 없어져
  // 원래 마커 1,723개를 한꺼번에 렌더하던 성능 문제가 사라진다.
  const nearbyItems = detail?.items ?? [];


  const [activeSection, setActiveSection] = useState(null);
  const aboutRef = useRef(null);
  const dataRef = useRef(null);
  const emptyRef = useRef(null);
  const mypageRef = useRef(null);

  useEffect(() => {
    const sections = [
      { ref: aboutRef, name: 'about' },
      { ref: dataRef, name: 'data' },
      { ref: emptyRef, name: 'empty' },
      { ref: mypageRef, name: 'mypage' },
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
              {origin && (
                <Circle
                  center={{ lat: origin.lat, lng: origin.lng }}
                  radius={RADIUS_M}
                  fillColor="#13f229"
                  fillOpacity={0.12}
                  strokeColor="#13f229"
                  strokeOpacity={0.6}
                  strokeWeight={1.5}
                />
              )}

              {/* 기준 레이어. 선택 전에는 이것만 보인다. */}
              <MarkerClusterer averageCenter={true} minLevel={CLUSTER_MIN_LEVEL}>
                {mode === 'housing'
                  ? housing.map(item => (
                      <HousingMarker
                        key={item.id}
                        item={item}
                        isSelected={origin?.id === item.id}
                        onSelect={handleSelectHousing}
                      />
                    ))
                  : visibleParks.map(park => (
                      <ParkMarker
                        key={park.id}
                        park={park}
                        isSelected={origin?.id === park.id}
                        onSelect={handleSelectPark}
                      />
                    ))}
              </MarkerClusterer>

              {/* 선택 후 반경 안에 들어온 대상. 보통 5~15개라 클러스터 없이 그린다. */}
              {nearbyItems.map(item =>
                mode === 'housing' ? (
                  <ParkMarker
                    key={`n-${item.id}`}
                    park={{
                      id: item.id, '공원명': item.name, '공원구분': item.subtype,
                      '위도': item.lat, '경도': item.lng, '구': item.gu_name,
                    }}
                    isSelected={
                      hovered === item.id
                      || (PARK_TYPE_TO_GROUP[item.subtype] || 'etc') === focusGroup
                    }
                    onSelect={() => {}}
                  />
                ) : (
                  <HousingMarker
                    key={`n-${item.id}`}
                    item={item}
                    isSelected={hovered === item.id}
                    onSelect={() => {}}
                  />
                )
              )}
            </Map>
          )}
        </div>

        <div className="sidebar-wrap" style={{ width: sidebarWidth }}>
          <SidebarResizer onResize={handleResize} />
          <Sidebar
            mode={mode}
            onModeChange={handleModeChange}
            origin={origin}
            detail={detail}
            loading={loading}
            onClose={() => { setOrigin(null); setDetail(null); }}
            onHover={setHovered}
            hidden={hiddenGroups}
            onToggleGroup={handleToggleGroup}
            focusGroup={focusGroup}
            onFocusGroup={handleFocusGroup}
          />
        </div>
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

      <div ref={mypageRef} data-section="mypage" className="scroll-section scroll-mypage">
        <div className="about-content">
          <section className="about-hero">
            <h1 className="about-hero-title">MyPage</h1>
            <p className="about-hero-sub">준비 중입니다</p>
          </section>
        </div>
      </div>
    </div>
  );
}

export default App;
