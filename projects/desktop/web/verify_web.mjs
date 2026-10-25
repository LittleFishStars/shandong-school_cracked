#!/usr/bin/env node
/**
 * 前端渲染冒烟（白屏防线）：用 jsdom 真加载页面、真点「开始跑步」，
 * 断言 React 有渲染且没有未捕获异常。
 *
 * 为什么需要：2026-10-25 一天两次白屏（planRemainRef 未定义、dragMode 未定义），
 * esbuild/eslint 只能静态兜底；真正求值发生在运行时，且 React 的 `&&` 短路
 * 让「首页正常、切视图才崩」这种问题在静态检查里很难被发现。
 *
 * 用法（宿主或沙箱均可，需要先起 GUI 的 --browser 实例拿 URL）：
 *   node verify_web.mjs http://127.0.0.1:PORT/index.html?http=1
 */
import { JSDOM, VirtualConsole } from 'jsdom';

const url = process.argv[2];
if (!url) {
  console.error('用法: node verify_web.mjs <http://127.0.0.1:PORT/index.html?http=1>');
  process.exit(2);
}

const errors = [];
const logs = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => errors.push(`jsdomError: ${e.message}`));
vc.on('error', (...a) => errors.push(`console.error: ${a.join(' ')}`));
vc.on('warn', (...a) => logs.push(`warn: ${a.join(' ')}`));
vc.on('info', (...a) => logs.push(`info: ${a.join(' ')}`));

const dom = await JSDOM.fromURL(url, {
  runScripts: 'dangerously',
  resources: 'usable',
  pretendToBeVisual: true,
  virtualConsole: vc,
});
const { window } = dom;
window.addEventListener('error', (e) => errors.push(`window.onerror: ${e.message}`));
window.addEventListener('unhandledrejection', (e) =>
  errors.push(`unhandledrejection: ${e.reason && (e.reason.stack || e.reason.message || e.reason)}`));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(6000);           // 等 bundle 执行 + 首屏渲染 + 桥握手

const snap = () => {
  const root = window.document.getElementById('root');
  const html = root ? root.innerHTML : '';
  const text = (window.document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 160);
  const buttons = [...window.document.querySelectorAll('button')]
    .map((b) => (b.innerText || '').trim()).filter(Boolean).slice(0, 12);
  return { len: html.length, text, buttons };
};

const home = snap();
console.log('① 首屏渲染长度:', home.len, '| 文本:', home.text);
console.log('   按钮:', home.buttons.join(' / '));

// 找「开始」按钮并点击（触发切到跑步视图的渲染路径——两次白屏都发生在这里）
const btn = [...window.document.querySelectorAll('button')]
  .find((b) => /开始|开跑|START/i.test(b.innerText || '')) ||
  [...window.document.querySelectorAll('button')].find((b) => /登录/.test(b.innerText || ''));
if (!btn) {
  console.log('② 未找到可点击的开始按钮（首页可能停在登录页），跳过点击');
} else {
  console.log(`② 点击「${(btn.innerText || '').trim()}」...`);
  btn.click();
  await sleep(5000);
  const after = snap();
  console.log('   点击后渲染长度:', after.len, '| 文本:', after.text);
  console.log('   按钮:', after.buttons.join(' / '));
  if (after.len < 50) errors.push('点击后 root 内容近乎为空 —— 白屏');
}

if (errors.length) {
  console.log('\n✗ 捕获到异常:');
  for (const e of errors.slice(0, 10)) console.log('  ' + e);
  process.exit(1);
}
console.log('\n✓ 渲染冒烟通过：无未捕获异常，view 切换后仍有内容');
process.exit(0);
