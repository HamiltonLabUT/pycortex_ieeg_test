# pycortex iEEG test pipeline

Imports a FreeSurfer subject into pycortex, anchors its electrodes to the
cortical surface, and builds a viewer you can open in a browser.

Two scripts, for two situations:

| script | when |
| --- | --- |
| `show_electrodes.py` | the subject is already in the pycortex database — the everyday case |
| `electrodes_new_subject.py` | first contact with a subject: import it, check it, then view it |

Once a subject has been imported, showing its electrodes is two lines of
pycortex, and `show_electrodes.py` is barely more than that:

```python
electrodes = cortex.electrodes.load_electrodes(elecs_path, subject=subject)
cortex.webgl.show(cortex.electrodes.blank(subject), electrodes=electrodes)
```

`show()` anchors the set itself, so there is no separate `anchor()` call.
`blank()` is an all-NaN dataset, which both renderers mask out — it draws
nothing and leaves the curvature showing, which is what you want under
electrodes when there is no functional data. For a flatmap instead:

```python
cortex.quickflat.make_figure(cortex.electrodes.blank(subject),
                             with_electrodes=electrodes, with_curvature=True)
```

Everything below is about `electrodes_new_subject.py`, which is longer because
it does the things you only do once per subject: import from FreeSurfer, import
the flattened surfaces, check the coordinates are in the surfaces' space, and
report what the placement policy made of each contact.

Needs the `electrodes` branch of
[HamiltonLabUT/pycortex](https://github.com/HamiltonLabUT/pycortex), which adds
`cortex.electrodes` and the electrode support in the flatmap and webgl
renderers. It will not work against upstream pycortex.

## What you need first

- **FreeSurfer**, sourced, with `$FREESURFER_HOME` and `$SUBJECTS_DIR` set. The
  import shells out to it.
- **A subject that has been through `recon-all`**, with an
  `elecs/TDT_elecs_all.mat` in the `img_pipe` layout (`elecmatrix`,
  `eleclabels`, and usually `anatomy`).
- **A flattened surface** — a `<hemi>.<patch>.patch.3d` in the subject's `surf/`
  directory — if you want flatmaps. The 3-D viewer works without one.
- **[uv](https://docs.astral.sh/uv/)**, or any way of making a Python 3.11
  virtualenv.

## Setup

This is the part that strands people, so do it exactly once and in order.

```bash
git clone -b electrodes https://github.com/HamiltonLabUT/pycortex.git
cd pycortex
uv venv --python 3.11 .venv
VIRTUAL_ENV=$PWD/.venv uv pip install -r requirements.txt
```

Then build the C extensions **in place**:

```bash
.venv/bin/python setup.py build_ext --inplace
```

Skipping that step is the single most common failure. It shows up as:

```
ImportError: cannot import name 'formats' from partially initialized module 'cortex'
```

which reads like a circular import and is not one — it means the compiled
`formats` and `openctm` extensions have not been built. They are specific to a
Python version, so rebuild if you change interpreters.

There is no `pip install` of this branch. Run everything with the repo on
`PYTHONPATH`, as below.

## Running it

Everyday, for a subject already imported:

```bash
cd /path/to/pycortex
PYTHONPATH=$PWD .venv/bin/python /path/to/show_electrodes.py SUBJID
```

That opens the viewer and blocks; Ctrl-C to stop it. It reads the montage from
`$SUBJECTS_DIR/SUBJID/elecs/TDT_elecs_all.mat`.

First time with a subject:

```bash
cd /path/to/pycortex
PYTHONPATH=$PWD .venv/bin/python /path/to/electrodes_new_subject.py SUBJID
```

Five steps, each printing what it did:

1. import the subject into the pycortex filestore (skipped if already there)
2. import the flattened surfaces from a flat patch
3. read the montage and check it is in the same coordinate space as the surfaces
4. anchor every contact and save the result into the filestore
5. write a static viewer, and a flatmap

Useful flags:

| flag | why |
| --- | --- |
| `--fs-dir PATH` | if `$SUBJECTS_DIR` is not what you want |
| `--no-flat` | **use this on re-runs** — see below |
| `--flat-patch NAME` | if auto-detection picks the wrong patch |
| `--wm smoothwm` | defaults to `white`; see below |
| `--out PATH` | viewer directory, defaults to `/tmp/<subject>_viewer` |

## Viewing it

The viewer directory has to be served over HTTP. Opening `index.html` from the
filesystem leaves it stuck on "Loading brain..." forever, because browsers block
the requests it makes from a `file://` page.

```bash
python3 -m http.server 8899 --directory /tmp/SUBJID_viewer
```

Then open <http://127.0.0.1:8899/index.html>. That server needs no pycortex —
any Python 3 will do.

Click **Open Controls**, top right:

- **surface** — `unfold` morphs between the anatomical, inflated and flat
  surfaces; `depth` chooses where through the cortical ribbon to sample;
  `surface_opacity` and `ghostiness` make the cortex translucent so contacts
  inside the brain show through.
- **electrodes** — `radius`, `lift`, `labels` (channel names on every contact),
  and `depth_window`.

Hovering a contact shows its name whether or not `labels` is on.

## Things that will otherwise cost you an afternoon

**Use `--no-flat` when you re-run.** Importing flats calls pycortex's
`import_flat`, which deletes that subject's `overlays.svg` and cached flatmaps —
deliberately, since the flatmap geometry has changed and ROIs drawn on the old
one no longer apply. Nothing is backed up. It costs nothing on a fresh subject
and costs you your ROI drawings later.

**Don't use a `.venv` inside this repo.** A virtualenv with a *copied* install of
pycortex will silently give you upstream pycortex with none of the electrode
code. Always run against the `electrodes` checkout with `PYTHONPATH`, as above.

**The subject has to be in the pycortex filestore**, not merely present in
FreeSurfer. That is what step 1 does. `load_electrodes(..., subject="X")` will
read the montage happily and then fail to anchor if `X` was never imported.

**Electrodes are patient data.** The pycortex filestore lives inside the pycortex
repo, and imported subjects land in `filestore/db/<subject>/`. A blanket
`filestore` rule in that repo's `.gitignore` keeps them out of commits — but
`S1`, the demo subject, is tracked because it predates that rule, so the
mechanism is not uniform. Check `git status` before pushing, and note that a
static viewer bundle embeds electrode coordinates as readable JSON in
`index.html`.

## Reading the output

Step 3 prints an alignment report. pycortex keeps FreeSurfer's surface RAS, so
TkRegRAS coordinates should land directly on the surfaces, and a correctly
registered subdural grid gives a median offset of a millimetre or two. A large
one means the coordinates are not in the surfaces' space. The check is run on
grid and strip contacts only — depth electrodes are legitimately centimetres
from the pia and would make a healthy montage look broken.

Step 4 prints what the placement policy made of each contact:

- `on_surface` — inside the cortical ribbon
- `projected` — outside it but placeable: a subdural contact above the pia, or a
  depth contact below the white matter
- `non_cortical` — the *anatomical label* says white matter or a subcortical
  structure. The geometry cannot tell, since a contact in white matter still has
  cortex a millimetre away on some sulcal bank; only the label knows. Expect
  most of your depth contacts here.
- `too_far` — no cortical column can honestly claim it
- `no_coordinate` — a placeholder row for an unconnected amplifier channel

Nothing is ever dropped silently. Every contact keeps its coordinate and its
anchor and is merely marked.
