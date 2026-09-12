"""Point the app at a throwaway database/output dir before it is imported."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="tryon-tests-"))
os.environ["TRYON_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["TRYON_OUTPUT_DIR"] = str(_TMP / "outputs")
os.environ["TRYON_ENVIRONMENT"] = "test"
