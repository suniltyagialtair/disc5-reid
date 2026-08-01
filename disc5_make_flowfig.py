# disc5_make_flowfig.py
# Regenerates Figure 1 (deployment view) for DISC5_ReID_System_Flow.md and the Re-ID User Manual.
#
# Figures 2 and 3 are produced by Graphviz from F2_fixed.dot and F3_fixed.dot. Figure 1 is drawn here
# instead, because it is a containment diagram -- what sits inside the PC boundary and what does
# not -- and an automatic layout engine scatters it. Hand placement also allows the red X to be
# drawn ON the boundary, which is the one thing Graphviz cannot express.
#
#   python disc5_make_flowfig1.py --outdir figures
#
# Outputs: flow01_deployment.png and flow01_deployment.svg
#
# Every value annotated on the figure is taken from the delivered disc5_gui_engine.py /
# disc5_gui_app.py / run_gui.py. Labels are measured against the renderer and shrunk until they
# fit, and the script refuses to finish quietly if two boxes overlap -- so neither text overflow
# nor collisions can survive an edit to the wording.

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ------------------------------------------------------------------ house style
INK, MUTED, RULE = "#1b2430", "#5b6672", "#c3cbd4"
STORE, RED = "#8c6d3f", "#c0392b"
FILL_IO, FILL_PROC, FILL_ZONE = "#f2f4f7", "#ffffff", "#f8f9fb"

FS_TITLE, FS_SUB, FS_BOX, FS_SMALL, FS_NOTE = 17, 11, 12, 9.5, 9.5
MIN_FS = 6.5
PAD_X, PAD_Y = 0.90, 0.86

FIG_W, FIG_H = 14.0, 8.0
_RECTS, _WARN = [], []


# ------------------------------------------------------------------ text fitting
def _extent(fig, ax, s, fs, weight, ls):
    t = ax.text(0.5, 0.5, s, fontsize=fs, fontweight=weight, ha="center", va="center",
                linespacing=ls)
    bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
    (x0, y0), (x1, y1) = ax.transAxes.inverted().transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
    t.remove()
    return abs(x1 - x0), abs(y1 - y0)


def _fit(fig, ax, s, fs, w, h, weight="normal", ls=1.35, tag=""):
    size = fs
    while size > MIN_FS:
        tw, th = _extent(fig, ax, s, size, weight, ls)
        if tw <= w * PAD_X and th <= h * PAD_Y:
            return size
        size -= 0.25
    _WARN.append(f"  ! does not fit its box: '{(tag or s).splitlines()[0][:34]}' - enlarge the box")
    return MIN_FS


def box(fig, ax, x, y, w, h, title, sub=None, edge=INK, fill=FILL_PROC, lw=1.5,
        fs=FS_BOX, fs_sub=FS_SMALL, align="center"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.016",
                                linewidth=lw, edgecolor=edge, facecolor=fill, zorder=2))
    _RECTS.append((x, y, w, h, title.replace("\n", " ")))
    if sub is None:
        s = _fit(fig, ax, title, fs, w, h, weight="bold", ls=1.3, tag=title)
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=s,
                color=INK, fontweight="bold", zorder=3, linespacing=1.3)
        return
    s1 = _fit(fig, ax, title, fs, w, h * 0.32, weight="bold", ls=1.2, tag=title)
    s2 = _fit(fig, ax, sub, fs_sub, w, h * 0.62, ls=1.38, tag=title + " [sub]")
    _, th = _extent(fig, ax, title, s1, "bold", 1.2)
    _, sh = _extent(fig, ax, sub, s2, "normal", 1.38)
    gap = h * 0.07
    top = y + h / 2 + (th + gap + sh) / 2
    ax.text(x + w / 2, top - th / 2, title, ha="center", va="center", fontsize=s1,
            color=INK, fontweight="bold", zorder=3, linespacing=1.2)
    ax.text(x + w / 2 if align == "center" else x + w * 0.06,
            top - th - gap - sh / 2, sub,
            ha=align, va="center", fontsize=s2, color=MUTED, zorder=3, linespacing=1.38)


def arrow(ax, pts, color=INK, lw=1.6):
    """Orthogonal arrow through an explicit list of points -- no diagonals, no guessing."""
    for a, b in zip(pts, pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, zorder=4,
                solid_capstyle="round")
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=13,
                                 linewidth=lw, color=color, zorder=4, shrinkA=0, shrinkB=0))


def check_overlaps():
    for i in range(len(_RECTS)):
        xi, yi, wi, hi, li = _RECTS[i]
        for j in range(i + 1, len(_RECTS)):
            xj, yj, wj, hj, lj = _RECTS[j]
            ox = min(xi + wi, xj + wj) - max(xi, xj)
            oy = min(yi + hi, yj + hj) - max(yi, yj)
            if ox > 0.004 and oy > 0.004:
                _WARN.append(f"  ! '{li}' overlaps '{lj}'")


# ------------------------------------------------------------------ the figure
def build(outdir, dpi):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # --- caption, above everything -------------------------------------------------
    ax.text(0.5, 0.985, "Figure 1: What runs, and where", ha="center", va="top",
            fontsize=FS_TITLE, color=INK, fontweight="bold")
    ax.text(0.5, 0.935,
            "Everything inside the dashed line sits on one stand-alone Windows PC. "
            "Nothing connects to a network.",
            ha="center", va="top", fontsize=FS_SUB, color=MUTED, style="italic")

    # --- the stand-alone PC --------------------------------------------------------
    ZX, ZY, ZW, ZH = 0.172, 0.165, 0.653, 0.725
    ax.add_patch(FancyBboxPatch((ZX, ZY), ZW, ZH, boxstyle="round,pad=0.004,rounding_size=0.016",
                                linewidth=1.3, edgecolor=RULE, facecolor=FILL_ZONE,
                                linestyle=(0, (5, 4)), zorder=1))
    ax.text(ZX + 0.014, ZY + ZH - 0.028, "Stand-alone Windows PC (NODPAC)",
            ha="left", va="top", fontsize=FS_SMALL, color=MUTED, style="italic", zorder=3)

    box(fig, ax, 0.200, 0.640, 0.140, 0.140, "Operator",
        "signs in with an\nin-app account", fill=FILL_IO, edge=MUTED)
    box(fig, ax, 0.200, 0.400, 0.140, 0.160, "Browser",
        "http://localhost:8520\nthis PC only", fill=FILL_IO, edge=MUTED)
    box(fig, ax, 0.368, 0.345, 0.232, 0.435, "disc5_gui.exe",
        "one self-contained folder\n\n"
        "•  local server on 127.0.0.1:8520\n"
        "•  disc5_gui_auth  — login, roles, log\n"
        "•  disc5_gui_app  — the screens\n"
        "•  disc5_gui_engine  — signal + model\n"
        "•  bundled PyTorch / CUDA runtime",
        edge=INK, lw=2.0, align="left")
    box(fig, ax, 0.368, 0.190, 0.232, 0.088, "disc5_arcface_8k_ft2_ep003.pth",
        "the model — 59,916,269 bytes, never modified",
        fill=FILL_IO, edge=RULE, fs=FS_SMALL, fs_sub=FS_NOTE)
    box(fig, ax, 0.656, 0.345, 0.152, 0.435, "Files it saves",
        "gallery.npz\ngallery_tonal.json\nusers.json\naudit_log.jsonl\n\n"
        "created as you use it,\nkept when you upgrade",
        edge=STORE, fill="#fdfbf7", lw=1.8)

    # --- carried in and out by hand ------------------------------------------------
    box(fig, ax, 0.010, 0.640, 0.145, 0.140, "Recordings in",
        "WAV files\nany sample rate", fill=FILL_IO, edge=MUTED)
    box(fig, ax, 0.010, 0.360, 0.145, 0.165, "What you get out",
        "ranked-result CSV\nspectrogram PNG\nactivity-log CSV", fill=FILL_IO, edge=MUTED)

    # --- no network ----------------------------------------------------------------
    box(fig, ax, 0.856, 0.505, 0.134, 0.115, "No network", fill="#fdf0ef", edge=RED, lw=1.7)

    # --- arrows, all orthogonal ----------------------------------------------------
    arrow(ax, [(0.155, 0.710), (0.200, 0.710)], color=MUTED)              # recordings -> operator
    arrow(ax, [(0.270, 0.640), (0.270, 0.560)], color=MUTED)              # operator  -> browser
    arrow(ax, [(0.340, 0.505), (0.368, 0.505)])                           # browser   -> exe
    arrow(ax, [(0.368, 0.440), (0.340, 0.440)])                           # exe       -> browser
    arrow(ax, [(0.200, 0.443), (0.155, 0.443)], color=MUTED)              # browser   -> outputs
    arrow(ax, [(0.484, 0.278), (0.484, 0.345)], color=MUTED)              # model     -> exe
    arrow(ax, [(0.600, 0.640), (0.656, 0.640)], color=STORE)              # exe       -> files
    arrow(ax, [(0.656, 0.470), (0.600, 0.470)], color=STORE)              # files     -> exe
    ax.text(0.496, 0.3115, "loaded once at start-up", ha="left", va="center",
            fontsize=FS_NOTE, color=MUTED, zorder=5)

    # the X sits ON the boundary -- squared up against the figure's aspect ratio
    cx, cy = ZX + ZW, 0.5625
    dx = 0.0105; dy = dx * (FIG_W / FIG_H)
    ax.plot([cx - dx, cx + dx], [cy - dy, cy + dy], color=RED, lw=3.0, zorder=6,
            solid_capstyle="round")
    ax.plot([cx - dx, cx + dx], [cy + dy, cy - dy], color=RED, lw=3.0, zorder=6,
            solid_capstyle="round")

    # --- note, below everything ----------------------------------------------------
    ax.text(0.5, 0.115,
            "Note: The screen is produced by a small server inside the application and shown in a "
            "browser. The server, the model and all data stay on this machine.",
            ha="center", va="top", fontsize=FS_NOTE, color=MUTED, style="italic")
    ax.text(0.5, 0.068,
            "Nothing connects to a network — no licence check, no usage reporting, no update service.",
            ha="center", va="top", fontsize=FS_NOTE, color=MUTED, style="italic")

    check_overlaps()
    os.makedirs(outdir, exist_ok=True)
    for ext in ("png", "svg"):
        p = os.path.join(outdir, f"flow01_deployment.{ext}")
        fig.savefig(p, dpi=dpi, bbox_inches="tight", facecolor="white")
        print(f"  wrote {p}  ({os.path.getsize(p):,} B)")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Regenerate Figure 1 of the Re-ID system-flow document.")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    print(f"writing Figure 1 to {os.path.abspath(args.outdir)}")
    build(args.outdir, args.dpi)
    print("\n".join(_WARN) if _WARN else "  all labels fit, no boxes overlap")


if __name__ == "__main__":
    main()
