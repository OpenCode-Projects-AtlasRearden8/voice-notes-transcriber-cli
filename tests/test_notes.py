from datetime import datetime

from vnt.notes import build_note, search_notes, slugify, write_note, yaml_value


def test_slugify_basic():
    assert slugify("Grocery list for the week!") == "grocery-list-for-the-week"


def test_slugify_unicode_and_empty():
    assert slugify("Café résumé") == "cafe-resume"
    assert slugify("!!!") == "voice-note"


def test_slugify_max_length_cuts_at_word():
    slug = slugify("one " + "x" * 80)
    assert len(slug) <= 60
    assert slug.count("---") == 0


def test_yaml_value_quotes_and_escapes():
    assert yaml_value('say "hi"') == '"say \\"hi\\""'
    assert yaml_value("my\nsummary") == '"my summary"'


def test_write_note_uses_year_month_folders(tmp_path):
    note_date = datetime(2026, 3, 5, 14, 30)
    path = write_note(
        tmp_path / "notes",
        title="Test Note",
        summary="A one-line summary.",
        transcript="hello\nworld",
        note_date=note_date,
        source_name="memo.m4a",
        transcriber="whisper-cli",
        summarizer="local-fallback",
    )
    expected = tmp_path / "notes" / "2026" / "03" / "2026-03-05-test-note.md"
    assert path == expected
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert 'title: "Test Note"' in content
    assert 'date: "2026-03-05 14:30"' in content
    assert "# Test Note" in content
    assert "## Transcript" in content
    assert "hello\nworld" in content


def test_write_note_collision_appends_counter(tmp_path):
    kwargs = dict(
        summary="s",
        transcript="t",
        note_date=datetime(2026, 6, 1, 9, 0),
        source_name="memo.m4a",
        transcriber="cmd",
        summarizer="local-fallback",
    )
    first = write_note(tmp_path / "notes", title="Same Title", **kwargs)
    second = write_note(tmp_path / "notes", title="Same Title", **kwargs)
    third = write_note(tmp_path / "notes", title="Same Title", **kwargs)
    assert first.name == "2026-06-01-same-title.md"
    assert second.name == "2026-06-01-same-title-2.md"
    assert third.name == "2026-06-01-same-title-3.md"


def test_search_notes_finds_matches(tmp_path):
    notes_dir = tmp_path / "notes"
    (notes_dir / "2026" / "10").mkdir(parents=True)
    (notes_dir / "2026" / "10" / "a.md").write_text("hello\neggs and coffee\n", encoding="utf-8")
    (notes_dir / "2026" / "10" / "b.md").write_text("nothing here\n", encoding="utf-8")
    results = search_notes(notes_dir, "EGGS")
    assert results and results[0][0].name == "a.md" and results[0][1] == 2
