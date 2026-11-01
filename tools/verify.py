#!/usr/bin/env python3
"""离线自检：预设块结构与安装器行为。不联网，也不碰真实 profile。

跑法：python tools/verify.py
依赖：PyYAML（pip install pyyaml）。任一检查失败则退出码非 0。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCK_PATH = ROOT / "preset" / "ultra.patch.block.yml"
INSTALL_PATH = ROOT / "tools" / "install.py"
README_PATH = ROOT / "README.md"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "verify.yml"

FAILS: list[tuple[str, str]] = []


def load_install_module():
    spec = importlib.util.spec_from_file_location("ultra_install", INSTALL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rows(text: str):
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_multi_constructor(
        "tag:yaml.org,2002:js",
        lambda loader, suffix, node: loader.construct_scalar(node),
    )
    docs = list(yaml.load_all(text, Loader=Loader))
    rows = docs[0] if docs else []
    return [] if rows is None else rows


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def iter_plugin_rows(plugins):
    """只遍历插件行：分组行的 config 是子插件列表，普通行的 config 不再往里钻。"""
    for row in plugins:
        if not isinstance(row, dict):
            continue
        yield row
        children = row.get("config")
        if isinstance(children, list):
            yield from iter_plugin_rows(children)


def find_preset(rows):
    hits = [row for row in walk(rows) if row.get("id") == "preset-ultra"]
    assert len(hits) == 1, f"期望恰好一个 preset-ultra，实际 {len(hits)} 个"
    return hits[0]


def check(name):
    def wrap(fn):
        try:
            detail = fn()
        except AssertionError as exc:
            FAILS.append((name, str(exc) or "断言失败"))
            print(f"[fail] {name}：{exc or '断言失败'}")
        except Exception as exc:  # noqa: BLE001 - 自检脚本要兜住一切
            FAILS.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"[fail] {name}：{type(exc).__name__}: {exc}")
        else:
            print(f"[ok]   {name}" + (f" — {detail}" if detail else ""))
        return fn

    return wrap


def snapshot_bytes(path: Path) -> bytes:
    return path.read_bytes()


# ── 静态检查 ────────────────────────────────────────────────────────────────


@check("块文件存在、UTF-8、LF、以换行结尾")
def _():
    assert BLOCK_PATH.is_file(), f"缺少 {BLOCK_PATH}"
    data = BLOCK_PATH.read_bytes()
    data.decode("utf-8")
    assert b"\r\n" not in data, "块文件含 CRLF（仓库要求 LF）"
    assert data.endswith(b"\n"), "块文件末尾没有换行"
    return f"{len(data)} 字节"


@check("受管块标记成对且位置正确")
def _():
    install = load_install_module()
    text = BLOCK_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    nonblank = [i for i, line in enumerate(lines) if line.strip()]
    assert lines[nonblank[0]] == install.START, "第一行不是安装器的 START 标记"
    assert lines[nonblank[-1]] == install.END, "最后一行不是 END 标记"
    assert text.count(install.START) == 1, "START 出现次数不是 1"
    assert text.count(install.END) == 1, "END 出现次数不是 1"
    assert install.LEGACY_STARTS and install.START not in install.LEGACY_STARTS, "旧标记集合异常"
    return "START/END 与 install.py 常量一致"


@check("YAML 可解析（!!js tag 也认）")
def _():
    rows = load_rows(BLOCK_PATH.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and len(rows) == 1, "顶层应只有一个 insert 行"
    assert isinstance(rows[0], dict) and list(rows[0]) == ["insert"], f"行键异常：{list(rows[0]) if isinstance(rows[0], dict) else rows[0]}"
    inserted = rows[0]["insert"]
    assert isinstance(inserted, list) and len(inserted) == 1, "insert 下应恰好一条预设声明"
    return "1 个 insert 行"


@check("预设行 id / 模块名正确")
def _():
    row = load_rows(BLOCK_PATH.read_text(encoding="utf-8"))[0]["insert"][0]
    assert row.get("id") == "preset-ultra", row.get("id")
    assert row.get("name") == "@deepseek-ai/dsh-agent-preset", row.get("name")
    return row["name"]


@check("预设元数据完整（id=ultra / 名称 / 描述 / order）")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    assert cfg.get("id") == "ultra", cfg.get("id")
    assert cfg.get("name") == "超频", cfg.get("name")
    desc = cfg.get("description")
    assert isinstance(desc, str) and 10 <= len(desc) <= 300, f"描述长度异常：{desc!r}"
    assert isinstance(cfg.get("order"), int) and cfg["order"] >= 5, f"order 应 ≥5：{cfg.get('order')!r}"
    return f"order={cfg['order']}，描述 {len(desc)} 字"


@check("插件树合法：id 唯一、name 非空、分组带 config")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    plugins = cfg["plugins"]
    seen, groups = set(), 0
    for row in iter_plugin_rows(plugins):
        pid, name = row.get("id"), row.get("name")
        assert isinstance(pid, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", pid), f"非法 id：{pid!r}"
        assert pid not in seen, f"插件 id 重复：{pid}"
        seen.add(pid)
        assert isinstance(name, str) and name, f"{pid} 缺少 name"
        if row.get("group"):
            groups += 1
            assert isinstance(row.get("config"), list) and row["config"], f"{pid} 是分组但没有 config 列表"
    return f"{len(seen)} 个插件行，{groups} 个分组"


@check("必备插件齐全")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    ids = {row["id"] for row in iter_plugin_rows(cfg["plugins"])}
    required = {
        "persona", "agent-instructions", "time-context", "tool-bash", "tool-pwsh",
        "tool-fs", "tool-fs-search", "tool-jobs", "tool-schedule", "skill-filesystem",
        "tool-skill", "command-goal", "tool-goal", "planning", "plan-mode",
        "compaction", "compaction-basic", "command-compact", "tool-result-pruner",
        "delegation", "tool-subagent-control", "tool-subagent-list-agents",
        "tool-subagent", "tool-subagent-fork", "tool-ask-user", "tool-todo",
        "tool-web", "tool-presentation", "present",
    }
    missing = sorted(required - ids)
    assert not missing, f"缺少：{', '.join(missing)}"
    return f"{len(required)} 个关键插件都在"


@check("persona 模板变量只有 provider / model")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    persona = next(row for row in iter_plugin_rows(cfg["plugins"]) if row["id"] == "persona")
    text = (persona["config"].get("prefix") or "") + "\n" + (persona["config"].get("suffix") or "")
    double = set(re.findall(r"\{\{([^{}]+)\}\}", text))
    single = set(re.findall(r"(?<!\{)\{(?!\{)([A-Za-z_][A-Za-z0-9_.-]*)\}(?!\})", text))
    unknown = sorted((double | single) - {"provider", "model"})
    assert not unknown, f"未注册的模板变量：{unknown}（本版 DSH 只认 provider/model）"
    return f"用到：{sorted(double | single) or '无'}"


@check("persona 关键文案与 9 条工作法")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    persona = next(row for row in iter_plugin_rows(cfg["plugins"]) if row["id"] == "persona")["config"]
    prefix, suffix = persona.get("prefix") or "", persona.get("suffix") or ""
    for anchor in ("Ultra（超频）模式", "用量立场：不限量，随便花", "KPI", "正确、完整、可验证"):
        assert anchor in prefix, f"prefix 缺少锚点：{anchor}"
    items = re.findall(r"(?m)^\s*(\d+)\.\s+\*\*", suffix)
    assert items == [str(i) for i in range(1, 10)], f"工作法编号异常：{items}"
    assert suffix.rstrip().endswith("记住：你非常富有，用户想看的是上限，不是省钱。"), "suffix 结尾不对"
    return f"prefix {len(prefix)} 字，suffix {len(suffix)} 字"


@check("persona 提到的工具都在预设里")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    ids = {row["id"] for row in iter_plugin_rows(cfg["plugins"])}
    persona = next(row for row in iter_plugin_rows(cfg["plugins"]) if row["id"] == "persona")["config"]
    text = (persona.get("prefix") or "") + (persona.get("suffix") or "")
    wanted = {
        "todo_write": "tool-todo",
        "subagent": "tool-subagent",
        "subagent_fork": "tool-subagent-fork",
        "goal": "tool-goal",
    }
    missing = [f"{word}→{pid}" for word, pid in wanted.items() if word in text and pid not in ids]
    assert not missing, f"persona 提到但未安装：{missing}"
    return "、".join(sorted({pid for pid in wanted.values()}))


@check("裁剪阈值放宽且自洽")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    pruner = next(row for row in iter_plugin_rows(cfg["plugins"]) if row["id"] == "tool-result-pruner")["config"]
    assert pruner.get("thresholdChars") == 32000, pruner.get("thresholdChars")
    assert pruner.get("headChars") == 16000, pruner.get("headChars")
    assert pruner.get("tailChars") == 4000, pruner.get("tailChars")
    assert pruner["headChars"] + pruner["tailChars"] <= pruner["thresholdChars"], "头尾之和超过阈值"
    return "32000 / 16000 / 4000"


@check("子 agent 路由已钉死")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    rows = {row["id"]: row for row in iter_plugin_rows(cfg["plugins"]) if "id" in row}
    spawn = rows["tool-subagent"]["config"]
    assert spawn.get("provider") == "spawn", spawn.get("provider")
    assert spawn.get("toolName") == "subagent", spawn.get("toolName")
    opts = spawn.get("agentOptions") or {}
    assert opts.get("provider") and opts.get("model"), f"agentOptions 不全：{opts}"
    fork = rows["tool-subagent-fork"]["config"]
    assert fork.get("provider") == "fork" and fork.get("toolName") == "subagent_fork"
    return f"{opts['provider']} / {opts['model']}"


@check("workflow 工具保持禁用")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    rows = {row["id"]: row for row in iter_plugin_rows(cfg["plugins"]) if "id" in row}
    for pid in ("workflow-ptc", "tool-workflow"):
        assert rows[pid].get("disabled") is True, f"{pid} 应 disabled: true"
    return "workflow-ptc、tool-workflow"


@check("bash / pwsh 平台守卫互补")
def _():
    cfg = find_preset(load_rows(BLOCK_PATH.read_text(encoding="utf-8")))["config"]
    rows = {row["id"]: row for row in iter_plugin_rows(cfg["plugins"]) if "id" in row}
    bash = str(rows["tool-bash"].get("disabled"))
    pwsh = str(rows["tool-pwsh"].get("disabled"))
    assert "process.platform" in bash and "win32" in bash and "===" in bash, bash
    assert "process.platform" in pwsh and "win32" in pwsh and "!==" in pwsh, pwsh
    return "win32 上 bash 禁用、pwsh 启用"


# ── 安装器行为（临时目录，不碰真实 profile）────────────────────────────────


FIXTURE = """# verify fixture —— 只活在临时目录里
- id: agent-preset-registry
  name: '@deepseek-ai/dsh-agent-preset-registry'
  config:
    default: ptc
"""


def run_install(*args: str, expect: int | None = None, env: dict | None = None, raw: bool = False):
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    if env:
        child_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(INSTALL_PATH), *args],
        capture_output=True,
        text=not raw,
        encoding=None if raw else "utf-8",
        errors=None if raw else "replace",
        env=child_env,
    )
    if expect is not None and proc.returncode != expect:
        err = proc.stderr if raw else (proc.stderr or "")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        raise AssertionError(f"退出码 {proc.returncode} ≠ {expect}；stderr={err.strip()[:400]}")
    return proc


def make_patch(tmp: Path, text: str = FIXTURE) -> Path:
    patch = tmp / "cordis.patch.yml"
    patch.write_text(text, encoding="utf-8", newline="\n")
    return patch


@check("安装器：未安装时 --check 返回 1")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        patch = make_patch(Path(tmp))
        run_install("--check", "--profile-patch", str(patch), expect=1)
        return str(patch)


@check("安装器：安装写入受管块，YAML 仍合法")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        patch = make_patch(Path(tmp))
        proc = run_install("--profile-patch", str(patch), expect=0)
        text = patch.read_text(encoding="utf-8")
        install = load_install_module()
        assert text.count(install.START) == 1 and text.count(install.END) == 1
        rows = load_rows(text)
        assert len(rows) == 2, f"安装后应有 2 行，实际 {len(rows)}"
        find_preset(rows)
        assert "备份" in proc.stdout
        return f"{len(text)} 字节，2 行"


@check("安装器：重复安装幂等（不写第二遍、不产生新备份）")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        patch = make_patch(Path(tmp))
        run_install("--profile-patch", str(patch), expect=0)
        before = snapshot_bytes(patch)
        backups_before = len(list(Path(tmp).glob("*.bak-ultra-*")))
        proc = run_install("--profile-patch", str(patch), expect=0)
        after = snapshot_bytes(patch)
        backups_after = len(list(Path(tmp).glob("*.bak-ultra-*")))
        assert before == after, "重复安装改动了文件"
        assert backups_after == backups_before, "重复安装产生了多余备份"
        assert "未改动" in proc.stdout, proc.stdout
        return "字节不变"


@check("安装器：--check 一致时返回 0")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        patch = make_patch(Path(tmp))
        run_install("--profile-patch", str(patch), expect=0)
        proc = run_install("--check", "--profile-patch", str(patch), expect=0)
        assert "一致" in proc.stdout
        return proc.stdout.strip()


@check("安装器：--print 与块文件逐字一致")
def _():
    proc = run_install("--print", expect=0, raw=True)
    block = BLOCK_PATH.read_bytes().replace(b"\r\n", b"\n")
    out = proc.stdout.replace(b"\r\n", b"\n")
    assert out == block, f"--print 输出 {len(out)} 字节，块文件 {len(block)} 字节"
    return f"{len(out)} 字节"


@check("安装器：--remove 还原原始补丁")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        patch = make_patch(Path(tmp))
        original = patch.read_text(encoding="utf-8")
        run_install("--profile-patch", str(patch), expect=0)
        run_install("--remove", "--profile-patch", str(patch), expect=0)
        restored = patch.read_text(encoding="utf-8")
        assert restored.split() == original.split(), "卸载后内容与原始补丁不一致"
        run_install("--check", "--profile-patch", str(patch), expect=1)
        return "内容与安装前一致（忽略行尾空白）"


@check("安装器：重复 START 时拒绝写入且不动文件")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        install = load_install_module()
        block = BLOCK_PATH.read_text(encoding="utf-8")
        patch = make_patch(Path(tmp))
        patch.write_text(FIXTURE + "\n" + block + block, encoding="utf-8", newline="\n")
        before = snapshot_bytes(patch)
        proc = run_install("--profile-patch", str(patch), expect=3)
        assert snapshot_bytes(patch) == before, "失败时文件被改动了"
        assert "两个受管块起始标记" in proc.stderr, proc.stderr
        return "退出码 3，文件未变"


@check("安装器：旧标记块自动迁移，不残留两份")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        install = load_install_module()
        block = BLOCK_PATH.read_text(encoding="utf-8")
        legacy = block.replace(install.START, install.LEGACY_STARTS[0])
        patch = make_patch(Path(tmp))
        patch.write_text(FIXTURE + "\n" + legacy, encoding="utf-8", newline="\n")
        run_install("--profile-patch", str(patch), expect=0)
        text = patch.read_text(encoding="utf-8")
        assert install.START in text, "新标记未写入"
        assert not any(mark in text for mark in install.LEGACY_STARTS), "旧标记仍残留"
        assert text.count(install.START) == 1
        assert len(find_preset(load_rows(text))["config"]["plugins"]) > 0
        return "旧块 → 新块"


@check("安装器：空补丁文件也能装")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        patch = make_patch(Path(tmp), "")
        run_install("--profile-patch", str(patch), expect=0)
        text = patch.read_text(encoding="utf-8")
        assert text.startswith(load_install_module().START), "空文件安装后未以 START 开头"
        rows = load_rows(text)
        assert len(rows) == 1, f"应为 1 行，实际 {len(rows)}"
        return "从零写出合法补丁"


@check("安装器：--profile + DSH_HOME 定位正确")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        env = {"DSH_HOME": tmp}
        proc = run_install("--check", env=env, expect=3)
        assert "找不到 profile 补丁" in proc.stderr, proc.stderr
        assert "profiles" in proc.stderr and "desktop" in proc.stderr, proc.stderr
        target = Path(tmp) / "profiles" / "desktop" / "cordis.patch.yml"
        target.parent.mkdir(parents=True)
        target.write_text(FIXTURE, encoding="utf-8", newline="\n")
        run_install("--check", env=env, expect=1)
        run_install(env=env, expect=0)
        run_install("--check", env=env, expect=0)
        return str(target)


# ── 仓库自身 ────────────────────────────────────────────────────────────────


@check("README 含安装与验收说明")
def _():
    text = README_PATH.read_text(encoding="utf-8")
    for anchor in (
        "https://github.com/Liaoyun666/dsh-ultra-preset",
        "tools/install.py",
        "--check",
        "--remove",
        "DeepSeek Harness",
        "MIT",
    ):
        assert anchor in text, f"README 缺少：{anchor}"
    return f"{len(text)} 字符"


@check("Markdown 相对链接都能落到文件")
def _():
    files = [README_PATH, *sorted((ROOT / "docs").glob("*.md"))]
    pattern = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    checked, dead = 0, []
    for md in files:
        text = md.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            target = target.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            checked += 1
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                dead.append(f"{md.name} → {target}")
    assert not dead, "死链：" + "；".join(dead)
    return f"{checked} 条链接"


@check("CI 覆盖 ubuntu + windows，且真的跑 verify.py")
def _():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "tools/verify.py" in text, "工作流没有跑 verify.py"
    assert "ubuntu-latest" in text and "windows-latest" in text, "矩阵缺少平台"
    assert "setup-python" in text and "pyyaml" in text, "没有装 Python / PyYAML"
    return "两平台 × 两版本 Python"


@check("LICENSE 是 MIT 全文")
def _():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License"), text[:32]
    assert "Copyright (c) 2026 Liaoyun666" in text, "版权行不对"
    assert "WITHOUT WARRANTY OF ANY KIND" in text, "缺少免责声明"
    return "MIT / 2026 Liaoyun666"


@check("仓库没有夹带本机路径或凭据")
def _():
    bad = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if "__pycache__" in path.parts or path.suffix in {".png", ".jpg", ".zip", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        needles = ("E:" + chr(92) + "工作区", "ghp" + "_", "315" + "68")
        for needle in needles:
            if needle in text:
                bad.append(f"{path.relative_to(ROOT)} 含 {needle!r}")
    assert not bad, "；".join(bad)
    return "干净"


def main() -> int:
    print(f"检查仓库：{ROOT}")
    print(f"Python {sys.version.split()[0]}")
    if FAILS:
        print(f"\n{len(FAILS)} 项失败：")
        for name, detail in FAILS:
            print(f"  - {name}：{detail}")
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
