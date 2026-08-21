"""Show a subject's electrodes in the pycortex viewer.

Assumes the subject is already in the pycortex database. If it is not, import it
once with electrodes_new_subject.py, or:

    cortex.freesurfer.import_subj("TCH06", whitematter_surf="white")
    cortex.freesurfer.import_flat("TCH06", patch="flat")

    python show_electrodes.py TCH06
"""

import os
import sys

import cortex

subject = sys.argv[1] if len(sys.argv) > 1 else "TCH06"
elecs = os.path.join(os.environ["SUBJECTS_DIR"], subject, "elecs", "TDT_elecs_all.mat")

electrodes = cortex.electrodes.load_electrodes(elecs, subject=subject)
cortex.webgl.show(cortex.electrodes.blank(subject), electrodes=electrodes)
