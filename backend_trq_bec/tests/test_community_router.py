from fastapi.routing import APIRoute

from trq_bec.server.app import app
from trq_bec.server.routers.community import router


def _route_contract() -> set[tuple[str, str, str]]:
    return {
        (route.path, next(iter(route.methods)), route.operation_id)
        for route in router.routes
        if isinstance(route, APIRoute)
    }


def test_community_router_preserves_public_contract() -> None:
    routes = _route_contract()

    assert ("/v1/feed/posts/{post_id}/comments", "GET", "listPostComments") in routes
    assert ("/v1/feed/posts/{post_id}/comments", "POST", "createPostComment") in routes
    assert ("/v1/feed/comments/{comment_id}", "PATCH", "updatePostComment") in routes
    assert ("/v1/feed/comments/{comment_id}", "DELETE", "deletePostComment") in routes
    assert ("/v1/feed/comments/{comment_id}/like", "PUT", "likePostComment") in routes
    assert ("/v1/feed/comments/{comment_id}/like", "DELETE", "unlikePostComment") in routes
    assert ("/v1/community/posts", "POST", "createCommunityPost") in routes
    assert ("/v1/community/posts/{post_id}", "PATCH", "updateCommunityPost") in routes
    assert ("/v1/community/posts/{post_id}", "DELETE", "deleteCommunityPost") in routes
    assert ("/v1/community/places", "POST", "createCuratedPlace") in routes
    assert ("/v1/community/places/{place_id}", "DELETE", "deleteCuratedPlace") in routes
    assert ("/v1/community/live-fairs", "POST", "createLiveFair") in routes
    assert ("/v1/community/live-fairs/{fair_id}/end", "POST", "endLiveFair") in routes
    assert ("/v1/community/live-fairs/{fair_id}", "DELETE", "deleteLiveFair") in routes


def test_community_router_is_present_in_public_openapi() -> None:
    schema = app.openapi()

    assert schema["paths"]["/v1/community/posts"]["post"]["operationId"] == (
        "createCommunityPost"
    )
    assert schema["paths"]["/v1/feed/posts/{post_id}/comments"]["post"]["operationId"] == (
        "createPostComment"
    )
    assert schema["paths"]["/v1/feed/comments/{comment_id}/like"]["delete"][
        "operationId"
    ] == "unlikePostComment"
    assert schema["paths"]["/v1/community/live-fairs/{fair_id}/end"]["post"][
        "operationId"
    ] == "endLiveFair"
    assert schema["paths"]["/v1/community/live-fairs/{fair_id}"]["delete"][
        "operationId"
    ] == "deleteLiveFair"
