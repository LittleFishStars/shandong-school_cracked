// 前端静态检查（白屏防线）：no-undef 抓「引用了不存在的变量」
// —— 2026-10-25 桌面跑步页白屏：JSX 表达式里用了未定义的 dragMode，
// esbuild 不报、自研正则误报率高，只有真正的 AST 作用域分析可靠。
// 同日还抓到 logout 里的 setDetail 遗留调用（点退出登录也会白屏）。
import globals from 'globals';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.es2021 },
    },
    plugins: { react, 'react-hooks': reactHooks },
    settings: { react: { version: 'detect' } },
    rules: {
      'no-undef': 'error',            // 白屏根因类：未定义变量
      'no-redeclare': 'error',
      'no-dupe-keys': 'error',
      'no-unreachable': 'error',
      'no-const-assign': 'error',
      'react/jsx-uses-vars': 'error', // JSX 里用到的组件算已使用
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
];
