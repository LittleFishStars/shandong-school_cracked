# 贡献指南

面向**开发/逆向贡献者**。只想跑起来用，看根目录 [README](README.md)；工程内各目录说明见 `work/README.md`、`report/README.md`。

## 仓库结构速览

```
ShanDong/
├── samples/     原始样本（唯一 APK，只读，Git LFS）
├── report/      分析报告 01–26（逆向结论唯一出处；注意两个 24 重号）
├── docs/        工程文档（docs/desktop/ 协议与打包、docs/android/ 接口契约与截图、
│                docs/capture-huawei.md 真机抓包对比指南、CLEANUP 记录）
├── reference/   签名算法参考实现 + 外部规格
├── scripts/     逆向脚本（dump / 脱壳 / 签名 / 核对）
├── work/        逆向工作区（dex/ native/ evidence/ dumps/ records/ meta/ toolchain/）
│                ★ records/logs/ 与 .tmp/ 含账号信息，已进 .gitignore，不要提交
├── projects/
│   ├── desktop/ ★ 桌面工作台 shandong-school_cracked（Python 包，GUI+CLI）
│   └── android/ ★ 安卓版（Chaquopy 整包复用桌面 Python 业务 + WebView 前端）
└── .github/workflows/  CI（打 tag 三平台构建 + Release）
```

## 桌面工作台（projects/desktop/）

**想改哪里**

| 想改什么 | 模块 |
|---|---|
| 协议常量 / 密钥 / 接口表 | `shandong_school_cracked/constants.py` |
| 加解密、签名、滑块、结算码 | `ciphers.py` / `crypto.py` |
| 轨迹、打卡点、报文构造、速度动力学 | `protocol.py`（`SpeedDynamics` 批量与实走共用） |
| 行为链（登录后浏览 / 跑后看成绩） | `behavior.py` + `constants.EP` 的「行为链」段 |
| 人脸扫脸与现场照加工 | `client.py`（`face_check` / `process_face_photo`）、`constants.FACE_PHOTO_*` |
| 设备口径（机型池 / 鸿蒙 / deviceId） | `constants.MODEL_POOL`、`constants.HM_PROFILE`、`net.public_fields()` / `user_agent()` |
| 摇杆实走 / 实走会话 | `walker.py` / `walk.py` |
| 登录 → 备跑 → 开跑 → 上传 → 结算 | `client.py` |
| SQLite 记录库 | `store.py` |
| 离线 Mock 服务端 | `mock.py` |
| 一次跑步完整编排 + 断点续传 | `engine.py` |
| GUI/CLI 门面（含退出自动结算） | `app.py` / `gui.py` / `cli.py` |
| 传输层（头/签名/代理/TLS 伪装） | `net.py` |
| 前端（React 18 + antd 4） | `web/src/`（esbuild → `web/app.bundle.js`，**产物要提交**） |
| 打包单文件 | `scripts/build_bin.py` + `packaging/` |

完整模块图见 [`projects/desktop/README.md`](projects/desktop/README.md)。

### 环境与运行

```bash
cd projects/desktop
python3 -m venv --system-site-packages .venv        # Arch：继承系统包
.venv/bin/pip install pywebview pycryptodome        # 可选：原生窗口 / 更快密码学后端
.venv/bin/python -m shandong_school_cracked         # 跑起来（GUI）
```

密码学后端 `pycryptodome → cryptography → 纯标准库` 自动择优，全缺失也能跑（内置纯 Python AES）。

### 测试与自检

```bash
cd projects/desktop
.venv/bin/python -m unittest discover -s tests -q        # 单元测试（326 项）
.venv/bin/python scripts/selfcheck.py -v                 # 端到端自检（76 项）
.venv/bin/python scripts/webcheck.py                     # 前端桥自检（59 项）
.venv/bin/python scripts/gui_probe.py --distance 1200    # 桌面外壳冒烟（真开窗口、点按钮）
.venv/bin/python scripts/realcheck.py --captcha-trials 5 # 真实服务端连通性（无需账号）
.venv/bin/python -m shandong_school_cracked check        # 两个自检一起跑
```

### 本地 Mock 模式（仅测试用）

内置一个**离线 Mock 服务端**（`mock.py`），不碰真实网络，用于单元 / 端到端调试与测试：

```bash
cd projects/desktop
.venv/bin/python -m shandong_school_cracked --mode mock gui     # 纯本地仿真，真接口一根毛都不碰
.venv/bin/python -m shandong_school_cracked mock --port 8899     # 只起本地 Mock 服务端
```

- 登录方式切到「本地 Mock」即走 Mock 通道；`session_mock` 与真实会话分开存本地，来回切换不用反复登录。
- 可在界面/脚本里注入延迟、随机失败率，配合测试用例模拟弱网与失败重试。
- **debug APK 默认走 Mock，release APK / 桌面发布件默认走真实服务端**。

### 安卓工作台（projects/android/）

```bash
cd projects/android
cp local.properties.example local.properties   # SDK 路径 + shandong.* 签名项
./scripts/build_web.sh                         # 前端 → app/src/main/assets/web/
./scripts/build_apk.sh                         # 约定：每次改完代码都要 debug + release 两套
python3 scripts/android_check.py               # 不需要手机的桥与全流程自检（27 项）
```

- 后端是桌面包的**整包 vendoring**（`app/src/main/python/shandong_school_cracked/`，仅去 `gui.py`）。
  **改完桌面包要整包同步过去**（曾因只改一端导致 `protocol.py` 落后一版）。
- 桥接口唯一权威是 [`docs/android/接口契约.md`](docs/android/接口契约.md)（44 个方法，
  与桌面 `gui.JsApi` 逐字一致）；改方法名/参数顺序/返回结构都算**破坏性变更**。
- 两端上传一致性回归：`python3 projects/scripts/parity_check.py`（17 接口逐字段）。
- 前端改动后跑 `python3 projects/scripts/web_lint.py`（eslint 门禁，造过一次 JSX 引用未定义变量白屏）。

### 打包与发布

```bash
cd projects/desktop && .venv/bin/python scripts/build_bin.py --zip   # 本平台单文件
```

细节（PyInstaller spec、Android job、图标、版本资源、踩过的坑）见 `docs/desktop/打包与发布.md`。

## 逆向工作（report/ scripts/ work/）

- `samples/` **只读**：脚本默认从 `samples/com.huachenjie.shandong_school.apk` 取样本。
- `work/` 只留证据与输入：`report/` 每条结论都标了对应路径，不要对 `work/` 做破坏性修改。
- `tmp/` 可随时清；只保留可重建的中间产物。
- 新增结论进 `report/`，配套脚本放 `report/` 旁的 `scripts/`；整理/归档记录更新 `docs/`。
- 逆向常用复现命令见 `work/README.md` 的「常用复现命令」。
- **安全红线**：`work/records/logs/`（会话日志含真实手机号）与 `.tmp/` 已进 `.gitignore`；
  2026-11-05 曾发现日志入库，已用 `git-filter-repo` 从全部历史移除并强推。**不得重新提交**。
- 抓包产物（pcap / HAR）只放 `tmp/capture/`，不提交、不贴日志；对比方法见
  [`docs/capture-huawei.md`](docs/capture-huawei.md)。

## 提交与推送

- 代码 / 报告改动**提交并推送**。
- **本机推送**：本机 `/etc/ssh` 配置属主异常，需用仓库包装脚本：

  ```bash
  GIT_SSH_COMMAND="$PWD/scripts/git-ssh-wrap.sh" git push origin main
  ```

## CI

`.github/workflows/build-release.yml`：push 以 `v*` 开头的 tag →
**三个平台**：`desktop` job 跑 Linux（ubuntu-22.04，glibc 2.35 兼容面宽）+ Windows 矩阵，
`android` job 用 JDK 21 + Python 3.12 出 debug/release APK，`release` job 汇总发 GitHub Release。
标签含 `-pre/-beta/-rc/-alpha` → 自动 `--prerelease`（不进 latest）。
手动触发只构建不发版；有 secret `SHANDONG_KEYSTORE_B64` 才签正式包。
测试在 `projects/desktop` 下跑（Windows 侧测试失败仅告警不阻断）；安卓侧跑前端 lint + 手势测试。