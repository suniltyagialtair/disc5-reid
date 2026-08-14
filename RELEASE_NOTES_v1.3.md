# Re-ID v1.3 â€” Release Notes

**Release date:** 2026-08-14 Â· **Repository:** `disc5-reid` Â· **Supersedes:** v1.2

## What's new since v1.2

**Native desktop window â€” no browser.** The application now opens in its own desktop window, titled *DISC5 Re-ID*, with its own icon. No web browser is launched, none needs to be installed, and no console window appears. Closing the window shuts the application down cleanly â€” there is no separate console to keep open.

**Self-contained rendering component.** The window's interface is drawn by an embedded rendering component (Microsoft WebView2, Fixed Version) packaged inside `Re-ID.zip` itself. It is a display library, not a browser: it has no address bar, no navigation controls and no network access beyond the application's own local loopback (`127.0.0.1:8520`, unreachable from other machines â€” unchanged from v1.2). Because the component ships inside the bundle, the application runs on machines with no browser and no internet connectivity, with nothing to install system-wide. This accounts for most of the growth in the size of `Re-ID.zip`.

**Exports now ask where to save.** The CSV and image download buttons open a standard Windows save dialog instead of saving silently to a browser's download folder. Every export remains logged.

**Diagnostics log.** Start-up and shutdown events, and any launch error, are written to `disc5_desktop_log.txt` beside `disc5_gui.exe` (there is no console to print them to). The file is plain text and safe to delete.

The acoustic engine, interface layout, sign-in and roles, and all file formats are unchanged: the same frozen checkpoint (`disc5_arcface_8k_ft2_ep003.pth`), the same signal settings, the same scoring, the same `gallery.npz` / `gallery_tonal.json` / `users.json` / `audit_log.jsonl`. **Results are directly comparable with v1.0 and v1.2.**

## Deferred to a future release

Per-segment progress reporting during enrolment and identification. The current progress bar advances per file, so enrolling a single recording shows no intermediate movement; finer-grained reporting requires a processing callback in the engine, which this release deliberately does not modify.

## Upgrading an existing installation â€” read before extracting

*Applies whether the installed version is v1.0 or v1.2; the procedure is the same.*

**There is no installer and no uninstaller.** Re-ID is a portable application: nothing is written to the registry, no Start-menu entries are created, and no admin rights are needed. Installing is extracting the folder; removing is deleting the folder. Because the gallery, accounts and activity log live **inside that folder** beside `disc5_gui.exe`, deleting or overwriting it deletes them too â€” which is why the four files below must be copied out before upgrading and copied back after. The only file outside the folder is a small display cache at `%LOCALAPPDATA%\DISC5_ReID\`, safe to delete at any time.

**Preserve the four state files.** If Re-ID is already installed, copy these files (those that exist) from beside `disc5_gui.exe` to a safe location **before** extracting the new bundle, and copy them back afterwards:

| File | Contents |
|---|---|
| `gallery.npz` | enrolled SKANN fingerprints |
| `gallery_tonal.json` | enrolled tonal lines |
| `users.json` | user accounts |
| `audit_log.jsonl` | activity history |

Extracting a new bundle over an installation without this step loses every enrolled vessel and every account.

## Fresh installation

1. Download `Re-ID.zip.001` and `Re-ID.zip.002` (the application archive is split for GitHub's 2 GiB per-file limit) and rejoin: `cmd /c copy /b Re-ID.zip.001+Re-ID.zip.002 Re-ID.zip`. Then verify: `CertUtil -hashfile Re-ID.zip SHA256` must match the value in `SHA256SUMS.txt` — a matching hash also proves the rejoin was byte-exact.
2. Extract to a writable folder (e.g. `C:\DISC5\Re-ID\`) â€” not `C:\Program Files\`.
3. Run `disc5_gui.exe`. If SmartScreen objects: **More info â†’ Run anyway**. The application window opens directly â€” no browser, no console.
4. Create the Admin account when prompted, then create Analyst/Operator accounts from the **Users** tab.

Full installation, operation and troubleshooting guidance is in the **Re-ID User Manual** attached to this release.

## Note on `Re-ID.zip`

As before, this is a **repackaged slim build** â€” the identical application with compile-time-only files removed (the `torch/include` C++ headers, `torch/bin`, and `.lib` import libraries; no runtime DLL and no CUDA library is touched). The bundled rendering component is included in full. Use the checksum below to identify the canonical copy.

## Release assets

| Asset | SHA-256 | Size |
|---|---|---|
| `Re-ID.zip` (rejoined from `.001`+`.002`) | `5f60bf8fd2b937334ebee58db32c267d0adc1a19163cb4579c5293b8c1e09292` | 2,437,748,936 B |
| `disc5_arcface_8k_ft2_ep003.pth` | `7ae59218bc98c7a30cc361bde5f22e90595eca0adcce929adad13764d41d6b8f` | 59,916,269 B |
| `ReID_User_Manual.pdf` | `0879456d957a5313ef7c61e5bcb637ede7245f74cb64a7ac470f635be222823b` | 28,428,057 B |
| `DISC5_ReID_Admin_Security_Note.pdf` | `203f61e6ef3aff4c0f56db28602040c428b0b779b85d8223a4c86c0e59a0d35b` | 25,350 B |
| `HOW_TO_USE.pdf` | `f4574911fdc71bbd77d6bda06a2e2fe25eaba63695fa9d6fded4fd37f327a6e7` | 24,495 B |
| `SHA256SUMS.txt` | â€” | â€” |

`DISC5_demo_clips_v2.zip` is unchanged and remains available on the v1.2 release page.
