from app.tasks.generate_collection_skill import _checkpoint_scripts, _render_collection_skill_report


def test_render_collection_skill_report_includes_sources():
    report = _render_collection_skill_report(
        collection_name="产品方法论合集",
        source_books=[{"title": "A"}, {"title": "B"}],
        consensus=[{"theme": "MVP", "supporting_book_count": 2, "confidence": 1.0}],
        candidate_tensions=[],
    )

    assert "产品方法论合集" in report
    assert "A" in report
    assert "MVP" in report


def test_checkpoint_scripts_preserves_existing_scripts_and_phase():
    scripts = _checkpoint_scripts(
        existing={"previous.json": "{}"},
        phase="normalized_kus_ready",
        artifacts={"deduped_view.json": "[1]"},
    )

    assert scripts["previous.json"] == "{}"
    assert scripts["deduped_view.json"] == "[1]"
    assert scripts["pipeline_phase"] == "normalized_kus_ready"
