from fastapi.routing import APIRoute

from trq_bec.server.app import app
from trq_bec.server.routers.directory import router


def test_directory_router_preserves_public_contract() -> None:
    routes = {
        (route.path, next(iter(route.methods)), route.operation_id): route
        for route in router.routes
        if isinstance(route, APIRoute)
    }

    assert ("/v1/profile/public", "PUT", "upsertAuthoritativePublicProfile") in routes
    assert ("/v1/directory/profile", "PUT", "upsertAuthoritativeDirectoryProfile") in routes
    assert ("/v1/profile/public/{uid}", "GET", "getAuthoritativePublicProfile") in routes
    assert ("/v1/directory/profile/me", "GET", "getOwnAuthoritativeDirectoryProfile") in routes
    assert ("/v1/search", "GET", "searchLiberRotas") in routes
    assert routes[
        ("/v1/directory/profile", "PUT", "upsertAuthoritativeDirectoryProfile")
    ].include_in_schema is False
    assert routes[
        ("/v1/directory/profile/me", "GET", "getOwnAuthoritativeDirectoryProfile")
    ].include_in_schema is False


def test_directory_router_is_present_in_public_openapi() -> None:
    schema = app.openapi()

    assert schema["paths"]["/v1/profile/public"]["put"]["operationId"] == (
        "upsertAuthoritativePublicProfile"
    )
    assert schema["paths"]["/v1/profile/public/{uid}"]["get"]["operationId"] == (
        "getAuthoritativePublicProfile"
    )
    assert schema["paths"]["/v1/search"]["get"]["operationId"] == "searchLiberRotas"
    assert "/v1/directory/profile" not in schema["paths"]
    assert "/v1/directory/profile/me" not in schema["paths"]
