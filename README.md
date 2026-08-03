# disc5-reid — SKANN Vessel Re-Identification (enrolment & inference)

The delivered DISC5 acoustic vessel re-identification application: a **frozen** neural fingerprint model plus a growing gallery, run as a local desktop app. Given a passive-sonar recording of an unknown contact, it returns a ranked shortlist of the most similar enrolled vessels, with the incumbent LOFAR-tonal method shown alongside as an independent second opinion.

The delivered model is the **ft2** checkpoint `disc5_arcface_8k_ft2_ep003.pth`. At inference only the backbone runs; the training classification head is discarded.

> **Companion repository:** how the model was trained — data, preprocessing, augmentation, architecture and training methodology — is documented in **`disc5-training`**. This README covers only running, enrolling and identifying.

---

## 1. System overview

### 1.1 What the system does
DISC5 **re-identifies individual vessels** from passive-sonar recordings. Given a recording of an unknown contact, it produces a compact acoustic **fingerprint** and matches it against a **gallery** of previously enrolled vessels, returning a ranked shortlist of the most similar known hulls.

This is **re-identification**, not classification:

- The task is to identify the *individual hull* (which specific ship), not the *type* (cargo / tanker / ferry). It must separate two different cargo ships, not merely label both "cargo."
- It is **open-set**: the answer is "matched vessel X" or "not in the database." Architecturally it is the same family of problem as speaker or face verification.
- The model has **frozen weights**; only the **gallery grows** as new vessels are enrolled. Enrolling a new hull is a single forward pass — no retraining, no new class.

### 1.2 The two methods shown side by side
Every query is scored by two independent methods, presented in parallel:

- **SKANN** — a learned neural fingerprint: a 512-number embedding of the sound. Similarity is cosine (higher = more alike).
- **LOFAR-tonal** — the established narrowband-line method (the incumbent workflow), shown as a second opinion. Similarity is the fraction of matched tonal lines.

The two are **never fused into a single number.** They are shown together; agreement between them (both ranking the same vessel near the top) is surfaced but not combined, because a fixed fusion was measured to *hurt* under speed/Doppler. The two scales are not comparable to each other — each is read against its own ranking.

### 1.3 Relationship to the incumbent NODPAC workflow
The current NODPAC procedure is manual: separate a target by bearing, export a WAV, run LOFAR and DEMON analysis in the Signature Analyser, hand-place harmonic markers, write tonal values to CSV, and run a similarity search against the LOFAR database (LDBMS). SKANN automates the fingerprinting and matching step: instead of an analyst reading and transcribing narrowband lines by eye, the network computes a fingerprint directly from the waveform, and matching is a cosine comparison against the gallery. The LOFAR-tonal column preserves the familiar line-based view as an independent cross-check.

---

## 2. Getting the application — two delivery paths

The application is delivered two ways. Which one you use depends on whether the machine has a Python toolchain.

### 2.1 Run from source (developers)
For a machine with Python — development, rebuilding, or running against the repo directly.

> **The trained model is not stored in the git tree.** A bare clone is not runnable or buildable by itself. Download `disc5_arcface_8k_ft2_ep003.pth` from the latest release's assets into the repository root (packaged rebuilds: into `_internal\`), and verify it before use: `CertUtil -hashfile disc5_arcface_8k_ft2_ep003.pth SHA256` must match the value in `SHA256SUMS.txt`.

```
git clone <owner>/disc5-reid
cd disc5-reid
# download disc5_arcface_8k_ft2_ep003.pth from the latest release assets (see note above)
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130   # Blackwell; see §6
pip install -r requirements.txt
streamlit run disc5_gui_app.py
```

### 2.2 Packaged bundle — `Re-ID.zip` (operators, no Python)
For an operator machine (e.g. the NODPAC PC) with **no Python and no internet** — a self-contained Windows bundle. It is attached to the GitHub **Release** for this repository as `Re-ID.zip`.

1. **Download** `Re-ID.zip` from the Releases page.
2. **Verify** the download transferred intact (it is ~2 GB — worth checking after any Teams/USB copy). In PowerShell:
   ```
   CertUtil -hashfile Re-ID.zip SHA256
   ```
   The value must match the SHA-256 published in the release notes (`SHA256SUMS.txt`).

3. **Extract** to an empty, **writable** folder — not inside `C:\Program Files\` (see §5). Right-click → Extract All → e.g. `C:\DISC5\Re-ID`. After extraction that folder contains `disc5_gui.exe` and an `_internal` folder.
4. **Run** `disc5_gui.exe`. A console window opens (keep it open — closing it stops the app) and the interface opens in the default browser.
5. **First run — create the Admin account.** On a fresh installation the app asks for a single **Admin** username and password before anything else. The Admin then creates Analyst and Operator accounts from the **Users** tab (see §3.1). Accounts and the activity log are stored beside the executable (`users.json`, `audit_log.jsonl`).

> `Re-ID.zip` is a **repackaged slim build**: the exact same application, with compile-time-only files removed (the `torch/include` C++ headers, `torch/bin`, and `.lib` import libraries — none of which a running application loads). It is therefore a *different artifact*, with a different size and checksum, from any earlier full bundle that may have been shared directly. Both run identically; use the checksum in the release notes to identify the canonical copy.

---

## 3. Using the application

### 3.1 Sign-in, roles and the activity log (v1.1)

Every session starts at a sign-in screen. Three roles, strictly nested — each includes everything below it:

| Role | Adds |
|---|---|
| **Operator** | Identify, view ranked results and the spectrogram, read the Gallery tab, export **query-scoped** CSVs (ranked results, query embedding, query tonal lines) |
| **Analyst** | Enrol; delete passages/vessels; clear the gallery; **gallery-wide** exports |
| **Admin** | **Users** tab (create/reset/disable/delete accounts, change roles); **Activity** tab (view/filter/export the audit log) |

Operational notes:

- **Accounts are created by the Admin only** — there is no self-signup. New accounts must set their own password at first sign-in, so no one (including the Admin) knows another user's working password.
- **Activity log** — every sign-in (including failures and lockouts), enrolment, deletion, query and export is appended to `audit_log.jsonl` with timestamp, user, role, action and outcome. Five failed sign-ins lock an account for 5 minutes. Idle sessions end after 20 minutes.
- **What the login is — and is not.** The sign-in puts a *name* against every action and prevents accidental gallery damage by non-Analysts. It is **not** a security boundary against someone with access to the PC: anyone at the machine can delete `users.json` (which returns the app to first-run setup; the gallery is untouched). Control of the PC itself remains the real access control. Passwords are scrypt-hashed so one user cannot read another's password from the file.
- The last enabled Admin cannot be demoted, disabled or deleted — the app refuses, so user administration can never be locked out.

### 3.2 Day-to-day workflow

- **Enrol** a vessel: load WAV recordings (folder or upload) → the app computes the 512-d SKANN fingerprint and the recording's top-20 LOFAR tonal lines and adds them to the gallery. Each recording is enrolled under its **filename**; a vessel may hold **several passages** — enrolling more than one per vessel is the single biggest lever on recall (a query scores against every passage and reports the best per vessel).
- **Identify** a query: ranked candidates by SKANN cosine, in parallel with a LOFAR-tonal list; agreement (both ranking a vessel in the top 3) is tagged.
- **Reading the scores** — the colour is a rough display band, not a decision rule: SKANN cosine ≥ 0.65 (green) / 0.45–0.65 (amber) / < 0.45 (grey); tonal match ≥ 0.35 / 0.15–0.35 / < 0.15. The two scales are **not comparable** to each other — compare each against its own ranking and weigh agreement. A flat column (everything similar, mostly amber/grey) is the correct answer when the contact is not in the gallery.
- **Spectrogram** — the query's LOFAR spectrogram with its most prominent tonal lines labelled in Hz (a display view; the score itself uses a stricter TPSW line set).
- **Export** — ranked results, query embedding, query tonal lines, and the full gallery (tonal lines + embeddings), as CSV.

Application state persists next to the executable in four files: `gallery.npz` (SKANN embeddings + metadata), `gallery_tonal.json` (tonal lines), `users.json` (accounts) and `audit_log.jsonl` (activity log). A freshly extracted bundle starts with an empty gallery and no accounts (first-run setup).

---

## 4. Signal settings (fixed — must match training)

- **8 kHz is fixed.** Inputs are resampled to 8 kHz mono, cut into 5 s / 40 000-sample segments, and z-normalised — identical to the training pipeline. Other rates silently desync the scores.
- **TPSW tonal whitener** (window 8 Hz, guard 1.5 Hz, alpha 3.0) — the same whitener as the scoring harness, so the tonal column reproduces the benchmark numbers.
- **Frozen model, growing gallery** — the model never retrains in the field; enrolment only grows the gallery.
- A clip shorter than ~5 s after resampling is rejected.

---

## 5. Deployment notes that will bite if skipped

- **Upgrading over an existing installation: preserve the four state files.** Before replacing an installed bundle with a new `Re-ID.zip`, copy `users.json`, `audit_log.jsonl`, `gallery.npz` and `gallery_tonal.json` aside and restore them next to the new `disc5_gui.exe`. Extracting a new bundle into the same folder without this loses every account and every enrolled vessel.
- **Local-only by design.** The app serves on `127.0.0.1:8520` — reachable only from the machine it runs on, not from the network. This is deliberate: the sign-in is an accountability control (see §3.1), not a network-security boundary, so the interface is not exposed to other machines.
- **Verify the system clock at installation.** Audit-log timestamps come from the machine's own clock; an air-gapped PC has no time synchronisation and will drift. Check the date/time at install and periodically thereafter.
- **Run from a writable folder** (e.g. `C:\DISC5\Re-ID\`, not `C:\Program Files\`). The gallery is written next to the application; if the folder is not writable, enrolment appears to run but the gallery comes back empty (the save fails silently).
- **GPU is effectively required.** The 8191-tap filterbank is impractically slow on CPU (minutes per segment). The sidebar must read `Compute: GPU`.
- **Blackwell GPUs (RTX 50-series, incl. the RTX 5060 Ti) require the cu130 CUDA build** of PyTorch — it carries the `sm_120` kernels. The packaged bundle already ships the correct cu130 build. If you run from source, a `cu126` build silently falls back to CPU on a 50-series card; `cuda.is_available()` returning `True` is *not* proof kernels run — the arch list must contain `sm_120` (see §6).
- **Visual C++ runtime:** the VC++ runtime DLLs the app needs are bundled inside `Re-ID.zip`. On a bare machine, if `import torch` still fails with a runtime error (e.g. `WinError 1114`), install the Microsoft Visual C++ 2015–2022 x64 Redistributable and retry.

---

## 6. Requirements & environment

The packaged bundle needs none of the below — it is self-contained. This section is for the run-from-source path and for anyone rebuilding.

- **Python 3.12**, Windows x64. (cu130 GPU wheels exist for cp311–cp313; Python 3.14 has none.)
- **PyTorch 2.11.0** (`+cu130`), installed as the GPU build explicitly:
  ```
  pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130
  ```
  Use `cu126` **only** for ≤ Hopper (RTX 40-series and earlier). cu130 is the default CUDA build on PyPI; cu128 has been removed from the matrix.

- **Exact versions shipped in the delivered bundle** (pin these to reproduce it): `torch 2.11.0+cu130`, `streamlit 1.58.0`, `numpy 2.5.0`, `scipy 1.18.0`, `soundfile 0.14.0`, `matplotlib 3.11.0`, `pillow 12.3.0`.

### Verify the GPU build carries Blackwell kernels
```
python -c "import torch; print(torch.__version__); print(torch.cuda.get_arch_list())"
```
Expect `2.11.0+cu130` and a list containing `sm_120`. If `sm_120` is absent you installed a non-cu130 wheel — reinstall torch from the cu130 index.

---

## 7. File manifest

Inside the extracted bundle (or the source repo):

| File | Role |
|---|---|
| `disc5_gui.exe` | The application (packaged bundle) — launcher at the top of the extracted folder |
| `disc5_gui_app.py` | Application UI — enrol / identify / gallery / export (source) |
| `disc5_gui_engine.py` | Model, 8 kHz preprocessing, gallery store, SKANN + TPSW-tonal scoring (source) |
| `disc5_gui_auth.py` | Sign-in, roles (Admin/Analyst/Operator), account store, activity log (source, v1.1) |
| `_internal/disc5_arcface_8k_ft2_ep003.pth` | The frozen ft2 checkpoint (59,916,269 bytes), loaded automatically |
| `_internal/` | Bundled Python runtime, torch (cu130) + CUDA DLLs, dependencies |
| `requirements.txt` | Python dependencies for the source path (torch installed separately) |
| `users.json` · `audit_log.jsonl` | Accounts and activity log — created at first run beside the executable; preserve on upgrade (§5) |

The engine is model-swappable: pointing `CKPT_NAME` at another checkpoint (e.g. the base `ep21`) is a one-line change with no code change.

---

## 8. Calibration

The system ships with a **calibration procedure and score distributions**, not a single fixed threshold — the operating point shifts with hardware, so the threshold is set against local ground truth on the target hardware, without retraining and without sharing data.

---

## Glossary

- **Re-identification** — matching a contact to a specific known individual, open-set ("matched X" or "not in database").
- **LOFAR** — low-frequency narrowband line analysis; the incumbent tonal method.
- **DEMON** — demodulation analysis for blade/shaft rate.
- **TPSW** (Two-Pass Split-Window) — the frequency-domain whitener used by the tonal scorer.
- **Embedding / fingerprint** — the 512-d L2-normalised vector the network produces; identity is nearest-neighbour by cosine over these.
- **Passage** — one recording/encounter of a vessel; a gallery vessel may hold several.

---

*For training data, preprocessing, augmentation, architecture, methodology and evaluation, see the `disc5-training` repository.*
