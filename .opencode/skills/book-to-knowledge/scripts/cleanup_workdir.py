"""
Cleanup temporary work directory for book-to-knowledge skill.
"""
import os
import shutil
import tempfile
from pathlib import Path

workdir = os.environ.get(
    "BOOK_SKILL_WORKDIR",
    str(Path(tempfile.gettempdir()) / "book_skill_work"),
)
if os.path.isdir(workdir):
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"cleaned: {workdir}")
else:
    print(f"nothing to clean: {workdir}")
