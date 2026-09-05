BEGIN;

CREATE TABLE IF NOT EXISTS marketplace_batch_idempotency (
  merchant_uid TEXT NOT NULL
    REFERENCES merchant_accounts(firebase_uid) ON DELETE CASCADE,
  client_request_id TEXT NOT NULL
    CHECK (char_length(client_request_id) BETWEEN 8 AND 100),
  operation_kind TEXT NOT NULL
    CHECK (operation_kind IN ('PRODUCT_ARCHIVE', 'OFFER_ACTION')),
  command_hash TEXT NOT NULL
    CHECK (command_hash ~ '^[0-9a-f]{64}$'),
  operation_id TEXT NOT NULL UNIQUE,
  response_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  PRIMARY KEY (merchant_uid, client_request_id),
  CHECK (
    (response_json IS NULL AND completed_at IS NULL)
    OR
    (response_json IS NOT NULL AND completed_at IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_marketplace_batch_idempotency_created
  ON marketplace_batch_idempotency(merchant_uid, created_at DESC);

INSERT INTO schema_migrations(version)
VALUES ('009_marketplace_batch_idempotency')
ON CONFLICT (version) DO NOTHING;

COMMIT;
