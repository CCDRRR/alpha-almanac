"""把 alpha-almanac（Alpha 農民曆）MCP server 加進 Claude Desktop 的設定檔（自動找位置、保留原設定、先備份）。

    .venv\\Scripts\\python -m wqbka.desktop_config            # 加入 / 更新
    .venv\\Scripts\\python -m wqbka.desktop_config --dry-run  # 只顯示會改哪個檔案
    .venv\\Scripts\\python -m wqbka.desktop_config --remove   # 移除

設定檔位置依版本不同（我們實測踩過）：
- Windows 新版（5.x，設定裡沒有 Developer）：%LOCALAPPDATA%\\Claude-Data\\claude_*\\claude_desktop_config.json
- Windows 舊版：%APPDATA%\\Claude\\claude_desktop_config.json
- macOS：~/Library/Application Support/Claude/claude_desktop_config.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .auth import ROOT

NAME = "alpha-almanac"
LEGACY = ["wqb-knowledge"]  # 改名前的舊名稱，加入新設定時一併移除


def find_config() -> Path:
    cands: list[Path] = []
    if sys.platform == "win32":
        local, roaming = Path(os.environ.get("LOCALAPPDATA", "")), Path(os.environ.get("APPDATA", ""))
        cands += sorted((local / "Claude-Data").glob("claude_*/claude_desktop_config.json"))   # 新版：已存在的檔
        cands += [d / "claude_desktop_config.json" for d in sorted((local / "Claude-Data").glob("claude_*"))
                  if d.is_dir()]                                                            # 新版：資料夾在、檔案還沒建
        cands += [roaming / "Claude" / "claude_desktop_config.json"]                          # 舊版
    elif sys.platform == "darwin":
        cands += [Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"]
    else:
        cands += [Path.home() / ".config/Claude/claude_desktop_config.json"]
    for p in cands:
        if p.exists():
            return p
    for p in cands:  # 都還沒有檔案：選第一個「資料夾存在」的位置
        if p.parent.exists():
            return p
    return cands[-1]


def server_entry() -> dict:
    py = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return {"command": str(py), "args": ["-m", "wqbka.mcp_server"],
            "env": {"PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8", "HF_HUB_OFFLINE": "1"}}


def main() -> int:
    path = find_config()
    remove, dry = "--remove" in sys.argv, "--dry-run" in sys.argv
    print(f"Claude Desktop 設定檔：{path}")
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else {}
    servers = cfg.setdefault("mcpServers", {})
    for old in LEGACY:
        servers.pop(old, None)
    if remove:
        servers.pop(NAME, None)
    else:
        servers[NAME] = server_entry()
    if dry:
        print(json.dumps({"mcpServers": {NAME: servers.get(NAME)}}, ensure_ascii=False, indent=2))
        return 0
    if path.exists():
        bak = path.with_name(path.name + f".bak-{datetime.now():%Y%m%d%H%M%S}")
        shutil.copy2(path, bak)
        print(f"已備份原設定：{bak.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("已移除 " if remove else "已加入 ") + NAME + "（其他設定保持不變）")
    print("請在系統匣的 Claude 圖示按右鍵 →「Quit」，再重新打開 Claude Desktop。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
