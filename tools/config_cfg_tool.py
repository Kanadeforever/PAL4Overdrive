#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PAL4 config.cfg 编解码工具 v2

config.cfg 是游戏的自定义二进制 KV 存储。
已验证格式 (文件大小 115 字节):
  头部 16B:  01 00 00 00  01 00 00 00  00 00 00 00  条目数(int32)
  每条记录: [标记 4B=01] [name_len 4B] [name] [value 4B]
  name 和 value 之间无填充，value 紧跟 name 末尾

用法:
  python config_cfg_tool.py d <config.cfg>            # 解码为文本
  python config_cfg_tool.py d <config.cfg> -o out.txt # 解码到文件
  python config_cfg_tool.py e <输入.txt> [输出.cfg]    # 编码
  python config_cfg_tool.py i <config.cfg>            # 信息
"""

import struct
import sys
from pathlib import Path
from typing import List, Tuple

# 已知 key 及其默认值
KNOWN_CONFIG = {
    "fullscreen": 0,
    "height": 768,
    "sync": 0,
    "widescreen": 1,
    "width": 1280,
}


def parse_cfg(data: bytes) -> List[Tuple[str, int]]:
    """
    解析 cfg 二进制。
    格式验证:
      16B 头部
      每条: [01 00 00 00] [name_len: LE int32] [name] [value: LE int32]
    """
    if len(data) < 16:
        return []

    h = struct.unpack("<IIII", data[0:16])
    claimed_count = h[3]

    entries = []
    pos = 16

    for _ in range(claimed_count):
        if pos + 12 > len(data):  # marker(4) + name_len(4) + min_val(4) = 12
            break

        # marker: 应为 1
        marker = struct.unpack("<I", data[pos : pos + 4])[0]
        if marker != 1:
            break

        name_len = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        if name_len < 1 or name_len > 100 or pos + 8 + name_len + 4 > len(data):
            break

        name = data[pos + 8 : pos + 8 + name_len].decode("ascii", errors="replace")

        val_off = pos + 8 + name_len
        value = struct.unpack("<I", data[val_off : val_off + 4])[0]

        entries.append((name, value))
        pos = val_off + 4  # 下一个条目的起始

    return entries


def build_cfg(entries: List[Tuple[str, int]]) -> bytes:
    """从 [(name, value), ...] 构建 cfg 二进制。"""
    buf = bytearray()
    buf.extend(struct.pack("<IIII", 1, 1, 0, len(entries)))

    for name, value in entries:
        name_bytes = name.encode("ascii")
        buf.extend(b"\x01\x00\x00\x00")  # marker
        buf.extend(struct.pack("<I", len(name_bytes)))  # name_len
        buf.extend(name_bytes)  # name
        buf.extend(struct.pack("<I", value))  # value (紧跟 name)

    return bytes(buf)


def decode(data: bytes) -> str:
    """解码为可读 INI 文本"""
    entries = parse_cfg(data)

    lines = [
        "; PAL4 config.cfg 解码输出",
        "; 编辑后可用 encode 模式写回",
        "",
        "[config]",
    ]

    found = set()
    for name, val in entries:
        tag = ""
        if name in ("width", "height"):
            tag = f"  # {'宽度' if name == 'width' else '高度'}"
        elif name in ("fullscreen", "sync", "widescreen"):
            tag = "  # 开启" if val else "  # 关闭"
        lines.append(f"{name}={val}{tag}")
        found.add(name)

    # 补全缺失的 key
    for key in KNOWN_CONFIG:
        if key not in found:
            default = KNOWN_CONFIG[key]
            lines.append(f"; {key}={default}  (缺失，将使用默认值)")

    lines.append(f"\n; 共 {len(entries)} 条")
    return "\n".join(lines)


def encode(text: str) -> bytes:
    """从文本编码为 cfg 二进制"""
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("#") or line.startswith("["):
            continue
        if "=" in line:
            key, _, val_str = line.partition("=")
            key = key.strip()
            val_str = val_str.split(";")[0].split("#")[0].strip()
            try:
                val = int(val_str)
                entries.append((key, val))
            except ValueError:
                print(f"  [警告] 无法解析: {key}={val_str}")

    if not entries:
        entries = list(KNOWN_CONFIG.items())

    return build_cfg(entries)


def show_info(data: bytes):
    """显示 cfg 文件信息"""
    print(f"  大小: {len(data)} 字节")
    h = struct.unpack("<IIII", data[0:16])
    print(f"  头部: [{h[0]}, {h[1]}, {h[2]}] | 条目数: {h[3]}")
    print()
    entries = parse_cfg(data)
    print(f"  解析到 {len(entries)} 条:")
    for name, val in entries:
        tag = ""
        if name in ("width", "height"):
            tag = f" ({name})"
        elif val:
            tag = "  [ON]"
        print(f"    {name:12s} = {val}{tag}")


def main():
    cfg_default = (
        Path(__file__).parent.parent.parent
        / "archive"
        / "仙剑4游戏本体(Steam版)"
        / "config.cfg"
    )

    if len(sys.argv) < 2:
        print(__doc__)
        print("\n当前默认 cfg 状态:")
        if cfg_default.exists():
            show_info(cfg_default.read_bytes())
        else:
            print(f"  (未找到: {cfg_default})")
        return

    cmd = sys.argv[1]

    if cmd in ("d", "decode"):
        src = sys.argv[2]
        src_path = Path(src)
        dst = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "-o" else src_path.with_suffix(".txt")
        data = src_path.read_bytes()
        text = decode(data)
        dst.write_text(text, encoding="utf-8")
        print(f"OK: {src} → {dst}")

    elif cmd in ("e", "encode"):
        src = sys.argv[2]
        dst = sys.argv[3] if len(sys.argv) > 3 else "config.cfg"
        text = Path(src).read_text(encoding="utf-8")
        data = encode(text)
        Path(dst).write_bytes(data)
        print(f"OK: {src} → {dst} ({len(data)} 字节)")

    elif cmd in ("i", "info"):
        show_info(Path(sys.argv[2]).read_bytes())

    else:
        print(f"未知命令: {cmd}\n可用: d(ecode), e(ncode), i(nfo)")


if __name__ == "__main__":
    main()
