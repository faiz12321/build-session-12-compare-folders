"""Compares two folders and reports what is only in one, and what differs.

Read-only: it opens files to read them and never writes, moves or deletes anything.
Run: python foldercompare.py FOLDER_A FOLDER_B [--quick]
"""
import filecmp
import os
import sys


def list_files(root):
    """Return (files, skipped): relative paths of regular files, and links/odd entries skipped."""
    files, skipped = [], []
    for here, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(here, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full) or not os.path.isfile(full):
                skipped.append(rel)
            else:
                files.append(rel)
        for d in list(dirs):
            if os.path.islink(os.path.join(here, d)):
                skipped.append(os.path.relpath(os.path.join(here, d), root).replace(os.sep, "/") + "/")
                dirs.remove(d)
    return files, skipped


def compare(a, b, quick=False):
    files_a, skipped_a = list_files(a)
    files_b, skipped_b = list_files(b)
    set_a, set_b = set(files_a), set(files_b)
    result = {"only_a": sorted(set_a - set_b), "only_b": sorted(set_b - set_a),
              "same": [], "different": [], "unreadable": [],
              "skipped": sorted(skipped_a + skipped_b), "quick": quick}
    for rel in sorted(set_a & set_b):
        try:
            equal = filecmp.cmp(os.path.join(a, rel), os.path.join(b, rel), shallow=quick)
        except OSError:
            result["unreadable"].append(rel)
            continue
        result["same" if equal else "different"].append(rel)
    return result


def report(result, a, b):
    mode = "quick (size and modified time)" if result["quick"] else "byte by byte"
    lines = ["Compared %s and %s, %s." % (a, b, mode)]
    for key, label in (("only_a", "Only in the first folder"), ("only_b", "Only in the second folder"),
                       ("different", "In both, different"), ("unreadable", "In both, could not be read"),
                       ("skipped", "Skipped (links or special files)")):
        lines.append("%s: %d" % (label, len(result[key])))
        lines.extend("  " + name for name in result[key])
    lines.append("In both, the same: %d" % len(result["same"]))
    if result["quick"]:
        lines.append("Quick mode trusts size and modified time. It can call two different files the same.")
    return "\n".join(lines)


def main(argv):
    args = [x for x in argv[1:] if x != "--quick"]
    quick = "--quick" in argv[1:]
    if len(args) != 2:
        print("Usage: python foldercompare.py FOLDER_A FOLDER_B [--quick]")
        return 2
    for folder in args:
        if not os.path.isdir(folder):
            print("Not a folder: " + folder)
            return 2
    result = compare(args[0], args[1], quick)
    print(report(result, args[0], args[1]))
    found = result["only_a"] or result["only_b"] or result["different"] or result["unreadable"]
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
