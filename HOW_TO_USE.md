# How to use the DISC5 SKANN GUI

A short operator's guide. This covers running the app and reading its output. It does **not**
cover building or installing it (see `README.md` for that).

## What this tool does
It compares a passive-sonar recording of an unknown contact against a **gallery** of recordings
you have already enrolled, and returns a **ranked shortlist** of which known vessel it most
resembles. Two independent methods are shown side by side:

- **SKANN** — a neural fingerprint (a 512-number summary of the sound). Higher cosine = more alike.
- **LOFAR-tonal** — the established narrowband-line method, shown as a second opinion.

Treat the result as a **ranked shortlist and a second opinion**, not an automatic identification.
The top candidate is the model's best guess, not a verdict. When SKANN and the tonal method both
put the same vessel near the top, that agreement is worth more than either alone.

## Before you start
- The model is **frozen**. Using the tool never changes it. Only the **gallery grows** as you
  enrol recordings.
- **Audio in:** WAV files. Any sample rate and mono or stereo are fine — the app resamples to
  8 kHz mono internally (the same preprocessing the system was measured on). A clip must be at
  least **~5 seconds** long; longer is better (more segments to average over).
- The gallery is saved next to the app (`gallery.npz` and `gallery_tonal.json`) and **persists**
  between sessions.

## Launching
Run from source (from the app folder, on a GPU machine):

```
streamlit run disc5_gui_app.py
```

A console window opens and prints a web address (e.g. `http://localhost:8501`); the app opens in
your browser. Keep the console open while you work — closing it stops the app. The sidebar should
read **`Compute: GPU`**; if it says CPU, the app is using a CPU-only PyTorch (see README — install
the GPU build) and embedding will be very slow.

> Keep the app folder somewhere **writable** (e.g. `D:\GUI-DISC5\`, not `C:\Program Files\`). The
> gallery is saved next to the app; if the folder isn't writable, enrolment appears to run but the
> gallery comes back empty.

*(If you were given a standalone `.exe` instead, double-click `disc5_gui.exe` — same caveat about a
writable folder.)*

## Task 1 — Enrol a vessel (build the gallery)
Open the **➕ Enrol vessel** tab.

1. Choose **Load from a folder on this machine** (point at a folder of WAVs) or **Upload files**.
2. Pick the recordings to enrol. Each is enrolled under its **filename**, so name files clearly
   before enrolling (e.g. `CRATER__passage1.wav`). The `.wav` is dropped from the label.
3. *(Optional)* open **Metadata** and record the source (IARA / NODPAC / ONC / ShipsEar / Other)
   and MMSI / IMO. Source is auto-filled from the filename prefix and MMSI from a `*clip_map.csv`
   sidecar if one sits beside the clips; anything you type overrides. Stored with the entry and
   shown in the Gallery tab and exports.
4. Click **Enrol**.

Tip: **enrol several passages of the same vessel** (different encounters) under the same vessel
name. The tool keeps each passage and, at query time, uses the best-matching one — this is the
single biggest thing you can do to improve recall.

## Task 2 — Identify an unknown contact
Open the **🔎 Identify (query)** tab.

1. Upload the query WAV.
2. Set **Show top N candidates** if you want a longer or shorter shortlist.
3. Click **Identify**.

You get two ranked columns:

- **SKANN** — candidates by embedding cosine.
- **LOFAR-tonal** — candidates by tonal match (only if the tonal toggle in the sidebar is on).

A small "✓ tonal agrees" tag appears when both methods rank the same vessel in their top 3.

### Reading the scores
The colour on each score is a **rough confidence band for display only — not a decision rule**:

| | green (stronger) | amber (weak/uncertain) | grey (low) |
|---|---|---|---|
| **SKANN** cosine | ≥ 0.65 | 0.45 – 0.65 | below 0.45 |
| **tonal** match | ≥ 0.35 | 0.15 – 0.35 | below 0.15 |

The two scales are **not comparable** — SKANN is a cosine of a dense fingerprint; tonal is a
fraction of matched lines. Don't read a SKANN 0.6 as "better" than a tonal 0.4. Compare each
method against its own ranking, and weigh **agreement** between them.

What "good" looks like in practice: a confident hit is a clear top candidate that is well above
the rest of its column **and** echoed by the other method. A flat column (everything similar,
mostly amber/grey) means "no strong match in the gallery" — which is the correct answer when the
contact isn't enrolled.

### See the tonal lines (spectrogram)
Click **🔬 Show query spectrogram**. A window opens with the query's LOFAR spectrogram; the
labelled markers are its most **prominent** narrowband tonals, each in Hz. Use it to eyeball the
contact's narrowband signature. (This is a display view of the strongest lines; it won't always
list exactly the same lines the tonal score uses, which applies a stricter detector.) You can
download the image as PNG or open it full-size in a new tab.

## Managing the gallery
Open the **📋 Gallery** tab to see every enrolled passage — vessel, source, MMSI/IMO, clip length
(s), sample rate (Hz), how many tonal lines, top frequencies, and when it was enrolled.

- **Delete one entry:** pick it in the dropdown and click **Delete this entry**. It is removed
  from both the SKANN and tonal stores.
- **Remove a whole vessel** or **Clear entire gallery:** sidebar → *Manage gallery* (coarse,
  use with care).

## Exporting
- From a query (**⬇ Downloads**): ranked results, the query's 512-d embedding, and the query's
  tonal lines — each as a separate CSV.
- From the Gallery tab: the full tonal gallery (one row per passage, metadata + up to 20
  frequency/strength pairs) and all gallery embeddings.

## Good practice & limits
- **Enrol clean, representative passages** and several per vessel.
- **Same gallery, mixed sources is fine** — you can hold IARA, NODPAC, ONC and ShipsEar entries
  together. Be aware a sparse or very different-sounding gallery makes the top rank look more
  confident than it is (few competitors).
- **It is a shortlisting aid.** On unseen vessels across different encounters, the correct vessel
  is the single top match less than half the time, but is usually within the top few — so review
  the shortlist, don't act on rank 1 alone. Confirm with the tonal second opinion, the
  spectrogram, and your own analysis.
- If a query is shorter than ~5 s after resampling it is rejected — use a longer clip.
