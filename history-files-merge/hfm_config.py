"""Central paths for the history-files-merge tools (standard library only).

Nothing here is machine-specific: PROJ comes from this file's location; the data folders come from environment
variables with a ~/Downloads default. Override per run, e.g.
    HFM_DATA_DONE=/Volumes/x/data.done HFM_SCRATCH=/tmp/hfm python3 -I session_tools_.../script.py ...

    PROJ      project folder (where this file lives)
    DL        HFM_DOWNLOADS   default ~/Downloads
    DD        HFM_DATA_DONE   default <DL>/data.done
    SCRATCH   HFM_SCRATCH     default <system temp>/hfm_scratch (created on first use by the scripts that need it)
"""
import os
import tempfile

PROJ = os.path.dirname(os.path.abspath(__file__))
DL = os.environ.get('HFM_DOWNLOADS', os.path.join(os.path.expanduser('~'), 'Downloads'))
DD = os.environ.get('HFM_DATA_DONE', os.path.join(DL, 'data.done'))
SCRATCH = os.environ.get('HFM_SCRATCH', os.path.join(tempfile.gettempdir(), 'hfm_scratch'))
