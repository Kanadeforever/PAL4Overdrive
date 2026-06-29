#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PAL4 config.cfg GUI 编辑器

放在 config.cfg 同目录下使用，自动加载/保存二进制配置。
"""

import struct
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
from typing import List, Tuple


# ── 二进制解析引擎（复用自 config_cfg_tool.py） ──────────

def parse_cfg(data: bytes) -> List[Tuple[str, int]]:
    """解析 cfg 二进制。"""
    if len(data) < 16:
        return []

    h = struct.unpack("<IIII", data[0:16])
    claimed_count = h[3]

    entries = []
    pos = 16

    for _ in range(claimed_count):
        if pos + 12 > len(data):
            break

        marker = struct.unpack("<I", data[pos: pos + 4])[0]
        if marker != 1:
            break

        name_len = struct.unpack("<I", data[pos + 4: pos + 8])[0]
        if name_len < 1 or name_len > 100 or pos + 8 + name_len + 4 > len(data):
            break

        name = data[pos + 8: pos + 8 + name_len].decode("ascii", errors="replace")
        value = struct.unpack("<I", data[pos + 8 + name_len: pos + 8 + name_len + 4])[0]
        entries.append((name, value))
        pos = pos + 8 + name_len + 4

    return entries


def build_cfg(entries: List[Tuple[str, int]]) -> bytes:
    """从 [(name, value), ...] 构建 cfg 二进制。"""
    buf = bytearray()
    buf.extend(struct.pack("<IIII", 1, 1, 0, len(entries)))

    for name, value in entries:
        name_bytes = name.encode("ascii")
        buf.extend(b"\x01\x00\x00\x00")                     # marker
        buf.extend(struct.pack("<I", len(name_bytes)))      # name_len
        buf.extend(name_bytes)                               # name
        buf.extend(struct.pack("<I", value))                 # value

    return bytes(buf)


# ── 配置字段定义 ──────────────────────────────────────

FIELDS = [
    ("width",      "宽度", 1280),
    ("height",     "高度", 768),
    ("sync",       "垂直同步", 0),
    ("widescreen", "宽屏", 1),
]

# 0/1 开关字段
BOOL_KEYS = {"sync", "widescreen"}


# ── GUI 主窗口 ────────────────────────────────────────

class ConfigGUI:
    def __init__(self, master: tk.Tk, cfg_path: Path):
        self.master = master
        self.cfg_path = cfg_path
        self.entries: dict[str, tk.Widget] = {}
        self.var_entries: dict[str, tk.StringVar] = {}

        master.title("PAL4配置器")
        master.resizable(False, False)

        # ── 输入区域 ──
        frame = ttk.Frame(master, padding=16)
        frame.pack(fill="both", expand=True)

        for i, (key, label, default) in enumerate(FIELDS):
            ttk.Label(frame, text=f"{label}：", anchor="e", width=16).grid(
                row=i, column=0, sticky="e", padx=(0, 8), pady=4
            )

            var = tk.StringVar()
            self.var_entries[key] = var

            if key in BOOL_KEYS:
                # 0/1 开关用 Spinbox
                w = ttk.Spinbox(frame, from_=0, to=1, textvariable=var, width=10)
            else:
                # 宽/高
                w = ttk.Spinbox(frame, from_=0, to=99999, textvariable=var, width=10)

            w.grid(row=i, column=1, sticky="w", pady=4)
            self.entries[key] = w

        # ── 保存按钮 ──
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(FIELDS), column=0, columnspan=2, pady=(16, 4))

        self.btn_save = ttk.Button(btn_frame, text="保存配置", command=self.on_save)
        self.btn_save.pack(side="left", padx=4)

        ttk.Button(btn_frame, text="退出", command=master.destroy).pack(side="left", padx=4)

        # ── 状态栏 ──
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(master, textvariable=self.status_var, relief="sunken",
                               anchor="w", padding=(8, 2))
        status_bar.pack(fill="x", side="bottom")

        # ── 加载数据 ──
        self.load_data()

        # ── 快捷键 ──
        master.bind("<Control-s>", lambda e: self.on_save())

    # ── 加载 ──

    def load_data(self):
        if not self.cfg_path.is_file():
            # 文件不存在：填入默认值，保存时自动创建
            self.status_var.set(f"⚠ 未找到 {self.cfg_path.name}，保存时将自动创建")
            for key, _, default in FIELDS:
                self.var_entries[key].set(str(default))
            return

        try:
            data = self.cfg_path.read_bytes()
            entries = parse_cfg(data)
            loaded = {k: v for k, v in entries}

            for key, _, default in FIELDS:
                val = loaded.get(key, default)
                self.var_entries[key].set(str(val))

            self.status_var.set(f"已加载 {self.cfg_path.name}（{len(entries)} 项）")
        except Exception as e:
            self.status_var.set(f"✗ 加载失败")
            messagebox.showerror("错误", f"无法解析 config.cfg：\n{e}")

    # ── 保存 ──

    def on_save(self):
        try:
            # 全屏固定为 0，不出现在界面中但写入文件
            entries: List[Tuple[str, int]] = [("fullscreen", 0)]
            for key, _, _ in FIELDS:
                raw = self.var_entries[key].get().strip()
                val = int(raw)
                entries.append((key, val))

            data = build_cfg(entries)
            self.cfg_path.write_bytes(data)
            self.status_var.set(f"✓ 已保存（{len(entries)} 项，{len(data)} 字节）")
        except ValueError as e:
            self.status_var.set("✗ 保存失败：输入格式错误")
            messagebox.showerror("输入错误", "请确保所有字段均为有效整数。")
        except Exception as e:
            self.status_var.set(f"✗ 保存失败")
            messagebox.showerror("错误", f"写入失败：\n{e}")


def main():
    # 脚本+exe所在目录下的 config.cfg
    script_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    cfg_path = script_dir / "config.cfg"

    root = tk.Tk()
    app = ConfigGUI(root, cfg_path)
    root.mainloop()


if __name__ == "__main__":
    main()
