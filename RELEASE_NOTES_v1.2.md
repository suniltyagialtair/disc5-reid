# Re-ID v1.2 — Release Notes

**Release date:** 3 August 2026 · **Repository:** `disc5-reid` · **Supersedes:** v1.0

> **Version ledger.** v1.1 was a code-only milestone: its features were committed to the repository but no v1.1 release or packaged bundle was ever published. For installed systems the upgrade path is therefore **v1.0 → v1.2** directly; this release carries everything since v1.0.

## What's new since v1.0

**Sign-in, roles and an activity log.** Every session starts at a login screen. On a fresh installation, first run creates the initial **Admin** account; the Admin creates all other accounts from the new **Users** tab. Three nested roles — **Operator** (identify, view results and the gallery, export query-scoped CSVs), **Analyst** (adds enrol, delete, clear, gallery-wide exports), **Admin** (adds user administration and the activity log). Every sign-in (including failures and lockouts), account change, enrolment, deletion, query and export is recorded to `audit_log.jsonl` beside the executable; Admins view, filter and export it from the new **Activity** tab.

**Account protections.** New accounts must set their own password at first sign-in; five failed sign-ins lock an account for 5 minutes; idle sessions end after 20 minutes; the last enabled Admin cannot be demoted, disabled or deleted. Passwords are stored scrypt-hashed. The sign-in provides accountability, not a security boundary against physical access — see the *Re-ID Administrator Security Note*.

**Sidecar metadata auto-fill — MMSI and IMO.** At enrolment, both MMSI and IMO now auto-fill from a `*clip_map.csv` sidecar when present; the reader accepts the column aliases `vessel_mmsi`/`mmsi` and `vessel_imo`/`imo`. (Previously only MMSI auto-filled, and only from a `vessel_mmsi` column.) Anything typed in the metadata fields overrides the sidecar.

**Spectrogram view disabled.** The "Show query spectrogram" button no longer renders the LOFAR display (renderer improvement pending); it now points the user to the **Query tonal lines** CSV download, which is the authoritative record of the detected lines. The User Manual (§12) documents CSV-based tonal verification, including a worked speed-change example.

**Interface.** Local-only binding (`127.0.0.1` — unreachable from other machines, by design); development controls removed; Users-tab guidance shortened; bundled `.streamlit` configuration.

The acoustic engine is unchanged: the same frozen checkpoint (`disc5_arcface_8k_ft2_ep003.pth`), the same signal settings, the same scoring. **Results are directly comparable with v1.0.**

## Model checkpoint now a standalone release asset

`disc5_arcface_8k_ft2_ep003.pth` is attached to this release as its own asset. The git tree deliberately contains no model weights, so a source clone is not buildable by itself — download the checkpoint from this release into `_internal\` (source builds: beside the scripts) and verify its SHA-256 against `SHA256SUMS.txt`. The README §2.1 documents this step.

## Upgrading from v1.0 — read before extracting

**Preserve the four state files.** If Re-ID is already installed, copy these files (those that exist) from beside `disc5_gui.exe` to a safe location **before** extracting the new bundle, and copy them back afterwards:

| File | Contents |
|---|---|
| `gallery.npz` | enrolled SKANN fingerprints |
| `gallery_tonal.json` | enrolled tonal lines |
| `users.json` | user accounts (v1.2+) |
| `audit_log.jsonl` | activity history (v1.2+) |

Extracting a new bundle over an installation without this step loses every enrolled vessel. On a v1.0 → v1.2 upgrade only the two gallery files exist; the first launch after upgrading shows the first-run Admin setup.

## Fresh installation

1. Download `Re-ID.zip` and verify: `CertUtil -hashfile Re-ID.zip SHA256` must match the value in `SHA256SUMS.txt`.
2. Extract to a writable folder (e.g. `C:\DISC5\Re-ID\`) — not `C:\Program Files\`.
3. Run `disc5_gui.exe`. If SmartScreen objects: **More info → Run anyway**.
4. Create the Admin account when prompted, then create Analyst/Operator accounts from the **Users** tab.

Full installation, operation and troubleshooting guidance is in the **Re-ID User Manual** attached to this release, which supersedes the v1.0 *Install and Operator Guide*.

## Note on `Re-ID.zip`

As at v1.0, this is a **repackaged slim build** — the identical application with compile-time-only files removed (the `torch/include` C++ headers, `torch/bin`, and `.lib` import libraries; no runtime DLL and no CUDA library is touched). Use the checksum below to identify the canonical copy.

## Release assets

| Asset | SHA-256 | Size |
|---|---|---|
| `Re-ID.zip` | `7f105ef17f526e553cfb590a503dfc8bb631fd833c35be87baa3a80b04c67f98` | 2,128,058,398 B |
| `DISC5_demo_clips_v2.zip` | `db8b15c0277a2ec227b2f32c7e55d5f981639364f55b1a099e0adc1c9adce4ae` | 574,568,962 B |
| `disc5_arcface_8k_ft2_ep003.pth` | `7ae59218bc98c7a30cc361bde5f22e90595eca0adcce929adad13764d41d6b8f` | 59,916,269 B |
| `ReID_User_Manual.pdf` | `a0c48801caf83f1e05abde32fb67c035310b3f4f2f5bb7c8bf2cf2166ef45178` | 28,428,228 B |
| `DISC5_ReID_Admin_Security_Note.pdf` | `d55d6f8ba82125cd4f1f17046a2c8a343e9471e7ed824d3fd6eb917b3d4ef132` | 21,899 B |
| `SHA256SUMS.txt` | — | — |

`DISC5_demo_clips_v2.zip` — the demonstration set for the manual's walkthrough (24 vessels, gallery + query folders, metadata sidecar) — is attached to this release. The ep21 checkpoint remains available on the v1.0 release page.

## Compatibility

- Windows 10/11 x64; NVIDIA GPU with a current driver (`nvidia-smi` must list the card). The bundle ships the cu130 CUDA build, covering RTX 50-series (Blackwell, `sm_120`).
- Galleries built with v1.0 are fully compatible — same model, same embedding space.
- Source builds: `disc5_gui_auth.py` is stdlib-only (no new dependencies); `requirements.txt` is unchanged; the model checkpoint must be downloaded from this release (see above).
