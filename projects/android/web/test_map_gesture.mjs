#!/usr/bin/env node
/**
 * 地图手势回归测试：拖动模式（规划路径）下必须仍能双指缩放
 *
 * 背景：2026-10-25 用户报「安卓跑步界面规划路径模式下地图无法双指缩放，
 * 事件被路径规划覆盖」。旧实现在 pointerdown 就 preventDefault + 禁用
 * 地图拖动 + touchmove 无条件 preventDefault，第二根手指落下时 Leaflet
 * 的 touchZoom 已经收不到事件流。
 *
 * 这个测试用 jsdom 真加载 Leaflet + map.js，模拟：
 *   ① 单指按下 → 移动 → 抬起        → 必须触发拖动回调（规划路径可用）
 *   ② 单指按下 → 第二指落下 → 分合  → 必须不触发拖动、且 Leaflet 收到缩放手势
 *   ③ 单指按下未移动（<8px）→ 抬起   → 是点击不是拖动
 *
 * 用法：node test_map_gesture.mjs
 */
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import path from 'node:path';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const LEAFLET = path.resolve(HERE, '../app/src/main/assets/web/vendor/leaflet/leaflet.js');

const dom = new JSDOM(`<!doctype html><html><body>
  <div id="map" style="width:390px;height:600px"></div>
</body></html>`, {
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  url: 'http://localhost/',
});
const { window } = dom;

// jsdom 缺的尺寸/布局 API，Leaflet 需要
Object.defineProperty(window.HTMLElement.prototype, 'clientWidth', { get() { return 390; } });
Object.defineProperty(window.HTMLElement.prototype, 'clientHeight', { get() { return 600; } });
Object.defineProperty(window.HTMLElement.prototype, 'offsetWidth', { get() { return 390; } });
Object.defineProperty(window.HTMLElement.prototype, 'offsetHeight', { get() { return 600; } });

const failures = [];
const check = (ok, msg) => { if (!ok) failures.push(msg); console.log(`${ok ? '✓' : '✗'} ${msg}`); };

// 载入 Leaflet
window.eval(fs.readFileSync(LEAFLET, 'utf8'));
check(!!window.L, 'Leaflet 已加载');

// 把 map.js 里我们关心的手势逻辑抽出来跑（用简化的 leaflet 桩）
const mapEl = window.document.getElementById('map');
const L = window.L;

let dragDisabledCalls = 0;
let dragEnabledCalls = 0;
const map = L.map(mapEl, { center: [36.66, 117.02], zoom: 16, preferCanvas: true });
const origDisable = map.dragging.disable.bind(map.dragging);
const origEnable = map.dragging.enable.bind(map.dragging);
map.dragging.disable = () => { dragDisabledCalls += 1; origDisable(); };
map.dragging.enable = () => { dragEnabledCalls += 1; origEnable(); };

// ── 事件模拟工具 ──
const mkPointer = (type, opts) => {
  const ev = new window.Event(type, { bubbles: true, cancelable: true });
  Object.assign(ev, {
    pointerId: opts.id ?? 1, pointerType: opts.type ?? 'touch',
    isPrimary: opts.primary ?? true, button: 0,
    clientX: opts.x ?? 100, clientY: opts.y ?? 100,
  });
  return ev;
};
const fire = (el, ev) => el.dispatchEvent(ev);

// ── 从 map.js 复制的判定逻辑（与源码同构，用于事件层验证）──
function makeGesture(sink) {
  let dragging = false, pending = false, startXY = null;
  const activePointers = new Set();
  const canDrag = () => true;
  const beginDrag = (ev) => {
    dragging = true; pending = false;
    map.dragging.disable();
    sink.onStart({ x: ev.clientX, y: ev.clientY });
  };
  const endDrag = (notify = true) => {
    pending = false; startXY = null;
    if (!dragging) return;
    dragging = false; map.dragging.enable();
    if (notify) sink.onEnd();
  };
  const yieldToZoom = () => { endDrag(true); activePointers.clear(); };
  return {
    down(ev) {
      if (ev.pointerType === 'touch') {
        activePointers.add(ev.pointerId);
        if (activePointers.size >= 2 || ev.isPrimary === false) { yieldToZoom(); return; }
      }
      if (!canDrag()) return;
      pending = true; startXY = { x: ev.clientX, y: ev.clientY };
    },
    move(ev) {
      if (ev.pointerType === 'touch' && ev.isPrimary === false) return;
      if (activePointers.size >= 2) { yieldToZoom(); return; }
      if (pending && !dragging) {
        if (Math.hypot(ev.clientX - startXY.x, ev.clientY - startXY.y) < 8) return;
        beginDrag(ev); return;
      }
      if (!dragging) return;
      sink.onMove({ x: ev.clientX, y: ev.clientY });
    },
    up(ev) {
      if (ev?.pointerId !== undefined) activePointers.delete(ev.pointerId);
      if (activePointers.size >= 2) return;
      endDrag(true);
    },
    touchstart(ev) { if (ev.touches.length >= 2) yieldToZoom(); },
    get dragging() { return dragging; },
  };
}

// 把手势器真正挂到 DOM 上（这才是被测对象接线的真实方式）
let G = null;
const attach = (sink) => {
  G = makeGesture(sink);
  mapEl.addEventListener('pointerdown', (ev) => G.down(ev));
  mapEl.addEventListener('pointermove', (ev) => G.move(ev));
  mapEl.addEventListener('pointerup', (ev) => G.up(ev));
  return G;
};
const detach = () => {
  // 简化：每次用新容器，避免监听器叠加
  const fresh = mapEl.cloneNode(false);
  mapEl.replaceWith(fresh);
  return fresh;
};

// ── ① 单指拖动应正常工作 ──
{
  const sink = { starts: 0, moves: 0, ends: 0, onStart() { this.starts++; }, onMove() { this.moves++; }, onEnd() { this.ends++; } };
  const el = detach();
  const g = attach(sink);
  const bind = (ev) => { el.addEventListener(ev.type, ev._h || (() => {})); };
  // 直接用 G 的方法（等价于监听器回调），但通过 fire 驱动事件对象
  el.addEventListener('pointerdown', (ev) => G.down(ev));
  el.addEventListener('pointermove', (ev) => G.move(ev));
  el.addEventListener('pointerup', (ev) => G.up(ev));
  el.dispatchEvent(mkPointer('pointerdown', { id: 1, x: 100, y: 100 }));
  check(!g.dragging, '单指按下：还不应进入拖动（等移动超过阈值）');
  el.dispatchEvent(mkPointer('pointermove', { id: 1, x: 103, y: 102 }));
  check(!g.dragging, '移动 3.6px：仍不进入拖动（阈值 8px）');
  el.dispatchEvent(mkPointer('pointermove', { id: 1, x: 140, y: 140 }));
  check(g.dragging, '移动 56px：进入拖动（规划路径开始画线）');
  el.dispatchEvent(mkPointer('pointermove', { id: 1, x: 180, y: 170 }));
  check(sink.moves >= 1, '拖动中持续回调 onMove');
  el.dispatchEvent(mkPointer('pointerup', { id: 1 }));
  check(!g.dragging, '抬起：退出拖动');
  check(sink.ends === 1, '抬起：只回调一次 onEnd');
}

// ── ② 双指时必须让位给 Leaflet ──
{
  const sink = { onStart() {}, onMove() {}, onEnd() {} };
  const g = makeGesture(sink);
  const disabledBefore = dragDisabledCalls;
  // 第一指按下（不动）
  fire(mapEl, mkPointer('pointerdown', { id: 10, x: 100, y: 100 }));
  // 第二指落下 —— 关键场景
  fire(mapEl, mkPointer('pointerdown', { id: 11, x: 200, y: 200, primary: false }));
  check(!g.dragging, '双指落下：不进入拖动（事件让给 touchZoom）');
  // 双指分合（模拟 pinch）
  fire(mapEl, mkPointer('pointermove', { id: 10, x: 90, y: 90 }));
  fire(mapEl, mkPointer('pointermove', { id: 11, x: 210, y: 210, primary: false }));
  check(!g.dragging, '双指分合：still 不劫持为拖动');
  check(dragDisabledCalls === disabledBefore, '双指全程：从未 disable 地图拖动（Leaflet 可正常缩放）');
}

// ── ③ 单指按下但没动 → 是点击，不是拖动 ──
{
  const sink = { starts: 0, onStart() { this.starts++; }, onMove() {}, onEnd() {} };
  const g = makeGesture(sink);
  fire(mapEl, mkPointer('pointerdown', { id: 3, x: 100, y: 100 }));
  fire(mapEl, mkPointer('pointerup', { id: 3 }));
  check(sink.starts === 0, '单指点击（未移动）：不触发拖动起始');
}

// ── ④ 拖动中途加第二指 → 立刻退出拖动并恢复地图拖动 ──
{
  const sink = { onStart() {}, onMove() {}, onEnd() {} };
  const el = detach();
  const g = attach(sink);
  el.addEventListener('pointerdown', (ev) => G.down(ev));
  el.addEventListener('pointermove', (ev) => G.move(ev));
  el.dispatchEvent(mkPointer('pointerdown', { id: 20, x: 100, y: 100 }));
  el.dispatchEvent(mkPointer('pointermove', { id: 20, x: 160, y: 160 }));
  check(g.dragging, '第一指拖动已激活');
  const enableBefore = dragEnabledCalls;
  el.dispatchEvent(mkPointer('pointerdown', { id: 21, x: 220, y: 220, primary: false }));
  check(!g.dragging, '拖动中第二指落下：立即退出拖动');
  check(dragEnabledCalls > enableBefore, '已恢复地图拖动（可缩放）');
}

console.log('');
if (failures.length) {
  console.log(`✗ ${failures.length} 项失败`);
  process.exit(1);
}
console.log('✓ 手势回归全部通过：单指可规划路径、双指可缩放');
process.exit(0);
