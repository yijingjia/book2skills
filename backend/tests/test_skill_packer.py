import zipfile

import pytest

from app.pipeline.packer import MissingReferencesError, SkillPacker


def test_pack_raises_when_references_required_and_missing(tmp_path):
    packer = SkillPacker()
    output = tmp_path / "skills.zip"

    with pytest.raises(MissingReferencesError):
        packer.pack(
            skill_md="# Router",
            references_dir=str(tmp_path / "missing-book-storage"),
            scripts={"metadata": {"generated_by": "agent"}},
            templates=None,
            output_path=str(output),
            book_title="Test Book",
            require_references=True,
        )

    assert not output.exists()


def test_pack_includes_references_when_present(tmp_path):
    storage = tmp_path / "book"
    references = storage / "references"
    references.mkdir(parents=True)
    (references / "index.json").write_text('{"chapters":[]}', encoding="utf-8")
    (references / "ch01.md").write_text("正文", encoding="utf-8")

    zip_path = SkillPacker().pack(
        skill_md="# Router",
        references_dir=str(storage),
        scripts={"metadata": {"generated_by": "agent"}},
        templates=None,
        output_path=str(tmp_path / "skills.zip"),
        book_title="Test Book",
        require_references=True,
    )

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    assert "references/index.json" in names
    assert "references/ch01.md" in names
    assert "manifest.json" in names
