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
            self.assertEqual(foldercompare.main(["p", str(self.a), str(self.b)]), 2)

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




class PathSafety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'sample'
        make_sample.make(self.root);self.file=self.root/'a'/'same.txt'
    def link(self,path,target,directory=False):
        try:path.symlink_to(target,target_is_directory=directory)
        except OSError:self.skipTest('Symlink creation unavailable')
    def code(self,path):
        with contextlib.redirect_stdout(io.StringIO()) as out:code=foldercompare.main(['foldercompare.py',str(path),str(self.root/'b')])
        return code,out.getvalue()
    def test_file_link_refuses(self):
        p=self.base/'linked';self.link(p,self.file)
        with self.assertRaises(OSError):foldercompare.safe_input(p,directory=True)
        self.assertEqual(self.code(p)[0],2)
    def test_linked_ancestor_refuses(self):
        p=self.base/'linked';self.link(p,self.root,True)
        self.assertEqual(self.code(p/'a')[0],2)
    def test_dangling_link_refuses(self):
        p=self.base/'linked';self.link(p,self.base/'missing')
        self.assertEqual(self.code(p)[0],2)
    def test_self_loop_refuses(self):
        p=self.base/'linked';self.link(p,p)
        self.assertEqual(self.code(p)[0],2)
    def test_hardlink_refuses(self):
        p=self.base/'hard';os.link(self.file,p)
        self.assertEqual(self.code(p)[0],2)
    def test_pipe_refuses_without_blocking(self):
        if not hasattr(os,'mkfifo'):self.skipTest('Unix pipe unavailable')
        p=self.base/'pipe';os.mkfifo(p)
        self.assertEqual(self.code(p)[0],2)
    def test_file_root_refuses(self):self.assertEqual(self.code(self.file)[0],2)
    def test_traversal_refuses(self):self.assertEqual(self.code(self.root/'..'/'sample'/'a')[0],2)
    def test_reparse_attribute_refuses(self):
        real=Path.lstat;target=self.root/'a'
        def fake(path,*args,**kwargs):
            value=real(path,*args,**kwargs)
            if path==target:return type('Reparse',(),{'st_mode':value.st_mode,'st_file_attributes':0x400})()
            return value
        with mock.patch.object(Path,'lstat',fake):self.assertEqual(self.code(target)[0],2)
    def test_metadata_failure_nonzero(self):
        with mock.patch.object(Path,'lstat',side_effect=OSError('forced metadata error')):
            code,text=self.code(self.file);self.assertEqual(code,2);self.assertIn('forced metadata error',text)
    def test_setup_linked_parent_refuses(self):
        p=self.base/'linked';self.link(p,self.root,True)
        with self.assertRaises(OSError):make_sample.make(p/'new')
        self.assertFalse((self.root/'new').exists())
    def test_setup_traversal_refuses(self):
        with self.assertRaises(OSError):make_sample.make(self.root/'..'/'new')


class TreeSafety(Base):
    def test_hardlinks_skipped_and_incomplete(self):
        self.put(self.a,'one',b'1');os.link(self.a/'one',self.a/'two')
        r=foldercompare.compare(self.a,self.b)
        self.assertEqual(r['skipped'],['one','two'])
        self.assertEqual(quiet_main(['p',str(self.a),str(self.b)]),2)
    def test_root_link_refuses(self):
        p=self.root/'alias'
        try:p.symlink_to(self.a,target_is_directory=True)
        except OSError:self.skipTest('Symlink creation unavailable')
        self.assertEqual(quiet_main(['p',str(p),str(self.b)]),2)
    def test_tree_metadata_error_is_incomplete(self):
        self.put(self.a,'one',b'1');real=Path.lstat
        def fake(p,*a,**kw):
            if p==self.a/'one':raise OSError('forced')
            return real(p,*a,**kw)
        with mock.patch.object(Path,'lstat',fake):
            self.assertEqual(quiet_main(['p',str(self.a),str(self.b)]),2)


if __name__ == "__main__":
    unittest.main()
