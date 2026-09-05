BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS device_keys (
  device_key_id TEXT PRIMARY KEY,
  firebase_uid TEXT NOT NULL,
  public_key_b64u TEXT NOT NULL,
  algorithm TEXT NOT NULL CHECK (algorithm IN ('ED25519_LAB')),
  storage_profile TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  UNIQUE (firebase_uid, public_key_b64u)
);

CREATE INDEX IF NOT EXISTS idx_device_keys_uid ON device_keys(firebase_uid);

CREATE TABLE IF NOT EXISTS coupon_definitions (
  coupon_id TEXT PRIMARY KEY CHECK (coupon_id ~ '^FEITUR-[0-9]{3}$'),
  owner_uid TEXT,
  title TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  valid_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO coupon_definitions (coupon_id, owner_uid, title, active)
VALUES
  ('FEITUR-001', NULL, '10% OFF na Feijoada', TRUE),
  ('FEITUR-002', NULL, 'Tour em Dobro', TRUE),
  ('FEITUR-003', NULL, '15% OFF Artesanato', TRUE),
  ('FEITUR-004', NULL, 'Entrada Gratuita Expo', TRUE)
ON CONFLICT (coupon_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS coupon_tokens (
  token_ref TEXT PRIMARY KEY,
  jti TEXT NOT NULL UNIQUE,
  issuer_uid TEXT NOT NULL,
  issuer_ref TEXT NOT NULL,
  coupon_id TEXT NOT NULL REFERENCES coupon_definitions(coupon_id),
  intent_json JSONB NOT NULL,
  envelope_json JSONB NOT NULL,
  policy_version TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'ISSUED' CHECK (status IN ('ISSUED', 'REDEEMED', 'HELD', 'REVOKED', 'EXPIRED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  redeemed_at TIMESTAMPTZ,
  redeemed_operation_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_coupon_tokens_expiry ON coupon_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_coupon_tokens_issuer ON coupon_tokens(issuer_uid, created_at DESC);

CREATE TABLE IF NOT EXISTS redemption_operations (
  operation_id TEXT PRIMARY KEY,
  firebase_uid TEXT NOT NULL,
  session_id TEXT NOT NULL UNIQUE,
  token_ref TEXT NOT NULL REFERENCES coupon_tokens(token_ref),
  device_key_id TEXT NOT NULL REFERENCES device_keys(device_key_id),
  challenge_id TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMPLETED', 'STEP_UP_REQUIRED', 'HELD', 'DENIED', 'EXPIRED')),
  result_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_redemption_uid ON redemption_operations(firebase_uid, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
  seq BIGINT PRIMARY KEY,
  event_id UUID NOT NULL UNIQUE,
  wall_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  operation_id TEXT NOT NULL,
  suite_id TEXT NOT NULL,
  key_ref_token TEXT NOT NULL,
  event_type TEXT NOT NULL,
  result TEXT NOT NULL,
  reason_codes JSONB NOT NULL,
  evidence_refs JSONB NOT NULL,
  details_json JSONB NOT NULL,
  prev_hash TEXT NOT NULL CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
  event_hash TEXT NOT NULL UNIQUE CHECK (event_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS audit_checkpoints (
  checkpoint_id UUID PRIMARY KEY,
  first_seq BIGINT NOT NULL,
  last_seq BIGINT NOT NULL,
  root_hash TEXT NOT NULL CHECK (root_hash ~ '^[0-9a-f]{64}$'),
  policy_version TEXT NOT NULL,
  signature_b64u TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (last_seq, root_hash)
);

CREATE OR REPLACE FUNCTION reject_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit ledger is append-only';
END;
$$;

DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events;
CREATE TRIGGER audit_events_no_update
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

DROP TRIGGER IF EXISTS audit_checkpoints_no_update ON audit_checkpoints;
CREATE TRIGGER audit_checkpoints_no_update
BEFORE UPDATE OR DELETE ON audit_checkpoints
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

INSERT INTO schema_migrations(version) VALUES ('001_initial')
ON CONFLICT (version) DO NOTHING;

COMMIT;
