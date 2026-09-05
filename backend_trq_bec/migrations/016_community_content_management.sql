BEGIN;

ALTER TABLE community_post_comments
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

INSERT INTO schema_migrations(version)
VALUES ('016_community_content_management')
ON CONFLICT (version) DO NOTHING;

COMMIT;
