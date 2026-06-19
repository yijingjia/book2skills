from app.main import app


def test_collection_skills_router_is_registered():
    paths = {route.path for route in app.routes}

    assert "/api/collection-skills/{skill_id}" in paths
    assert "/api/collection-skills/{skill_id}/pack" in paths
    assert "/api/collection-skills/{skill_id}/download" in paths
