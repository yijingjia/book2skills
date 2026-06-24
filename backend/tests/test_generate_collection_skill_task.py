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


def test_checkpoint_scripts_includes_same_as_judgments():
    scripts = _checkpoint_scripts(
        {},
        "normalized_kus_ready",
        {
            "same_as_judgments.json": "[{\"decision\":\"same_as\"}]",
            "same_as_edges.json": "[]",
        },
    )

    assert scripts["pipeline_phase"] == "normalized_kus_ready"
    assert "same_as_judgments.json" in scripts


def test_collection_normalization_artifact_contract_keys():
    from app.pipeline.cross_book_normalizer import CrossBookNormalizationResult

    result = CrossBookNormalizationResult(
        source_kus={"knowledge_units": []},
        similarity_candidates={"pairs": []},
        same_as_judgments={"judgments": []},
        normalized_ku_groups={"groups": []},
        same_as_edges={"edges": []},
        deduped_view={"knowledge_units_count": 0, "knowledge_units": []},
        deduped_view_kus=[],
    )

    artifacts = {
        "source_kus.json": result.source_kus,
        "ku_similarity_candidates.json": result.similarity_candidates,
        "same_as_judgments.json": result.same_as_judgments,
        "same_as_edges.json": result.same_as_edges,
        "normalized_ku_groups.json": result.normalized_ku_groups,
        "deduped_view.json": result.deduped_view,
    }

    assert sorted(artifacts) == [
        "deduped_view.json",
        "ku_similarity_candidates.json",
        "normalized_ku_groups.json",
        "same_as_edges.json",
        "same_as_judgments.json",
        "source_kus.json",
    ]
