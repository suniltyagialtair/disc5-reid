# Re-ID v1.1 — Release Notes

**Release date:** TBD-AT-PACKAGING · **Repository:** `disc5-reid` · **Supersedes:** v1.0

## What's new

v1.1 adds **sign-in, roles and an activity log** to the Re-ID application. The acoustic engine is unchanged: the same frozen checkpoint (`disc5_arcface_8k_ft2_ep003.pth`), the same signal settings, the same scoring. Results are directly comparable with v1.0.

- **Sign-in** — every session starts at a login screen. On a fresh installation, first run creates the initial **Admin** account; the Admin creates all other accounts from the new **Users** tab. There is no self-signup.
- **Three nested roles** — **Operator** (identify, view results and the gallery, export query-scoped CSVs), **Analyst** (adds enrol, delete, clear, gallery-wide exports), **Admin** (adds user administration and the activity log). Each role includes everything below it.
- **Activity log** — every sign-in (including failures and lockouts), account change, enrolment, deletion, query and export is recorded to `audit_log.jsonl` beside the executable, with timestamp, user, role, action and outcome. Admins view, filter and export it from the new **Activity** tab.
- **Account protections** — new accounts must set their own password at first sign-in; five failed sign-ins lock an account for 5 minutes; idle sessions end after 20 minutes; the last enabled Admin cannot be demoted, disabled or deleted.
- **Local-only interface** — the application now binds to `127.0.0.1` and is not reachable from other machines on the network, by design.
- **Cleaner interface** — development controls (file-change prompts, Deploy toolbar) no longer appear.

The sign-in puts a name against every action and prevents accidental gallery damage; it is not a security boundary against someone with physical access to the PC (see the User Manual, §8). Passwords are stored scrypt-hashed.

## Upgrading from v1.0 — read before extracting

**Preserve the four state files.** If Re-ID is already installed, copy these files (those that exist) from beside `disc5_gui.exe` to a safe location **before** extracting the new bundle, and copy them back afterwards:

| File | Contents |
|---|---|
| `gallery.npz` | enrolled SKANN fingerprints |
| `gallery_tonal.json` | enrolled tonal lines |
| `users.json` | user accounts (v1.1+) |
| `audit_log.jsonl` | activity history (v1.1+) |

Extracting a new bundle over an installation without this step loses every enrolled vessel and (from v1.1 onward) every account. On a v1.0 → v1.1 upgrade only the two gallery files exist; the first launch after upgrading shows the first-run Admin setup.

## Fresh installation

1. Download `Re-ID.zip` and verify: `CertUtil -hashfile Re-ID.zip SHA256` must match the value in `SHA256SUMS.txt`.
2. Extract to a writable folder (e.g. `C:\DISC5\Re-ID\`) — not `C:\Program Files\`.
3. Run `disc5_gui.exe`. If SmartScreen objects: **More info → Run anyway**.
4. Create the Admin account when prompted, then create Analyst/Operator accounts from the **Users** tab.

Full installation, operation and troubleshooting guidance is in the **Re-ID User Manual** attached to this release, which supersedes the v1.0 *Install and Operator Guide*.

## Release assets

| Asset | SHA-256 | Size |
|---|---|---|
| `Re-ID.zip` | TBD-AT-PACKAGING | TBD |
| `ReID_User_Manual.pdf` | TBD-AT-PACKAGING | TBD |
| `SHA256SUMS.txt` | — | — |

`DISC5_demo_clips.zip` and the ep21 checkpoint are unchanged from v1.0 and remain available on the v1.0 release page.

## Compatibility

- Windows 10/11 x64; NVIDIA GPU with a current driver (`nvidia-smi` must list the card). The bundle ships the cu130 CUDA build, covering RTX 50-series (Blackwell, `sm_120`).
- Galleries built with v1.0 are fully compatible — same model, same embedding space.
- Source builds: `disc5_gui_auth.py` is a new module (stdlib-only, no new dependencies); `requirements.txt` is unchanged.
