# -*- coding: utf-8 -*-
"""pytest: adds the project root to sys.path for `import pipeline`."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
