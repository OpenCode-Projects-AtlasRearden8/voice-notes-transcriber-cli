from pathlib import Path

from conftest import make_asr_command

DEAD_ENDPOINT = "http://127.0.0.1:9/v1"


def note_paths(notes_dir: Path) -> list[Path]:
    return sorted(notes_dir.rglob("*.md"))


def test_process_with_offline_local_asr(tmp_path, run_cli):
    audio = tmp_path / "memo1.m4a"
    audio.write_bytes(b"not-really-audio")
    (tmp_path / "memo1.m4a.expected.txt").write_text(
        "Please buy eggs and coffee.", encoding="utf-8"
    )
    cmd = make_asr_command()
    notes_dir = tmp_path / "notes"
    rc = run_cli([
        "process",
        "--asr-command", cmd,
        "--notes-dir", notes_dir,
        "--base-url", DEAD_ENDPOINT,
        "--offline",  # endpoint skipped entirely; local heuristic summary
        str(audio),
    ])
    assert rc == 0
    notes = note_paths(notes_dir)
    assert len(notes) == 1
    # Goes into notes/<year>/<month> based on the audio file's mtime.
    parts = notes[0].parent.relative_to(notes_dir).parts
    assert len(parts) == 2
    assert all(part.isdigit() and len(part) in (2, 4) for part in parts)
    content = notes[0].read_text(encoding="utf-8")
    assert "Please buy eggs and coffee." in content
    assert "## Transcript" in content
    assert 'transcriber: "fake_asr.py"' in content
    assert 'summarizer: "local-fallback"' in content


def test_process_with_endpoint_for_everything(tmp_path, run_cli, server):
    audio = tmp_path / "memo2.m4a"
    audio.write_bytes(b"not-really-audio")
    notes_dir = tmp_path / "notes"
    rc = run_cli([
        "process",
        "--notes-dir", notes_dir,
        "--base-url", server.base_url,
        str(audio),
    ])
    assert rc == 0
    notes = note_paths(notes_dir)
    assert len(notes) == 1
    content = notes[0].read_text(encoding="utf-8")
    assert "<h1>Fake Title</h1>" not in content and "# Fake Title" in content
    assert "TRANSCRIPT FROM memo2.m4a" in content
    assert 'transcriber: "endpoint:fake-whisper"' in content
    assert 'summarizer: "endpoint:fake-llm"' in content


def test_process_falls_back_to_endpoint_when_command_fails(tmp_path, run_cli, server):
    audio = tmp_path / "memo3.m4a"
    audio.write_bytes(b"not-really-audio")
    notes_dir = tmp_path / "notes"
    rc = run_cli([
        "process",
        "--asr-command", "definitely-not-a-real-command-xyz {input}",
        "--notes-dir", notes_dir,
        "--base-url", server.base_url,
        str(audio),
    ])
    assert rc == 0
    content = note_paths(notes_dir)[0].read_text(encoding="utf-8")
    assert "TRANSCRIPT FROM memo3.m4a" in content
    assert "# Fake Title" in content


def test_process_all_backends_fail_returns_error(tmp_path, run_cli, monkeypatch):
    audio = tmp_path / "memo4.m4a"
    audio.write_bytes(b"not-really-audio")
    monkeypatch.setenv("VNT_NOTES_DIR", str(tmp_path / "notes"))
    monkeypatch.setenv("VNT_BASE_URL", "http://127.0.0.1:9/v1")
    rc = run_cli(["process", str(audio)])
    assert rc == 1
    assert note_paths(tmp_path / "notes") == []


def test_dry_run_writes_nothing(tmp_path, run_cli):
    audio = tmp_path / "memo5.m4a"
    audio.write_bytes(b"not-really-audio")
    (tmp_path / "memo5.m4a.expected.txt").write_text("hello there", encoding="utf-8")
    notes_dir = tmp_path / "notes"
    rc = run_cli([
        "process", "--offline",
        "--asr-command", make_asr_command(),
        "--notes-dir", notes_dir,
        str(audio), "--dry-run",
    ])
    assert rc == 0
    assert not notes_dir.exists()


def test_folder_with_and_without_recursive(tmp_path, run_cli):
    (tmp_path / "a.m4a").write_bytes(b"a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.m4a").write_bytes(b"b")
    notes_dir = tmp_path / "notes"
    cmd = make_asr_command()

    rc = run_cli([
        "process", "--offline",
        "--asr-command", cmd,
        "--notes-dir", notes_dir,
        "--date", "2025-05-04",
        str(tmp_path),
    ])
    top_only = note_paths(notes_dir)
    assert rc == 0
    assert len(top_only) == 1
    assert "2025/05" in str(top_only[0].parent)

    rc = run_cli([
        "process", "--offline", "--recursive",
        "--asr-command", cmd,
        "--notes-dir", notes_dir,
        "--date", "2025-05-04",
        str(tmp_path),
    ])
    assert rc == 0
    names = [n.name for n in note_paths(notes_dir)]
    assert len(names) == 3  # 1 existing + a.m4a (collision -2) + new b.m4a note


def test_unsupported_extension_is_skipped(tmp_path, run_cli):
    audio = tmp_path / "notes.docx"
    audio.write_bytes(b"doc")
    notes_dir = tmp_path / "notes"
    rc = run_cli([
        "process", "--offline",
        "--asr-command", make_asr_command(),
        "--notes-dir", notes_dir,
        str(audio),
    ])
    assert rc == 2
    assert note_paths(notes_dir) == []


def test_bare_paths_default_to_process(tmp_path, run_cli):
    audio = tmp_path / "memo6.m4a"
    audio.write_bytes(b"x")
    (tmp_path / "memo6.m4a.expected.txt").write_text("bare path input", encoding="utf-8")
    notes_dir = tmp_path / "notes"
    rc = run_cli([
        str(audio),
        "--offline",
        "--asr-command", make_asr_command(),
        "--notes-dir", notes_dir,
    ])
    assert rc == 0
    assert len(note_paths(notes_dir)) == 1


def test_search(tmp_path, run_cli):
    notes_dir = tmp_path / "notes" / "2026" / "10"
    notes_dir.mkdir(parents=True)
    (notes_dir / "2026-10-01-a.md").write_text("eggs and coffee\n", encoding="utf-8")
    (notes_dir / "2026-10-02-b.md").write_text("nothing to see\n", encoding="utf-8")
    rc = run_cli(["search", "eggs", "--notes-dir", tmp_path / "notes"])
    assert rc == 0
    rc = run_cli(["search", "zebra", "--notes-dir", tmp_path / "notes"])
    assert rc == 1


def test_init_creates_config(tmp_path, monkeypatch, run_cli):
    monkeypatch.chdir(tmp_path)
    rc = run_cli(["init"])
    assert rc == 0
    cfg = tmp_path / "vnt.toml"
    assert cfg.exists()
    assert "asr_command" in cfg.read_text(encoding="utf-8")
    rc = run_cli(["init"])  # second run refuses to overwrite
    assert rc == 2


def test_config_file_is_used(tmp_path, run_cli):
    audio = tmp_path / "memo7.m4a"
    audio.write_bytes(b"x")
    (tmp_path / "memo7.m4a.expected.txt").write_text("configured notes dir", encoding="utf-8")
    cfg = tmp_path / "my.toml"
    my_cmd = make_asr_command()
    cfg.write_text(
        f'notes_dir = "{tmp_path / "renamed"}"\nasr_command = "{my_cmd}"\noffline = true\n',
        encoding="utf-8",
    )
    rc = run_cli([str(audio), "--config", cfg])
    assert rc == 0
    assert note_paths(tmp_path / "renamed")


def test_doctor_reports_problems(tmp_path, run_cli, server):
    audio_cfg = tmp_path / "vnt.toml"
    rc = run_cli([
        "doctor",
        "--notes-dir", tmp_path / "notes",
        "--base-url", server.base_url,
        "--asr-command", "missing-command-123 {input}",
    ])
    assert rc == 0  # endpoint reachable counts as an available route
    rc = run_cli([
        "doctor",
        "--notes-dir", tmp_path / "notes",
        "--base-url", DEAD_ENDPOINT,
    ])
    assert rc == 1  # no ASR configured and endpoint unreachable
