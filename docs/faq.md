# FAQ

## 预设选择器里看不到「超频」

按顺序排查：

1. `python tools/install.py --check` 是否返回 0。返回 1 是没装，2 是块过期。
2. 看补丁文件里有没有受管块：`~/.dsh/profiles/desktop/cordis.patch.yml` 末尾应有两行标记。
3. **新开一个会话**。已经开着的会话不会重新读预设。
4. 仍看不到就重启 DSH：预设 roster 由 `agentPresets` 注册表在插件 apply 时登记，
   个别版本要重启才会重新拉一次。
5. 还不行就在会话里调 `plugin_manager list_plugins`，找 `patchId: preset-ultra`。
   行在但选择器没有，多半是 registry 还没刷新（重启）。

## 选了「超频」，回答却和普通会话一样

先确认三件事：

- 会话确实是**安装之后**新建的；
- 选中的是「超频」，不是「PTC」；
- 问它「你的 KPI 是什么」，答「正确、完整、可验证」才说明 persona 生效。

persona 生效但行为没变，通常是因为任务本身不需要那套工作法——它不会让简单问题变长。

## 报错 `unknown prompt variable "{cwd}"`

persona 里写了未注册的模板变量。本版 DSH 只注册 `provider` 和 `model`。
把 `{cwd}` 之类删掉：工作目录由 runtime context 自动提供，不需要写进 persona。
改完重跑 `tools/install.py`，再新开会话。

## `--check` 返回 2

块与 `preset/ultra.patch.block.yml` 不一致。两种可能：

- 你改过块文件但还没重新安装 → 跑一次 `tools/install.py`。
- DSH 升级后内置预设新增了插件 → 对比新版本 asar 里的
  `dsh-web-app/presets/ptc.patch.yml`，把新行同步进块文件，再安装。

## `--check` 返回 1，但我记得装过

三种常见原因：装到了别的 profile（`--profile` 缺省是 `desktop`）；
`DSH_HOME` 指向了别处；或者补丁被 DSH 的「重置」操作覆盖了。用
`python tools/install.py --check --profile-patch <路径>` 指到具体文件确认。

## 安装器说找不到 profile 补丁

它默认找 `$DSH_HOME/profiles/desktop/cordis.patch.yml`（没有 `DSH_HOME` 时用
`~/.dsh`）。先让 DSH 启动一次，目录就会生成；或者用 `--profile` /
`--profile-patch` 指定。安装器**不会**替你创建 profile 目录。

## Windows 上 `python` 不是命令

用 `py tools/install.py`。本机 `py` 是 Python 3.10，脚本要求 ≥ 3.9。
`python3` 在 Windows 上通常也没有。

## 会不会影响其他会话的人格

不会。persona 挂在预设 scope 里，只对这个预设创建的会话生效。
host 层原有的 persona 仍然作用于其他会话。

## 能改文案或裁剪阈值吗

可以，改 `preset/ultra.patch.block.yml`：

- persona：`config.plugins[0].config.prefix / suffix`；
- 裁剪：`tool-result-pruner` 的 `thresholdChars / headChars / tailChars`；
- 路由：`tool-subagent` 的 `agentOptions.provider / model`。

改完 `python tools/install.py`，`--check` 应回到 0，再新开会话。
注意别在 persona 里加未注册的模板变量。

## 子 agent 为什么钉死 `deepseek-flash`

子 agent 默认会继承父会话的路由；主会话换成别的模型时，子 agent 可能跟着漂。
钉死后行为可预期，也方便按成本核算。不需要就把 `agentOptions` 整段删掉。

## 为什么 `order` 是 6

内置四个根预设占 1~4，5 空着；6 让「超频」排在它们后面，不抢默认位。
它只是排序，不影响功能。

## 卸载后 `.bak-ultra-*` 能删吗

能。备份只用于回滚这一次写入；确认新配置没问题后即可删除。
安装器每次写入都会新建一份，不会覆盖旧备份。

## 可以只要块文件、不要安装器吗

可以。把 `preset/ultra.patch.block.yml` 整个追加到 profile 补丁末尾，效果与安装器一致。
安装器只是帮你处理备份、去重、校验和卸载。

## 这算插件吗，能在插件市场里装吗

不算。它是一条 **profile 补丁**，声明一个预设；插件市场装的是 npm 模块。
两者可以共存，但预设必须在 profile 补丁里声明。

## 以前用别的脚本装过，标记不一样怎么办

安装器认得旧标记
`# ── preset-ultra（超频模式；由 dsh-patches/ultra-preset/install.py 维护，勿手改） ──`：
直接跑一次 `tools/install.py` 就会原地替换成新标记，不会留下两份。

替换之后**别再跑那个旧脚本**——它只认旧标记，会再追加一个块，补丁里就有两个
`preset-ultra` 了（本安装器遇到这种情况会拒绝写入并提示手动清理）。
