from fastapi.routing import APIRoute

from trq_bec.server.app import app
from trq_bec.server.routers.institutions import router


def _route_contract() -> set[tuple[str, str, str]]:
    return {
        (route.path, next(iter(route.methods)), route.operation_id)
        for route in router.routes
        if isinstance(route, APIRoute)
    }


def test_institutions_router_preserves_public_contract() -> None:
    routes = _route_contract()

    expected = {
        ("/v1/institution/profile", "GET", "getOwnInstitutionProfile"),
        ("/v1/institution/profile", "PATCH", "updateOwnInstitutionProfile"),
        ("/v1/institution/reports/summary", "GET", "getOwnInstitutionReportSummary"),
        ("/v1/institution/groups", "POST", "createInstitutionGroup"),
        ("/v1/institution/groups", "GET", "listInstitutionGroups"),
        ("/v1/institution/groups/{group_id}/close", "POST", "closeInstitutionGroup"),
        ("/v1/institution/groups/{group_id}/invitations", "POST", "inviteInstitutionSeller"),
        ("/v1/institution/groups/{group_id}/members", "GET", "listInstitutionGroupMembers"),
        ("/v1/entrepreneur/institution-invitations", "GET", "listOwnInstitutionInvitations"),
        ("/v1/entrepreneur/institution-invitations/{membership_id}/accept", "POST", "acceptInstitutionInvitation"),
        ("/v1/entrepreneur/institution-invitations/{membership_id}/decline", "POST", "declineInstitutionInvitation"),
        ("/v1/entrepreneur/institution-memberships/{membership_id}/leave", "POST", "leaveInstitutionMembership"),
        ("/v1/institution/groups/{group_id}/members/{membership_id}/remove", "POST", "removeInstitutionGroupMember"),
        ("/v1/institution/reports/sales", "GET", "getInstitutionSalesReport"),
        ("/v1/institution/funded-events", "POST", "createInstitutionFundedEvent"),
        ("/v1/institution/funded-events", "GET", "listInstitutionFundedEvents"),
        ("/v1/institution/funded-events/{event_id}/seller-allocations", "PUT", "setInstitutionEventSellerAllocations"),
        ("/v1/institution/funded-events/{event_id}/activate", "POST", "activateInstitutionFundedEvent"),
        ("/v1/institution/funded-events/{event_id}/end", "POST", "endInstitutionFundedEvent"),
        ("/v1/institution/funded-events/{event_id}/report", "GET", "getInstitutionFundedEventReport"),
        ("/v1/entrepreneur/funded-events", "GET", "listEntrepreneurFundedEvents"),
        ("/v1/entrepreneur/funded-events/{event_id}/report", "GET", "getEntrepreneurFundedEventReport"),
        ("/v1/entrepreneur/funded-events/{event_id}/product-allocations", "PUT", "setInstitutionEventProductAllocations"),
    }

    assert routes == expected


def test_institutions_router_is_present_in_public_openapi() -> None:
    schema = app.openapi()

    assert schema["paths"]["/v1/institution/groups"]["post"]["operationId"] == (
        "createInstitutionGroup"
    )
    assert schema["paths"]["/v1/institution/reports/sales"]["get"]["operationId"] == (
        "getInstitutionSalesReport"
    )
    assert schema["paths"]["/v1/institution/funded-events/{event_id}/report"]["get"][
        "operationId"
    ] == "getInstitutionFundedEventReport"
    assert schema["paths"]["/v1/entrepreneur/funded-events/{event_id}/product-allocations"]["put"][
        "operationId"
    ] == "setInstitutionEventProductAllocations"
