# disc5_patch_toolbar_icons_edge.py
# Paints the profile avatar, Copilot "Chat" button, notification badge and stray icons out of
# Edge (white-toolbar) screenshots while preserving the address bar (localhost:8520), the
# rounded field/container outlines, and the trailing "..." menu; geometry is auto-detected
# per file with loud failures on anything unexpected.
#
# Usage:  python disc5_patch_toolbar_icons_edge.py <in_dir> <out_dir>
#         Patches every screenshot_*.png / Capture*.PNG in <in_dir>, writes same-named files
#         to <out_dir>. Tab strip and page content are untouched.
# Deps :  pip install pillow numpy
#
# Method (calibrated on the 2026-08-02 VM Edge set):
#   Zone A - inside the address field: from the end of the "localhost:8520" text to the
#            field's right edge; removes in-field icons (favourites star etc.).
#   Zone B - right of the field up to the "..." dots; removes the avatar (saturated circle,
#            red badge), the Copilot icon + "Chat" label and the remaining buttons.
#   Both zones are filled per-row from a verified icon-free column, so the light-grey
#   rounded outlines (field ~x105-1641, right container) are carried across intact.

import sys, os, glob
import numpy as np
from PIL import Image

DARK = 200          # grey level below which a pixel counts as icon/text ink
SEP = 240           # full-row mean below this marks the toolbar's bottom separator
MARGIN = 10         # px kept clear of text, field edges and the menu dots
MENU_MAX_W = 16     # sanity ceiling for the "..." cluster width
MENU_MAX_PX = 60    # sanity ceiling for its dark-pixel count
GAP = 12            # column gap separating icon clusters


def _clusters(mask_cols):
    xs = np.where(mask_cols)[0]
    if xs.size == 0:
        return []
    out, s, p = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - p > GAP:
            out.append((s, p)); s = x
        p = x
    out.append((s, p))
    return out


def _clean_column(dark, lo, hi):
    """First column in [lo, hi) with zero dark pixels, else None."""
    for x in range(lo, hi):
        if not dark[:, x].any():
            return x
    return None


def patch_one(src, dst):
    a = np.asarray(Image.open(src).convert("RGB")).astype(int)
    h, w, _ = a.shape

    # toolbar top: first row that is white across (nearly) the full width - only the
    # toolbar's top band satisfies this; tab-strip rows carry the tab title, the new-tab
    # "+" and the window buttons and never reach the threshold
    whitefrac = (a[:140].mean(axis=2) > 250).mean(axis=1)
    top = next((y for y in range(5, 130) if whitefrac[y] >= 0.95), None)
    if top is None:
        raise SystemExit(f"{src}: no white toolbar found below the tab strip")

    # toolbar bottom: first row whose full-width mean drops (grey separator / page edge)
    bot = next((y for y in range(top + 20, min(top + 80, h)) if a[y].mean() < SEP), None)
    if bot is None:
        raise SystemExit(f"{src}: toolbar bottom separator not found")

    band = a[top:bot]
    grey = band.mean(axis=2)
    dark = grey < DARK
    cl = _clusters(dark.any(axis=0))
    left = [c for c in cl if c[1] < w / 2]
    right = [c for c in cl if c[0] >= w / 2]
    if not left or not right:
        raise SystemExit(f"{src}: could not split toolbar clusters left/right")

    addr_end = max(c[1] for c in left)          # end of "localhost:8520"
    menu = right[-1]                            # rightmost cluster = "..." dots
    mw, mpx = menu[1] - menu[0] + 1, int(dark[:, menu[0]:menu[1] + 1].sum())
    if mw > MENU_MAX_W or mpx > MENU_MAX_PX:
        raise SystemExit(f"{src}: rightmost cluster w={mw} px={mpx} does not look like the "
                         f"'...' menu - inspect manually")

    # address-field right edge: longest light-grey outline row, run containing addr_end.
    # In-field icons (favourites star, an active-download highlight, ...) can interrupt the
    # outline, so runs separated by small gaps are merged before taking the field extent.
    outline = (grey > DARK) & (grey < 252)
    row_i = int(outline.sum(axis=1).argmax())
    runs = _clusters(outline[row_i])
    merged = [list(runs[0])]
    for r in runs[1:]:
        if r[0] - merged[-1][1] <= 60:      # bridge icon-sized interruptions
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    field = next((r for r in merged if r[0] <= addr_end <= r[1]), None)
    if field is None or field[1] - field[0] < 800:
        raise SystemExit(f"{src}: address-field outline not found (row {row_i + top})")
    field_right = field[1]

    # sanity: the region right of the field must hold the saturated avatar/Copilot pixels
    zb = band[:, field_right + MARGIN:menu[0] - MARGIN]
    if int((zb.max(axis=2) - zb.min(axis=2)).max()) < 100:
        raise SystemExit(f"{src}: no saturated icon right of the field - already patched?")

    out = a.copy()

    # Zone A - inside the address field: per-row fill from an icon-free column so the
    # field's rounded outline is carried across while in-field icons vanish.
    ax0, ax1 = addr_end + MARGIN, field_right - MARGIN
    if ax1 - ax0 < 50:
        raise SystemExit(f"{src}: zone A [{ax0}:{ax1}] implausibly narrow")
    xs = _clean_column(dark, ax0, ax1)
    if xs is None:
        raise SystemExit(f"{src}: no icon-free sample column in zone A [{ax0}:{ax1}]")
    for y in range(top, bot):
        out[y, ax0:ax1] = a[y, xs]
    # ink sweep across the cap seam: an in-field icon can sit flush against the field's
    # right cap (e.g. when Edge shortens the field for a download button); remove dark
    # icon ink there while leaving the light-grey cap outline untouched
    seam = out[top:bot, ax0:field_right + 5]
    sg = seam.mean(axis=2)
    seam[sg < DARK] = 255
    out[top:bot, ax0:field_right + 5] = seam
    print(f"  zone A: paint=[{ax0}:{ax1}] sample_col={xs} + ink sweep to {field_right + 5}")

    # Zone B - field edge to the "..." dots: plain white fill (deliberately removes the
    # right-hand button container along with the avatar and Copilot "Chat" button), then a
    # cleanup sweep that whites out any residual light-grey outline stubs right of the
    # field while leaving the dark menu dots untouched.
    bx0, bx1 = field_right + 5, menu[0] - 2
    if bx1 - bx0 < 50:
        raise SystemExit(f"{src}: zone B [{bx0}:{bx1}] implausibly narrow")
    out[top:bot, bx0:bx1] = 255
    seg = out[top:bot, field_right + 1:w]
    sg = seg.mean(axis=2)
    seg[(sg > DARK) & (sg < 252)] = 255
    out[top:bot, field_right + 1:w] = seg
    print(f"  zone B: paint=[{bx0}:{bx1}] + outline sweep [{field_right + 1}:{w}]")

    Image.fromarray(out.astype(np.uint8)).save(dst)
    print(f"{os.path.basename(src)}: {w}x{h} rows[{top}:{bot}] addr_end={addr_end} "
          f"field_right={field_right} menu={menu} -> {dst}")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: python disc5_patch_toolbar_icons_edge.py <in_dir> <out_dir>")
    in_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(in_dir, "screenshot_*.png")) +
                   glob.glob(os.path.join(in_dir, "Capture*.PNG")))
    if not files:
        raise SystemExit(f"no screenshot_*.png / Capture*.PNG in {in_dir}")
    for p in files:
        patch_one(p, os.path.join(out_dir, os.path.basename(p)))


if __name__ == "__main__":
    main()
