# report/ —— 分析报告 01–26

样本：`com.huachenjie.shandong_school` v8.7.7（versionCode 26101017），
SHA-256 `4e74df34c08cab0f7b5a1903e5dc204d7a0bf69d56e085731191ea0f909dd470`。

## 编号与主题

| 号 | 主题 |
|---|---|
| 01–03 | 初步分析、插件与载荷、容器 DEX 静态还原 |
| 04–06 | 完整脱壳、业务协议、native 签名黑盒 |
| 07–09 | 核心业务链路、隐藏 SO、安全 SDK |
| 10–13 | 收尾、liby 结构还原、签名定位与攻破 |
| 14–15 | 加固谱系、服务端端到端验证 |
| 16–19 | 跑步链路 / native 编码 encodeRun / 通信层 / 流程一致性核对 |
| 20–22 | 登录持久化、多用户、结算 1112 排查 |
| 23 | 阳光跑上传接口二次核对 |
| 24 ×2 | **`24-反编译接口忠实性核对.md`（协议核对）与 `24-人脸识别实现分析.md`（人脸专题）重号**：引用时写全文件名，别再单写「报告二十四」 |
| 25 | 人脸绕过实现与 TLS 伪装 |
| 26 | 轨迹方案对比与真人数据基准（v(t) 速度动力学、现场照随机化） |
| 18-b2 | 协议成果合集（附于 18 之后，不是独立编号） |

## 已知勘误（后续报告已修正，引用旧报告前先看）

| 出处 | 旧结论 | 现行口径 |
|---|---|---|
| 报告 24（人脸）§1.2 | 服务端随机生成检查点里程 | `randomDistance` 由**客户端**在服务端下发的 `[lower, upper]` 区间内随机生成 |
| 报告 24（人脸）§3.4 | 跑中照文件名 RSA 加密 | **死代码**（r()/s() 无调用者），真实对象名 = `md5` |
| 报告 24（核对） | — | 以脱壳原始 dex 的 `annotation_item` 为唯一判据，jadx 输出仅作参考 |

## 路径说明（2026-10-22 之后）

报告里写的 `work/...` 是**整理前**的路径；2026-10-22 工作区按类别重组，对应关系：

| 报告里的旧路径 | 现在的位置 |
|---|---|
| `work/APP_ALL4`、`work/jadx_FULL`、`work/jadx_shell`、`work/rebuild`、`work/shell_full.dex`、`work/stars_hidden.dex` | `work/dex/…` |
| `work/allso`、`work/hidden_so3`、`work/ghidra_blob`、`work/liby_runtime`、`work/liby_segs` | `work/native/…` |
| `work/certs`、`work/blob_info`、`work/plugins`、`work/jars` | `work/evidence/…` |
| `work/dump`、`work/dump_final` | `work/dumps/…` |
| `work/notes`、`work/logs`、`work/frida` | `work/records/…` |
| `work/android-sdk`、`work/jadx_V2`、`work/rebuilt`、`work/peek`、`work/apks`、`work/jadx_plugins`、`work/reference`、`work/tools/fs` | 已清理（再生方式见 `docs/CLEANUP-2026-10-22.md`） |

`scripts/` 下的脚本已按新路径更新；`work/README.md` 有完整目录说明。
完整删除/迁移记录见 [`../docs/CLEANUP-2026-10-22.md`](../docs/CLEANUP-2026-10-22.md)。

## 与实现的关系

报告是逆向结论的唯一出处；协议常量与接口表的**实现出口**是
`projects/desktop/shandong_school_cracked/constants.py`，行为口径文档见
[`../docs/desktop/协议说明.md`](../docs/desktop/协议说明.md)。
改协议只改 `constants.py`，并在报告里补上判据。桌面↔安卓**上传数据一致性**用
`projects/scripts/parity_check.py` 回归（17 接口逐字段）。
