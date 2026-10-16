# Compare two fictional folders

Save three source files in a NEW empty lesson folder.

    python make_sample.py
    python foldercompare.py sample/a sample/b
    python -m unittest -v

Two Windows and two Ubuntu full replays run the exact visible source versions. Final 41 small fixture tests pass, with platform skips for Unix pipes on Windows and Windows junctions on Ubuntu. Symlink creation can skip where unavailable. Displayed stdout is first Windows output, not normalized or mixed. Pair differences are unittest time.
Link/error changes only: final comparer refuses root/ancestor symbolic links/reparse points and traversal. Tree aliases, hardlinks, special entries and metadata failures skip without opening and give incomplete exit 2. Read/list errors also change from prior exit 1 to error exit 2. Complete differences remain 1, complete agreement 0. Existing skipped-entry reports now return 2 instead of false clean success. The naive first version remains sample-only and must be replaced.
Original ordinary-file comparison, filecmp cache clearing, empty-folder reporting, ordering and quick-mode rules remain unchanged. Quick mode can call different contents the same when metadata agrees; even quick mode reads contents when times differ. Separate setup refuses existing paths, linked parents and traversal, without reset or deletion.
The final comparer has no write/move/delete/network code. No atomic snapshot, hostile-race defense or total time/memory limit. Stop editors/sync; files can change between checks. Paths can be private. Tests use small fictional fixtures, not every filesystem or backup verification. No desktop Windows/macOS recording. Recorder removes only its own temporary fixture folder. Decisions and feedback are teaching text, not recorded output.

MIT code. Python separately licensed/not included.

Reference: https://docs.python.org/3/library/os.html

Windows final pair: https://github.com/faiz12321/lesson-lab/actions/runs/38971477393
Ubuntu pair: https://github.com/faiz12321/lesson-lab/actions/runs/38971549237
