import contextlib
import io
import os
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

import foldercompare
import make_sample


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a = self.root / "a"
        self.b = self.root / "b"
        self.a.mkdir()
        self.b.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, folder, name, data, stamp=1700000000):
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.utime(p, (stamp, stamp))


class TestCompare(Base):
    def test_identical_folders(self):
        self.put(self.a, "x.txt", b"1")
        self.put(self.b, "x.txt", b"1")
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["same"], ["x.txt"])
        self.assertEqual(r["different"] + r["only_a"] + r["only_b"], [])

    def test_only_in_one_side(self):
        self.put(self.a, "left.txt", b"1")
        self.put(self.b, "right.txt", b"1")
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["only_a"], ["left.txt"])
        self.assertEqual(r["only_b"], ["right.txt"])

    def test_different_content(self):
        self.put(self.a, "x.txt", b"abc")
        self.put(self.b, "x.txt", b"abd")
        self.assertEqual(foldercompare.compare(self.a, self.b)["different"], ["x.txt"])

    def test_different_size(self):
        self.put(self.a, "x.txt", b"abc")
        self.put(self.b, "x.txt", b"abcd")
        self.assertEqual(foldercompare.compare(self.a, self.b)["different"], ["x.txt"])

    def test_subfolders_use_forward_slashes(self):
        self.put(self.a, "d/e/x.txt", b"1")
        self.put(self.b, "d/e/x.txt", b"2")
        self.assertEqual(foldercompare.compare(self.a, self.b)["different"], ["d/e/x.txt"])

    def test_quick_mode_can_miss_a_change(self):
        self.put(self.a, "x.txt", b"100")
        self.put(self.b, "x.txt", b"900")
        self.assertEqual(foldercompare.compare(self.a, self.b, quick=True)["same"], ["x.txt"])
        self.assertEqual(foldercompare.compare(self.a, self.b, quick=False)["different"], ["x.txt"])

    def test_quick_mode_reads_files_when_times_differ(self):
        self.put(self.a, "x.txt", b"100", 1700000000)
        self.put(self.b, "x.txt", b"900", 1700005000)
        self.assertEqual(foldercompare.compare(self.a, self.b, quick=True)["different"], ["x.txt"])

    def test_default_is_byte_by_byte_with_different_times(self):
        self.put(self.a, "x.txt", b"100", 1700000000)
        self.put(self.b, "x.txt", b"100", 1700005000)
        self.assertEqual(foldercompare.compare(self.a, self.b)["same"], ["x.txt"])

    def test_empty_folders(self):
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["same"] + r["different"] + r["only_a"] + r["only_b"], [])

    def test_symlink_is_skipped(self):
        self.put(self.a, "real.txt", b"1")
        try:
            os.symlink(self.a / "real.txt", self.a / "link.txt")
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot make links")
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["skipped"], ["link.txt"])
        self.assertEqual(r["only_a"], ["real.txt"])

    def test_files_untouched_after_run(self):
        self.put(self.a, "x.txt", b"abc")
        self.put(self.b, "x.txt", b"abd")
        before = [(p.read_bytes(), p.stat().st_mtime) for p in (self.a / "x.txt", self.b / "x.txt")]
        foldercompare.compare(self.a, self.b)
        after = [(p.read_bytes(), p.stat().st_mtime) for p in (self.a / "x.txt", self.b / "x.txt")]
        self.assertEqual(before, after)
        self.assertEqual(sorted(os.listdir(self.a)), ["x.txt"])


def quiet_main(args):
    with contextlib.redirect_stdout(io.StringIO()):
        return foldercompare.main(args)


class TestEdges(Base):
    def test_empty_folder_only_on_one_side(self):
        (self.a / "empty").mkdir()
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["only_a"], ["empty/"])

    def test_empty_folder_in_both_is_same(self):
        (self.a / "empty").mkdir()
        (self.b / "empty").mkdir()
        self.assertEqual(foldercompare.compare(self.a, self.b)["same"], ["empty/"])

    def test_file_in_one_and_folder_in_other(self):
        self.put(self.a, "x", b"1")
        self.put(self.b, "x/y.txt", b"1")
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["only_a"], ["x"])
        self.assertEqual(r["only_b"], ["x/y.txt"])

    def test_unlistable_folder_makes_result_incomplete(self):
        self.put(self.a, "x.txt", b"1")

        def fake_walk(top, onerror=None, **kw):
            if str(top) == str(self.b) and onerror:
                onerror(PermissionError(13, "denied", str(self.b / "locked")))
            return iter([])

        with mock.patch("foldercompare.os.walk", fake_walk):
            r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["not_listed"], ["locked"])
        self.assertIn("INCOMPLETE", foldercompare.report(r, "a", "b"))
        with mock.patch("foldercompare.os.walk", fake_walk), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(foldercompare.main(["p", str(self.a), str(self.b)]), 1)

    def test_special_file_is_not_opened(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("this system has no named pipes")
        os.mkfifo(self.a / "pipe")
        os.mkfifo(self.b / "pipe")
        out = {}
        worker = threading.Thread(target=lambda: out.update(foldercompare.compare(self.a, self.b)), daemon=True)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "compare hung on a named pipe")
        self.assertEqual(out["skipped"], ["pipe", "pipe"])
        self.assertEqual(out["same"] + out["different"], [])

    def test_windows_junction_is_skipped(self):
        if os.name != "nt" or not hasattr(os.path, "isjunction"):
            self.skipTest("junctions are a Windows feature and need Python 3.12")
        self.put(self.root, "target/inside.txt", b"1")
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.a / "jn"), str(self.root / "target")],
                              capture_output=True)
        if made.returncode != 0:
            self.skipTest("could not make a junction here")
        r = foldercompare.compare(self.a, self.b)
        self.assertEqual(r["skipped"], ["jn/"])
        self.assertEqual(r["only_a"], [])

    def test_changed_file_seen_after_earlier_run(self):
        self.put(self.a, "x.txt", b"100")
        self.put(self.b, "x.txt", b"100")
        self.assertEqual(foldercompare.compare(self.a, self.b)["same"], ["x.txt"])
        self.put(self.b, "x.txt", b"900")
        self.assertEqual(foldercompare.compare(self.a, self.b)["different"], ["x.txt"])


class TestMain(Base):
    def test_exit_codes(self):
        self.put(self.a, "x.txt", b"1")
        self.put(self.b, "x.txt", b"1")
        self.assertEqual(quiet_main(["p", str(self.a), str(self.b)]), 0)
        self.put(self.b, "y.txt", b"1")
        self.assertEqual(quiet_main(["p", str(self.a), str(self.b)]), 1)

    def test_bad_arguments(self):
        self.assertEqual(quiet_main(["p", str(self.a)]), 2)
        self.assertEqual(quiet_main(["p", str(self.a), str(self.root / "nope")]), 2)

    def test_report_text(self):
        make_sample.make(self.root / "s")
        r = foldercompare.compare(self.root / "s" / "a", self.root / "s" / "b")
        text = foldercompare.report(r, "a", "b")
        self.assertIn("Only in the first folder: 1", text)
        self.assertIn("Only in the second folder: 1", text)
        self.assertIn("In both, different: 1", text)
        self.assertIn("price.txt", text)
        self.assertIn("In both, the same: 2", text)

    def test_sample_quick_mode_misses_price(self):
        make_sample.make(self.root / "s")
        r = foldercompare.compare(self.root / "s" / "a", self.root / "s" / "b", quick=True)
        self.assertEqual(r["different"], [])
        self.assertIn("price.txt", r["same"])
        self.assertIn("It can call two different files the same", foldercompare.report(r, "a", "b"))


class SetupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample = self.root / 'sample'

    def test_existing_folder_preserves_nested_bytes_and_metadata(self):
        (self.sample / 'nested').mkdir(parents=True)
        keep = self.sample / 'nested' / 'keep.bin'
        keep.write_bytes(b'KEEP')
        before = (keep.read_bytes(), keep.stat().st_mtime_ns)
        with self.assertRaises(FileExistsError):
            make_sample.make(self.sample)
        self.assertEqual(before, (keep.read_bytes(), keep.stat().st_mtime_ns))
        self.assertEqual(sorted(p.relative_to(self.sample).as_posix() for p in self.sample.rglob('*')), ['nested','nested/keep.bin'])

    def test_existing_file_preserved(self):
        self.sample.write_bytes(b'KEEP')
        before = (self.sample.read_bytes(), self.sample.stat().st_mtime_ns)
        with self.assertRaises(FileExistsError):
            make_sample.make(self.sample)
        self.assertEqual(before, (self.sample.read_bytes(), self.sample.stat().st_mtime_ns))

    def test_repeat_setup_preserves_generated_bytes_and_metadata(self):
        make_sample.make(self.sample)
        before = {p.relative_to(self.sample).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in self.sample.rglob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            make_sample.make(self.sample)
        self.assertEqual(before, {p.relative_to(self.sample).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in self.sample.rglob("*") if p.is_file()})

    def test_cli_refuses_without_replacing(self):
        import shutil, subprocess, sys
        script = self.root / 'make_sample.py'
        shutil.copyfile(Path(__file__).resolve().parent / 'make_sample.py', script)
        self.sample.mkdir()
        keep = self.sample / 'keep'
        keep.write_bytes(b'KEEP')
        result = subprocess.run([sys.executable,str(script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        self.assertIn('Nothing was replaced or deleted',result.stderr)
        self.assertEqual(keep.read_bytes(),b'KEEP')




if __name__ == "__main__":
    unittest.main()
