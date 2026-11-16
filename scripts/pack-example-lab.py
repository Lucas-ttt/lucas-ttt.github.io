"""Pack the example directory with canonical LF text for byte-level checks."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


folder = Path(__file__).resolve().parents[1] / "public/examples/agent-lab"
files = sorted(
    path for path in folder.rglob("*")
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
)
with ZipFile(folder.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
    for path in files:
        original = path.read_bytes()
        data = original.replace(b"\r\n", b"\n")
        if data != original:
            path.write_bytes(data)
        archive.write(path, "agent-lab/" + path.relative_to(folder).as_posix())
