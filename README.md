# Compare two folders

A small read-only Python tool built step by step. Give it two folders and it lists the files that are only in one of them and the files that are in both but different. By default it reads the files and compares them byte by byte. With `--quick` it trusts size and modified time, which is faster and can miss a change.

## Run it

    python make_sample.py                                     # makes sample/a and sample/b
    python foldercompare.py sample/a sample/b                 # byte by byte
    python foldercompare.py sample/a sample/b --quick         # size and modified time first
    python -m unittest -v                                     # twenty-two automated tests (some are skipped on systems that lack the feature)

On Windows, if `python` is not found, use `py`.

## Files

- `foldercompare.py` - the tool
- `make_sample.py` - makes two small made-up folders
- `test_foldercompare.py` - tests

## Setup safety and evidence

Setup refuses an existing sample path. It creates a new folder and exclusively writes eight fictional files in sample/a and sample/b. It never resets old data. Start in a new empty lesson folder. Four added collision/repeat checks preserve nested unrelated bytes and modification times. The checker is unchanged. Tests use small temporary fixtures, not all filesystems. Reports reveal file names and paths; keep private output private.

Two Windows and two Ubuntu recordings each ran 26 tests, with one platform-specific check skipped (named pipes on Windows, Windows junctions on Ubuntu). Each platform pair differs only in unittest time. Displays use first Windows output. Recorder writes exact visible first/final file versions into its own unique temporary folder and removes only that folder. Setup itself refuses a repeat run. Comparison exit 1 means differences or incomplete results.

## Notes

- Python's filecmp module, which this tool uses, treats two files as equal in its default shallow mode if their size and modified time match (https://docs.python.org/3/library/filecmp.html). The sample shows a file that this can miss.
- The tool only reads files. It does not copy, move or delete anything.
- Links, Windows junctions (Python 3.12 or later) and special files such as named pipes are listed as skipped and are never opened. The two folders you name are used as given, so do not name a link as a root.
- Empty folders are listed, with a slash after the name. Other folders are not listed on their own, only the files inside them.
- If a folder cannot be listed, the report says INCOMPLETE and the tool exits with 1, so the result is not mistaken for a full comparison.
- A file in one folder and a folder with the same name in the other are listed separately.
- Each run starts with a clean comparison cache, so a file changed since an earlier run in the same program is read again.
- File names are compared exactly as written, so names that differ only in letter case are listed as different files.
- Large folders were not tested, and reading every file can take a while.
- "In both, the same" means the compared bytes matched in the default mode. In --quick mode it means size and modified time matched, which is weaker. It does not compare permissions, owners or other file details.
- Tested only on small made-up folders. Python 3.10 (Linux) and, by GitHub Actions, Python 3.12 on Windows and Ubuntu. Not tested on a Windows 10 or 11 desktop.
- Educational example, no warranty. Use at your own risk.
- Code is MIT licensed (see LICENSE). Python is a separate project with its own license; this repository does not include it.
