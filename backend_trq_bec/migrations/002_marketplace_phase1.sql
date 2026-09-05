BEGIN;

-- A Fase 1 admite somente um dispositivo ativo por identidade. Troca de
-- aparelho deve passar por recuperação explícita, nunca apenas por um ID token.
CREATE UNIQUE INDEX IF NOT EXISTS uq_device_keys_one_active_per_uid
  ON device_keys(firebase_uid) WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS merchant_accounts (
  firebase_uid TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  establishment_id TEXT NOT NULL UNIQUE,
  establishment_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED')),
  approved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
  product_id TEXT PRIMARY KEY CHECK (product_id ~ '^PROD-[A-Z0-9]{8,32}$'),
  merchant_uid TEXT NOT NULL REFERENCES merchant_accounts(firebase_uid),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  price_minor BIGINT NOT NULL CHECK (price_minor > 0),
  currency TEXT NOT NULL DEFAULT 'BRL' CHECK (currency ~ '^[A-Z]{3}$'),
  stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_merchant ON products(merchant_uid, created_at DESC);

CREATE TABLE IF NOT EXISTS live_offers (
  offer_id TEXT PRIMARY KEY CHECK (offer_id ~ '^OFFER-[A-Z0-9]{12,32}$'),
  token_ref TEXT NOT NULL UNIQUE,
  merchant_uid TEXT NOT NULL REFERENCES merchant_accounts(firebase_uid),
  product_id TEXT NOT NULL REFERENCES products(product_id),
  discount_type TEXT NOT NULL CHECK (discount_type IN ('PERCENT', 'FIXED_AMOUNT')),
  discount_value BIGINT NOT NULL CHECK (discount_value > 0),
  original_amount_minor BIGINT NOT NULL CHECK (original_amount_minor > 0),
  discount_amount_minor BIGINT NOT NULL CHECK (discount_amount_minor > 0),
  final_amount_minor BIGINT NOT NULL CHECK (final_amount_minor > 0),
  currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  maximum_redemptions INTEGER NOT NULL CHECK (maximum_redemptions > 0),
  redeemed_count INTEGER NOT NULL DEFAULT 0 CHECK (redeemed_count >= 0),
  maximum_per_user INTEGER NOT NULL DEFAULT 1 CHECK (maximum_per_user = 1),
  starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose = 'LIVE_FAIR_DISCOUNT'),
  status TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE', 'PAUSED', 'EXHAUSTED', 'EXPIRED', 'REVOKED', 'CANCELLED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (final_amount_minor = original_amount_minor - discount_amount_minor),
  CHECK (redeemed_count <= maximum_redemptions),
  CHECK (expires_at > starts_at)
);

CREATE INDEX IF NOT EXISTS idx_live_offers_merchant ON live_offers(merchant_uid, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_offers_expiry ON live_offers(status, expires_at);

ALTER TABLE coupon_tokens ADD COLUMN IF NOT EXISTS offer_id TEXT;
ALTER TABLE coupon_tokens ALTER COLUMN coupon_id DROP NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'coupon_tokens_offer_id_fkey'
  ) THEN
    ALTER TABLE coupon_tokens
      ADD CONSTRAINT coupon_tokens_offer_id_fkey
      FOREIGN KEY (offer_id) REFERENCES live_offers(offer_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'coupon_tokens_one_resource_chk'
  ) THEN
    ALTER TABLE coupon_tokens
      ADD CONSTRAINT coupon_tokens_one_resource_chk
      CHECK (num_nonnulls(coupon_id, offer_id) = 1);
  END IF;
END;
$$;

ALTER TABLE redemption_operations ADD COLUMN IF NOT EXISTS replay_jti TEXT;
UPDATE redemption_operations SET replay_jti = operation_id WHERE replay_jti IS NULL;
ALTER TABLE redemption_operations ALTER COLUMN replay_jti SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_redemption_replay_jti ON redemption_operations(replay_jti);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
  redemption_id UUID PRIMARY KEY,
  offer_id TEXT NOT NULL REFERENCES live_offers(offer_id),
  buyer_uid TEXT NOT NULL,
  device_key_id TEXT NOT NULL REFERENCES device_keys(device_key_id),
  operation_id TEXT NOT NULL UNIQUE REFERENCES redemption_operations(operation_id),
  status TEXT NOT NULL CHECK (status IN ('REDEEMED')),
  amount_saved_minor BIGINT NOT NULL CHECK (amount_saved_minor > 0),
  reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ledger_event_id TEXT,
  UNIQUE (offer_id, buyer_uid)
);

CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_buyer
  ON coupon_redemptions(buyer_uid, committed_at DESC);

INSERT INTO schema_migrations(version) VALUES ('002_marketplace_phase1')
ON CONFLICT (version) DO NOTHING;

COMMIT;
