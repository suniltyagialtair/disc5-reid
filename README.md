# DISC5 SKANN Vessel Re-Identification — GUI

Re-identifies vessels from passive-sonar recordings using the **SKANN ft#2 backbone**
(frozen weights, growing gallery). The incumbent **LOFAR-tonal** method is shown as an
independent second opinion alongside SKANN. Runs as a local Streamlit web app.

> **Companion repository:** training data, methodology, and the full technical documentation (`DISC5_SKANN_Technical_Documentation.md`) are in [`disc5-training`](https://github.com/suniltyagialtair/disc5-training) (under construction).

---

## Quick start — run from source (recommended)

You need **Python 3.11–3.13** (3.14 has no GPU torch wheel yet) and an **NVIDIA GPU**. CPU
works but is impractically slow (minutes per 5 s segment — the 8191-tap filterbank), so a GPU
is strongly advised.

> **Air-gapped install (NODPAC):** do **not** run the `pip install` commands below — they need
> the internet. Use the offline bundle's `install_offline.bat`, which installs the same cu130
> wheels from the local `wheels\` folder with no network. The steps below are the online
> run-from-source path for a development / build machine.

**1. Install a GPU build of PyTorch FIRST** (not from requirements.txt — see note below):

```
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130
```

`cu130` carries the `sm_120` kernels the **Blackwell RTX 50-series** (including the RTX 5060 Ti)
requires, and is now the default CUDA build on PyPI. Use `cu126` **only** for older
(≤Hopper — RTX 40-series and earlier) cards on older drivers: `cu126` does **not** contain
Blackwell `sm_120` kernels, so on a 50-series card it silently falls back to CPU. (cu128 has
been removed from PyTorch's matrix — pin cu130.)

**2. Install the rest:**

```
pip install -r requirements.txt
```

**3. Verify torch sees the GPU** (must print `True`):

```
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

On a Blackwell card also confirm the build carries `sm_120`:

```
python -c "import torch; print(torch.cuda.get_arch_list())"
```

`cuda.is_available()` being `True` is *not* proof kernels run — the arch list must contain
`sm_120`. If it doesn't, you installed a non-cu130 wheel (redo step 1).

**4. Run the app** from this folder (so it finds the checkpoint and can write the gallery):

```
streamlit run disc5_gui_app.py
```

It opens in your browser at the address the console prints (e.g. `http://localhost:8501`).
The sidebar should read **`Compute: GPU (<your card>)`** — if it says CPU, torch isn't the
GPU build (redo step 1) or has no CUDA-capable device.

### Two things that will bite if skipped
- **Run from a writable folder.** The gallery (`gallery.npz`, `gallery_tonal.json`) is written
  next to `disc5_gui_app.py`. If the folder isn't writable, enrolment appears to run but the
  gallery comes back empty (the save fails silently). Keep this folder on a normal drive
  (e.g. `D:\GUI-DISC5\`), not under `C:\Program Files\`.
- **Visual C++ runtime.** If `import torch` throws a `c10.dll` / `WinError 1114`, install the
  **Microsoft Visual C++ x64 Redistributable** (https://aka.ms/vs/17/release/vc_redist.x64.exe),
  reboot, retry. On a bare Windows 11 machine this is a hard prerequisite, not optional.

The checkpoint `disc5_arcface_8k_ft2_ep003.pth` ships in this folder and is loaded automatically.

---

## What it does
- **Enrol** a vessel: load WAV recordings (folder or browser upload) → the app computes a 512-d
  SKANN embedding and adds it to a persistent gallery, plus the recording's top-20 LOFAR tonal
  lines. The model never retrains; only the gallery grows. Each recording is enrolled under its
  **filename**; a vessel may hold **several passages** — enrol more than one for better recall.
  - Optional **Metadata** per entry (expander): source (IARA / NODPAC / ONC / ShipsEar / Other)
    and MMSI / IMO. Source is auto-filled from the filename prefix and MMSI from a `*clip_map.csv`
    sidecar if present; what you type overrides. Shown in the Gallery tab and exports.
- **Identify** a query WAV: ranked candidates by SKANN cosine, plus a parallel LOFAR-tonal list.
  Where both rank a vessel in the top 3 it's flagged as agreement (never fused).
  - **Show query spectrogram** → a separate window with the query's LOFAR spectrogram
    (median-whitened, magma) and its most **prominent** tonal lines labelled in Hz. This is a
    **display** view (prominence-picked), distinct from the TPSW line set that drives the score.
- **Gallery** tab: read-only table of every enrolled passage (vessel, source, MMSI/IMO,
  length (s), sample rate (Hz), tonal-line count, top frequencies, enrol time), and **delete any
  single entry** (removes it from both the SKANN and tonal stores).
- **Export** to CSV: ranked results, query embedding (512-d), query tonal lines, gallery tonal
  lines (wide), and gallery embeddings.

## Files
| file | role |
|---|---|
| `disc5_gui_app.py` | Streamlit UI (enrol / identify / gallery / export) |
| `disc5_gui_engine.py` | model, 8 kHz preprocessing, gallery store, SKANN + TPSW tonal scoring |
| `requirements.txt` | Python deps (torch installed separately — see Quick start) |
| `disc5_arcface_8k_ft2_ep003.pth` | the ft#2 checkpoint (loaded automatically from this folder) |
| `run_gui.py`, `disc5_gui.spec`, `build_gui.bat` | **only** for building a standalone .exe; ignore for run-from-source |

## Settings
- **Inference batch size** (sidebar): default **4**. Raise for speed if VRAM allows.
- **Show LOFAR-tonal column**: toggle the second-opinion panel.

## Design notes (important)
- **8 kHz is fixed.** Inputs are resampled to 8 kHz mono, cut into 5 s (40000-sample) segments,
  z-normalised — identical to the evaluation pipeline. Other rates silently desync scores.
- **TPSW tonal whitener** (win 8 Hz, guard 1.5 Hz, alpha 3.0) — same whitener as the scoring
  harness, so the tonal column reproduces the banked benchmark numbers.
- **Per-passage gallery.** A vessel holds several passages; a query scores against every passage
  and reports the best per vessel. Delete is per-passage in the Gallery tab.
- **The ft#2 head does not ship.** Inference uses only the backbone + gallery cosine; the training
  head (incl. ONC class rows) is ignored at load. Swap engines by pointing `CKPT_NAME` at another
  checkpoint (e.g. ep21) — no code change.
- **SKANN and tonal are never fused** — shown side by side as independent opinions (fixed fusion
  was measured to hurt under speed/Doppler). Agreement is surfaced, not combined.

---

## Building a standalone .exe (optional — not needed to run)
Only if you want a double-click bundle instead of `streamlit run`. Build on a GPU machine with a
cu130 environment:
1. Install GPU torch (`pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130`),
   then `pip install -r requirements.txt` and `pip install pyinstaller`.
2. `python -m PyInstaller disc5_gui.spec --noconfirm`
3. Launch `dist\disc5_gui\disc5_gui.exe` (onedir; console shows the localhost URL).
4. **Run the exe from a writable folder** (same gallery-save caveat as above), and confirm the
   sidebar reads `Compute: GPU`. With the cu130 torch wheel the CUDA libraries live in
   `dist\disc5_gui\_internal\torch\lib\` (look for `c10_cuda.dll`, `cudart64_13.dll`,
   `cublas64_13.dll`), **not** an `_internal\nvidia` folder — absence of that folder is normal
   and not a sign of a CPU build.

### Tonal gallery note (builds before 2026-06-15)
The tonal whitener changed from a percentile background to **TPSW**. If carrying over an old
`gallery_tonal.json`, clear and re-enrol the tonal gallery once so fingerprints reproduce the
benchmark scores. The SKANN `gallery.npz` is unaffected.
