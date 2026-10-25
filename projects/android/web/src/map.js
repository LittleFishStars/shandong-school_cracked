/* Leaflet 地图封装：新建实例、切换瓦片、重绘围栏/打卡点/起点/路线/轨迹
   移动端改造：在桌面版基础上新增「拖动模式」单指规划复制点轨迹（§4），
   通过 touch 事件实现，拖动期间禁用地图平移。 */
const TILES = {
  amap: {
    url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    subdomains: '1234', maxZoom: 18, attribution: '&copy; 高德地图',
  },
  'amap-sat': {
    url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
    subdomains: '1234', maxZoom: 18, attribution: '&copy; 高德地图（卫星）',
  },
  osm: {
    url: 'https://{s}.tile.openstreetmap.de/{z}/{x}/{y}.png',
    subdomains: 'abc', maxZoom: 19, attribution: '&copy; OpenStreetMap',
  },
  none: null,
};

const HOME = [36.6615, 117.0265];

export function initMap(el, onClickRef, ghostRef, dragModeRef) {
  const L = window.L;
  const m = L.map(el, { center: HOME, zoom: 16, zoomControl: true, preferCanvas: true });
  m.layers = {};
  // 叠放次序（低 -> 高）：围栏 < 起点 < 规划轨迹 < 轨迹 < 打卡点 < 复制点 < 人
  const panes = [
    ['fencePane', 380],
    ['startPane', 390],
    ['ghostPathPane', 400],
    ['trackPane', 410],
    ['cpsPane', 420],
    ['ghostPane', 430],
    ['personPane', 440],
  ];
  for (const [name, z] of panes) {
    m.createPane(name);
    const pane = m.getPane(name);
    if (pane) pane.style.zIndex = String(z);
  }
  for (const k of ['fence', 'start', 'ghostPath', 'track', 'cps', 'ghost', 'person']) {
    m.layers[k] = L.layerGroup().addTo(m);
  }
  m.on('click', (e) => {
    const fn = onClickRef && onClickRef.current;
    if (fn) fn(e.latlng.lat, e.latlng.lng);
  });

  const container = m.getContainer();
  m.on('contextmenu', (e) => { if (e.originalEvent) e.originalEvent.preventDefault(); });
  container.addEventListener('contextmenu', (ev) => ev.preventDefault());

  /* ────────────────── 移动端：拖动模式（§4）──────────────────
     桌面版用鼠标右键；移动端无右键，改为「拖动模式下任意单指按住拖动」。

     ★ 与双指缩放的共存规则（2026-10-25 修复地图无法缩放）：
       旧实现在 pointerdown 就 preventDefault + 禁用地图拖动 + 在 touchmove
       里无条件 preventDefault —— 第二根手指落下时事件流已被掐断，Leaflet
       的 touchZoom（依赖 touchstart 双指 + touchmove）永远收不到，于是
       规划路径模式下地图完全没法缩放。

       新规则：
         ① 单指按下时**只记录候选**，不立刻 preventDefault、不禁用拖动；
         ② 确认是「单指移动」后才进入拖动（超过 8px 阈值），此时才禁平移；
         ③ 只要检测到第二根手指（touchstart.touches.length >= 2 或
            pointerdown 时已有活跃指针），**立即放弃拖动**并把控制权交还
            Leaflet（恢复 m.dragging），且此后不再拦截 touchmove；
         ④ touchmove 只在「拖动已激活且仍是单指」时 preventDefault。 */
  let dragging = false;
  let pending = false;          // 单指按下、尚未确认是拖动
  let startXY = null;
  const activePointers = new Set();

  const getLatLng = (ev) => {
    try {
      return m.mouseEventToLatLng(ev);
    } catch (_) { return null; }
  };

  const isDragMode = () => {
    const d = dragModeRef && dragModeRef.current;
    return !!(d && d.dragMode);
  };

  const canDrag = () => {
    const g = ghostRef && ghostRef.current;
    return !!(g && g.enabled && isDragMode());
  };

  const beginDrag = (ev) => {
    dragging = true;
    pending = false;
    try { m.dragging.disable(); } catch (_) { /* 忽略 */ }
    const g = ghostRef && ghostRef.current;
    const ll = getLatLng(ev);
    if (ll && g && g.onStart) g.onStart(ll.lat, ll.lng);
  };

  const endDrag = (notify = true) => {
    pending = false;
    startXY = null;
    if (!dragging) return;
    dragging = false;
    try { m.dragging.enable(); } catch (_) { /* 忽略 */ }
    const g = ghostRef && ghostRef.current;
    if (notify && g && g.onEnd) g.onEnd();
  };

  /* 双指介入：立刻让位给 Leaflet 的 touchZoom */
  const yieldToZoom = () => {
    endDrag(true);              // 结束并复位已画路径段（保持已有 ghostPath 不变）
    activePointers.clear();
  };

  const onPointerDown = (ev) => {
    if (ev.pointerType === 'touch' || ev.pointerType === 'pen') {
      activePointers.add(ev.pointerId);
      // 第二根手指：让路，不做任何 preventDefault
      if (activePointers.size >= 2 || ev.isPrimary === false) {
        yieldToZoom();
        return;
      }
    } else if (ev.button !== undefined && ev.button !== 0) {
      return;                   // 只认左键
    }
    if (!canDrag()) return;
    // 不在这里 preventDefault / disable：先观察是否真的移动
    pending = true;
    startXY = { x: ev.clientX, y: ev.clientY };
  };

  const onPointerMove = (ev) => {
    if (ev.pointerType === 'touch' && ev.isPrimary === false) return;
    // 双指（或在拖动中新增手指）→ 让位
    if (activePointers.size >= 2) { yieldToZoom(); return; }
    if (pending && !dragging) {
      if (!canDrag()) { pending = false; return; }
      const dx = ev.clientX - startXY.x;
      const dy = ev.clientY - startXY.y;
      if (Math.hypot(dx, dy) < 8) return;      // 阈值内：还可能是点击/缩放
      beginDrag(ev);
      return;
    }
    if (!dragging) return;
    const g = ghostRef && ghostRef.current;
    const ll = getLatLng(ev);
    if (ll && g && g.onMove) g.onMove(ll.lat, ll.lng);
  };

  const onPointerUp = (ev) => {
    if (ev && ev.pointerId !== undefined) activePointers.delete(ev.pointerId);
    if (activePointers.size >= 2) return;
    endDrag(true);
  };

  /* touch 层：双指时必须完全放行，否则 Leaflet touchZoom 收不到事件 */
  const onTouchStart = (ev) => {
    if (ev.touches && ev.touches.length >= 2) yieldToZoom();
  };

  container.addEventListener('pointerdown', onPointerDown);
  container.addEventListener('pointermove', onPointerMove);
  container.addEventListener('pointerup', onPointerUp);
  container.addEventListener('pointercancel', onPointerUp);
  container.addEventListener('touchstart', onTouchStart, { passive: true });
  // 鼠标（浏览器调试/桌面壳拖动）
  container.addEventListener('mousedown', (ev) => { if (ev.button === 0) onPointerDown(ev); });
  container.addEventListener('mousemove', (ev) => { if (dragging || pending) onPointerMove(ev); });
  window.addEventListener('mouseup', () => onPointerUp());
  window.addEventListener('touchend', (ev) => {
    if (ev.touches && ev.touches.length >= 1) return;   // 还有手指在屏幕上
    onPointerUp();
  });
  // 只有「拖动已真正激活且仍是单指」才阻止默认（防页面滚动）
  container.addEventListener('touchmove', (ev) => {
    if (dragging && (!ev.touches || ev.touches.length === 1)) ev.preventDefault();
  }, { passive: false });

  return m;
}

export function setTileLayer(map, kind) {
  const L = window.L;
  if (!map) return;
  if (map._tile) { map.removeLayer(map._tile); map._tile = null; }
  const conf = TILES[kind];
  if (!conf) return;
  map._tile = L.tileLayer(conf.url, {
    subdomains: conf.subdomains, maxZoom: conf.maxZoom, attribution: conf.attribution,
  }).addTo(map);
}

/* 一次重绘全部叠加层；data 变化时调用 */
export function renderMap(map, data) {
  const L = window.L;
  if (!map) return;
  const { status, walkPoints, checkpoints, ghostPath, fitKey } = data || {};
  const st = status || {};
  const layers = map.layers;

  /* 围栏 */
  layers.fence.clearLayers();
  const fence = (st.fence_polygon || []).map(([a, b]) => [Number(a), Number(b)])
    .filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b));
  if (fence.length >= 3) {
    L.polygon(fence, { pane: 'fencePane', color: '#52c41a', weight: 2, fillColor: '#95de64', fillOpacity: 0.12 }).addTo(layers.fence);
  }

  /* 打卡点（服务端开跑后下发；开跑前用预览点） */
  layers.cps.clearLayers();
  const cps = (Array.isArray(checkpoints) && checkpoints.length) ? checkpoints : [];
  cps.forEach((p, i) => {
    const lat = Number(p.lat), lng = Number(p.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const passed = Number(p.passed) === 1 || p.passed === true;
    const num = p.index != null ? Number(p.index) + 1 : i + 1;
    L.marker([lat, lng], {
      icon: L.divIcon({
        className: 'cp-icon',
        iconSize: [20, 20],
        iconAnchor: [10, 10],
        html: `<span class="cp-label${passed ? ' passed' : ''}">${num}</span>`,
      }),
      pane: 'cpsPane',
      keyboard: false,
    }).addTo(layers.cps);
  });

  /* 起点 */
  layers.start.clearLayers();
  const sp = st.start_point;
  if (sp && Number.isFinite(Number(sp.lat)) && Number.isFinite(Number(sp.lng))) {
    L.marker([Number(sp.lat), Number(sp.lng)], {
      icon: L.divIcon({ className: 'start-label', html: '起', iconSize: [22, 22], iconAnchor: [11, 11] }),
      pane: 'startPane',
    }).addTo(layers.start);
  }

  /* 本次轨迹（线）与人（当前位置，单独一层放最上面） */
  layers.track.clearLayers();
  layers.person.clearLayers();
  if (Array.isArray(walkPoints) && walkPoints.length > 1) {
    L.polyline(walkPoints.map((p) => [Number(p.lat), Number(p.lng)]), {
      pane: 'trackPane', color: '#1677ff', weight: 4, opacity: 0.9,
    }).addTo(layers.track);
    const last = walkPoints[walkPoints.length - 1];
    L.circleMarker([Number(last.lat), Number(last.lng)], {
      pane: 'personPane', radius: 7, color: '#ffffff', weight: 2.5, fillColor: '#1677ff', fillOpacity: 1,
    }).addTo(layers.person);
  }

  /* 复制点轨迹（规划轨迹，压在人/打卡点/轨迹之下）与复制点（在打卡点之上） */
  layers.ghostPath.clearLayers();
  layers.ghost.clearLayers();
  if (Array.isArray(ghostPath) && ghostPath.length > 1) {
    L.polyline(ghostPath.map((p) => [Number(p[0]), Number(p[1])]), {
      pane: 'ghostPathPane', color: '#13c2c2', weight: 3, dashArray: '4 6', opacity: 0.9,
    }).addTo(layers.ghostPath);
    const last = ghostPath[ghostPath.length - 1];
    L.circleMarker([Number(last[0]), Number(last[1])], {
      pane: 'ghostPane', radius: 7, color: '#ffffff', weight: 2, fillColor: '#13c2c2', fillOpacity: 1,
    }).addTo(layers.ghost);
  }

  /* 镜头：围栏或起点首次出现时 fit */
  const key = String(fitKey || '');
  if (key && map._fitKey !== key) {
    map._fitKey = key;
    const pts = fence.length >= 3 ? fence : (sp ? [[Number(sp.lat), Number(sp.lng)]] : []);
    if (pts.length) {
      try { map.fitBounds(L.latLngBounds(pts).pad(0.2), { animate: false }); } catch (_) { /* 忽略 */ }
    }
  }
}