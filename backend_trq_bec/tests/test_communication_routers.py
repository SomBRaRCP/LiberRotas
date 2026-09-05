from fastapi.routing import APIRoute

from trq_bec.server.app import app
from trq_bec.server.routers.messaging import router as messaging_router
from trq_bec.server.routers.support import router as support_router


def _route_contract(router) -> set[tuple[str, str, str, bool]]:
    return {
        (route.path, next(iter(route.methods)), route.operation_id, route.include_in_schema)
        for route in router.routes
        if isinstance(route, APIRoute)
    }


def test_messaging_router_preserves_public_contract() -> None:
    routes = _route_contract(messaging_router)

    assert ("/v1/messages", "POST", "createDirectMessage", True) in routes
    assert ("/v1/messages/conversations", "GET", "listPrivateConversations", True) in routes
    assert (
        "/v1/messages/conversations/{conversation_id}",
        "GET",
        "getPrivateConversation",
        True,
    ) in routes
    assert (
        "/v1/messages/conversations/{conversation_id}/messages",
        "POST",
        "sendPrivateConversationMessage",
        True,
    ) in routes
    assert (
        "/v1/messages/conversations/{conversation_id}/read",
        "POST",
        "markPrivateConversationRead",
        True,
    ) in routes
    assert ("/v1/messages/blocks", "GET", "listMessageBlocks", True) in routes
    assert ("/v1/messages/blocks/{uid}", "POST", "blockMessageProfile", True) in routes
    assert ("/v1/messages/blocks/{uid}", "PUT", "putMessageBlock", False) in routes
    assert ("/v1/messages/blocks/{uid}", "DELETE", "unblockMessageProfile", True) in routes


def test_support_router_preserves_public_contract() -> None:
    routes = _route_contract(support_router)

    assert ("/v1/support/requests", "POST", "createSupportRequest", True) in routes
    assert ("/v1/support/requests", "GET", "listSupportRequests", True) in routes
    assert (
        "/v1/support/requests/{conversation_id}",
        "GET",
        "getSupportRequest",
        True,
    ) in routes
    assert (
        "/v1/support/requests/{conversation_id}/messages",
        "POST",
        "sendSupportRequestMessage",
        True,
    ) in routes
    assert (
        "/v1/support/requests/{conversation_id}/resolve",
        "POST",
        "resolveSupportRequest",
        True,
    ) in routes


def test_communication_routers_are_present_in_public_openapi() -> None:
    schema = app.openapi()

    assert schema["paths"]["/v1/messages"]["post"]["operationId"] == "createDirectMessage"
    assert schema["paths"]["/v1/messages/blocks/{uid}"]["post"]["operationId"] == (
        "blockMessageProfile"
    )
    assert "put" not in schema["paths"]["/v1/messages/blocks/{uid}"]
    assert schema["paths"]["/v1/support/requests"]["post"]["operationId"] == (
        "createSupportRequest"
    )
    assert schema["paths"]["/v1/support/requests/{conversation_id}/resolve"]["post"][
        "operationId"
    ] == "resolveSupportRequest"
