BEGIN;

ALTER TABLE private_messages
  ADD COLUMN IF NOT EXISTS media_id UUID
    REFERENCES media_assets(media_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_private_messages_media
  ON private_messages (media_id)
  WHERE media_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS community_post_comments (
  comment_id TEXT PRIMARY KEY
    CHECK (char_length(comment_id) BETWEEN 8 AND 160),
  post_id TEXT NOT NULL
    REFERENCES community_post_search(post_id) ON DELETE CASCADE,
  author_uid TEXT NOT NULL
    REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  parent_comment_id TEXT
    REFERENCES community_post_comments(comment_id) ON DELETE CASCADE,
  client_comment_id TEXT NOT NULL
    CHECK (char_length(client_comment_id) BETWEEN 8 AND 100),
  body TEXT NOT NULL
    CHECK (char_length(body) BETWEEN 1 AND 1000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (author_uid, client_comment_id),
  CHECK (parent_comment_id IS NULL OR parent_comment_id <> comment_id)
);

CREATE INDEX IF NOT EXISTS idx_community_post_comments_post
  ON community_post_comments (post_id, created_at, comment_id);

CREATE INDEX IF NOT EXISTS idx_community_post_comments_parent
  ON community_post_comments (parent_comment_id, created_at, comment_id)
  WHERE parent_comment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS community_comment_likes (
  comment_id TEXT NOT NULL
    REFERENCES community_post_comments(comment_id) ON DELETE CASCADE,
  firebase_uid TEXT NOT NULL
    REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (comment_id, firebase_uid)
);

CREATE INDEX IF NOT EXISTS idx_community_comment_likes_uid
  ON community_comment_likes (firebase_uid, created_at DESC);

INSERT INTO schema_migrations(version)
VALUES ('013_private_message_images_and_post_comments')
ON CONFLICT (version) DO NOTHING;

COMMIT;
