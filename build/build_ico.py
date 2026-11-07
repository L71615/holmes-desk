# -*- coding: utf-8 -*-
"""
生成 Windows 资源管理器能正确显示的 .ico。

Pillow 直接存 ico 会把每一帧都写成 PNG 压缩，部分 Windows 版本的图标提取器
对小尺寸 PNG 帧不认，桌面图标就退化成白纸。这里 <=128 的帧用经典 BMP(DIB)
格式写，只有 256 用 PNG —— 与主流 .ico 一致。
"""
import io
import struct
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "judgedee" / "assets"


def dib_bytes(img: Image.Image) -> bytes:
    """32bpp BGRA，行序自下而上，后接 1bpp AND 掩码。"""
    w, h = img.size
    px = img.convert("RGBA")
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b, a = px.getpixel((x, y))
            row += bytes((b, g, r, a))
        rows.append(bytes(row))
    bitmap = b"".join(rows)
    mask_row_len = ((w + 31) // 32) * 4
    mask = bytes(mask_row_len * h)          # 全 0 = 全部不透明
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0,
                         len(bitmap) + len(mask), 0, 0, 0, 0)
    return header + bitmap + mask


def write_ico(src_png: Path, out_ico: Path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    base = Image.open(src_png).convert("RGBA")
    frames = []
    for s in sizes:
        frames.append((s, base.resize((s, s), Image.LANCZOS)))

    entries, blob, offset = [], b"", 6 + 16 * len(frames)
    for s, img in frames:
        if s >= 256:
            buf = io.BytesIO()
            img.save(buf, "PNG")
            data = buf.getvalue()
        else:
            data = dib_bytes(img)
        entries.append(struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32,
                                   len(data), offset))
        blob += data
        offset += len(data)

    with open(out_ico, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(frames)))
        fh.write(b"".join(entries))
        fh.write(blob)
    print("wrote", out_ico, out_ico.stat().st_size, "bytes", sizes)


if __name__ == "__main__":
    # 以仓库里现成的 256 帧为源，重写一份「BMP 帧 + 256 PNG」的 ico
    ico = ASSETS / "judgedee-app.ico"
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ico
    base = Image.open(ico)
    base.size = (256, 256)
    tmp = HERE / "_icon_src.png"
    base.convert("RGBA").save(tmp)
    write_ico(tmp, out)
    tmp.unlink()
