"""Matplotlib styling aligned with the matplotlib-plot-style skill."""

from __future__ import annotations

import matplotlib.pyplot as plt

FIGSIZE = (11, 5)
BAR_COLOR = "#0033cc"
LINE_COLORS = {
    "energy": "#0033cc",
    "dnl": "#0033cc",
    "inl": "#cc0000",
    "sndr": "#0033cc",
    "sfdr": "#cc0000",
    "thd": "#7f3fbf",
    "enob": "#e67300",
    "spectrum": "#0033cc",
}
LINEWIDTH_MAIN = 4.0
LINEWIDTH_SECONDARY = 3.0
GRID_ALPHA = 0.35
TITLE_SIZE = 17
LABEL_SIZE = 13
TICK_SIZE = 10
SPINE_WIDTH = 2.0
GRID_LINEWIDTH = 1.1


def apply_rcparams() -> None:
    """Set global typography once per process."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "Liberation Sans", "DejaVu Sans"]
    plt.rcParams["font.weight"] = "bold"
    plt.rcParams["axes.labelweight"] = "bold"
    plt.rcParams["axes.titleweight"] = "bold"


def apply_style(ax: plt.Axes, *, grid_axis: str | None = None) -> None:
    """Apply consistent axis styling to one axes."""
    if grid_axis is None:
        ax.grid(alpha=GRID_ALPHA, linewidth=GRID_LINEWIDTH)
    else:
        ax.grid(axis=grid_axis, alpha=GRID_ALPHA, linewidth=GRID_LINEWIDTH)
    ax.tick_params(axis="both", labelsize=TICK_SIZE)
    for spine in ax.spines.values():
        spine.set_linewidth(SPINE_WIDTH)
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)


def downsample_stride(length: int) -> int:
    """Stride for long series before plotting."""
    return max(length // 512, 1)
