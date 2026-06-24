from pathlib import Path


def test_book2skills_mcp_server_registers_collection_tools():
    server_path = Path("scripts/book2skills_mcp_server.py")
    content = server_path.read_text(encoding="utf-8")

    expected_tools = [
        "book2skills_list_collections",
        "book2skills_create_collection",
        "book2skills_get_collection",
        "book2skills_generate_collection_skill",
        "book2skills_list_collection_skills",
        "book2skills_get_collection_skill",
        "book2skills_wait_collection_skill_ready",
        "book2skills_pack_collection_skill",
        "book2skills_retry_collection_skill",
        "book2skills_download_collection_skill",
    ]

    for tool_name in expected_tools:
        assert f"def {tool_name}" in content
