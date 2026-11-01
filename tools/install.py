#!/usr/bin/env python3
"""把「超频（Ultra）」Agent 预设装进 DSH profile 的 cordis.patch.yml。

原理：在 profile 补丁末尾维护一个受管块，块内容来自本仓库 preset/ultra.patch.block.yml。
profile 补丁是热重载的，但只影响**之后创建**的 Agent —— 已经开着的会话保持旧组合，
要新开一个会话，才看得到预设选择器里的「超频」。

用法：
  python tools/install.py                   # 安装 / 更新（先备份，重复运行替换受管块）
  python tools/install.py --check           # 0=已装且一致 1=未装 2=已装但过期
  python tools/install.py --remove          # 卸载（先备份）
  python tools/install.py --print           # 只打印块内容，不写盘
  python tools/install.py --profile dev     # 换 profile（缺省 desktop）
  python tools/install.py --profile-patch D:/x/cordis.patch.yml
  python tools/install.py --block D:/x/ultra.patch.block.yml

环境变量 DSH_HOME 会覆盖 ~/.dsh。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
from pathlib import Path
from typing import NoReturn

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

START = "# ── preset-ultra（超频模式；由 dsh-ultra-preset/tools/install.py 维护，勿手改） ──"
END = "# ── /preset-ultra ──"
# 旧版（dsh-patches/ultra-preset）写进 profile 的标记：安装时自动替换，不用手动清理
LEGACY_STARTS = (
    "# ── preset-ultra（超频模式；由 dsh-patches/ultra-preset/install.py 维护，勿手改） ──",
)
PRESET_ID = "ultra"
PRESET_ROW = f"preset-{PRESET_ID}"


def die(message: str, code: int = 3) -> NoReturn:
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(code)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def locate_block(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_file():
            die(f"找不到块文件：{candidate}")
        return candidate
    for candidate in (REPO / "preset" / "ultra.patch.block.yml", HERE / "ultra.patch.block.yml"):
        if candidate.is_file():
            return candidate
    die("找不到 preset/ultra.patch.block.yml；用 --block 指定块文件")


def locate_patch(args: argparse.Namespace) -> Path:
    if args.profile_patch:
        return Path(args.profile_patch).expanduser()
    home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    return home / "profiles" / args.profile / "cordis.patch.yml"


def strip_managed(text: str) -> tuple[str, str | None]:
    """去掉受管块（新旧标记都认），返回 (剩余文本, 块原文或 None)。"""
    starts = {START, *LEGACY_STARTS}
    out: list[str] = []
    region: list[str] = []
    installed = False
    skipping = False
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if bare in starts:
            if skipping or installed:
                die(f"补丁里出现了两个受管块起始标记（{bare[:48]}…），先手动清理")
            installed, skipping = True, True
            region = [bare]
            continue
        if skipping:
            region.append(bare)
            if bare == END:
                skipping = False
            continue
        out.append(line)
    if skipping:
        die("受管块起始标记没有对应的结束标记，先手动清理")
    return "".join(out), ("\n".join(region) if installed else None)


def normalize(text: str) -> str:
    """忽略行尾空白与首尾空行的比较形式。"""
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def walk_dicts(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_dicts(value)


def iter_plugin_rows(plugins):
    """只遍历插件行：分组行的 config 是子插件列表，普通行的 config 不再往里钻。"""
    for row in plugins:
        if not isinstance(row, dict):
            continue
        yield row
        children = row.get("config")
        if isinstance(children, list):
            yield from iter_plugin_rows(children)


def validate_yaml(text: str, require_preset: bool = True) -> None:
    try:
        import yaml
    except ImportError:
        print("[warn] 没装 PyYAML，跳过语法校验（pip install pyyaml）", file=sys.stderr)
        return

    class Loader(yaml.SafeLoader):
        pass

    # cordis 用 !!js 标量做 Loader 表达式，SafeLoader 默认不认这个 tag
    Loader.add_multi_constructor(
        "tag:yaml.org,2002:js",
        lambda loader, suffix, node: loader.construct_scalar(node),
    )

    try:
        docs = list(yaml.load_all(text, Loader=Loader))
    except yaml.YAMLError as exc:
        die(f"YAML 解析失败：{exc}")
    rows = docs[0] if docs else []
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        die("profile 补丁顶层不是列表")

    if not require_preset:
        return

    hits = [row for row in walk_dicts(rows) if row.get("id") == PRESET_ROW]
    if len(hits) != 1:
        die(f"期望恰好一个 {PRESET_ROW} 声明，实际 {len(hits)} 个")
    config = hits[0].get("config") or {}
    if config.get("id") != PRESET_ID:
        die(f"{PRESET_ROW} 的 config.id 不是 {PRESET_ID}")
    plugins = config.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        die(f"{PRESET_ROW} 的 config.plugins 为空")

    seen: set[str] = set()
    for row in iter_plugin_rows(plugins):
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            die("插件行缺少字符串 id：" + repr(row)[:120])
        if row_id in seen:
            die(f"插件 id 重复：{row_id}")
        seen.add(row_id)
        name = row.get("name")
        if not isinstance(name, str) or not name:
            die(f"插件 {row_id} 缺少 name")


def backup(path: Path) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak-ultra-{stamp}")
    if target.exists():
        target = path.with_name(f"{path.name}.bak-ultra-{stamp}-{os.getpid()}")
    target.write_bytes(path.read_bytes())
    return target


def main() -> int:
    ap = argparse.ArgumentParser(
        description="安装 / 检查 / 卸载 DSH 的「超频（Ultra）」Agent 预设",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--check", action="store_true", help="只比对：0=一致 1=未装 2=过期")
    ap.add_argument("--remove", "--uninstall", dest="remove", action="store_true", help="删除受管块")
    ap.add_argument("--print", dest="show", action="store_true", help="打印块内容")
    ap.add_argument("--profile", default="desktop", help="profile 名（缺省 desktop）")
    ap.add_argument("--profile-patch", default=None, help="直接指定 cordis.patch.yml 路径")
    ap.add_argument("--block", default=None, help="指定块文件（缺省 preset/ultra.patch.block.yml）")
    args = ap.parse_args()

    block_path = locate_block(args.block)
    block = read_text(block_path).replace("\r\n", "\n")
    if not block.endswith("\n"):
        block += "\n"

    if args.show:
        sys.stdout.write(block)
        return 0

    patch = locate_patch(args)
    if not patch.is_file():
        die(
            f"找不到 profile 补丁：{patch}\n"
            "先确认 DSH 至少启动过一次，或用 --profile / --profile-patch 指定"
        )

    text = read_text(patch)
    rest, region = strip_managed(text)

    if args.check:
        if region is None:
            print(f"未安装：{patch}")
            return 1
        if normalize(region) == normalize(block):
            print(f"已安装且一致：{patch}")
            return 0
        print(f"已安装但内容过期（与 {block_path.name} 不一致）：{patch}")
        return 2

    if args.remove:
        if region is None:
            print(f"未安装，无需删除：{patch}")
            return 1
        saved = backup(patch)
        validate_yaml(rest, require_preset=False)
        write_text(patch, rest)
        print(f"已删除 {PRESET_ROW} 受管块：{patch}")
        print(f"备份：{saved}")
        print("提示：已经开着的会话不受影响；新会话里这个预设会消失。")
        return 0

    if region is not None and normalize(region) == normalize(block):
        print(f"已安装且一致，未改动：{patch}")
        return 0

    saved = backup(patch)
    head = rest.rstrip("\n")
    new_text = (head + "\n\n" if head else "") + block.rstrip("\n") + "\n"
    validate_yaml(new_text)
    write_text(patch, new_text)
    print(f"已写入 {PRESET_ROW}：{patch}")
    print(f"备份：{saved}")
    print("下一步：新开一个 DSH 会话，在预设选择器里选「超频」；已开着的会话不会变。")
    print("自检：python tools/install.py --check（0=已装且一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
