# 华为手机「网络报文分析」抓包对比指南

目的：用华为开发者选项自带的报文抓包，采一份**原版 App 从冷启动到进入阳光跑
并开跑**的真实流量，与本实现（桌面/安卓）的启动序列逐项对照，验证行为链
（登录 → 首页浏览 → 跑步模块）在**顺序、域名、节奏**上是否对得上。

---

## 进展（2026-11-05）

本指南写于 2026-11-04「准备阶段」。实际拿数据走的是**手机端 Reqable / HttShark**（内置用户 CA +
可直接导出 HAR），比华为「网络报文分析」的原始 pcap 信息量更大，**已完成解密**（说明应用层
没有硬 pinning）。得到的结论已落进代码，不再是待办：

| 发现 | 落地位置 |
|---|---|
| 鸿蒙口径 `platform=4` / `appVersion 8.7.1` / `buildVersion 26101314` | `constants.HM_PROFILE`（`--hm`） |
| 鸿蒙 `modelName` 是**纯型号**（`ALN-AL80`，非 `MANUFACTURER\|MODEL`） | 同上；`net.public_fields()` |
| 鸿蒙 UA 全小写且**无括号段**：`shandong/8.7.1` | `net.user_agent()`（`platform == "4"` 分支） |
| 登录后→进跑步前的**真实浏览实序** | `behavior.py` + `constants.EP` 行为链段（已重排） |
| `schoolLetter/redDot`、`task/getDescription` 是鸿蒙 8.7.1 新增（8.7.7 dex 无此路由） | `constants.EP` 注释 |
| satoken 活跃期滚动续期，放着不用（实测 10 天）失效返 `1503` | [`协议说明 §4.0.1`](desktop/协议说明.md) |

下文保留 pcap 路线，用于**无解密条件下的节奏（域名/连接簇）对比**，与已完成的字段级核对互补。

---

## 0 · 先说清楚这份抓包能看到什么、看不到什么

| 项 | 能否看到 | 说明 |
|---|---|---|
| 域名（SNI/DNS） | ✅ | `api.huachenjie.com`、`mh5.huachenjie.com`、`oss-cdn.huachenjie.com` … |
| 每条连接的时间/间隔 | ✅ | 行为链的**节奏**（红点 → 社区流 → 帖子 → 排行 → 资料）靠这个验证 |
| TLS 握手、TCP 流 | ✅ | 包数、方向、大小 |
| **HTTPS 明文 path / 请求体** | ❌ | 华为的报文分析是**原始 pcap**，不是 MITM 解密，看不到 `/run-front/...` |
| 明文 HTTP | ✅ | 原版 `usesCleartextTraffic=true`，若个别请求走明文可直接看到完整 URL |

**所以这条路线验证的是「访问了哪些域名、按什么节奏、几个连接」，不是报文字段。**
要看 path/body 得走方案 B（MITM，见 §5）。两者互补，不冲突。

### 已核实的关键事实（决定方案 B 可行性）

用 `aapt2` 从原版 APK 里读出的配置：

```
AndroidManifest.xml:
  android:debuggable="false"
  android:usesCleartextTraffic="true"
  android:networkSecurityConfig="@xml/network_security_config"

res/xml/network_security_config.xml:
  <base-config cleartextTrafficPermitted="true">
    <trust-anchors>
      <certificates src="system" />
      <certificates src="user" />      ← ★ 信任用户 CA
    </trust-anchors>
  </base-config>
```

即**系统级允许 MITM 解密**（装了用户 CA 就生效）。但 APK 里还有
`assets/huachenjie.pem`（`CN=*.huachenjie.com` 的证书链，见
`report/10-三项收尾与加固谱系确定.md` §1.3），且反编译里
`com.huachenjie.common.cache_webview.a` 有自定义 `X509TrustManager` /
`SSLSocketFactory` 装配入口——**存在应用层证书绑定的可能**。
所以 MITM 能不能看到明文要实测，指南里给了判定方法（§5.3）。

---

## 1 · 手机侧准备（一次性）

1. **开发者选项**：设置 → 关于本机 → 连点「版本号」7 次 → 输入锁屏密码。
2. 找到入口（不同 EMUI/HarmonyOS 版本措辞略有差异）：
   - 设置 → 系统和更新 → 开发人员选项 → **「网络报文分析」/「抓包」/「TCPdump」**
   - 或：设置 → 系统和更新 → 开发人员选项 → 「网络」分组下
   - 部分机型入口在「开发者选项 → 网络共享/调试」里，叫 **「启用网络报文日志」**
3. 打开开关，确认提示「抓包文件保存在…」（常见路径：
   `/sdcard/Download/`、`/sdcard/Huawei/Debug/`、`/sdcard/log/` 或
   `/data/local/tmp/`，以开关旁的提示为准）。
4. **清空后台**、关掉其他 App 的自动同步（微信/应用市场/系统更新），
   否则 pcap 里全是噪声，域名过滤也救不回来。
5. 建议连 **WiFi**（ Cellular 下部分机型只抓 WiFi 口），并记下手机时间
   （后面把 pcap 时间轴和操作时刻对上）。

---

## 2 · 现场操作（关键：按顺序、报点）

> 抓包前先**卸载/退登原版 App**，确保是「冷启动 + 完整登录」路径，
> 而不是会话恢复——我们要的正是登录后的首屏行为链。

| 时刻 | 操作 | 备注 |
|---|---|---|
| T0 | **打开「网络报文分析」开关**，开始抓 | 记下墙上时钟时间 |
| T0+2s | 启动原版闪动校园 App | 停留启动页/隐私协议 |
| T1 | 同意隐私协议 → 进入登录页 | 密码登录 |
| T2 | 点「登录」 | 滑块验证码照常过 |
| T3 | **进首页后不要动**，停留 30 秒 | ★ 这段就是行为链：红点/社区流/推荐/排行都是这段时间发出去的 |
| T4 | 点进「阳光跑」 | 学期/围栏/规则/概览 |
| T5 | 进入跑步准备页，**停 10 秒** | 不点开始 |
| T6 | 点「开始跑步」，走 30 秒 | 分段上传开始 |
| T7 | 结束/放弃这次跑步，回首页停 10 秒 | 跑后行为（详情/排行/红点） |
| T8 | **关闭抓包开关** | 导出文件 |

**每个时刻在纸上记一笔**（T0/T2/T3/T4/T6 的时钟时间），后面把 pcap
的相对秒数换算成绝对时刻，就能知道哪一簇请求属于哪个阶段。

> ⚠ 别在抓包期间刷微信/切后台，噪声会混进 `huachenjie` 之外的域名，
> 但不影响我们按域名过滤；主要影响是连接数变多，节奏判断变难。

---

## 3 · 导出与传回电脑

1. 手机文件管理里找到 pcap/pcapng（扩展名可能是 `.pcap`、`.pcapng`、
   `.cap`，个别 EMUI 版本导出为 `.txt` 的 hex dump——若如此，用
   `text2pcap -q dump.txt capture.pcap` 转回标准 pcap）。
2. 传到电脑，放到工作区（**别放 `/tmp`**，DSH 沙箱每次调用后 `/tmp` 不保留）：

   ```
   /home/ylxc/Projects/lib/ShanDong/tmp/capture/
   ```

   用 `adb pull` 也行：

   ```bash
   adb pull /sdcard/Download/network_dump.pcapng ~/Projects/lib/ShanDong/tmp/capture/
   ```

3. 先确认文件是标准 pcap：

   ```bash
   file capture.pcapng
   tshark -r capture.pcapng -c 3           # 能列出头 3 帧就是标准格式
   ```

---

## 4 · 分析（本仓库现成工具）

### 4.1 生成时间线

```bash
cd ~/Projects/lib/ShanDong
python3 projects/desktop/scripts/pcap_timeline.py \
    tmp/capture/capture.pcapng \
    --host huachenjie \
    --out tmp/capture/timeline.txt
```

输出形如：

```
# capture.pcapng — 闪动校园时间线（… 条，域名过滤 ('huachenjie',)）
   0.000s  [DNS ]  解析 api.huachenjie.com
   0.312s  [SNI ]  HTTPS → api.huachenjie.com (dst …)
   1.204s  [SNI ]  HTTPS → api.huachenjie.com
   …
```

按第 2 节记的 T0/T2/T4 时刻把相对秒数分段，就能得到：
**登录前 / 登录 / 首页 30s / 阳光跑模块 / 跑步中 / 跑后** 各自的连接簇。

### 4.2 与「预期序列」对照

本实现（含新补的行为链）的预期域名/阶段：

| 阶段 | 预期看到的连接 | 对应接口 |
|---|---|---|
| 冷启动 | `api.huachenjie.com` 1–2 条 | `common/getConfig`、`common/syncTime`、`detect/configV2` |
| 登录 | `api.huachenjie.com` + `mh5.huachenjie.com`（滑块 H5） | `captcha/*`、`auth/loginCheck`、`auth/loginPassword` |
| **登录后首页（行为链）** | 短时间内一簇连接（~8s 内 5–9 条，带明显间隔） | `api/message/redDot`、`api/works/recommend/pool/list`、`api/works/details`×1–2、`api/works/updateVisit`×1–2、`rank/distance`、`account/personal`、`mySchool/simpleInfo` |
| 阳光跑模块 | 一簇连接 | `semesterSelector`、`querySunRunAbstractInfoV2`、`querySchoolFences`、`checkSunRunConfig`、`querySchoolRunSummary`、`queryUnFinishRun` |
| 跑步中 | 周期性连接（15s/60s 节拍） | `uploadRunRecord`、`uploadStepsRecord`、`uploadPaceRecord`… |
| 跑后 | 3 条左右带间隔 | `runRecordDetail`、`rank/distance`、`api/message/redDot` |

**判定口径**：
- 全部落在 `api.huachenjie.com`（少量 `mh5` / `oss-cdn` 属预期）；
- 登录后与「阳光跑模块」之间**必须有独立的一簇**且带 0.5–3s 的间隔
  （这就是行为链的真实时间停顿）——如果两簇连成一片、中间没有间隔，
  说明真机并没有这段浏览，我们补的顺序或节奏要调整；
- 若登录后**完全没有**首页簇，直接跳到阳光跑模块，那行为链就得重新评估。

### 4.3 看完整域名清单（找我们没实现的域名）

```bash
tshark -r tmp/capture/capture.pcapng -Y "tls.handshake.type==1" \
  -T fields -e tls.handshake.extensions_server_name | sort | uniq -c | sort -rn
```

出现 `api.huachenjie.com` 之外的陌生域名（尤其登录/首页阶段），
说明还有没覆盖到的请求面，值得单独追。

### 4.4 若拿到的是解密后的 HAR（方案 B）

```bash
python3 projects/desktop/scripts/har_diff.py capture.har            # 只看抓包
python3 projects/desktop/scripts/har_diff.py capture.har --compare   # 与本实现逐字段对比
```

`har_diff.py` 的 `ROUTE_KEYS` 已扩展到 **18 个路由**：跑步链路 10 个（规则预检 / 开跑 /
四类上传 / 打卡 / 结算 / 人脸底图 / OSS 令牌）+ 行为链 8 个（消息红点 / 社区推荐流 /
帖子详情 / 上报浏览 / 个人资料 / 本校信息 / 里程排行榜 / 跑单详情）。
新增路由时直接往 `ROUTE_KEYS` 里加条目即可；不在表里的走 `--dump` 看原始样本。

---

## 5 · 方案 B：想看明文 path/body（可选，与上面互补）

华为的报文分析**不解密**。要用 MITM 看到 `/run-front/...`，需要：

1. 电脑装 mitmproxy（`pip install mitmproxy` 或包管理器装 `mitmproxy`），
   起 `mitmweb --listen-port 8888 --set block_global=false`，
   或 `mitmdump -w /home/ylxc/Projects/lib/ShanDong/tmp/capture/flow.har --set hardump=...`
   （导出 HAR 用 `mitmdump -w flow.mitm` + `mitmproxy2har`，或直接用
   `--set save_stream_file` 配合导出脚本；最简单是 `mitmweb` 里
   File → Export → HAR）。
2. 手机 WiFi 代理指向电脑 `8888`，浏览器访问 `mitm.it` 装用户 CA
   （原版 NSC 信任 `user`，系统层面放行）。
3. **判定是否真的解密成功**（§0 的 pinning 疑点）：
   - mitmweb 里能看到 `https://api.huachenjie.com/run-front/auth/loginCheck`
     这类明文 → 没绑定，直接导出 HAR 走 §4.4；**实测已走通这条**（Reqable / HttShark 能解密）
   - 只看到 `CONNECT api.huachenjie.com:443` 后立刻 `TLS handshake failed`
     或 App 报网络错误 → 应用层校验证书，MITM 这条路走不通，
     回到 pcap 时间线（§4）即可，**本次任务不需要强行解密**。
4. 安全：抓包含真实账号 token，**只放工作区 `tmp/capture/`（.gitignore
   已忽略 `tmp/`），不要提交、不要贴日志**。用完即删。

---

## 6 · 交付清单（抓完给我这些）

| 文件 | 必需 | 说明 |
|---|---|---|
| `tmp/capture/capture.pcapng` | ✅ | 原始抓包 |
| `tmp/capture/timeline.txt` | ✅ | `pcap_timeline.py` 输出 |
| 第 2 节记的 T0/T2/T3/T4/T6 时刻 | ✅ | 手写几行即可，用来对齐阶段 |
| `flow.har` | ✅ | 实测已拿到（Reqable / HttShark 导出），字段级核对已完成 |
| 手机机型 / EMUI 或 HarmonyOS 版本 | ⭕ | 不同版本抓包路径有差异 |

拿到后我做三件事：
1. 按阶段拆时间线，核对**行为链是否真实存在、顺序与间隔是否一致**（✓ 已完成，行为链已重排）；
2. 若发现真机有我们没实现的域名/阶段，补进 `constants.EP` + `behavior.py`（✓ 已补 worksConfig /
   jackpot / tasks / getCommonConfig / suggestion / schoolLetter redDot / userResource / task description）；
3. 生成一份对照报告（`report/27-真机启动流量对照.md`），含差异表与结论（⏳ 待做：现有结论已
   写进 [`docs/desktop/协议说明.md`](desktop/协议说明.md) §4.0.1 与 §6.0.1，如需独立报告再补）。

---

## 7 · 工具现状

| 工具 | 状态 |
|---|---|
| `projects/desktop/scripts/pcap_timeline.py` | ✅ 新增：pcap → 时间线（DNS/SNI/HTTP） |
| `projects/desktop/scripts/har_diff.py` | ✅ 已扩：HAR 逐字段对比（**18 路由**：跑步链路 10 + 行为链 8） |
| `tshark` | ✅ 本机已装 `/usr/bin/tshark` |
| `mitmproxy` | ⭕ 本机未装；实际改用**手机端 Reqable / HttShark**（已完成解密并导出 HAR） |
| 原版 APK 的 NSC / 证书资产 | ✅ 已核实（本指南 §0） |
| 真机 pcap / HAR | ✅ HAR 已拿到并完成字段级核对（2026-11-05）；pcap 时间线路线保留作节奏对比 |
