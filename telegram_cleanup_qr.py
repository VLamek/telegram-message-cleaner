from __future__ import annotations

import tkinter as tk

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def build_qr_matrix(data: str) -> list[list[bool]]:
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    return [[bool(cell) for cell in row] for row in matrix]


def create_qr_photoimage(data: str, scale: int = 6) -> tk.PhotoImage:
    matrix = build_qr_matrix(data)
    size = len(matrix)
    image = tk.PhotoImage(width=size, height=size)

    for y, row in enumerate(matrix):
        colors = " ".join("#000000" if cell else "#ffffff" for cell in row)
        image.put("{" + colors + "}", to=(0, y))

    return image.zoom(max(1, scale), max(1, scale))
