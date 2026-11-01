# Changelog

## 0.1.0 — 2026-11-02

首个公开版本。

- 预设 `ultra`（显示名「超频」，`order: 6`）：以 DSH 0.2.1-rc.3 内置 `ptc` 预设的插件列表为底。
- persona：用量立场 + 「正确 / 完整 / 可验证」KPI + 9 条超频工作法。
- 工具结果裁剪放宽到 32000 / 16000 / 4000 字符。
- 子 agent 路由钉死为 `deepseek-account` / `deepseek-flash`。
- `tools/install.py`：安装 / `--check` / `--remove` / `--print` / `--profile` / `--profile-patch`，
  受管块 + 自动备份，兼容旧版标记的自动迁移。
- `tools/verify.py`：29 项离线自检，含临时目录里的安装往返测试。
- CI：ubuntu + windows × Python 3.10 / 3.13。
