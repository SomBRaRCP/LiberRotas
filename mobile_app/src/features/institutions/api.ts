import type { AuthenticatedRequest } from "@/api/http-client";

export type SupportBadge = "GREEN" | "YELLOW" | "RED";
export type InstitutionBadgePolicy = { green_percent: number; yellow_percent: number; red_percent: number };
export type InstitutionBadgeDistribution = { policy: InstitutionBadgePolicy; seller_badges: Record<string, SupportBadge> };

export type InstitutionGroup = {
  badge_policy: InstitutionBadgePolicy | null;
  group_id: string;
  owner_uid: string;
  name: string;
  description: string | null;
  city: string | null;
  status: "ACTIVE" | "CLOSED";
  created_at: string;
  updated_at: string;
  closed_at: string | null;
};

export type InstitutionMembershipStatus = "PENDING" | "ACTIVE" | "DECLINED" | "REMOVED" | "LEFT";

export type InstitutionMembership = {
  support_badge: SupportBadge | null;
  membership_id: string;
  group_id: string;
  group_name: string;
  institution_name: string;
  seller_uid: string;
  seller_name: string;
  status: InstitutionMembershipStatus;
  invited_at: string;
  responded_at: string | null;
  active_from: string | null;
  ended_at: string | null;
  updated_at: string;
};

export type InstitutionSalesCurrencyTotal = {
  currency: string;
  gross_original_amount_minor: number;
  gross_final_amount_minor: number;
  total_discount_amount_minor: number;
};

export type InstitutionSellerSales = {
  group_name: string;
  seller_name: string;
  membership_status: InstitutionMembershipStatus;
  active_from: string;
  ended_at: string | null;
  confirmed_redemptions: number;
  units_sold: number;
  amounts_unavailable_count: number;
  totals_by_currency: InstitutionSalesCurrencyTotal[];
};

export type InstitutionSalesReport = {
  period_from: string;
  period_to: string;
  group_filter: string | null;
  confirmed_redemptions: number;
  units_sold: number;
  amounts_unavailable_count: number;
  totals_by_currency: InstitutionSalesCurrencyTotal[];
  sellers: InstitutionSellerSales[];
  limit: number;
  offset: number;
  has_more: boolean;
  generated_at: string;
  financial_notice: string;
};

export type FundedEventEndMode = "TIME" | "COUPONS";
export type FundedEventStatus = "DRAFT" | "ACTIVE" | "ENDED";
export type FundedEventAllocationMode = "EQUAL" | "CUSTOM";

export type InstitutionFundedEventProductAllocation = {
  product_id: string;
  product_title: string;
  allocated_amount_minor: number;
  allocation_mode: FundedEventAllocationMode;
};

export type InstitutionFundedEventSellerAllocation = {
  membership_id: string;
  seller_uid: string;
  seller_name: string;
  allocated_amount_minor: number;
  allocation_mode: FundedEventAllocationMode;
  product_allocation_configured: boolean;
  product_allocations: InstitutionFundedEventProductAllocation[];
};

export type InstitutionFundedEvent = {
  badge_distribution: InstitutionBadgeDistribution | null;
  event_id: string;
  group_id: string;
  group_name: string;
  name: string;
  description: string | null;
  funding_source: "DONATION" | "INSTITUTION_BUDGET" | "OTHER";
  budget_amount_minor: number;
  currency: string;
  end_mode: FundedEventEndMode;
  starts_at: string;
  ends_at: string | null;
  coupon_limit: number | null;
  current_coupon_redemptions: number;
  status: FundedEventStatus;
  end_reason: "TIME" | "COUPONS" | "MANUAL" | null;
  created_at: string;
  updated_at: string;
  activated_at: string | null;
  ended_at: string | null;
  seller_allocations: InstitutionFundedEventSellerAllocation[];
};

export type EntrepreneurFundedEvent = {
  event_id: string;
  institution_name: string;
  group_name: string;
  name: string;
  description: string | null;
  allocated_amount_minor: number;
  currency: string;
  end_mode: FundedEventEndMode;
  starts_at: string;
  ends_at: string | null;
  coupon_limit: number | null;
  current_coupon_redemptions: number;
  status: FundedEventStatus;
  product_allocation_configured: boolean;
  product_allocations: InstitutionFundedEventProductAllocation[];
};

export type InstitutionFundedEventProductReport = {
  product_id: string;
  product_title: string;
  allocated_amount_minor: number;
  confirmed_redemptions: number;
  units_sold: number;
  gross_original_amount_minor: number;
  gross_final_amount_minor: number;
  discount_used_minor: number;
  amount_due_minor: number;
  unfunded_discount_minor: number;
  remaining_budget_minor: number;
};

export type InstitutionFundedEventSellerReport = {
  seller_uid: string;
  seller_name: string;
  allocated_amount_minor: number;
  confirmed_redemptions: number;
  units_sold: number;
  gross_original_amount_minor: number;
  gross_final_amount_minor: number;
  discount_used_minor: number;
  amount_due_minor: number;
  unfunded_discount_minor: number;
  remaining_budget_minor: number;
  products: InstitutionFundedEventProductReport[];
};

export type InstitutionFundedEventReport = {
  event: InstitutionFundedEvent;
  confirmed_redemptions: number;
  units_sold: number;
  gross_original_amount_minor: number;
  gross_final_amount_minor: number;
  discount_used_minor: number;
  amount_due_minor: number;
  unfunded_discount_minor: number;
  remaining_budget_minor: number;
  sellers: InstitutionFundedEventSellerReport[];
  generated_at: string;
  financial_notice: string;
};

export type EntrepreneurFundedEventReport = {
  event: EntrepreneurFundedEvent;
  confirmed_redemptions: number;
  units_sold: number;
  gross_original_amount_minor: number;
  gross_final_amount_minor: number;
  discount_used_minor: number;
  amount_due_minor: number;
  unfunded_discount_minor: number;
  remaining_budget_minor: number;
  products: InstitutionFundedEventProductReport[];
  generated_at: string;
  financial_notice: string;
};

export type InstitutionProfile = {
  firebase_uid: string;
  email: string;
  name: string;
  description: string | null;
  city: string | null;
  status: "ACTIVE" | "PENDING" | "SUSPENDED" | "DISABLED";
  created_at: string;
  updated_at: string;
};

export type InstitutionReportsSummary = {
  total_groups: number;
  active_groups: number;
  closed_groups: number;
  last_group_created_at: string | null;
  generated_at: string;
};

export type CreateInstitutionGroupInput = {
  name: string;
  description?: string;
  city?: string;
};

export type LoadInstitutionSalesReportInput = {
  groupId?: string;
  periodFrom: string;
  periodTo: string;
};

export type CreateInstitutionFundedEventInput = {
  groupId: string;
  name: string;
  description?: string;
  fundingSource: "DONATION" | "INSTITUTION_BUDGET" | "OTHER";
  budgetAmountMinor: number;
  endMode: FundedEventEndMode;
  startsAt: string;
  endsAt?: string;
  couponLimit?: number;
};

export type UpdateInstitutionProfileInput = {
  name?: string;
  description?: string | null;
  city?: string | null;
};

export function createInstitutionsApi(requestAuthenticated: AuthenticatedRequest) {
  async function createInstitutionGroup(input: CreateInstitutionGroupInput): Promise<InstitutionGroup> {
    return requestAuthenticated("POST", "/v1/institution/groups", {
      name: input.name.trim(),
      description: input.description?.trim() || null,
      city: input.city?.trim() || null,
    });
  }

  async function listInstitutionGroups(): Promise<InstitutionGroup[]> {
    const response = await requestAuthenticated<{ groups: InstitutionGroup[] }>("GET", "/v1/institution/groups");
    return response.groups;
  }

  function closeInstitutionGroup(groupId: string): Promise<InstitutionGroup> {
    return requestAuthenticated("POST", `/v1/institution/groups/${encodeURIComponent(groupId)}/close`);
  }

  function inviteInstitutionSeller(groupId: string, sellerName: string): Promise<InstitutionMembership> {
    return requestAuthenticated(
      "POST",
      `/v1/institution/groups/${encodeURIComponent(groupId)}/invitations`,
      { seller_name: sellerName.trim() },
    );
  }

  async function listInstitutionGroupMemberships(groupId: string): Promise<InstitutionMembership[]> {
    const memberships: InstitutionMembership[] = [];
    for (let offset = 0; offset <= 10_000; offset += 100) {
      const response = await requestAuthenticated<{ memberships: InstitutionMembership[]; has_more: boolean }>(
        "GET",
        `/v1/institution/groups/${encodeURIComponent(groupId)}/members?limit=100&offset=${offset}`,
      );
      memberships.push(...response.memberships);
      if (!response.has_more) break;
    }
    return memberships;
  }

  async function listEntrepreneurInstitutionMemberships(): Promise<InstitutionMembership[]> {
    const memberships: InstitutionMembership[] = [];
    for (let offset = 0; offset <= 10_000; offset += 100) {
      const response = await requestAuthenticated<{ memberships: InstitutionMembership[]; has_more: boolean }>(
        "GET",
        `/v1/entrepreneur/institution-invitations?limit=100&offset=${offset}`,
      );
      memberships.push(...response.memberships);
      if (!response.has_more) break;
    }
    return memberships;
  }

  function respondInstitutionInvitation(
    membershipId: string,
    decision: "ACCEPT" | "DECLINE",
  ): Promise<InstitutionMembership> {
    const action = decision === "ACCEPT" ? "accept" : "decline";
    return requestAuthenticated(
      "POST",
      `/v1/entrepreneur/institution-invitations/${encodeURIComponent(membershipId)}/${action}`,
    );
  }

  function leaveInstitutionMembership(membershipId: string): Promise<InstitutionMembership> {
    return requestAuthenticated(
      "POST",
      `/v1/entrepreneur/institution-memberships/${encodeURIComponent(membershipId)}/leave`,
    );
  }

  function removeInstitutionGroupMember(groupId: string, membershipId: string): Promise<InstitutionMembership> {
    return requestAuthenticated(
      "POST",
      `/v1/institution/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(membershipId)}/remove`,
    );
  }

  function loadInstitutionSalesReport(input: LoadInstitutionSalesReportInput): Promise<InstitutionSalesReport> {
    const groupFilter = input.groupId ? `&group_id=${encodeURIComponent(input.groupId)}` : "";
    return requestAuthenticated(
      "GET",
      `/v1/institution/reports/sales?from=${encodeURIComponent(input.periodFrom)}&to=${encodeURIComponent(input.periodTo)}${groupFilter}&limit=100&offset=0`,
    );
  }

  function createInstitutionFundedEvent(
    input: CreateInstitutionFundedEventInput,
  ): Promise<InstitutionFundedEvent> {
    return requestAuthenticated("POST", "/v1/institution/funded-events", {
      group_id: input.groupId,
      name: input.name.trim(),
      description: input.description?.trim() || null,
      funding_source: input.fundingSource,
      budget_amount_minor: input.budgetAmountMinor,
      currency: "BRL",
      end_mode: input.endMode,
      starts_at: input.startsAt,
      ends_at: input.endMode === "TIME" ? input.endsAt : null,
      coupon_limit: input.endMode === "COUPONS" ? input.couponLimit : null,
    });
  }

  async function listInstitutionFundedEvents(): Promise<InstitutionFundedEvent[]> {
    const response = await requestAuthenticated<{ events: InstitutionFundedEvent[] }>(
      "GET",
      "/v1/institution/funded-events?limit=100",
    );
    return response.events;
  }

  function setInstitutionFundedEventSellerAllocations(
    eventId: string,
    allocations: { sellerUid: string; allocatedAmountMinor: number }[],
  ): Promise<InstitutionFundedEvent> {
    return requestAuthenticated(
      "PUT",
      `/v1/institution/funded-events/${encodeURIComponent(eventId)}/seller-allocations`,
      {
        allocations: allocations.map((allocation) => ({
          seller_uid: allocation.sellerUid,
          allocated_amount_minor: allocation.allocatedAmountMinor,
        })),
      },
    );
  }

  function activateInstitutionFundedEvent(eventId: string): Promise<InstitutionFundedEvent> {
    return requestAuthenticated("POST", `/v1/institution/funded-events/${encodeURIComponent(eventId)}/activate`);
  }

  function endInstitutionFundedEvent(eventId: string): Promise<InstitutionFundedEvent> {
    return requestAuthenticated("POST", `/v1/institution/funded-events/${encodeURIComponent(eventId)}/end`);
  }

  function loadInstitutionFundedEventReport(eventId: string): Promise<InstitutionFundedEventReport> {
    return requestAuthenticated("GET", `/v1/institution/funded-events/${encodeURIComponent(eventId)}/report`);
  }

  async function listEntrepreneurFundedEvents(): Promise<EntrepreneurFundedEvent[]> {
    const response = await requestAuthenticated<{ events: EntrepreneurFundedEvent[] }>(
      "GET",
      "/v1/entrepreneur/funded-events?limit=100",
    );
    return response.events;
  }

  function loadEntrepreneurFundedEventReport(eventId: string): Promise<EntrepreneurFundedEventReport> {
    return requestAuthenticated("GET", `/v1/entrepreneur/funded-events/${encodeURIComponent(eventId)}/report`);
  }

  function setEntrepreneurFundedEventProductAllocations(
    eventId: string,
    allocations: { productId: string; allocatedAmountMinor: number }[],
  ): Promise<EntrepreneurFundedEvent> {
    return requestAuthenticated(
      "PUT",
      `/v1/entrepreneur/funded-events/${encodeURIComponent(eventId)}/product-allocations`,
      {
        allocations: allocations.map((allocation) => ({
          product_id: allocation.productId,
          allocated_amount_minor: allocation.allocatedAmountMinor,
        })),
      },
    );
  }

  function loadInstitutionProfile(): Promise<InstitutionProfile> {
    return requestAuthenticated("GET", "/v1/institution/profile");
  }

  function updateInstitutionProfile(input: UpdateInstitutionProfileInput): Promise<InstitutionProfile> {
    const body: UpdateInstitutionProfileInput = {};
    if (input.name !== undefined) body.name = input.name.trim();
    if (input.description !== undefined) body.description = input.description?.trim() || null;
    if (input.city !== undefined) body.city = input.city?.trim() || null;
    return requestAuthenticated("PATCH", "/v1/institution/profile", body);
  }

  function loadInstitutionReportsSummary(): Promise<InstitutionReportsSummary> {
    return requestAuthenticated("GET", "/v1/institution/reports/summary");
  }

  function setInstitutionBadgePolicy(groupId: string, policy: InstitutionBadgePolicy): Promise<InstitutionGroup> {
    return requestAuthenticated("PUT", `/v1/institution/groups/${encodeURIComponent(groupId)}/badge-policy`, policy);
  }

  function setInstitutionMemberBadge(groupId: string, membershipId: string, badge: SupportBadge): Promise<InstitutionMembership> {
    return requestAuthenticated("PUT", `/v1/institution/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(membershipId)}/badge`, { support_badge: badge });
  }

  function applyInstitutionEventBadges(eventId: string): Promise<InstitutionFundedEvent> {
    return requestAuthenticated("POST", `/v1/institution/funded-events/${encodeURIComponent(eventId)}/badge-allocations`);
  }

  return {
    setInstitutionBadgePolicy,
    setInstitutionMemberBadge,
    applyInstitutionEventBadges,
    activateInstitutionFundedEvent,
    closeInstitutionGroup,
    createInstitutionFundedEvent,
    createInstitutionGroup,
    endInstitutionFundedEvent,
    inviteInstitutionSeller,
    leaveInstitutionMembership,
    listEntrepreneurFundedEvents,
    listEntrepreneurInstitutionMemberships,
    listInstitutionFundedEvents,
    listInstitutionGroupMemberships,
    listInstitutionGroups,
    loadEntrepreneurFundedEventReport,
    loadInstitutionFundedEventReport,
    loadInstitutionProfile,
    loadInstitutionReportsSummary,
    loadInstitutionSalesReport,
    removeInstitutionGroupMember,
    respondInstitutionInvitation,
    setEntrepreneurFundedEventProductAllocations,
    setInstitutionFundedEventSellerAllocations,
    updateInstitutionProfile,
  };
}
