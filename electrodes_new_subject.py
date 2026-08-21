#!/usr/bin/env python
"""Import a FreeSurfer subject into pycortex and build an electrode viewer.

Expects a FreeSurfer subject directory containing the usual recon-all output
plus an ``elecs/TDT_elecs_all.mat`` in the img_pipe layout.

    python electrodes_new_subject.py EC143
    python electrodes_new_subject.py EC143 --fs-dir /Applications/freesurfer/subjects

Runs five steps, each of which prints what it did:

  1. import the subject into the pycortex filestore (skipped if already there)
  2. import the flattened surfaces from a flat patch
  3. read the montage and check it lives in the same space as the surfaces
  4. anchor every contact and save the result into the filestore
  5. write a static viewer directory, and a flatmap

Step 1 does not bring flat surfaces -- hence step 2, which needs a
`<hemi>.<patch>.patch.3d` produced by flattening. The patch name is detected
automatically; pass --flat-patch to choose between several, or --no-flat to
skip. The 3-D viewer works without flats; flatmaps do not.

NOTE: importing flats deletes that subject's overlays.svg (ROI drawings) and
cached flatmaps, because the flatmap geometry has changed. Skip step 2 with
--no-flat if you have ROIs you care about and the flats are already imported.
"""

import argparse
import glob
import os
import sys

import numpy as np

import cortex
from cortex.electrodes import (
    PlacementPolicy,
    check_alignment,
    load_electrodes,
    load_surface_pairs,
)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject", help="FreeSurfer subject id, also used as the pycortex name")
    ap.add_argument("--fs-dir", default=os.environ.get("SUBJECTS_DIR"),
                    help="FreeSurfer SUBJECTS_DIR (default: $SUBJECTS_DIR)")
    ap.add_argument("--elecs", default=None,
                    help="path to the montage (default: <fs-dir>/<subject>/elecs/TDT_elecs_all.mat)")
    ap.add_argument("--wm", default="white",
                    help="which FreeSurfer surface to import as wm (default: white)")
    ap.add_argument("--name", default="clinical", help="name for the saved electrode set")
    ap.add_argument("--out", default=None, help="viewer output dir (default: /tmp/<subject>_viewer)")
    ap.add_argument("--reimport", action="store_true",
                    help="re-import even if the subject is already in the filestore")
    ap.add_argument("--flat-patch", default=None,
                    help="flat patch name, i.e. the X in <hemi>.X.patch.3d "
                         "(default: auto-detected)")
    ap.add_argument("--no-flat", action="store_true",
                    help="do not import flat surfaces (leaves overlays.svg alone)")
    ap.add_argument("--no-viewer", action="store_true", help="stop after anchoring")
    args = ap.parse_args()

    subject = args.subject
    if args.fs_dir is None:
        sys.exit("No --fs-dir given and $SUBJECTS_DIR is not set.")
    elecs = args.elecs or os.path.join(
        args.fs_dir, subject, "elecs", "TDT_elecs_all.mat")
    outpath = args.out or "/tmp/%s_viewer" % subject

    # -- 1. import ---------------------------------------------------------
    # `white` rather than the `smoothwm` default: smoothwm is smoothed, which
    # distorts the pia-to-white distance, and that distance is exactly what
    # every electrode's cortical depth is normalised by.
    already = subject in cortex.db.subjects
    if already and not args.reimport:
        print("[1/5] %s is already in the pycortex filestore; skipping import." % subject)
    else:
        print("[1/5] importing %s from %s (wm surface: %s)..." % (subject, args.fs_dir, args.wm))
        cortex.freesurfer.import_subj(
            freesurfer_subject=subject, pycortex_subject=subject,
            freesurfer_subject_dir=args.fs_dir, whitematter_surf=args.wm)
        cortex.db.reload_subjects()
        print("      imported.")

    # -- 2. flat surfaces --------------------------------------------------
    if args.no_flat:
        print("[2/5] skipping flat import (--no-flat)")
    else:
        patch = args.flat_patch
        if patch is None:
            found = sorted(glob.glob(os.path.join(
                args.fs_dir, subject, "surf", "lh.*.patch.3d")))
            names = [os.path.basename(f)[3:-len(".patch.3d")] for f in found]
            if not names:
                sys.exit("No lh.*.patch.3d in %s/%s/surf -- flatten first, or pass "
                         "--no-flat." % (args.fs_dir, subject))
            if len(names) > 1:
                print("      several patches found: %s" % ", ".join(names))
            patch = names[-1]
        print("[2/5] importing flat surfaces from patch %r..." % patch)
        cortex.freesurfer.import_flat(
            fs_subject=subject, patch=patch, cx_subject=subject,
            freesurfer_subject_dir=args.fs_dir, auto_overwrite=True)
        print("      imported.")

    surfaces = load_surface_pairs(subject)
    has_wm = surfaces["lh"].wm is not None
    print("      surfaces: %s   white matter present: %s"
          % (", ".join(sorted(surfaces)), has_wm))
    if not has_wm:
        print("      WARNING: no white-matter surface, so cortical depth will be NaN")
    try:
        cortex.db.get_surf(subject, "flat", "lh")
        has_flat = True
    except IOError:
        has_flat = False
    print("      flat surfaces: %s%s" % (
        has_flat, "" if has_flat else "  (3-D viewer fine; flatmaps will not work)"))

    # -- 2. read and sanity-check -----------------------------------------
    print("\n[3/5] reading %s" % elecs)
    eset = load_electrodes(elecs, subject=subject)
    print("      %d contacts in %d groups: %s"
          % (len(eset), len(eset.groups), ", ".join(eset.groups)))
    print("      device types: %s" % ", ".join(sorted(set(eset.group_type)) or ["<none>"]))

    # Judge alignment on the surface contacts only. Depth electrodes are
    # legitimately centimetres from the pia and would read as misregistered.
    surface_only = eset.select(group_type=["grid", "strip"])
    if len(surface_only):
        print()
        print(check_alignment(surface_only.coords, surfaces).summary())
    else:
        print("      no grid/strip contacts, so skipping the alignment check")

    # -- 3. anchor ---------------------------------------------------------
    print("\n[4/5] anchoring...")
    anchors = eset.anchor()
    print(anchors.summary())
    if has_wm:
        d = eset.depth[np.isfinite(eset.depth)]
        if len(d):
            print("      depth: %.2f to %.2f (0 = pia, 1 = white matter)" % (d.min(), d.max()))
    print("      median offset from the cortical column: %.2f mm"
          % np.nanmedian(anchors.offset_mm))

    path = cortex.db.save_electrodes(subject, eset, name=args.name, overwrite=True)
    print("      saved %s" % path)
    print("      reload later with: cortex.db.get_electrodes(%r, %r)" % (subject, args.name))

    # -- 4. viewer ---------------------------------------------------------
    if args.no_viewer:
        return
    print("\n[5/5] building the viewer in %s" % outpath)
    nverts = cortex.db.get_surf(subject, "fiducial", merge=True)[0].shape[0]
    blank = cortex.Vertex(np.full(nverts, np.nan), subject)   # NaN draws nothing: curvature only
    cortex.webgl.make_static(outpath, blank, electrodes=eset, overlays_visible=())
    if has_flat:
        import matplotlib
        matplotlib.use("Agg")
        png = os.path.join(outpath, "flatmap.png")
        # Coloured by cortical depth rather than a flat colour: 0 is the pia,
        # 1 the white matter, and anything well past 1 is a contact whose
        # surface position is a locality rather than a location.
        fig = cortex.quickflat.make_figure(
            blank, with_rois=False, with_colorbar=False, with_curvature=True,
            with_electrodes=eset, electrode_values=eset.depth,
            electrode_kwargs=dict(size=55, cmap="RdYlBu_r", vmin=-0.5, vmax=2.5))
        fig.savefig(png, dpi=150, bbox_inches="tight", facecolor="white")
        print("      flatmap written to %s" % png)

    print("\ndone. serve it with:")
    print("    python3 -m http.server 8899 --directory %s" % outpath)
    print("then open http://127.0.0.1:8899/index.html")


if __name__ == "__main__":
    main()
