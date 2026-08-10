"""Shared sys.path bootstrap (recycle pass #9, 2026-08-10).

Every script used to copy its own sys.path hack to make Core's flat imports
(``import config``, ``from engine_data import ...``) resolvable. This is the
single place that logic lives now:

    import bootstrap          # adds repo root + Core/ to sys.path
    root_dir = bootstrap.ROOT # if the script needs the repo root

Works from any cwd: Python always puts the script's own directory on
sys.path, and bootstrap.py lives at the repo root.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(ROOT, 'Core')

for _p in (CORE, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
