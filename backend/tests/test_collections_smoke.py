from app.main import app


def test_collections_router_is_registered():
    paths = {route.path for route in app.routes}

    assert "/api/collections" in paths
    assert "/api/collections/{collection_id}" in paths
