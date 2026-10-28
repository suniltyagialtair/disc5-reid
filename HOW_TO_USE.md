# Re-ID — How to Use (Quick Start)

*One page. The full reference is the **Re-ID User Manual**; administrators should also read the **Administrator Security Note** ([DISC5_ReID_Admin_Security_Note_protected.pdf](DISC5_ReID_Admin_Security_Note_protected.pdf)). Password-protected; ask the maintainers for the password.*

## 1. Install (once)

1. Verify the download: `CertUtil -hashfile Re-ID.zip SHA256` — the value must match `SHA256SUMS.txt` from the release.
2. Extract to a **writable** folder, e.g. `C:\DISC5\Re-ID\` — never inside `C:\Program Files\`.
3. Double-click `disc5_gui.exe`. If SmartScreen objects: **More info → Run anyway**. The application opens in its own window — no browser, no console.
4. On first run, create the **Admin** account. The Admin then creates Analyst and Operator accounts from the **Users** tab. Sign in with your own name — the activity log records what is done under it.

## 2. Enrol vessels (build the gallery)

*Analyst or Admin.* **Enrol vessel** tab → choose a source:

- **Upload files** — pick one or more WAV recordings (up to 200 MB each), or
- **Load from a folder on this machine** — bulk enrolment, no size cap.

Each recording is enrolled under its filename. Optional metadata (source, MMSI, IMO) can be typed or auto-filled from a `*clip_map.csv` sidecar. Enrol several passages per vessel for better recall.

## 3. Identify a contact

*Any role.* **Identify (query)** tab → upload the query WAV → **Identify**.

Two independent result panels appear:

- **SKANN** — ranked candidates by cosine similarity of the acoustic fingerprint (the primary result).
- **LOFAR-tonal** — matched-fraction over detected tonal lines (shown when the sidebar toggle is on; needs tonals that persist ≥ 10 s, so very short clips may show none).

The two scores are on different scales and are never combined. Agreement between them (both ranking a vessel in the top 3) raises confidence.

## 4. Export and review

Download buttons below the results save CSVs (and the labelled tonal listing) — a save dialog asks where. **Gallery** tab lists everything enrolled; **Activity** tab (Admin) shows the full audit trail. Every enrol, delete, query and export is logged.

## 5. Shut down

Close the window. That is the complete shutdown — nothing else is left running.

## Good to know

- WAV only; any sample rate (resampled to 8 kHz internally); minimum usable length ~5 s.
- The interface is reachable **only on this machine**, by design.
- Recognition quality on this system reflects the demonstration configuration; see the User Manual's notes on interpreting scores before drawing operational conclusions.
- If the window fails to open, check `disc5_desktop_log.txt` beside `disc5_gui.exe` and see Manual §17 (Troubleshooting).
