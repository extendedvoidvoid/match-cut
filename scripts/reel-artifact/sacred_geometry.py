"""Full-canvas background: vectorized max-sat smudge + tiled sacred-geometry puzzle."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from render import CANVAS_H, CANVAS_W, PHI

SQRT3 = math.sqrt(3.0)
GRID_COLS = 18
GRID_ROWS = 30
NUM_CELLS = GRID_COLS * GRID_ROWS

BRIGHT_PALETTE: list[tuple[int, int, int]] = [
    (255, 0, 255), (0, 255, 255), (255, 255, 0), (0, 128, 255),
    (255, 0, 128), (0, 255, 128), (255, 128, 0), (128, 0, 255),
    (255, 64, 64), (64, 255, 255), (255, 255, 128), (128, 255, 64),
]


@dataclass(frozen=True)
class GridCell:
    row: int
    col: int
    motif: int  # 0..3


def capacity_at(time_sec: float, total_sec: float) -> float:
    if total_sec <= 0:
        return 1.0
    return min(1.0, max(0.0, time_sec / total_sec))


def _cell_size() -> tuple[float, float]:
    return CANVAS_W / GRID_COLS, CANVAS_H / GRID_ROWS


def _spiral_cell_order() -> list[tuple[int, int]]:
    """Phi-biased center-outward order for puzzle reveal."""
    cr, cc = GRID_ROWS // 2, GRID_COLS // 2
    cells = [(r, c) for r in range(GRID_ROWS) for c in range(GRID_COLS)]
    cells.sort(key=lambda rc: (rc[0] - cr) ** 2 + (rc[1] - cc) ** 2 + (rc[0] * PHI + rc[1]) * 0.01)
    return cells


_SPIRAL_ORDER = _spiral_cell_order()
_CELL_META: list[GridCell] = [
    GridCell(r, c, (i * 7 + r * 3 + c) % 4) for i, (r, c) in enumerate(_SPIRAL_ORDER)
]


def _bright_color(idx: int, cap: float) -> tuple[int, int, int]:
    b, g, r = BRIGHT_PALETTE[idx % len(BRIGHT_PALETTE)]
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[0, 0, 1] = 200.0 + 55.0 * cap
    hsv[0, 0, 2] = min(255.0, 180.0 + 75.0 * cap)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)[0, 0]
    return int(out[0]), int(out[1]), int(out[2])


def _palette_from_boundary(rgb: np.ndarray, head_mask: np.ndarray, n: int = 10) -> np.ndarray:
    edge = head_mask & ~cv2.erode(head_mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    pts = np.argwhere(edge)
    colors = np.array(BRIGHT_PALETTE[:n], dtype=np.uint8)
    if len(pts) == 0:
        return colors
    rng = np.random.default_rng(len(pts))
    picks = pts[rng.choice(len(pts), size=min(n, len(pts)), replace=False)]
    raw = rgb[picks[:, 0], picks[:, 1]].astype(np.float32)
    hsv = cv2.cvtColor(raw.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, 0, 1] = 255.0
    hsv[:, 0, 2] = np.clip(hsv[:, 0, 2] * 1.4, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).reshape(-1, 3)


def vectorized_fragmented_smear(
    outside: np.ndarray,
    palette: np.ndarray,
    seed: int,
    capacity: float,
) -> np.ndarray:
    """100% outside pixels filled — max-sat fragmented mosaic."""
    h, w = CANVAS_H, CANVAS_W
    frag = max(4, int(round(18 - 14 * capacity)))
    sub = max(2, frag // 2)

    rng = np.random.default_rng(seed)
    n_colors = max(1, len(palette))
    color_idx = rng.integers(0, n_colors, size=((h + sub - 1) // sub, (w + sub - 1) // sub))

    yy, xx = np.mgrid[0:h, 0:w]
    cell_y = np.minimum(color_idx.shape[0] - 1, yy // sub)
    cell_x = np.minimum(color_idx.shape[1] - 1, xx // sub)
    smear = palette[color_idx[cell_y, cell_x]].astype(np.uint8)

    # Coarser fragment overlay for early sparse feel, fades as capacity rises
    if capacity < 0.95:
        coarse = max(frag, 8)
        coarse_h = (h + coarse - 1) // coarse
        coarse_w = (w + coarse - 1) // coarse
        coarse_idx = rng.integers(0, n_colors, size=(coarse_h, coarse_w))
        cy2 = np.minimum(coarse_idx.shape[0] - 1, yy // coarse)
        cx2 = np.minimum(coarse_idx.shape[1] - 1, xx // coarse)
        coarse_layer = palette[coarse_idx[cy2, cx2]].astype(np.uint8)
        mix = 1.0 - capacity * 0.85
        smear = np.clip(smear.astype(np.float32) * (1 - mix) + coarse_layer.astype(np.float32) * mix, 0, 255).astype(np.uint8)

    bg = np.zeros((h, w, 3), dtype=np.uint8)
    bg[outside] = smear[outside]

    hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
    hsv[outside, 1] = 255
    hsv[outside, 2] = 255
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _draw_cell_motif(canvas: np.ndarray, cell: GridCell, cap: float, cell_idx: int) -> None:
    cw, ch = _cell_size()
    x0 = int(cell.col * cw)
    y0 = int(cell.row * ch)
    x1 = int(min(CANVAS_W, x0 + cw))
    y1 = int(min(CANVAS_H, y0 + ch))
    if x1 <= x0 or y1 <= y0:
        return

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    rad = min(cw, ch) * (0.22 + 0.18 * cap)
    col = _bright_color(cell_idx, cap)
    col2 = _bright_color(cell_idx + 5, cap)
    thick = max(1, int(1 + 3 * cap))

    if cell.motif == 0:
        cv2.circle(canvas, (int(cx), int(cy)), max(2, int(rad)), col, -1, cv2.LINE_AA)
        cv2.circle(canvas, (int(cx), int(cy)), max(2, int(rad * 0.55)), col2, -1, cv2.LINE_AA)
        cv2.circle(canvas, (int(cx), int(cy)), max(1, int(rad * 0.2)), col, -1, cv2.LINE_AA)
    elif cell.motif == 1:
        for k in range(6):
            a = math.radians(k * 60.0 + cell_idx * 7)
            ox = int(cx + rad * 0.55 * math.cos(a))
            oy = int(cy + rad * 0.55 * math.sin(a))
            cv2.circle(canvas, (ox, oy), max(2, int(rad * 0.35)), col, -1, cv2.LINE_AA)
        cv2.circle(canvas, (int(cx), int(cy)), max(2, int(rad * 0.3)), col2, -1, cv2.LINE_AA)
    elif cell.motif == 2:
        pts = []
        for k in range(6):
            a = math.radians(k * 60.0)
            pts.append((int(cx + rad * math.cos(a)), int(cy + rad * math.sin(a))))
        cv2.fillConvexPoly(canvas, np.array(pts, dtype=np.int32), col)
        cv2.polylines(canvas, [np.array(pts, dtype=np.int32)], True, col2, thick, cv2.LINE_AA)
    else:
        step = rad * (1.0 - 1.0 / PHI)
        for i in (-1, 0, 1):
            cv2.circle(canvas, (int(cx + i * step), int(cy)), max(2, int(rad * 0.4)), col, -1, cv2.LINE_AA)
        cv2.ellipse(
            canvas, (int(cx), int(cy)), (max(2, int(rad)), max(2, int(rad * 0.65))),
            cell_idx * 11 % 180, 0, 360, col2, -1, cv2.LINE_AA,
        )


def _max_density_pass(canvas: np.ndarray, cap: float) -> None:
    """Extra full-canvas tiling when capacity near max."""
    if cap < 0.85:
        return
    cw, ch = _cell_size()
    small = min(cw, ch) * 0.12
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cx = int((col + 0.5) * cw)
            cy = int((row + 0.5) * ch)
            idx = row * GRID_COLS + col
            c = _bright_color(idx + 3, cap)
            cv2.circle(canvas, (cx, cy), max(1, int(small)), c, -1, cv2.LINE_AA)


class PuzzleState:
    """Cumulative geometry — one cell per frame."""

    def __init__(self) -> None:
        self._canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
        self._last_n = 0
        self._density_done = False

    def cells_for_frame(self, frame_index: int) -> int:
        return min(frame_index + 1, NUM_CELLS)

    def render_through(self, frame_index: int, cap: float) -> np.ndarray:
        n = self.cells_for_frame(frame_index)
        while self._last_n < n:
            cell = _CELL_META[self._last_n]
            _draw_cell_motif(self._canvas, cell, cap, self._last_n)
            self._last_n += 1
        if cap >= 0.85 and self._last_n >= NUM_CELLS and not self._density_done:
            _max_density_pass(self._canvas, cap)
            self._density_done = True
        return self._canvas


def render_background_layer(
    face_rgb: np.ndarray,
    head_mask: np.ndarray,
    frame_index: int,
    time_sec: float,
    seed: int,
    total_sec: float,
    puzzle: PuzzleState,
) -> np.ndarray:
    """Opaque full-canvas background; composite head from face_rgb only."""
    outside = ~head_mask
    cap = capacity_at(time_sec, total_sec)

    palette = _palette_from_boundary(face_rgb, head_mask, 12)
    smear = vectorized_fragmented_smear(outside, palette, seed + frame_index, cap)
    geo = puzzle.render_through(frame_index, cap).copy()

    geo_alpha = 0.15 + 0.70 * cap
    bg = smear.astype(np.float32)
    if outside.any():
        g = geo.astype(np.float32)
        for c in range(3):
            ch = bg[:, :, c]
            ch[outside] = (
                ch[outside] * (1.0 - geo_alpha) + g[outside, c] * geo_alpha
            )
            bg[:, :, c] = ch

    if cap >= 0.95:
        hsv = cv2.cvtColor(bg.astype(np.uint8), cv2.COLOR_BGR2HSV)
        hsv[outside, 1] = 255
        hsv[outside, 2] = 255
        bg = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).astype(np.float32)

    out = bg.astype(np.uint8)
    out[head_mask] = face_rgb[head_mask]
    return out


# Legacy entry — face_montage uses render_background_layer directly
def apply_sacred_geometry_smear(
    rgb: np.ndarray,
    head_mask: np.ndarray,
    frame_index: int,
    time_sec: float,
    seed: int,
    *,
    total_frames: int = 921,
    puzzle: PuzzleState | None = None,
    total_sec: float = 60.0,
) -> np.ndarray:
    state = puzzle or PuzzleState()
    return render_background_layer(
        rgb, head_mask, frame_index, time_sec, seed, total_sec, state,
    )