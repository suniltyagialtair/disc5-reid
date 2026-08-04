# disc5_extend_demo_set.py
# Extends the staged demo set (C:\demo_vessels) with 3 IARA vessels (1 gallery + 2 query
# passages each, cross-collection/distinct-condition only), renamed to fictitious identities
# continuing the existing scheme; extends demo_clip_map.csv and the internal rename_map.csv.
#
#   python disc5_extend_demo_set.py --iara-root C:\Users\suniltyagi\IARA --demo-root C:\demo_vessels
#
# Idempotent: refuses to run if any target filename already exists.

import argparse
import csv
import os
import shutil

# (source IARA filename, fictitious name, role, demo date, fictitious MMSI, fictitious IMO)
PLAN = [
    ("IARA_557__STARNAV_AQUARIUS__A-0148.wav", "DECCAN_VOYAGER", "gallery", "2026-05-08", "419512336", "9941728"),
    ("IARA_557__STARNAV_AQUARIUS__B-0489.wav", "DECCAN_VOYAGER", "query",   "2026-06-07", "419512336", "9941728"),
    ("IARA_557__STARNAV_AQUARIUS__D-1054.wav", "DECCAN_VOYAGER", "query",   "2026-10-22", "419512336", "9941728"),
    ("IARA_99__CARLOS_VIEIRA__C-0687.wav",     "INDIGO_WAVE",    "gallery", "2026-05-12", "372845113", "9917342"),
    ("IARA_99__CARLOS_VIEIRA__B-0478.wav",     "INDIGO_WAVE",    "query",   "2026-06-23", "372845113", "9917342"),
    ("IARA_99__CARLOS_VIEIRA__D-1035.wav",     "INDIGO_WAVE",    "query",   "2026-10-25", "372845113", "9917342"),
    ("IARA_82__CAMPOS_CONTENDER__C-0706.wav",  "AMBER_CREST",    "gallery", "2026-05-16", "419228547", "9925816"),
    ("IARA_82__CAMPOS_CONTENDER__C-0746.wav",  "AMBER_CREST",    "query",   "2026-07-09", "419228547", "9925816"),
    ("IARA_82__CAMPOS_CONTENDER__C-0756.wav",  "AMBER_CREST",    "query",   "2026-10-29", "419228547", "9925816"),
]


def find_source(root, filename):
    for dirpath, _, files in os.walk(root):
        if filename in files:
            return os.path.join(dirpath, filename)
    raise SystemExit(f"source not found under {root}: {filename}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iara-root", default=r"C:\Users\suniltyagi\IARA")
    ap.add_argument("--demo-root", default=r"C:\demo_vessels")
    args = ap.parse_args()

    # pre-flight: sources exist, targets do not, identities are new
    jobs = []
    existing_names = set()
    clip_map = os.path.join(args.demo_root, "demo_clip_map.csv")
    with open(clip_map, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing_names.add(row["filename"].split("__")[0])
            existing_mmsi = row["vessel_mmsi"]
    for src_name, fict, role, date, mmsi, imo in PLAN:
        src = find_source(args.iara_root, src_name)
        dst_dir = os.path.join(args.demo_root, "gallery" if role == "gallery" else "query")
        dst = os.path.join(dst_dir, f"{fict}__{date}.wav")
        if os.path.exists(dst):
            raise SystemExit(f"target already exists (already run?): {dst}")
        jobs.append((src, dst, src_name, fict, role, date, mmsi, imo))
    for fict in {j[3] for j in jobs}:
        if fict in existing_names:
            raise SystemExit(f"fictitious name collides with existing set: {fict}")

    # copy + extend both maps
    for src, dst, src_name, fict, role, date, mmsi, imo in jobs:
        shutil.copy2(src, dst)
        print(f"copied {src_name} -> {os.path.relpath(dst, args.demo_root)}")
    with open(clip_map, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for _, _, _, fict, role, date, mmsi, imo in jobs:
            w.writerow([f"{fict}__{date}.wav", mmsi, imo])
    ren_map = os.path.join(args.demo_root, "rename_map.csv")
    with open(ren_map, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for src, _, src_name, fict, role, date, mmsi, imo in jobs:
            w.writerow([src_name.split("__")[0] + "_" + src_name.split("__")[1],
                        fict, role, date, mmsi, imo, f"{fict}__{date}.wav", src])

    # verification
    n_g = len(os.listdir(os.path.join(args.demo_root, "gallery")))
    n_q = len(os.listdir(os.path.join(args.demo_root, "query")))
    print(f"\ngallery files (incl. sidecar if present): {n_g}")
    print(f"query files: {n_q}")
    bad = [n for d in ("gallery", "query")
           for n in os.listdir(os.path.join(args.demo_root, d)) if "speed" in n.lower()]
    print("filenames containing 'speed':", bad or "none")


if __name__ == "__main__":
    main()
