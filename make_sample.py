"""Makes two made-up folders, sample/a and sample/b.

Run: python make_sample.py
"""
import os
import sys
import stat
from pathlib import Path

STAMP = 1700000000  # one fixed modified time for every file, so size and time look alike

A = {"same.txt": b"hello\n", "notes/todo.txt": b"buy milk\n", "only_in_a.txt": b"left\n",
     "price.txt": b"price: 100\n"}
B = {"same.txt": b"hello\n", "notes/todo.txt": b"buy milk\n", "only_in_b.txt": b"right\n",
     "price.txt": b"price: 900\n"}  # same size as in a, different content


def write(folder, files):
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
        os.utime(path, (STAMP, STAMP))


def make(root):
    root = Path(root).absolute()
    if '..' in root.parts:
        raise OSError('Parent-traversal paths are unsupported.')
    for parent in reversed(root.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise OSError('Linked/reparse-point parents are unsupported.')
    root.mkdir()
    write(root / "a", A)
    write(root / "b", B)
    return root


if __name__ == "__main__":
    try:
        make(Path(__file__).absolute().parent / "sample")
    except FileExistsError:
        raise SystemExit("Stopped: sample already exists. Nothing was replaced or deleted.")
    print("Made sample/a and sample/b")
    sys.exit(0)
