BEGIN;

CREATE TABLE IF NOT EXISTS institution_funded_events (
  event_id TEXT PRIMARY KEY
    CHECK (event_id ~ '^IEVT-[A-Z0-9]{16,32}$'),
  owner_uid TEXT NOT NULL
    REFERENCES institutional_profiles(firebase_uid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL
    REFERENCES institution_groups(group_id) ON DELETE RESTRICT,
  name TEXT NOT NULL
    CHECK (char_length(name) BETWEEN 3 AND 160),
  description TEXT
    CHECK (description IS NULL OR char_length(description) <= 1000),
  funding_source TEXT NOT NULL
    CHECK (funding_source IN ('DONATION', 'INSTITUTION_BUDGET', 'OTHER')),
  budget_amount_minor BIGINT NOT NULL
    CHECK (budget_amount_minor BETWEEN 1 AND 100000000000),
  currency TEXT NOT NULL DEFAULT 'BRL'
    CHECK (currency ~ '^[A-Z]{3}$'),
  end_mode TEXT NOT NULL
    CHECK (end_mode IN ('TIME', 'COUPONS')),
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ,
  coupon_limit INTEGER,
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'ACTIVE', 'ENDED')),
  end_reason TEXT
    CHECK (end_reason IS NULL OR end_reason IN ('TIME', 'COUPONS', 'MANUAL')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  activated_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  CHECK (
    (end_mode = 'TIME' AND ends_at IS NOT NULL AND ends_at > starts_at
      AND coupon_limit IS NULL)
    OR
    (end_mode = 'COUPONS' AND ends_at IS NULL
      AND coupon_limit BETWEEN 1 AND 1000000)
  ),
  CHECK (
    (status = 'DRAFT' AND activated_at IS NULL AND ended_at IS NULL
      AND end_reason IS NULL)
    OR
    (status = 'ACTIVE' AND activated_at IS NOT NULL AND ended_at IS NULL
      AND end_reason IS NULL)
    OR
    (status = 'ENDED' AND ended_at IS NOT NULL AND end_reason IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_institution_funded_events_owner_status
  ON institution_funded_events(owner_uid, status, starts_at DESC);

CREATE INDEX IF NOT EXISTS idx_institution_funded_events_group_status
  ON institution_funded_events(group_id, status, starts_at DESC);

CREATE TABLE IF NOT EXISTS institution_event_seller_allocations (
  event_id TEXT NOT NULL
    REFERENCES institution_funded_events(event_id) ON DELETE RESTRICT,
  membership_id TEXT NOT NULL
    REFERENCES institution_group_memberships(membership_id) ON DELETE RESTRICT,
  seller_uid TEXT NOT NULL
    REFERENCES merchant_accounts(firebase_uid) ON DELETE RESTRICT,
  allocated_amount_minor BIGINT NOT NULL
    CHECK (allocated_amount_minor >= 0),
  allocation_mode TEXT NOT NULL DEFAULT 'EQUAL'
    CHECK (allocation_mode IN ('EQUAL', 'CUSTOM')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, seller_uid),
  UNIQUE (event_id, membership_id)
);

CREATE INDEX IF NOT EXISTS idx_institution_event_seller_uid
  ON institution_event_seller_allocations(seller_uid, event_id);

CREATE TABLE IF NOT EXISTS institution_event_product_allocations (
  event_id TEXT NOT NULL,
  seller_uid TEXT NOT NULL,
  product_id TEXT NOT NULL
    REFERENCES products(product_id) ON DELETE RESTRICT,
  allocated_amount_minor BIGINT NOT NULL
    CHECK (allocated_amount_minor >= 0),
  allocation_mode TEXT NOT NULL DEFAULT 'EQUAL'
    CHECK (allocation_mode IN ('EQUAL', 'CUSTOM')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, product_id),
  FOREIGN KEY (event_id, seller_uid)
    REFERENCES institution_event_seller_allocations(event_id, seller_uid)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_institution_event_products_seller
  ON institution_event_product_allocations(event_id, seller_uid, product_id);

INSERT INTO account_permissions(firebase_uid, permission)
SELECT firebase_uid, 'institution.events.manage'
  FROM access_accounts
 WHERE role = 'institution'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO account_permissions(firebase_uid, permission)
SELECT firebase_uid, 'institution.event_allocations.manage'
  FROM access_accounts
 WHERE role = 'entrepreneur'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('014_institution_funded_events')
ON CONFLICT (version) DO NOTHING;

COMMIT;
