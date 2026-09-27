from __future__ import annotations

import numpy as np

BRAIN_MAP_POSITIONS = {
    "AF7": (-0.50, 0.48),
    "AF8": (0.50, 0.48),
    "TP9": (-0.82, -0.20),
    "TP10": (0.82, -0.20),
}


def interpolate_brain_activity_idw(channel_scores, positions=None, grid_size=140, power=3.0):
    positions = positions or BRAIN_MAP_POSITIONS
    names = [c for c in positions if c in channel_scores]
    pts = np.array([positions[c] for c in names], float)
    vals = np.array([channel_scores[c] for c in names], float)
    xs = np.linspace(-1.05, 1.05, grid_size)
    ys = np.linspace(-1.05, 1.05, grid_size)
    xx, yy = np.meshgrid(xs, ys)
    grid = np.full(xx.shape, np.nan)
    for i in range(grid_size):
        for j in range(grid_size):
            x, y = xx[i, j], yy[i, j]
            if x * x + y * y > 1.0:
                continue
            d = np.sqrt((pts[:, 0] - x) ** 2 + (pts[:, 1] - y) ** 2) + 1e-9
            w = 1.0 / (d ** power)
            grid[i, j] = np.sum(w * vals) / np.sum(w)
    return xs, ys, grid
