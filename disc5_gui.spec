# disc5_gui.spec
# PyInstaller spec for the DISC5 SKANN GUI (Windows, onedir recommended for torch+CUDA).
# Build on the GPU VM:   python -m PyInstaller disc5_gui.spec --noconfirm
#
# onedir (not onefile) is deliberate: a onefile exe re-extracts ~2-4 GB of torch+CUDA libs to a
# temp dir on every launch (slow, and can trip AV). onedir unpacks once into dist/disc5_gui/.
#
# 2026-08-11 (v1.3): entrypoint is now run_gui_desktop.py (native pywebview/WebView2 window,
# no browser). console=False — load errors go to disc5_desktop_log.txt beside the exe, not a
# console. pywebview + its .NET bridge (pythonnet/clr_loader) collected. If a folder named
# webview2_fixed\ sits beside this spec at build time (WebView2 Fixed Version runtime, staged
# from G:\My Drive\DISC5\webview2_fixed\), it is bundled whole so the app runs browser-less on
# air-gapped machines with no installed WebView2. Building without it still works (Evergreen
# fallback) — dev convenience only; the release build MUST include it.
#
# 2026-07-28: disc5_gui_auth.py added (login/roles/audit, v1.1). Stdlib-only -- no new
# packages to collect; it rides as a data file beside the app exactly like the engine.
#
# 2026-06-15: matplotlib is now bundled (for the query-spectrogram button). It was previously in
# `excludes` -- that line is removed and matplotlib is added to the collect_all loop, otherwise the
# frozen exe raises ModuleNotFoundError the moment the spectrogram button is pressed.
#
# If the first build errors on a missing import, add it to hiddenimports and rebuild -- that is
# the expected first-build iteration for torch + streamlit, not a design fault.

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("streamlit", "torch", "scipy", "soundfile", "numpy", "matplotlib", "altair",
            "pyarrow", "PIL",
            "webview", "clr_loader", "pythonnet"):   # v1.3: pywebview + .NET bridge
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# our own source files + bundled model weights (read-only, loaded via sys._MEIPASS)
datas += [
    ("disc5_gui_app.py", "."),
    ("disc5_gui_engine.py", "."),
    ("disc5_gui_auth.py", "."),          # 2026-07-28: login/roles/audit module (1A/1B)
    ("disc5_arcface_8k_ft2_ep003.pth", "."),
]

# v1.3: WebView2 Fixed Version runtime (~200 MB). Directory tuple => copied recursively.
if os.path.isdir("webview2_fixed"):
    datas += [("webview2_fixed", "webview2_fixed")]
else:
    print("WARNING: webview2_fixed\\ not found beside the spec — building WITHOUT the bundled "
          "WebView2 runtime (Evergreen fallback only). Do NOT ship this build to NODPAC.")

hiddenimports += collect_submodules("streamlit")
hiddenimports += ["disc5_gui_engine", "disc5_gui_app", "disc5_gui_auth",
                  "scipy.signal", "scipy.special", "soundfile",
                  "matplotlib.backends.backend_agg",
                  "streamlit.web.cli", "streamlit.runtime.scriptrunner.magic_funcs",
                  # v1.3: pywebview Windows backend
                  "webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]

block_cipher = None

a = Analysis(
    ["run_gui_desktop.py"],              # v1.3: was run_gui.py
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "tests"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="disc5_gui",
    console=False,           # v1.3: no console window; errors -> disc5_desktop_log.txt
    disable_windowed_traceback=False,
    icon="disc5_reid.ico" if os.path.isfile("disc5_reid.ico") else None,  # v1.3: own icon if present
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="disc5_gui",
)
