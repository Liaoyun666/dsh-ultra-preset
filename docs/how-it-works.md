# 这个预设是怎么挂进 DSH 的

> 读这一页不需要改任何东西。它解释三件事：YAML 块落在哪、为什么改完要新开会话、
> 以及哪些做法会和它打架。

## 1. DSH 的组合顺序

一个 profile 的插件树是**叠加**出来的，从下到上：

```text
bundle 默认补丁（DSH 自带）
        ↓
profile 补丁  ~/.dsh/profiles/desktop/cordis.patch.yml   ← 本仓库写这里
        ↓
--patch 覆盖（命令行临时加的）
```

profile 根目录的 `cordis.yml` 只是一个空列表，文件头写得很清楚：

```yaml
# Edit cordis.patch.yml, not this file.
[]
```

所以安装器只碰 `cordis.patch.yml`。

## 2. 一个 `- insert:` 块意味着什么

Loader 把补丁当成一组指令，`insert` 表示往插件树里插入一行：

```yaml
- insert:
    - id: preset-ultra                     # Loader 里的编辑地址
      name: '@deepseek-ai/dsh-agent-preset' # 要加载的模块
      config: { ... }                       # 传给模块的配置
```

- `id` 是这一行在 Loader 树里的**地址**，插件的编辑、禁用、替换都按它找。
- `name` 是要加载的 npm 模块；这里用 DSH 自带的预设声明插件。
- `config` 原样交给插件。

## 3. 预设声明插件做了什么

```yaml
config:
  id: ultra          # 会话保存的预设标识
  name: 超频          # 选择器里显示的名字
  description: ...
  order: 6           # 排序；内置是 1~4
  plugins: [...]     # 这个预设自己的插件树
```

`dsh-agent-preset-registry` 会给**每个声明**建一套独立 scope 和一棵内存 Loader 树，
再按代际退役旧树。因此：

- 修改预设**不会**动到已经创建的会话——它们的组合在创建时就固化了（代际隔离）。
- 新会话拿到新树。
- 这也是「装完看不见」最常见的原因：没有新开会话。

## 4. 行 id 与 config.id 不是一回事

| | 值 | 谁在用 |
|---|---|---|
| 行 id | `preset-ultra` | Loader：定位、编辑、禁用这一行 |
| `config.id` | `ultra` | 会话：记住「我用的是哪个预设」 |

Web UI 的预设编辑器按**行 id** 写一条覆盖。如果它写了一条新的
`- id: preset-ultra`，而本仓库的受管块也是这个 id，就会出现两份声明，
谁生效取决于补丁顺序——这就是 README 说「别用 UI 改它」的原因。

## 5. persona 为什么只能挂在预设里

```yaml
- id: persona
  name: '@deepseek-ai/dsh-persona'
  config:
    prefix: |-   # 插到 DEPLOYMENT_PERSONA_PREFIX 位置
      ...
    suffix: |-   # 插到 DEPLOYMENT_PERSONA_SUFFIX 位置
      ...
```

- `dsh-persona` 是 **scope-only** 的：挂在 host 层会和 deployment persona 冲突。
  挂在预设 scope 里则只覆盖这个预设的会话。
- `prefix` / `suffix` 是文本注入，不是整份提示词替换；runtime context、工具说明等
  仍由各自插件提供。
- 模板变量只有 `{{provider}}` / `{{model}}` 两个（本版 DSH 的 system-prompt 注册表）。
  写别的变量会让该轮直接报 `unknown prompt variable`。

## 6. 三个 `cordis:group` 与 isolate

块里有三个分组，各自把一组子系统圈在预设 scope 内：

| 分组 | isolate | 里面有什么 |
|---|---|---|
| `planning` | `planMode` | `plan-mode` |
| `compaction` | `compaction`、`toolResultPruner` | 压缩、`/compact`、工具结果裁剪 |
| `delegation` | `workflowEngine` | 子 agent、子 agent 控制、workflow 行 |

`isolate` 让这些子系统在这个预设里有独立实例，不和 host 上的同名服务串味。
`workflow-ptc` / `tool-workflow` 仍然 `disabled: true`：不启用工作流引擎，
但保留行，方便以后打开。

## 7. 安装器为什么用「受管块」

profile 补丁是用户自己的文件，可能有别的行。整文件覆盖会毁掉它们；逐行 patch 又太脆。
受管块是折中：

- **可重复安装**：先按标记剥离旧块，再追加新块，永远只有一份。
- **可精确卸载**：只删两个标记之间的内容，其余原样保留。
- **可比对**：`--check` 把块与仓库文件逐行比较，返回 0/1/2。
- **可迁移**：旧版 `dsh-patches/ultra-preset` 的标记也认，安装时自动换成新标记。

写盘顺序是「先备份 → 解析校验 → 再写入」，校验不过就退出，文件保持原样。

## 8. 一次完整的流向

```text
preset/ultra.patch.block.yml
        │  install.py 追加（带标记）
        ▼
~/.dsh/profiles/desktop/cordis.patch.yml
        │  Loader 热重载补丁
        ▼
插件树里多出 include:preset-ultra（@deepseek-ai/dsh-agent-preset）
        │  registry 建 scope + 内存 Loader 树
        ▼
预设选择器里出现「超频」
        │  新开会话、选中
        ▼
会话带上 persona + 32k 裁剪 + 钉死路由的子 agent
```
