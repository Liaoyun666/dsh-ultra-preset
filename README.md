# dsh-ultra-preset

[![verify](https://github.com/Liaoyun666/dsh-ultra-preset/actions/workflows/verify.yml/badge.svg)](https://github.com/Liaoyun666/dsh-ultra-preset/actions/workflows/verify.yml)
[![license](https://img.shields.io/github/license/Liaoyun666/dsh-ultra-preset)](https://github.com/Liaoyun666/dsh-ultra-preset/blob/main/LICENSE)
[![python](https://img.shields.io/badge/python-%E2%89%A53.9-informational)](https://www.python.org/)

> 公开仓：<https://github.com/Liaoyun666/dsh-ultra-preset>
>
> 给 **DeepSeek Harness（DSH）** 的「超频（Ultra）」Agent 预设：
> **用量不限，质量优先**。一个 YAML 块 + 一个安装器，装进 desktop profile，
> 新开会话就能在预设选择器里选「超频」。

## 1. 它是什么

DSH 的每个会话都从一个 **Agent 预设**长出来：预设决定这个会话挂哪些插件、带什么样的人格。
内置的四个根预设各有取舍——`standard` 轻、`ptc` 工具面最全、`minimal` 只剩骨架、
`cordis` 面向内核开发——没有一个把「token 不限量、质量优先」写进人格。

本仓库补上这一个：

| | |
|---|---|
| 预设 id | `ultra`（会话里保存的就是它） |
| 显示名 | 超频 |
| 顺序 | `order: 6`，排在内置的 standard/1、ptc/2、minimal/3、cordis/4 之后 |
| 插件面 | 与 `ptc` 逐行一致（完整工具面 + PTC 呈现） |
| 四处差异 | persona、工具结果裁剪阈值、子 agent 路由、workflow 禁用（第 4 节） |

persona 的核心是三句话：

> 用量立场：不限量，随便花。
> 唯一允许节省的是零信息增益的浪费。
> 这个模式的 KPI 只有三个：正确、完整、可验证。

后面接 9 条工作法：**先定验收 → 把事查透再答 → 想透一层 → 一次做对 → 并行不串行 →
验证到能复现 → 交付前自审 → 长任务不中断 → 先结论后依据**。

## 2. 一分钟安装

```bash
git clone https://github.com/Liaoyun666/dsh-ultra-preset.git
cd dsh-ultra-preset

python tools/install.py          # 写进 ~/.dsh/profiles/desktop/cordis.patch.yml
python tools/install.py --check  # 0 = 已装且一致
```

- Windows 上 `python` 不在 PATH 就用 `py tools/install.py`，同一个脚本。
- 目标文件已有内容也没关系：脚本只在末尾维护一个受管块
  （`# ── preset-ultra … ──` / `# ── /preset-ultra ──`），
  动手前先备份成 `cordis.patch.yml.bak-ultra-<时间戳>`。
- 换 profile：`--profile dev`；换整条路径：`--profile-patch D:/somewhere/cordis.patch.yml`；
  `DSH_HOME` 会覆盖 `~/.dsh`。
- 不想跑脚本：把 [preset/ultra.patch.block.yml](preset/ultra.patch.block.yml) 整个追加到
  profile 补丁末尾即可，效果一样。
- 以前用旧脚本（`dsh-patches/ultra-preset`）装过也没关系：安装器认得旧标记，
  会原地换成新标记，不会留两份；换完别再跑旧脚本，否则它会再加一个块。

装完**新开一个会话**，在预设选择器里选「超频」。已经开着的会话不会变：
profile 补丁是热重载的，但预设只影响之后创建的 Agent。

## 3. 怎么确认装上了

三层，从便宜到贵：

1. 退出码与文本：

   ```bash
   python tools/install.py --check   # 已安装且一致：...（退出码 0）
   ```

2. 在任意 DSH 会话里调 `plugin_manager list_plugins`，应出现：

   ```json
   {"entryId":"include:preset-ultra","moduleName":"@deepseek-ai/dsh-agent-preset",
    "enabled":true,"fiberPhase":"active","patchId":"preset-ultra"}
   ```

3. 新会话选「超频」，问一句「你现在是什么模式、KPI 是什么」：
   答出**正确 / 完整 / 可验证**，且没有 `unknown prompt variable` 报错。

仓库自检（CI 每次 push 都跑，两平台 × 两版本 Python）：

```bash
python tools/verify.py   # 29 项：块结构 + 安装器行为，纯离线
```

## 4. 和 ptc 的四处差异

| # | 位置 | ptc | ultra | 为什么 |
|---|---|---|---|---|
| 1 | `persona` | 无 | 用量立场 + KPI + 9 条工作法 | 这就是这个预设存在的理由 |
| 2 | `tool-result-pruner` | 8192 / 4096 / 1024 | **32000 / 16000 / 4000** | 宁可多占上下文，也不丢证据 |
| 3 | `tool-subagent` | 不钉路由 | `deepseek-account` / `deepseek-flash` | 避免子 agent 静默继承父会话路由 |
| 4 | `workflow-ptc`、`tool-workflow` | `disabled: true` | 同左 | 与 ptc 一致，避免和工作流工具打架 |

第 2 行的三个数是 `thresholdChars / headChars / tailChars`：超过 32k 字符才裁剪，
保留头 16k、尾 4k。ptc 的门槛更窄，长日志、长文件列表经常被裁掉关键行。

其余（planning / compaction / delegation 三个分组、bash / pwsh 平台守卫、
`tool-ask-user`、`tool-todo`、`tool-web`、presentation `mode: ptc`、
`present`、plugin-manager / market 禁用）逐行照抄 `ptc`。

## 5. 目录结构

```text
dsh-ultra-preset/
├── preset/ultra.patch.block.yml   # 唯一真源：一个 - insert: 块
├── tools/install.py               # 安装 / 检查 / 卸载（PyYAML 可选）
├── tools/verify.py                # 29 项离线自检 + 临时目录安装往返测试
├── docs/how-it-works.md           # 这个预设是怎么挂进 DSH 的
├── docs/faq.md                    # 装不上 / 不生效 / 升级后过期
└── .github/workflows/verify.yml   # ubuntu + windows × Python 3.10 / 3.13
```

## 6. 兼容性与升级

- 在 **DSH 0.2.1-rc.3**（win32 x64）上开发与实测；插件列表取自该版本内置的 `ptc` 预设。
- 依赖：Python ≥ 3.9。`PyYAML` 可选——没装时安装器跳过语法校验、照常写入，
  `verify.py` 则需要它。
- DSH 升级后内置预设可能新增插件，本块不会自动长出来：

  ```bash
  python tools/install.py --check   # 2 = 已装但与仓库里的块不一致（通常是升级后）
  ```

  这时对比新版本 asar 里的 `dsh-web-app/presets/ptc.patch.yml`，把新插件行同步进
  `preset/ultra.patch.block.yml`，再跑一次安装器覆盖。步骤见
  [docs/faq.md](docs/faq.md#--check-返回-2)。

## 7. 边界

- **persona 里只能写 `{{provider}}` / `{{model}}`**：本版 DSH 的系统提示只注册了这两个
  模板变量，写 `{cwd}` 之类会让该轮直接失败（`unknown prompt variable`）。
- persona 只能挂在预设里；挂到 host 层会和别的 persona 冲突。
- 预设**不是安全沙箱**：它是一段 YAML，能加载任意插件、执行 host 代码。只装你信得过的块。
- 别用 Web UI 的预设编辑器改 ultra：那会另写一条 `- id: preset-ultra` 覆盖，
  两份声明谁生效由先后顺序决定，很容易互相打架。改文案请改块文件再跑安装器。
- 卸载：`python tools/install.py --remove`（同样先备份）。备份文件确认无误后可以删。

## 8. 许可

MIT，见 [LICENSE](LICENSE)。预设文案欢迎改成你自己的口味：
改 `preset/ultra.patch.block.yml` 里的 persona，再跑一次 `tools/install.py` 就行。
