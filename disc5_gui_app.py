# disc5_gui_app.py
# DISC5 SKANN vessel re-identification — desktop GUI (Streamlit).
# Workflow: enrol vessel recordings into a growing gallery, then query a recording and see a
# ranked candidate list. SKANN (ft#2 backbone, frozen) is the primary engine; the LOFAR-tonal
# method is shown as a PARALLEL second opinion (never fused — fusion poisons under Doppler).
# Gallery persists in files next to the app. Model weights are bundled (see resource_path).
#
# 2026-06-14  Enrol fix: folder-load + upload modes, lightweight multiselect preview, filename-stem
#             labels, GPU memory release in the enrol loop.
# 2026-06-14b SKANN/tonal panes visually distinct; 5 customisable CSV downloads; result persisted
#             in session_state so download buttons survive reruns.
# 2026-06-15  This update:
#   - Tonal engine now uses the TPSW whitener (engine fix) so the tonal column reproduces the
#     banked benchmark. CLEAR AND RE-ENROL the tonal gallery once after deploying this build.
#   - New "Gallery" tab: inspect every enrolled passage (vessel, source, MMSI/IMO, #segments,
#     tonal lines) and delete ANY single entry (removes from both the SKANN and tonal stores).
#   - Optional metadata at enrol: source (IARA/NODPAC/ONC/ShipsEar/Other) + MMSI/IMO, stored
#     in meta and shown in the inspector / exports. (The store stays per-passage JSON+npz; the CSV
#     is an export, not the store — one row per ship would lose multi-passage recall.)
#   - "Show query spectrogram" button: disabled in v1.2 (renderer pending) - shows a pointer to the tonal-lines CSV download
#
# Run (dev):     streamlit run disc5_gui_app.py
# Frozen .exe:   launched via run_gui.py entrypoint (see disc5_gui.spec)
# Extra dep:     matplotlib  (add to requirements.txt and the PyInstaller spec — see handover notes)
#
# 2026-07-28  Login/roles/audit (1A/1B): local login gate (disc5_gui_auth), two roles —
#             three nested roles — Operator (identify + view + query-scoped exports),
#             Analyst (+ enrol/delete/clear/gallery-wide exports), Admin (+ Users account
#             administration and the Activity audit view). Every login, enrol, delete, query
#             and export is written to audit_log.jsonl beside the exe; accounts in users.json
#             (scrypt). First run bootstraps the Admin.
#
# 2026-06-15b Gallery tab: metadata is a RECORD (source/MMSI/IMO) auto-filled at enrol from the
#             filename prefix + any *clip_map.csv sidecar (was all-null on bulk enrol); operator
#             entry still overrides. Table drops the internal `segs` column, adds clip length (s)
#             and sample rate (Hz, from orig_sr), and points to the embeddings/tonal detail CSVs.
#             Length needs re-enrol to populate on pre-existing rows; sr shows for old rows already.

import os, sys, csv, io, gc, time, base64, datetime, functools
from pathlib import Path
import numpy as np
import streamlit as st

import disc5_gui_engine as E
import disc5_gui_auth as A

APP_TITLE = "DISC5 — SKANN Vessel Re-Identification"
CKPT_NAME = "disc5_arcface_8k_ft2_ep003.pth"
SOURCES = ["(unspecified)", "IARA", "NODPAC", "ONC", "ShipsEar", "Other"]

# --------------------------------------------------------------------------- paths (frozen-safe)
def resource_path(name):
    """Bundled read-only resource (weights): works in dev and inside a PyInstaller onefile."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

def app_dir():
    """Writable dir next to the executable/script — where the gallery files live."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

GALLERY_EMB = os.path.join(app_dir(), "gallery.npz")
GALLERY_TON = os.path.join(app_dir(), "gallery_tonal.json")
CKPT_PATH   = resource_path(CKPT_NAME)

# --------------------------------------------------------------------------- cached singletons
@st.cache_resource(show_spinner="Loading SKANN model (ft#2)…")
def get_engine(batch):
    if not os.path.exists(CKPT_PATH):
        st.error(f"Model file not found: {CKPT_NAME}. It must sit beside the app / be bundled.")
        st.stop()
    return E.SKANNEngine(CKPT_PATH, batch=batch)

def get_gallery():
    return E.Gallery(GALLERY_EMB)

def get_tonal_gallery():
    return E.TonalGallery(GALLERY_TON)

# --------------------------------------------------------------------------- helpers
def _save_upload(uploaded):
    tmp = os.path.join(app_dir(), f"_tmp_{int(time.time()*1000)}_{uploaded.name}")
    with open(tmp, "wb") as f:
        f.write(uploaded.getbuffer())
    return tmp

def _release_gpu():
    """Free per-file CUDA cache + python garbage between enrolments (prevents drift on long runs)."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

def _list_wavs(folder):
    """Sorted list of .wav files in a folder (case-insensitive, top level only)."""
    d = Path(folder)
    if not d.is_dir():
        return None
    return sorted([p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".wav"])

def score_badge(score, lo, hi):
    """Colour a cosine/tonal score: green high, amber mid, grey low (display only, not a decision)."""
    if score >= hi:   return "#1a7f37"
    if score >= lo:   return "#9a6700"
    return "#6e7781"

# ----- metadata auto-fill (the all-null cause was bulk enrol with the record left blank) -------
# Map a filename prefix to a Source tag; explicit operator entry always overrides these.
PREFIX_SOURCE = (("ONC_", "ONC"), ("IARA_", "IARA"), ("NODPAC_", "NODPAC"),
                 ("DC_", "NODPAC"), ("SHIPSEAR_", "ShipsEar"))

@functools.lru_cache(maxsize=128)
def _sidecar_meta(folder):
    """{filename_stem -> {mmsi, imo}} read from any *clip_map.csv in `folder` or its parent.
    Accepts column aliases vessel_mmsi|mmsi and vessel_imo|imo. Cached per folder."""
    out = {}
    for d in (folder, os.path.dirname(folder)):
        if not d or not os.path.isdir(d):
            continue
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith("clip_map.csv"):
                    with open(os.path.join(d, fn), newline="") as fh:
                        for r in csv.DictReader(fh):
                            stem = os.path.splitext((r.get("filename") or "").strip())[0]
                            mm = ((r.get("vessel_mmsi") or r.get("mmsi")) or "").strip()
                            im = ((r.get("vessel_imo") or r.get("imo")) or "").strip()
                            if stem and (mm or im):
                                out.setdefault(stem, {"mmsi": mm, "imo": im})
        except OSError:
            pass
    return out

def derive_metadata(src_path, display_name):
    """Best-effort metadata record {source, mmsi, imo} from the filename prefix + sidecar clip-map.
    Fills only what the operator left blank; never overrides typed values (merge happens in caller)."""
    prov = {}
    up = (display_name or "").upper()
    for pre, tag in PREFIX_SOURCE:
        if up.startswith(pre):
            prov["source"] = tag
            break
    sc = _sidecar_meta(os.path.dirname(os.path.abspath(src_path))).get(display_name)
    if sc:
        if sc.get("mmsi"): prov["mmsi"] = sc["mmsi"]
        if sc.get("imo"):  prov["imo"] = sc["imo"]
    return prov

def enrol_path(eng, gal, tgal, src_path, display_name, show_tonal, extra_meta=None):
    """Embed one recording and add it (+ optional tonal lines) to the gallery under `display_name`.
    The tonal passage key is stored in the SKANN meta so a single passage can later be deleted from
    both stores together. Returns (status, msg): status in {'ok','short','error'}."""
    try:
        emb, osr, nseg = eng.embed_wav(src_path)
        if emb is None:
            return "short", f"{display_name}: too short (<5 s after 8 kHz resample) — skipped."
        tonal_key = f"{display_name}__{int(time.time()*1e6)}"
        dur_s = E.clip_duration_s(src_path)
        meta = dict(file=os.path.basename(src_path), orig_sr=int(osr), n_seg=int(nseg),
                    dur_s=(round(float(dur_s), 2) if dur_s else ""),
                    enrolled=datetime.datetime.now().isoformat(timespec="seconds"),
                    tonal_key=(tonal_key if show_tonal else ""))
        # metadata record: auto-fill from filename/sidecar, then let any typed value override
        prov = derive_metadata(src_path, display_name)
        if extra_meta:
            for k, v in extra_meta.items():
                if v:
                    prov[k] = v
        meta.update({k: v for k, v in prov.items() if v})
        gal.add(display_name, emb, meta)
        if show_tonal:
            lines = E.tonal_lines_from_wav(src_path)
            tgal.add(tonal_key, display_name, lines)
        return "ok", f"{display_name} ({nseg} seg, native {osr} Hz)"
    except Exception as ex:
        return "error", f"{display_name}: {type(ex).__name__}: {ex}"
    finally:
        _release_gpu()

def render_rank_card(r, method, score_prefix, lo, hi, agree_html=""):
    """One ranked candidate card, accent-coloured per method (skann=blue, tonal=teal)."""
    accent = "#1f6feb" if method == "skann" else "#1f9e8f"
    border = f"4px solid {accent}" if r["rank"] == 1 else f"3px solid {accent}55"
    col = score_badge(r["score"], lo, hi)
    st.markdown(
        f'<div class="blockc" style="border-left:{border}">'
        f'<span class="rk">#{r["rank"]}</span> '
        f'<span class="vname">{r["vessel"]}</span>{agree_html}<br>'
        f'<span class="scorep" style="color:{col}">{score_prefix} {r["score"]:.3f}</span></div>',
        unsafe_allow_html=True)

# ---- spectrogram (deck fig_tonal_pair style: median whiten, magma, cyan Hz labels, navy axes) -
def spectrogram_png(wav_path, title):
    """Render the query's LOFAR spectrogram in the 09-Jun deck style (disc5_plot_deck_figures):
    median-whitened, magma, with only the most PROMINENT tonal lines labelled in Hz (cyan + black
    halo) over a tight band bracketing those lines. Display view -- prominence gating avoids the
    'fake line' noise the score's persistence detector produced on a wide axis. Returns PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    NAVY = "#1E2761"

    freqs, times, w_db, lines = E.deck_spectrogram(wav_path)
    nyq = float(freqs[-1])
    if lines:                                          # tight band around the prominent lines (deck-like)
        span = lines[-1] - lines[0]; margin = max(20.0, 0.2 * span)
        lo, hi = max(0.0, lines[0] - margin), min(nyq, lines[-1] + margin)
        if hi - lo < 120:
            mid = 0.5 * (lo + hi); lo, hi = max(0.0, mid - 60), min(nyq, mid + 60)
    else:
        lo, hi = 0.0, 500.0
    band = (freqs >= lo) & (freqs <= hi)

    fig, ax = plt.subplots(figsize=(9.0, 4.4), dpi=150)
    ax.pcolormesh(times, freqs[band], w_db[band], cmap="magma",
                  vmin=-6, vmax=18, shading="auto", rasterized=True)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("time (s)", color=NAVY, fontsize=10)
    ax.set_ylabel("frequency (Hz)", color=NAVY, fontsize=10)
    ax.set_title(f"{title}  ·  LOFAR spectrogram  ·  {len(lines)} prominent tonal(s)",
                 color=NAVY, fontsize=11, fontweight="bold")
    ax.tick_params(colors=NAVY, labelsize=9)
    halo = [pe.withStroke(linewidth=2.4, foreground="black", alpha=0.6)]
    xr = times[-1] if len(times) else 1.0
    for f in lines:
        if lo <= f <= hi:
            ax.text(xr * 0.99, f, f"{f:.0f}", color="#9af7f7", fontsize=8.5,
                    va="center", ha="right", fontweight="bold", path_effects=halo)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()

# ---- CSV builders (each returns a string; downloads are offered as separate buttons) ----------
def csv_ranked(name, osr, nseg, sk_rank, tn_rank):
    """Side-by-side ranked table: SKANN and tonal paired by rank position."""
    buf = io.StringIO(); w = csv.writer(buf)
    has_t = bool(tn_rank)
    hdr = ["query_clip", "native_sr", "n_segments", "rank", "skann_candidate", "skann_cos"]
    if has_t:
        hdr += ["tonal_candidate", "tonal_match"]
    w.writerow(hdr)
    for i in range(max(len(sk_rank), len(tn_rank))):
        s = sk_rank[i] if i < len(sk_rank) else None
        t = tn_rank[i] if i < len(tn_rank) else None
        row = [name, osr, nseg, i + 1,
               (s["vessel"] if s else ""), (f'{s["score"]:.6f}' if s else "")]
        if has_t:
            row += [(t["vessel"] if t else ""), (f'{t["score"]:.6f}' if t else "")]
        w.writerow(row)
    return buf.getvalue()

def csv_query_embedding(name, q_emb):
    """512-d query embedding, long format (one row per dimension)."""
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["query_clip", "dim", "value"])
    for i, v in enumerate(q_emb):
        w.writerow([name, i, f"{float(v):.6f}"])
    return buf.getvalue()

def csv_query_tonal(name, q_lines):
    """Query LOFAR lines: rank (by strength), frequency Hz, strength dB-above-background."""
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["query_clip", "rank", "freq_hz", "strength_db"])
    for rk, (f, db) in enumerate(q_lines, 1):
        w.writerow([name, rk, f"{float(f):.3f}", f"{float(db):.3f}"])
    return buf.getvalue()

def csv_gallery_tonal(tgal):
    """Every enrolled passage's LOFAR lines (long format), tagged by candidate + passage key."""
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["candidate", "passage_key", "rank", "freq_hz", "strength_db"])
    for key, rec in tgal.lines.items():
        for rk, (f, db) in enumerate(rec.get("lines", []), 1):
            w.writerow([rec.get("vessel", ""), key, rk, f"{float(f):.3f}", f"{float(db):.3f}"])
    return buf.getvalue()

def csv_gallery_tonal_wide(gal, tgal):
    """One row per enrolled passage with metadata + up to 20 (freq,db) line pairs.
    This is the inspectable export the operator asked for — per PASSAGE (not per ship) so
    multi-passage recall and single-entry deletion are preserved."""
    buf = io.StringIO(); w = csv.writer(buf)
    hdr = ["passage_idx", "vessel", "source", "mmsi", "imo", "file", "enrolled", "n_lines"]
    for k in range(1, 21):
        hdr += [f"f{k}_hz", f"db{k}"]
    w.writerow(hdr)
    for i, (lab, meta) in enumerate(zip(gal.labels, gal.meta)):
        key = (meta or {}).get("tonal_key", "")
        rec = tgal.lines.get(key, {})
        lines = rec.get("lines", [])
        row = [i, lab, (meta or {}).get("source", ""), (meta or {}).get("mmsi", ""),
               (meta or {}).get("imo", ""), (meta or {}).get("file", ""),
               (meta or {}).get("enrolled", ""), len(lines)]
        for k in range(20):
            if k < len(lines):
                row += [f"{float(lines[k][0]):.3f}", f"{float(lines[k][1]):.3f}"]
            else:
                row += ["", ""]
        w.writerow(row)
    return buf.getvalue()

def csv_gallery_embeddings(gal):
    """Every enrolled passage embedding, long format (candidate, passage_idx, dim, value)."""
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["candidate", "passage_idx", "dim", "value"])
    for pi, (lab, vec) in enumerate(zip(gal.labels, gal.emb)):
        for i, v in enumerate(vec):
            w.writerow([lab, pi, i, f"{float(v):.6f}"])
    return buf.getvalue()

# --------------------------------------------------------------------------- page
st.set_page_config(page_title=APP_TITLE, page_icon="🛰️", layout="wide")

st.markdown("""
<style>
  .blockc {background:#0d1117;border:1px solid #21262d;border-radius:10px;padding:14px 18px;margin-bottom:10px;}
  .vname  {font-size:1.05rem;font-weight:600;color:#e6edf3;}
  .scorep {font-variant-numeric:tabular-nums;font-weight:700;}
  .rk     {color:#8b949e;font-size:.8rem;}
  .agree  {color:#1a7f37;font-weight:600;}
  .panehdr{font-size:1.35rem;font-weight:800;padding:10px 16px;border-radius:9px 9px 0 0;
           margin-bottom:12px;letter-spacing:.01em;}
  .panehdr small{display:block;font-size:.74rem;font-weight:500;opacity:.85;
           text-transform:none;letter-spacing:0;margin-top:2px;}
  .skann  {background:#0d2440;color:#79c0ff;border:1px solid #1f6feb;border-bottom:3px solid #1f6feb;}
  .tonal  {background:#0d2b27;color:#56d4bf;border:1px solid #1f9e8f;border-bottom:3px solid #1f9e8f;}
</style>
""", unsafe_allow_html=True)

st.title("🛰️ DISC5 — SKANN Vessel Re-Identification")

# ---- login gate (1A): everything below runs only for a signed-in user -------------------------
user = A.require_login(app_dir())

# sidebar ----------------------------------------------------------------------------------------
with st.sidebar:
    A.render_sidebar_identity(app_dir(), user)
    st.divider()
    st.header("Settings")
    batch = st.number_input("Inference batch size", 1, 64, E.DEFAULT_BATCH, 1,
                            help="Lower = less GPU memory. 4 is safe on a modest VM GPU. "
                                 "Affects speed/memory only — never the score.")
    eng = get_engine(int(batch))
    gal = get_gallery()
    tgal = get_tonal_gallery()
    show_tonal = st.toggle("Show LOFAR-tonal column", value=True,
                           help="Independent second opinion. Not fused with SKANN.")
    st.divider()
    st.caption(f"**Compute:** {eng.device_str}")
    st.caption(f"**Model:** {CKPT_NAME}  (frozen backbone)")
    st.caption(f"**Gallery:** {gal.n_passages()} passages · {len(gal.vessels())} vessels")
    if eng.device_str == "CPU":
        st.warning("Running on CPU — embedding is very slow (~minutes/segment). "
                   "Use a GPU machine for operational speed.", icon="⚠️")
    if A.is_analyst(user):
        with st.expander("Manage gallery"):
            v = st.selectbox("Remove a vessel (all its passages)", ["—"] + gal.vessels())
            if st.button("Remove", use_container_width=True) and v != "—":
                A.audit(app_dir(), user, "gallery_remove_vessel", v)
                gal.remove_label(v); tgal.remove_label(v)
                st.session_state.pop("qres", None); st.rerun()
            if st.button("Clear entire gallery", type="secondary", use_container_width=True):
                A.audit(app_dir(), user, "gallery_clear", f"{gal.n_passages()} passage(s)")
                gal.clear(); tgal.clear()
                st.session_state.pop("qres", None); st.rerun()

# Roles are nested. Operator: Identify + Gallery (read-only). Analyst: + Enrol and gallery
# management. Admin: + Activity (audit) and Users (account administration).
if A.is_admin(user):
    tab_query, tab_enrol, tab_gallery, tab_activity, tab_users = st.tabs(
        ["🔎 Identify (query)", "➕ Enrol vessel", "📋 Gallery", "📊 Activity", "👥 Users"])
elif A.is_analyst(user):
    tab_query, tab_enrol, tab_gallery = st.tabs(
        ["🔎 Identify (query)", "➕ Enrol vessel", "📋 Gallery"])
    tab_activity = tab_users = None
else:
    tab_query, tab_gallery = st.tabs(["🔎 Identify (query)", "📋 Gallery"])
    tab_enrol = tab_activity = tab_users = None

# enrol ------------------------------------------------------------------------------------------
if tab_enrol is not None:   # Analyst only — hidden for Operators
    with tab_enrol:
        st.subheader("Add vessel recordings to the gallery")
        st.caption("The model is frozen; the gallery grows. Each recording is enrolled under its "
                   "**filename** (the `.wav` is dropped) — no relabelling. Enrol several passages per "
                   "vessel for better recall.")

        with st.expander("Metadata (optional — source · MMSI · IMO, stored with each entry, "
                         "shown in the Gallery tab)"):
            st.caption("Left blank, **Source** is auto-detected from the filename prefix "
                       "(`ONC_`, `IARA_`, `DC_`/`NODPAC_`, `SHIPSEAR_`) and **MMSI** is read from a "
                       "`*clip_map.csv` sidecar if one sits beside the clips. Anything you type here "
                       "overrides the auto-fill.")
            pc1, pc2, pc3 = st.columns(3)
            src_tag = pc1.selectbox("Source", SOURCES, key="enrol_source")
            mmsi_tag = pc2.text_input("MMSI (optional)", key="enrol_mmsi")
            imo_tag = pc3.text_input("IMO (optional)", key="enrol_imo")
        extra = {"source": ("" if src_tag == "(unspecified)" else src_tag),
                 "mmsi": mmsi_tag.strip(), "imo": imo_tag.strip()}

        mode = st.radio("Source", ["Load from a folder on this machine", "Upload files"],
                        horizontal=True, key="enrol_mode")

        if mode == "Load from a folder on this machine":
            folder = st.text_input("Folder path", key="enrol_folder",
                                   placeholder=r"e.g. C:\Users\suniltyagi\NODPAC\gallery__clean")
            files = _list_wavs(folder) if folder else None
            if folder and files is None:
                st.error("Folder not found. Check the path (it must be on the machine running the app).")
            elif files is not None:
                st.caption(f"**{len(files)}** WAV file(s) found. Pick the recordings to enrol — "
                           "each becomes a gallery entry named after its file.")
                names = [p.name for p in files]
                picks = st.multiselect("Recordings to enrol", names, default=names, key="enrol_picks")
                chosen = [p for p in files if p.name in set(picks)]
                if st.button(f"Enrol {len(chosen)} recording(s)", type="primary", disabled=not chosen):
                    prog = st.progress(0.0, text="Enrolling…")
                    done = skipped = 0; problems = []
                    for i, p in enumerate(chosen, 1):
                        status, msg = enrol_path(eng, gal, tgal, str(p), p.stem, show_tonal, extra)
                        A.audit(app_dir(), user, "enrol", p.stem, outcome=status)
                        if status == "ok":
                            done += 1
                        else:
                            skipped += 1; problems.append(msg)
                        prog.progress(i / len(chosen), text=f"Enrolling… {i}/{len(chosen)}")
                    prog.empty()
                    st.success(f"Enrolled **{done}** recording(s)" +
                               (f"; skipped {skipped}." if skipped else "."))
                    if problems:
                        with st.expander(f"{len(problems)} skipped / failed"):
                            for m in problems:
                                st.write("• " + m)
                    st.rerun()

        else:
            ups = st.file_uploader("Recording(s) (WAV)", type=["wav"],
                                   accept_multiple_files=True, key="enrol_up")
            if ups:
                st.caption(f"**{len(ups)}** file(s) ready — each enrolled under its filename.")
            if st.button("Enrol", type="primary", disabled=not ups):
                prog = st.progress(0.0, text="Enrolling…")
                done = skipped = 0; problems = []
                for i, up in enumerate(ups, 1):
                    p = _save_upload(up)
                    try:
                        status, msg = enrol_path(eng, gal, tgal, p, Path(up.name).stem, show_tonal, extra)
                    finally:
                        try: os.remove(p)
                        except OSError: pass
                    A.audit(app_dir(), user, "enrol", Path(up.name).stem, outcome=status)
                    if status == "ok":
                        done += 1
                    else:
                        skipped += 1; problems.append(msg)
                    prog.progress(i / len(ups), text=f"Enrolling… {i}/{len(ups)}")
                prog.empty()
                st.success(f"Enrolled **{done}** recording(s)" +
                           (f"; skipped {skipped}." if skipped else "."))
                if problems:
                    with st.expander(f"{len(problems)} skipped / failed"):
                        for m in problems:
                            st.write("• " + m)
                st.rerun()

# query ------------------------------------------------------------------------------------------
with tab_query:
    st.subheader("Identify a recording against the gallery")
    if gal.n_passages() == 0:
        st.info("Gallery is empty. Enrol at least one vessel first.")
    qup = st.file_uploader("Query recording (WAV)", type=["wav"], key="query_up")
    topn = st.slider("Show top N candidates", 3, 25, 10)

    if st.button("Identify", type="primary", disabled=qup is None):
        # drop the previous query's kept WAV before saving the new one
        prev = st.session_state.get("qres", {}).get("wav_path")
        if prev and os.path.exists(prev):
            try: os.remove(prev)
            except OSError: pass
        p = _save_upload(qup)          # kept for the session so the spectrogram button can use it
        try:
            with st.spinner("Embedding query…"):
                q_emb, osr, nseg = eng.embed_wav(p)
            if q_emb is None:
                st.error("Query too short (<5 s after 8 kHz resample).")
                try: os.remove(p)
                except OSError: pass
                st.stop()
            q_lines = E.tonal_lines_from_wav(p) if show_tonal else []
            sk_rank = gal.query(q_emb)
            tn_rank = tgal.query(q_lines) if show_tonal else []
        finally:
            _release_gpu()
        st.session_state["qres"] = dict(
            name=qup.name, osr=int(osr), nseg=int(nseg), wav_path=p,
            q_emb=[float(x) for x in q_emb],
            q_lines=[[float(f), float(db)] for f, db in q_lines],
            sk_rank=sk_rank, tn_rank=tn_rank)
        A.audit(app_dir(), user, "query", qup.name, n_seg=int(nseg),
                top_match=(sk_rank[0]["vessel"] if sk_rank else "(empty gallery)"))

    res = st.session_state.get("qres")
    if res:
        name, osr, nseg = res["name"], res["osr"], res["nseg"]
        sk_rank, tn_rank = res["sk_rank"], res["tn_rank"]
        q_emb, q_lines = res["q_emb"], res["q_lines"]
        wav_path = res.get("wav_path")
        has_tonal = show_tonal and bool(tn_rank)
        tn_lookup = {r["vessel"]: r for r in tn_rank}

        st.caption(f"Query: **{name}** · native {osr} Hz · {nseg} segments · "
                   f"gallery {len(gal.vessels())} vessels / {gal.n_passages()} passages")

        # spectrogram view disabled pending renderer improvement (v1.2) - the button now
        # points the user to the tonal-lines CSV export instead.
        if wav_path and os.path.exists(wav_path):
            if st.button("🔬 Show query spectrogram (tonals labelled)"):
                st.info("The spectrogram view is unavailable in this version. Use the "
                        "**Query tonal lines** download in the Downloads panel below to "
                        "inspect the detected tonals — the frequency and strength of "
                        "every line the tonal score uses.")

        cols = st.columns([1, 1] if has_tonal else [1])
        with cols[0]:
            st.markdown('<div class="panehdr skann">SKANN'
                        '<small>ranked candidates · cosine similarity of the 512-d embedding</small>'
                        '</div>', unsafe_allow_html=True)
            for r in sk_rank[:topn]:
                tn = tn_lookup.get(r["vessel"])
                agree = ('<span class="agree"> · ✓ tonal agrees</span>'
                         if has_tonal and tn and tn["rank"] <= 3 and r["rank"] <= 3 else "")
                render_rank_card(r, "skann", "cos", 0.45, 0.65, agree)
        if has_tonal:
            with cols[1]:
                st.markdown('<div class="panehdr tonal">LOFAR-tonal'
                            '<small>ranked candidates · strength-weighted matched fraction '
                            '(&le;20 lines)</small></div>', unsafe_allow_html=True)
                if not tn_rank:
                    st.caption("No tonal lines extracted from query (or empty tonal gallery).")
                for r in tn_rank[:topn]:
                    render_rank_card(r, "tonal", "match", 0.15, 0.35)

        st.caption("SKANN and LOFAR-tonal are independent and on different scales — SKANN is a "
                   "cosine of dense 512-d embeddings, tonal is a matched fraction over &le;20 lines. "
                   "Agreement (both rank a vessel in the top 3) raises confidence; they are never "
                   "numerically combined.")

        # ---- customisable downloads (separate buttons) ----------------------------------------
        with st.expander("⬇ Downloads", expanded=False):
            stem = Path(name).stem
            st.caption("Each export is a separate CSV. Query files reflect the query above; "
                       "gallery files reflect the current gallery.")
            if st.download_button("Ranked results", csv_ranked(name, osr, nseg, sk_rank, tn_rank),
                                  file_name=f"disc5_query_{stem}.csv", mime="text/csv",
                                  key="dl_ranked", use_container_width=True):
                A.audit(app_dir(), user, "export_ranked", name)
            st.download_button("Query embedding (512-d)", csv_query_embedding(name, q_emb),
                               file_name=f"disc5_query_{stem}_embedding.csv", mime="text/csv",
                               key="dl_qemb", use_container_width=True)
            st.download_button("Query tonal lines", csv_query_tonal(name, q_lines),
                               file_name=f"disc5_query_{stem}_tonal.csv", mime="text/csv",
                               key="dl_qton", disabled=not q_lines, use_container_width=True)
            if A.is_analyst(user):
                st.divider()
                if st.download_button("Gallery tonal lines (all enrolled)", csv_gallery_tonal(tgal),
                                      file_name="disc5_gallery_tonal.csv", mime="text/csv",
                                      key="dl_gton", disabled=not tgal.lines,
                                      use_container_width=True):
                    A.audit(app_dir(), user, "export_gallery_tonal", "(all)")
                if st.download_button("Gallery embeddings (all enrolled)", csv_gallery_embeddings(gal),
                                      file_name="disc5_gallery_embeddings.csv", mime="text/csv",
                                      key="dl_gemb", disabled=gal.n_passages() == 0,
                                      use_container_width=True):
                    A.audit(app_dir(), user, "export_gallery_embeddings", "(all)")

# gallery inspector ------------------------------------------------------------------------------
with tab_gallery:
    st.subheader("Enrolled gallery")
    if gal.n_passages() == 0:
        st.info("Gallery is empty. Enrol at least one vessel.")
    else:
        st.caption(f"{gal.n_passages()} passage(s) across {len(gal.vessels())} vessel(s). "
                   "Each row is one enrolled passage (a vessel may have several).")

        # read-only table (markdown — light over RDP, no canvas widgets)
        rows = ["| # | vessel | source | MMSI | IMO | length (s) | sr (Hz) | tonal lines | "
                "top freqs (Hz) | enrolled |",
                "|--:|---|---|---|---|--:|--:|--:|---|---|"]
        for i, (lab, meta) in enumerate(zip(gal.labels, gal.meta)):
            m = meta or {}
            key = m.get("tonal_key", "")
            lines = tgal.lines.get(key, {}).get("lines", [])
            top = ", ".join(f"{float(f):.0f}" for f, _ in sorted(lines, key=lambda x: -x[1])[:5])
            dur = m.get("dur_s", "")
            dur_str = f"{float(dur):.1f}" if dur not in ("", None) else "—"
            sr = m.get("orig_sr", "")
            sr_str = f"{int(sr)}" if sr not in ("", None) else "—"
            rows.append(f"| {i} | {lab} | {m.get('source','') or '—'} | {m.get('mmsi','') or '—'} | "
                        f"{m.get('imo','') or '—'} | {dur_str} | {sr_str} | {len(lines)} | "
                        f"{top or '—'} | {m.get('enrolled','')} |")
        st.markdown("\n".join(rows))
        st.caption("Per-passage 512-d embeddings → **Gallery embeddings (CSV)**; full per-passage "
                   "tonal line lists → **Tonal gallery (wide CSV)** — both at the bottom of this tab.")

        if A.is_analyst(user):
            st.divider()
            st.markdown("**Delete a single entry**")
            opts = [f"{i}: {lab}  ({(meta or {}).get('file','')})"
                    for i, (lab, meta) in enumerate(zip(gal.labels, gal.meta))]
            pick = st.selectbox("Passage to delete", ["—"] + opts, key="gal_del_pick")
            if st.button("🗑 Delete this entry", type="secondary", disabled=pick == "—"):
                idx = int(pick.split(":", 1)[0])
                A.audit(app_dir(), user, "gallery_delete_passage", pick)
                key = (gal.meta[idx] or {}).get("tonal_key", "")
                gal.remove_index(idx)
                if key:
                    tgal.remove_key(key)
                st.session_state.pop("qres", None)
                st.success(f"Deleted entry #{idx}.")
                st.rerun()

            st.divider()
            c1, c2 = st.columns(2)
            if c1.download_button("Tonal gallery (wide CSV: metadata + 20 line pairs)",
                                  csv_gallery_tonal_wide(gal, tgal),
                                  file_name="disc5_gallery_tonal_wide.csv", mime="text/csv",
                                  key="dl_gton_wide", use_container_width=True):
                A.audit(app_dir(), user, "export_gallery_tonal_wide", "(all)")
            if c2.download_button("Gallery embeddings (CSV)", csv_gallery_embeddings(gal),
                                  file_name="disc5_gallery_embeddings.csv", mime="text/csv",
                                  key="dl_gemb2", use_container_width=True):
                A.audit(app_dir(), user, "export_gallery_embeddings", "(all)")
        else:
            st.caption("Deletion and gallery-wide exports are Analyst functions.")

# activity & users (Analyst only) ----------------------------------------------------------------
if tab_activity is not None:
    with tab_activity:
        A.render_activity_tab(app_dir(), user)
if tab_users is not None:
    with tab_users:
        A.render_users_tab(app_dir(), user)
