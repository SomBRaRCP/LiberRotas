BEGIN;

CREATE TABLE IF NOT EXISTS media_variants (
  media_id UUID NOT NULL
    REFERENCES media_assets(media_id) ON DELETE CASCADE,
  variant TEXT NOT NULL
    CHECK (variant IN ('thumbnail', 'display')),
  bucket_name TEXT NOT NULL
    CHECK (char_length(bucket_name) BETWEEN 3 AND 222),
  object_key TEXT NOT NULL
    CHECK (
      char_length(object_key) BETWEEN 3 AND 1024
      AND object_key !~ '(^|/)\.\.($|/)'
      AND position(chr(92) IN object_key) = 0
      AND object_key !~ '^/'
    ),
  content_type TEXT NOT NULL
    CHECK (content_type = 'image/webp'),
  size_bytes BIGINT NOT NULL
    CHECK (size_bytes BETWEEN 1 AND 52428800),
  checksum_sha256 TEXT NOT NULL
    CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  crc32c TEXT
    CHECK (crc32c IS NULL OR char_length(crc32c) BETWEEN 1 AND 32),
  object_generation BIGINT
    CHECK (object_generation IS NULL OR object_generation > 0),
  width INTEGER NOT NULL CHECK (width > 0),
  height INTEGER NOT NULL CHECK (height > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (media_id, variant),
  UNIQUE (bucket_name, object_key)
);

CREATE INDEX IF NOT EXISTS idx_media_variants_media
  ON media_variants (media_id, variant);

INSERT INTO schema_migrations(version)
VALUES ('020_media_variants')
ON CONFLICT (version) DO NOTHING;

COMMIT;
