import json

from app.tasks.generate_collection_skill import _build_model_config, _checkpoint_scripts


def test_build_model_config_contains_models_without_keys(monkeypatch):
    monkeypatch.setattr("app.tasks.generate_collection_skill.settings.LLM_PROVIDER", "qwen")
    monkeypatch.setattr("app.tasks.generate_collection_skill.settings.QWEN_GENERATION_MODEL", "qwen-test")
    monkeypatch.setattr("app.tasks.generate_collection_skill.settings.QWEN_CHAT_MODEL", "qwen-chat")
    monkeypatch.setattr("app.tasks.generate_collection_skill.settings.EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr("app.tasks.generate_collection_skill.settings.OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    config = _build_model_config()

    assert config["llm_provider"] == "qwen"
    assert config["generation_model"] == "qwen-test"
    assert config["chat_model"] == "qwen-chat"
    assert "api_key" not in json.dumps(config).lower()


def test_checkpoint_scripts_accepts_metadata_keys():
    scripts = _checkpoint_scripts(
        existing={},
        phase="source_kus_loaded",
        artifacts={"model_config.json": json.dumps({"generation_model": "qwen-test"})},
    )

    assert scripts["pipeline_phase"] == "source_kus_loaded"
    assert "model_config.json" in scripts
