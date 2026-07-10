# disc5_gui.spec
# PyInstaller spec for the DISC5 SKANN GUI (Windows, onedir recommended for torch+CUDA).
# Build on the GPU VM:   python -m PyInstaller disc5_gui.spec --noconfirm
#
# onedir (not onefile) is deliberate: a onefile exe re-extracts ~2-4 GB of torch+CUDA libs to a
# temp dir on every launch (slow, and can trip AV). onedir unpacks once into dist/disc5_gui/.
#
# 2026-06-15: matplotlib is now bundled (for the query-spectrogram button). It was previously in
# `excludes` -- that line is removed and matplotlib is added to the collect_all loop, otherwise the
# frozen exe raises ModuleNotFoundError the moment the spectrogram button is pressed.
#
# If the first build errors on a missing import, add it to hiddenimports and rebuild -- that is
# the expected first-build iteration for torch + streamlit, not a design fault.

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("streamlit", "torch", "scipy", "soundfile", "numpy", "matplotlib", "altair", "pyarrow", "PIL"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# our own source files + bundled model weights (read-only, loaded via sys._MEIPASS)
datas += [
    ("disc5_gui_app.py", "."),
    ("disc5_gui_engine.py", "."),
    ("disc5_arcface_8k_ft2_ep003.pth", "."),
]

hiddenimports += collect_submodules("streamlit")
hiddenimports += ["disc5_gui_engine", "disc5_gui_app",
                  "scipy.signal", "scipy.special", "soundfile",
                  "matplotlib.backends.backend_agg",
                  "streamlit.web.cli", "streamlit.runtime.scriptrunner.magic_funcs"]

block_cipher = None

a = Analysis(
    ["run_gui.py"],
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
    console=True,            # keep console: shows the Streamlit URL + any load errors
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="disc5_gui",
)
