BEGIN;

-- Permite combinar igualdade de TEXT com faixas de tempo em uma restrição
-- GiST. Isso protege também importações e manutenções futuras contra duas
-- filiações históricas sobrepostas para o mesmo vendedor.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Snapshot financeiro autoritativo do momento do resgate. Ofertas podem ser
-- alteradas depois; por isso relatorios nunca devem consultar o valor atual da
-- oferta para reconstruir uma venda passada.
ALTER TABLE coupon_redemptions
  ADD COLUMN IF NOT EXISTS merchant_uid TEXT,
  ADD COLUMN IF NOT EXISTS product_id TEXT,
  ADD COLUMN IF NOT EXISTS original_amount_minor BIGINT,
  ADD COLUMN IF NOT EXISTS final_amount_minor BIGINT,
  ADD COLUMN IF NOT EXISTS currency TEXT,
  ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS snapshot_quality TEXT NOT NULL DEFAULT 'CURRENT';

UPDATE coupon_redemptions AS redemption
   SET merchant_uid = offer.merchant_uid,
       product_id = COALESCE(
         NULLIF(operation.result_json ->> 'product_id', ''),
         offer.product_id
       ),
       final_amount_minor = CASE
         WHEN operation.result_json ->> 'final_amount_minor' ~ '^[0-9]+$'
           THEN (operation.result_json ->> 'final_amount_minor')::BIGINT
         ELSE NULL
       END,
       original_amount_minor = CASE
         WHEN operation.result_json ->> 'final_amount_minor' ~ '^[0-9]+$'
           THEN (operation.result_json ->> 'final_amount_minor')::BIGINT
                + redemption.amount_saved_minor
         ELSE NULL
       END,
       currency = offer.currency,
       snapshot_quality = CASE
         WHEN operation.result_json ->> 'final_amount_minor' ~ '^[0-9]+$'
           THEN 'LEGACY_RESULT'
         ELSE 'LEGACY_UNAVAILABLE'
       END
  FROM live_offers AS offer,
       redemption_operations AS operation
 WHERE offer.offer_id = redemption.offer_id
   AND operation.operation_id = redemption.operation_id
   AND (
     redemption.merchant_uid IS NULL
     OR redemption.product_id IS NULL
     OR redemption.currency IS NULL
     OR redemption.original_amount_minor IS NULL
     OR redemption.final_amount_minor IS NULL
   );

ALTER TABLE coupon_redemptions
  ALTER COLUMN merchant_uid SET NOT NULL,
  ALTER COLUMN product_id SET NOT NULL,
  ALTER COLUMN currency SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'coupon_redemptions_merchant_uid_fkey'
  ) THEN
    ALTER TABLE coupon_redemptions
      ADD CONSTRAINT coupon_redemptions_merchant_uid_fkey
      FOREIGN KEY (merchant_uid) REFERENCES merchant_accounts(firebase_uid);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'coupon_redemptions_product_id_fkey'
  ) THEN
    ALTER TABLE coupon_redemptions
      ADD CONSTRAINT coupon_redemptions_product_id_fkey
      FOREIGN KEY (product_id) REFERENCES products(product_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'coupon_redemptions_snapshot_amounts_chk'
  ) THEN
    ALTER TABLE coupon_redemptions
      ADD CONSTRAINT coupon_redemptions_snapshot_amounts_chk CHECK (
        (original_amount_minor IS NULL AND final_amount_minor IS NULL
          AND snapshot_quality = 'LEGACY_UNAVAILABLE')
        OR
        (original_amount_minor > 0 AND final_amount_minor > 0
          AND original_amount_minor >= final_amount_minor)
      );
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'coupon_redemptions_quantity_chk'
  ) THEN
    ALTER TABLE coupon_redemptions
      ADD CONSTRAINT coupon_redemptions_quantity_chk CHECK (quantity > 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'coupon_redemptions_currency_chk'
  ) THEN
    ALTER TABLE coupon_redemptions
      ADD CONSTRAINT coupon_redemptions_currency_chk CHECK (currency ~ '^[A-Z]{3}$');
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'coupon_redemptions_snapshot_quality_chk'
  ) THEN
    ALTER TABLE coupon_redemptions
      ADD CONSTRAINT coupon_redemptions_snapshot_quality_chk CHECK (
        snapshot_quality IN ('CURRENT', 'LEGACY_RESULT', 'LEGACY_UNAVAILABLE')
      );
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_merchant_committed
  ON coupon_redemptions(merchant_uid, committed_at DESC);

CREATE TABLE IF NOT EXISTS institution_group_memberships (
  membership_id TEXT PRIMARY KEY CHECK (membership_id ~ '^IGM-[A-Z0-9]{16,32}$'),
  group_id TEXT NOT NULL REFERENCES institution_groups(group_id) ON DELETE RESTRICT,
  merchant_uid TEXT NOT NULL REFERENCES merchant_accounts(firebase_uid) ON DELETE RESTRICT,
  invited_by_uid TEXT NOT NULL REFERENCES institutional_profiles(firebase_uid) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'ACTIVE', 'DECLINED', 'REMOVED', 'LEFT')),
  invited_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  responded_at TIMESTAMPTZ,
  active_from TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (status = 'PENDING' AND responded_at IS NULL AND active_from IS NULL AND ended_at IS NULL)
    OR (status = 'ACTIVE' AND responded_at IS NOT NULL AND active_from IS NOT NULL AND ended_at IS NULL)
    OR (status = 'DECLINED' AND responded_at IS NOT NULL AND active_from IS NULL AND ended_at IS NOT NULL)
    OR (status = 'REMOVED' AND responded_at IS NOT NULL AND ended_at IS NOT NULL)
    OR (status = 'LEFT' AND responded_at IS NOT NULL
        AND active_from IS NOT NULL AND ended_at IS NOT NULL)
  ),
  CHECK (active_from IS NULL OR active_from >= invited_at),
  CHECK (ended_at IS NULL OR ended_at >= invited_at),
  CHECK (active_from IS NULL OR ended_at IS NULL OR ended_at >= active_from)
);

-- Convites pendentes podem coexistir. Uma venda, porem, deve pertencer a uma
-- unica instituicao/grupo: o empreendedor so pode ter uma filiacao ativa.
CREATE UNIQUE INDEX IF NOT EXISTS uq_institution_membership_one_active_merchant
  ON institution_group_memberships(merchant_uid)
  WHERE status = 'ACTIVE';

CREATE UNIQUE INDEX IF NOT EXISTS uq_institution_membership_one_pending_group
  ON institution_group_memberships(group_id, merchant_uid)
  WHERE status = 'PENDING';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'institution_membership_no_time_overlap'
  ) THEN
    ALTER TABLE institution_group_memberships
      ADD CONSTRAINT institution_membership_no_time_overlap
      EXCLUDE USING gist (
        merchant_uid WITH =,
        tstzrange(active_from, ended_at, '[)') WITH &&
      )
      WHERE (active_from IS NOT NULL);
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_institution_memberships_group_status
  ON institution_group_memberships(group_id, status, invited_at DESC);
CREATE INDEX IF NOT EXISTS idx_institution_memberships_merchant_status
  ON institution_group_memberships(merchant_uid, status, invited_at DESC);

CREATE TABLE IF NOT EXISTS institution_membership_events (
  event_id TEXT PRIMARY KEY,
  membership_id TEXT NOT NULL
    REFERENCES institution_group_memberships(membership_id) ON DELETE RESTRICT,
  actor_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE RESTRICT,
  event_type TEXT NOT NULL
    CHECK (event_type IN ('INVITED', 'ACCEPTED', 'DECLINED', 'REMOVED', 'LEFT', 'GROUP_CLOSED')),
  previous_status TEXT,
  new_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (previous_status IS NULL OR previous_status IN ('PENDING', 'ACTIVE')),
  CHECK (new_status IN ('PENDING', 'ACTIVE', 'DECLINED', 'REMOVED', 'LEFT'))
);

CREATE INDEX IF NOT EXISTS idx_institution_membership_events_membership
  ON institution_membership_events(membership_id, created_at, event_id);

CREATE OR REPLACE FUNCTION reject_institution_membership_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'institution membership event ledger is append-only';
END;
$$;

DROP TRIGGER IF EXISTS institution_membership_events_no_update
  ON institution_membership_events;
CREATE TRIGGER institution_membership_events_no_update
BEFORE UPDATE OR DELETE ON institution_membership_events
FOR EACH ROW EXECUTE FUNCTION reject_institution_membership_event_mutation();

INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'institution.memberships.respond'
  FROM access_accounts
 WHERE role = 'entrepreneur'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('010_institution_seller_reports')
ON CONFLICT (version) DO NOTHING;

COMMIT;
