BEGIN;

CREATE TABLE IF NOT EXISTS media_assets (
  media_id UUID PRIMARY KEY,
  owner_user_id TEXT NOT NULL
    REFERENCES access_accounts(firebase_uid) ON DELETE RESTRICT,
  entity_type TEXT NOT NULL
    CHECK (entity_type IN (
      'user', 'entrepreneur', 'product', 'post', 'fair', 'institution', 'support'
    )),
  entity_id TEXT NOT NULL
    CHECK (char_length(entity_id) BETWEEN 1 AND 160),
  media_role TEXT NOT NULL
    CHECK (media_role IN (
      'avatar', 'entrepreneur_logo', 'institution_logo', 'product_image',
      'post_image', 'fair_cover', 'support_attachment'
    )),
  bucket_name TEXT NOT NULL
    CHECK (char_length(bucket_name) BETWEEN 3 AND 222),
  object_key TEXT NOT NULL
    CHECK (
      char_length(object_key) BETWEEN 3 AND 1024
      AND object_key !~ '(^|/)\.\.($|/)'
      AND position(chr(92) IN object_key) = 0
      AND object_key !~ '^/'
    ),
  original_filename TEXT NOT NULL
    CHECK (char_length(original_filename) BETWEEN 1 AND 255),
  declared_content_type TEXT NOT NULL
    CHECK (declared_content_type IN ('image/jpeg', 'image/png', 'image/webp')),
  detected_content_type TEXT
    CHECK (
      detected_content_type IS NULL
      OR detected_content_type IN ('image/jpeg', 'image/png', 'image/webp')
    ),
  declared_size_bytes BIGINT NOT NULL
    CHECK (declared_size_bytes BETWEEN 1 AND 52428800),
  size_bytes BIGINT
    CHECK (size_bytes IS NULL OR size_bytes BETWEEN 1 AND 52428800),
  checksum_sha256 TEXT
    CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'),
  crc32c TEXT
    CHECK (crc32c IS NULL OR char_length(crc32c) BETWEEN 1 AND 32),
  object_generation BIGINT
    CHECK (object_generation IS NULL OR object_generation > 0),
  width INTEGER CHECK (width IS NULL OR width > 0),
  height INTEGER CHECK (height IS NULL OR height > 0),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN (
      'pending', 'uploaded', 'processing', 'ready', 'rejected',
      'quarantined', 'deleted', 'orphaned'
    )),
  visibility TEXT NOT NULL DEFAULT 'restricted'
    CHECK (visibility IN ('private', 'public_processed', 'restricted')),
  moderation_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (moderation_status IN ('pending', 'approved', 'rejected', 'flagged')),
  rejection_reason TEXT
    CHECK (rejection_reason IS NULL OR char_length(rejection_reason) BETWEEN 3 AND 80),
  client_request_id TEXT NOT NULL
    CHECK (char_length(client_request_id) BETWEEN 8 AND 100),
  upload_expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  uploaded_at TIMESTAMPTZ,
  confirmed_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  created_by TEXT NOT NULL
    REFERENCES access_accounts(firebase_uid) ON DELETE RESTRICT,
  deleted_by TEXT
    REFERENCES access_accounts(firebase_uid) ON DELETE RESTRICT,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  UNIQUE (bucket_name, object_key),
  UNIQUE (owner_user_id, client_request_id),
  CHECK (
    (status = 'ready' AND detected_content_type IS NOT NULL AND size_bytes IS NOT NULL
      AND checksum_sha256 IS NOT NULL AND width IS NOT NULL AND height IS NOT NULL
      AND confirmed_at IS NOT NULL)
    OR status <> 'ready'
  ),
  CHECK (
    (status = 'deleted' AND deleted_at IS NOT NULL AND deleted_by IS NOT NULL)
    OR status <> 'deleted'
  )
);

CREATE INDEX IF NOT EXISTS idx_media_assets_owner_status_created
  ON media_assets (owner_user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_assets_entity_role_status
  ON media_assets (entity_type, entity_id, media_role, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_assets_pending_expiry
  ON media_assets (upload_expires_at)
  WHERE status IN ('pending', 'uploaded', 'processing');

CREATE INDEX IF NOT EXISTS idx_media_assets_orphaned
  ON media_assets (created_at)
  WHERE status = 'orphaned';

INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'media.upload'
  FROM access_accounts
 WHERE role IN ('visitor', 'entrepreneur', 'institution')
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'media.support'
  FROM access_accounts
 WHERE role = 'support'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'media.admin'
  FROM access_accounts
 WHERE role = 'admin'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('012_media_assets')
ON CONFLICT (version) DO NOTHING;

COMMIT;
