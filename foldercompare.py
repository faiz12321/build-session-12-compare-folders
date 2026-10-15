"""Compares two folders and reports what is only in one, and what differs.

Read-only: it opens files to read them and never writes, moves or deletes anything.
Run: python foldercompare.py FOLDER_A FOLDER_B [--quick]
"""
import filecmp
import os
import sys


def is_link(path):
    """True for symbolic links and, on Python 3.12 and later, Windows junctions."""
    junction = getattr(os.path, "isjunction", None)
    return os.path.islink(path) or bool(junction and junction(path))


def list_files(root):
    """Return (entries, skipped, errors).

    entries: relative paths of regular files, plus empty folders written with a trailing slash.
    skipped: links, junctions and special files (they are never opened).
    errors: folders that could not be listed, so the result is incomplete.
    """
    entries, skipped, errors = [], [], []

    def note_error(error):
        errors.append(os.path.relpath(error.filename, root).replace(os.sep, "/") if error.filename else ".")

    for here, dirs, names in os.walk(root, onerror=note_error):
        dirs.sort()
        for d in list(dirs):
            full = os.path.join(here, d)
            if is_link(full):
                skipped.append(os.path.relpath(full, root).replace(os.sep, "/") + "/")
                dirs.remove(d)
        for name in sorted(names):
            full = os.path.join(here, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if is_link(full) or not os.path.isfile(full):
                skipped.append(rel)
            else:
                entries.append(rel)
        if not dirs and not names and here != str(root) and os.path.abspath(here) != os.path.abspath(root):
            entries.append(os.path.relpath(here, root).replace(os.sep, "/") + "/")
    return entries, skipped, errors


def compare(a, b, quick=False):
    filecmp.clear_cache()
    files_a, skipped_a, errors_a = list_files(a)
    files_b, skipped_b, errors_b = list_files(b)
    set_a, set_b = set(files_a), set(files_b)
    result = {"only_a": sorted(set_a - set_b), "only_b": sorted(set_b - set_a),
              "same": [], "different": [], "unreadable": [],
              "skipped": sorted(skipped_a + skipped_b),
              "not_listed": sorted(errors_a + errors_b), "quick": quick}
    for rel in sorted(set_a & set_b):
        if rel.endswith("/"):
            result["same"].append(rel)
            continue
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
    if result["not_listed"]:
        lines.append("INCOMPLETE: %d folder(s) could not be listed, so this result does not cover them:" % len(result["not_listed"]))
        lines.extend("  " + name for name in result["not_listed"])
    for key, label in (("only_a", "Only in the first folder"), ("only_b", "Only in the second folder"),
                       ("different", "In both, different"), ("unreadable", "In both, could not be read"),
                       ("skipped", "Skipped, not compared (links, junctions, special files)")):
        lines.append("%s: %d" % (label, len(result[key])))
        lines.extend("  " + name for name in result[key])
    lines.append("In both, the same: %d" % len(result["same"]))
    lines.append("Folders are listed only when empty, with a slash after the name.")
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
    found = (result["only_a"] or result["only_b"] or result["different"]
             or result["unreadable"] or result["not_listed"])
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
