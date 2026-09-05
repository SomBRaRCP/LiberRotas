BEGIN;

-- A conta pode ser usada em mais de um aparelho. O primeiro vinculo fica
-- ativo; aparelhos adicionais aguardam confirmacao pelo e-mail cadastrado.
DROP INDEX IF EXISTS uq_device_keys_one_active_per_uid;

ALTER TABLE device_keys
  DROP CONSTRAINT IF EXISTS device_keys_status_check;

ALTER TABLE device_keys
  ADD CONSTRAINT device_keys_status_check
  CHECK (status IN ('ACTIVE', 'PENDING_APPROVAL', 'REVOKED'));

ALTER TABLE device_keys
  ADD COLUMN IF NOT EXISTS device_name TEXT,
  ADD COLUMN IF NOT EXISTS platform TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS model_name TEXT,
  ADD COLUMN IF NOT EXISTS app_version TEXT,
  ADD COLUMN IF NOT EXISTS approval_token_hash TEXT,
  ADD COLUMN IF NOT EXISTS approval_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approval_last_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS notification_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED';

ALTER TABLE device_keys
  DROP CONSTRAINT IF EXISTS device_keys_platform_check,
  DROP CONSTRAINT IF EXISTS device_keys_notification_status_check,
  DROP CONSTRAINT IF EXISTS device_keys_approval_hash_check,
  DROP CONSTRAINT IF EXISTS device_keys_approval_state_check,
  DROP CONSTRAINT IF EXISTS device_keys_device_name_length_check,
  DROP CONSTRAINT IF EXISTS device_keys_model_name_length_check,
  DROP CONSTRAINT IF EXISTS device_keys_app_version_length_check;

ALTER TABLE device_keys
  ADD CONSTRAINT device_keys_platform_check
    CHECK (platform IN ('android', 'ios', 'web', 'windows', 'macos', 'linux', 'unknown')),
  ADD CONSTRAINT device_keys_notification_status_check
    CHECK (notification_status IN ('NOT_REQUIRED', 'PENDING', 'SENT', 'NOT_CONFIGURED', 'FAILED')),
  ADD CONSTRAINT device_keys_approval_hash_check
    CHECK (approval_token_hash IS NULL OR approval_token_hash ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT device_keys_approval_state_check
    CHECK (
      (status = 'PENDING_APPROVAL' AND approval_token_hash IS NOT NULL AND approval_expires_at IS NOT NULL)
      OR
      (status <> 'PENDING_APPROVAL' AND approval_token_hash IS NULL AND approval_expires_at IS NULL)
    ),
  ADD CONSTRAINT device_keys_device_name_length_check
    CHECK (device_name IS NULL OR char_length(device_name) BETWEEN 1 AND 80),
  ADD CONSTRAINT device_keys_model_name_length_check
    CHECK (model_name IS NULL OR char_length(model_name) BETWEEN 1 AND 120),
  ADD CONSTRAINT device_keys_app_version_length_check
    CHECK (app_version IS NULL OR char_length(app_version) BETWEEN 1 AND 40);

CREATE INDEX IF NOT EXISTS idx_device_keys_uid_status_last_seen
  ON device_keys(firebase_uid, status, last_seen_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_device_keys_approval_token_hash
  ON device_keys(approval_token_hash)
  WHERE approval_token_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_device_keys_pending_approval_expiry
  ON device_keys(approval_expires_at)
  WHERE status = 'PENDING_APPROVAL';

INSERT INTO schema_migrations(version)
VALUES ('011_multi_device_account_security')
ON CONFLICT (version) DO NOTHING;

COMMIT;
