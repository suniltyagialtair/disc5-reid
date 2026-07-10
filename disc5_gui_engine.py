# disc5_gui_engine.py
# SKANN re-identification engine for the DISC5 GUI deliverable (ft#2 backbone, SKANN-only).
# Self-contained: model architecture, 8 kHz preprocessing, gallery persistence, SKANN cosine
# scoring, and a parallel (display-only, never fused) LOFAR-tonal scorer.
#
# CRITICAL — every preprocessing / model / scoring constant below is lifted VERBATIM from the
# evaluation path so the GUI's scores match the banked benchmark numbers exactly:
#   - SR=8000, SEG=40000 (5 s), MIN_TAIL=8000, mono downmix, resample_poly, per-seg znorm,
#     tiled windows + final tail kept if >=1 s        (disc5_prep_navy.py)
#   - SKFilterbank + DISC5Encoder                      (DISC5_Allbench_SKANN_ftONC.ipynb, Cell 1)
#   - load_encoder backbone-only (ft#2 736-head ignored), pool = per-seg L2norm -> mean -> renorm
#   - LOFAR/TPSW lines + symmetric strength-weighted +-1 Hz tonal_score  (disc5_score_navy_tonal.py)
# Changing any of these silently desyncs the GUI from the benchmark; do not "tidy" them.

import os, json, time
from math import gcd
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from scipy.signal import spectrogram as scipy_spectrogram
from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d, median_filter

import torch
import torch.nn as nn
import torch.nn.functional as F

# ----------------------------------------------------------------------------- config
SR, SEG, MIN_TAIL = 8000, 40000, 8000          # 5 s segments @ 8 kHz
EPS = 1e-8
DEFAULT_BATCH = 4                               # modest VM GPU; CPU-safe too
EMBED_DIM = 512

def pick_device():
    return torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# ----------------------------------------------------------------------------- model (verbatim)
class SKFilterbank(nn.Module):
    def __init__(self, in_ch=1, out_ch=64, kernels=(127, 511, 2047, 8191), d=4):
        super().__init__(); self.convs = nn.ModuleList(); self.norms = nn.ModuleList(); ng = min(16, out_ch)
        for k in kernels:
            self.convs.append(nn.Conv1d(in_ch, out_ch, k, padding=k // 2)); self.norms.append(nn.GroupNorm(ng, out_ch))
        self.squeeze = nn.Linear(out_ch, d); self.excites = nn.ModuleList([nn.Linear(d, out_ch) for _ in kernels])
    def forward(self, x):
        outs = [F.relu(n(c(x))) for c, n in zip(self.convs, self.norms)]
        L = min(o.shape[-1] for o in outs); outs = [o[..., :L] for o in outs]
        st = torch.stack(outs, 0); U = st.sum(0); z = F.relu(self.squeeze(U.mean(-1)))
        a = F.softmax(torch.stack([e(z) for e in self.excites], 0), 0).unsqueeze(-1)
        return (st * a).sum(0)

class DISC5Encoder(nn.Module):
    def __init__(self, kernels=(127, 511, 2047, 8191), sk_ch=64, embed_dim=512):
        super().__init__(); self.fb = SKFilterbank(1, sk_ch, tuple(kernels))
        self.l1 = nn.Sequential(nn.Conv2d(1, 64, 3, stride=(1, 1), padding=1), nn.GroupNorm(16, 64), nn.ReLU(True))
        self.l2 = nn.Sequential(nn.Conv2d(64, 128, 3, stride=(1, 4), padding=1), nn.GroupNorm(16, 128), nn.ReLU(True))
        self.l3 = nn.Sequential(nn.Conv2d(128, 256, 3, stride=(1, 4), padding=1), nn.GroupNorm(16, 256), nn.ReLU(True))
        self.l4 = nn.Sequential(nn.Conv2d(256, 512, 3, stride=(2, 4), padding=1), nn.GroupNorm(16, 512), nn.ReLU(True))
        self.l5 = nn.Sequential(nn.Conv2d(512, 512, 3, stride=(2, 2), padding=1), nn.GroupNorm(16, 512), nn.ReLU(True))
        self.pool = nn.AdaptiveAvgPool2d(1)
    def forward(self, x):
        h = self.fb(x).unsqueeze(1)
        for l in (self.l1, self.l2, self.l3, self.l4, self.l5):
            h = l(h)
        return F.normalize(self.pool(h).flatten(1), dim=1)

def load_encoder(ckpt_path, device):           # verbatim from disc5_score_onc_eval.py
    enc = DISC5Encoder().to(device).eval()
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    state = ck.get('model', ck.get('state_dict', ck)) if isinstance(ck, dict) else ck
    enc_state = {k.replace('encoder.', '', 1): v for k, v in state.items() if k.startswith('encoder.')}
    if not enc_state:
        enc_state = {k: v for k, v in state.items() if not k.startswith(('head.', 'arcface', 'fc'))}
    missing, unexpected = enc.load_state_dict(enc_state, strict=False)
    assert not missing, f'missing encoder weights: {missing[:5]}'
    return enc, len(missing), len(unexpected)

# ----------------------------------------------------------------------------- preprocessing (verbatim)
def clip_duration_s(path):
    """Clip duration in seconds from the file header (no full decode). None on failure."""
    try:
        info = sf.info(str(path))
        return float(info.frames) / float(info.samplerate)
    except Exception:
        return None

def load_audio_resample(path, sr_target=SR):
    y, sr = sf.read(str(path), always_2d=True)
    y = y.mean(axis=1).astype('float32')
    if sr != sr_target:
        g = gcd(sr, sr_target)
        y = resample_poly(y, sr_target // g, sr // g).astype('float32')
    return y.astype('float32'), sr

def znorm(y):
    m, s = float(y.mean()), float(y.std())
    return ((y - m) if s < EPS else (y - m) / s).astype('float32')

def windows(y, seg=SEG, min_tail=MIN_TAIL):
    n = len(y)
    if n < seg:
        return []
    out = [y[i * seg:(i + 1) * seg] for i in range(n // seg)]
    if n - (n // seg) * seg >= min_tail:
        out.append(y[n - seg:])
    return out

def wav_to_segments(path):
    """WAV -> list of [1,1,40000] float32 tensors (clean enrol/query path; no aug/speed)."""
    y, orig_sr = load_audio_resample(path, SR)
    segs = windows(y)
    tens = [torch.from_numpy(znorm(s)).view(1, 1, SEG) for s in segs]
    return tens, orig_sr, len(segs)

# ----------------------------------------------------------------------------- SKANN embedding (verbatim pooling)
class SKANNEngine:
    def __init__(self, ckpt_path, device=None, batch=DEFAULT_BATCH):
        self.device = device or pick_device()
        self.batch = int(batch)
        self.enc, self.n_missing, self.n_unexpected = load_encoder(ckpt_path, self.device)
        self.ckpt_path = str(ckpt_path)

    @property
    def device_str(self):
        if self.device.type == 'cuda':
            try: return f'GPU ({torch.cuda.get_device_name(0)})'
            except Exception: return 'GPU'
        return 'CPU'

    def embed_segments(self, seg_tensors):
        """Per-segment L2-normalised embedding -> mean -> renorm. Verbatim pool_paths logic."""
        if not seg_tensors:
            return None
        segs = []
        with torch.no_grad():
            for b in range(0, len(seg_tensors), self.batch):
                t = torch.cat(seg_tensors[b:b + self.batch]).to(self.device)
                segs.append(F.normalize(self.enc(t), dim=1).cpu())
        return F.normalize(torch.cat(segs).mean(0), dim=0).numpy().astype('float32')

    def embed_wav(self, path):
        tens, orig_sr, n_seg = wav_to_segments(path)
        if not tens:
            return None, orig_sr, 0
        return self.embed_segments(tens), orig_sr, n_seg

# ----------------------------------------------------------------------------- gallery store
class Gallery:
    """Persistent enrolment store: one row per enrolled passage (embedding + label + meta).
    A vessel may have several passages; query scores aggregate to the best passage per vessel."""
    def __init__(self, path):
        self.path = Path(path)
        self.emb = np.zeros((0, EMBED_DIM), dtype='float32')
        self.labels, self.meta = [], []
        if self.path.exists():
            self.load()

    def load(self):
        d = np.load(self.path, allow_pickle=True)
        self.emb = d['emb'].astype('float32')
        self.labels = list(d['labels'])
        self.meta = list(d['meta'])

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, emb=self.emb, labels=np.array(self.labels, dtype=object),
                 meta=np.array(self.meta, dtype=object))

    def add(self, label, embedding, meta=None):
        self.emb = np.vstack([self.emb, embedding[None, :].astype('float32')])
        self.labels.append(str(label))
        self.meta.append(meta or {})
        self.save()

    def remove_label(self, label):
        keep = [i for i, l in enumerate(self.labels) if l != label]
        self.emb = self.emb[keep] if keep else np.zeros((0, EMBED_DIM), dtype='float32')
        self.labels = [self.labels[i] for i in keep]
        self.meta = [self.meta[i] for i in keep]
        self.save()

    def remove_index(self, idx):
        """Delete a single enrolled passage by row index (one gallery entry)."""
        keep = [j for j in range(len(self.labels)) if j != idx]
        self.emb = self.emb[keep] if keep else np.zeros((0, EMBED_DIM), dtype='float32')
        self.labels = [self.labels[j] for j in keep]
        self.meta = [self.meta[j] for j in keep]
        self.save()

    def clear(self):
        self.emb = np.zeros((0, EMBED_DIM), dtype='float32')
        self.labels, self.meta = [], []
        self.save()

    def vessels(self):
        return sorted(set(self.labels))

    def n_passages(self):
        return len(self.labels)

    def query(self, q_emb):
        """Cosine of query vs every enrolled passage, then best-per-vessel, ranked desc.
        Embeddings are unit-norm, so dot == cosine. Returns list of dicts (ranked)."""
        if self.emb.shape[0] == 0 or q_emb is None:
            return []
        sims = self.emb @ q_emb.astype('float32')
        best = {}
        for i, lab in enumerate(self.labels):
            s = float(sims[i])
            if lab not in best or s > best[lab]['score']:
                best[lab] = dict(vessel=lab, score=s, passage_idx=int(i), meta=self.meta[i])
        ranked = sorted(best.values(), key=lambda r: -r['score'])
        for rank, r in enumerate(ranked, 1):
            r['rank'] = rank
        return ranked

# ----------------------------------------------------------------------------- LOFAR / TPSW tonal (verbatim, display-only)
STFT_WINDOW_SEC, STFT_OVERLAP_FRAC, STFT_NFFT_MULT = 4.0, 0.75, 2
TPSW_WIN_HZ, TPSW_GUARD_HZ, TPSW_ALPHA = 8.0, 1.5, 3.0   # post-TPSW whitener (matches scorer)
BACKGROUND_PERCENTILE, TONAL_THRESHOLD_DB, TONAL_MIN_PERSIST_SEC = 50, 8.0, 10
TONAL_FREQ_MIN_HZ, TONAL_FREQ_MAX_HZ, TONAL_BAND_WIDTH_HZ = 3.5, 2000, 2.0
TOP_K, TOL_HZ = 20, 1.0

def _compute_stft(audio, sr):
    nperseg = int(STFT_WINDOW_SEC * sr); noverlap = int(nperseg * STFT_OVERLAP_FRAC)
    nfft = nperseg * STFT_NFFT_MULT
    return scipy_spectrogram(audio, fs=sr, nperseg=nperseg, noverlap=noverlap,
                             nfft=nfft, mode='psd', scaling='density')

def _normalise_spectrogram(freqs, Sxx):
    # TPSW: two-pass split-window background over FREQUENCY (verbatim from disc5_score_allbench_tonal.py,
    # win=8.0Hz, guard=1.5Hz, alpha=3.0). This replaces the old percentile background so the GUI tonal
    # lines and matched-fraction reproduce the banked benchmark numbers.
    fr = freqs[1] - freqs[0]
    M = max(1, int(round(TPSW_WIN_HZ / fr)))     # outer half-window (bins)
    G = max(1, int(round(TPSW_GUARD_HZ / fr)))   # centre guard half-width (excludes the line itself)
    def split_mean(X):                           # mean over [+-(G..M+G)] excluding centre +-G, per frame
        full = uniform_filter1d(X, size=2 * (M + G) + 1, axis=0, mode='reflect') * (2 * (M + G) + 1)
        cent = uniform_filter1d(X, size=2 * G + 1, axis=0, mode='reflect') * (2 * G + 1)
        return (full - cent) / max(2 * M, 1)
    bg1 = np.maximum(split_mean(Sxx), 1e-20)
    bg2 = np.maximum(split_mean(np.minimum(Sxx, TPSW_ALPHA * bg1)), 1e-20)   # 2nd pass, tonal-clipped
    return 10 * np.log10(np.maximum(Sxx / bg2, 1e-10))

def _detect_persistent(spec_db, freqs, times):
    fm = (freqs >= TONAL_FREQ_MIN_HZ) & (freqs <= TONAL_FREQ_MAX_HZ)
    f_sub, s_sub = freqs[fm], spec_db[fm, :]
    if len(times) < 2 or len(f_sub) < 2:
        return []
    dt = times[1] - times[0]; min_frames = max(1, int(TONAL_MIN_PERSIST_SEC / dt))
    fr = freqs[1] - freqs[0]; bw = max(1, int(TONAL_BAND_WIDTH_HZ / fr))
    n_bands = len(f_sub) // bw
    band_freqs = []; band_spec = np.zeros((n_bands, s_sub.shape[1]))
    for bi in range(n_bands):
        sb = bi * bw; eb = min(sb + bw, len(f_sub))
        band_spec[bi, :] = np.max(s_sub[sb:eb, :], axis=0)
        band_freqs.append(float(f_sub[sb + np.argmax(np.mean(s_sub[sb:eb, :], axis=1))]))
    above = band_spec > TONAL_THRESHOLD_DB; persistent = []
    for bi in range(n_bands):
        row = above[bi, :]; start = None
        for ti in range(len(row)):
            if row[ti] and start is None:
                start = ti
            elif not row[ti] and start is not None:
                if ti - start >= min_frames:
                    persistent.append(dict(freq_hz=band_freqs[bi], mean_db=float(np.mean(band_spec[bi, start:ti]))))
                start = None
        if start is not None and len(row) - start >= min_frames:
            persistent.append(dict(freq_hz=band_freqs[bi], mean_db=float(np.mean(band_spec[bi, start:]))))
    return sorted(persistent, key=lambda t: t['mean_db'], reverse=True)

def _top_lines(persistent, k=TOP_K):
    best = {}
    for ln in persistent:
        f = ln['freq_hz']
        if f not in best or ln['mean_db'] > best[f]:
            best[f] = ln['mean_db']
    return sorted(best.items(), key=lambda x: -x[1])[:k]    # [(freq, mean_db), ...]

def tonal_lines_from_wav(path):
    """LOFAR top-20 persistent lines for a WAV (resampled to 8 kHz). No z-norm (background-pctile handles level)."""
    y, _ = load_audio_resample(path, SR)
    freqs, times, Sxx = _compute_stft(y, SR)
    return _top_lines(_detect_persistent(_normalise_spectrogram(freqs, Sxx), freqs, times))

def spectrogram_with_lines(path):
    """Return (freqs, times, spec_db, lines) for plotting: the SAME TPSW-whitened spectrogram and the
    SAME detected top-K lines the tonal scorer uses, so the figure explains the displayed tonal score."""
    y, _ = load_audio_resample(path, SR)
    freqs, times, Sxx = _compute_stft(y, SR)
    spec_db = _normalise_spectrogram(freqs, Sxx)
    lines = _top_lines(_detect_persistent(spec_db, freqs, times))
    return freqs, times, spec_db, lines

# ----------------------------------------------------------------------------- deck-style display spectrogram
# This reproduces disc5_plot_deck_figures.fig_tonal_pair (the 09-Jun deck): a MEDIAN-whitened
# spectrogram and only the most PROMINENT narrowband peaks (find_peaks on the time-averaged
# whitened spectrum). It is a DISPLAY view only -- it deliberately does NOT use the TPSW persistence
# line detector that drives the tonal score, because that detector (top-20, 8 dB / 10 s persistence)
# marks weak noise excursions that look like "fake lines" on a wide axis. Prominence gating keeps
# only tonals that genuinely stand out.
DECK_WHITEN_WIN_HZ = 7.0          # median background half-window (deck value)

def _whiten_median(y, sr):
    nperseg = int(STFT_WINDOW_SEC * sr); noverlap = int(nperseg * STFT_OVERLAP_FRAC)
    nfft = nperseg * STFT_NFFT_MULT
    f, t, S = scipy_spectrogram(y, fs=sr, nperseg=nperseg, noverlap=noverlap, nfft=nfft,
                                mode='psd', scaling='density')
    fr = f[1] - f[0]; win = max(3, int(round(DECK_WHITEN_WIN_HZ / fr)))
    base = np.maximum(median_filter(S, size=(win, 1)), 1e-20)
    return f, t, 10 * np.log10(np.maximum(S / base, 1e-10))

def deck_spectrogram(path, max_lines=8, fmin=10.0, fmax=1500.0, prominence=3.0):
    """Deck-style LOFAR view: median-whitened spectrogram + the most prominent tonal lines.
    Returns (freqs, times, w_db, lines_hz). `lines_hz` are the top-`max_lines` peaks by prominence
    on the time-averaged whitened spectrum within [fmin,fmax] -- the same picker the deck used,
    generalised off the deck's hard-coded 20-70 Hz band. Higher `prominence` => fewer, cleaner lines."""
    y, _ = load_audio_resample(path, SR)
    f, t, w = _whiten_median(y, SR)
    fr = f[1] - f[0]
    band = (f >= fmin) & (f <= fmax)
    fsub = f[band]; favg = w[band].mean(axis=1)
    pk, props = find_peaks(favg, prominence=prominence, distance=max(1, int(round(2.0 / fr))))
    if len(pk):
        order = np.argsort(props['prominences'])[::-1][:max_lines]
        lines = sorted(float(fsub[pk[i]]) for i in order)
    else:
        lines = []
    return f, t, w, lines

def tonal_score(a, b, tol=TOL_HZ):              # symmetric strength-weighted +-1 Hz matched fraction (verbatim)
    if not a or not b:
        return 0.0
    def frac(q, g):
        gf = np.array([f for f, _ in g]); den = sum(w for _, w in q)
        if den <= 0:
            return 0.0
        num = sum(w for f, w in q if np.min(np.abs(gf - f)) <= tol)
        return num / den
    return 0.5 * (frac(a, b) + frac(b, a))

class TonalGallery:
    """Parallel tonal store: top-20 LOFAR lines per enrolled passage. Display-only, NEVER fused."""
    def __init__(self, path):
        self.path = Path(path)
        self.lines = {}     # passage_key -> {'vessel':..., 'lines':[[f,db],...]}
        if self.path.exists():
            self.lines = json.load(open(self.path))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(self.lines, open(self.path, 'w'))

    def add(self, key, vessel, lines):
        self.lines[key] = dict(vessel=str(vessel), lines=[[float(f), float(d)] for f, d in lines])
        self.save()

    def remove_label(self, label):
        self.lines = {k: v for k, v in self.lines.items() if v['vessel'] != label}
        self.save()

    def remove_key(self, key):
        """Delete a single enrolled passage by its passage key."""
        if key in self.lines:
            del self.lines[key]
            self.save()

    def clear(self):
        self.lines = {}; self.save()

    def query(self, q_lines):
        """tonal_score of query lines vs every enrolled passage, best-per-vessel, ranked desc."""
        if not self.lines or not q_lines:
            return []
        ql = [(f, d) for f, d in q_lines]
        best = {}
        for key, rec in self.lines.items():
            gl = [(f, d) for f, d in rec['lines']]
            s = tonal_score(ql, gl)
            v = rec['vessel']
            if v not in best or s > best[v]['score']:
                best[v] = dict(vessel=v, score=float(s))
        ranked = sorted(best.values(), key=lambda r: -r['score'])
        for rank, r in enumerate(ranked, 1):
            r['rank'] = rank
        return ranked
