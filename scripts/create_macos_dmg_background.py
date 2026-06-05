from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path


WIDTH = 640
HEIGHT = 420
BACKGROUND = (246, 248, 250, 255)
ARROW = (72, 86, 104, 255)
ARROW_SHADOW = (0, 0, 0, 28)


def blend_pixel(buffer: bytearray, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    if x < 0 or y < 0 or x >= WIDTH or y >= HEIGHT:
        return
    offset = (y * WIDTH + x) * 4
    r, g, b, a = color
    alpha = a / 255
    inv = 1 - alpha
    buffer[offset] = round(r * alpha + buffer[offset] * inv)
    buffer[offset + 1] = round(g * alpha + buffer[offset + 1] * inv)
    buffer[offset + 2] = round(b * alpha + buffer[offset + 2] * inv)
    buffer[offset + 3] = 255


def draw_rounded_bar(
    buffer: bytearray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    radius: int,
    color: tuple[int, int, int, int],
) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            left = x < x0 + radius
            right = x > x1 - radius
            if left or right:
                center_x = x0 + radius if left else x1 - radius
                center_y = (y0 + y1) // 2
                if (x - center_x) ** 2 + (y - center_y) ** 2 > radius**2:
                    continue
            blend_pixel(buffer, x, y, color)


def point_in_triangle(
    px: int,
    py: int,
    a: tuple[int, int],
    b: tuple[int, int],
    c: tuple[int, int],
) -> bool:
    def sign(p1: tuple[int, int], p2: tuple[int, int], p3: tuple[int, int]) -> int:
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    p = (px, py)
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_negative = d1 < 0 or d2 < 0 or d3 < 0
    has_positive = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_negative and has_positive)


def draw_triangle(
    buffer: bytearray,
    a: tuple[int, int],
    b: tuple[int, int],
    c: tuple[int, int],
    color: tuple[int, int, int, int],
) -> None:
    min_x = min(a[0], b[0], c[0])
    max_x = max(a[0], b[0], c[0])
    min_y = min(a[1], b[1], c[1])
    max_y = max(a[1], b[1], c[1])
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if point_in_triangle(x, y, a, b, c):
                blend_pixel(buffer, x, y, color)


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, pixels: bytearray) -> None:
    raw = bytearray()
    for y in range(HEIGHT):
        raw.append(0)
        start = y * WIDTH * 4
        raw.extend(pixels[start : start + WIDTH * 4])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + png_chunk(b"IEND", b"")
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: create_macos_dmg_background.py OUTPUT_PNG")

    pixels = bytearray(BACKGROUND * (WIDTH * HEIGHT))

    draw_rounded_bar(pixels, 255, 206, 382, 222, 8, ARROW_SHADOW)
    draw_triangle(pixels, (404, 214), (374, 190), (374, 238), ARROW_SHADOW)

    draw_rounded_bar(pixels, 252, 202, 379, 218, 8, ARROW)
    draw_triangle(pixels, (401, 210), (371, 186), (371, 234), ARROW)

    write_png(Path(sys.argv[1]), pixels)


if __name__ == "__main__":
    main()
