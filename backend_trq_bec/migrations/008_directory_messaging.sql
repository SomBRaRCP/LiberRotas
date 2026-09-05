BEGIN;

CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS public_profile_directory (
  firebase_uid TEXT PRIMARY KEY REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 3 AND 60),
  normalized_name TEXT NOT NULL UNIQUE CHECK (char_length(normalized_name) BETWEEN 3 AND 120),
  role TEXT NOT NULL CHECK (role IN ('visitor', 'entrepreneur', 'institution')),
  city TEXT NOT NULL CHECK (char_length(city) BETWEEN 2 AND 120),
  address TEXT CHECK (address IS NULL OR char_length(address) BETWEEN 3 AND 240),
  category TEXT NOT NULL DEFAULT '' CHECK (char_length(category) <= 160),
  interests JSONB NOT NULL DEFAULT '[]'::jsonb,
  avatar_uri TEXT CHECK (avatar_uri IS NULL OR char_length(avatar_uri) <= 4096),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_public_profile_directory_name
  ON public_profile_directory (normalized_name);
CREATE INDEX IF NOT EXISTS idx_public_profile_directory_role
  ON public_profile_directory (role, updated_at DESC);

CREATE TABLE IF NOT EXISTS community_post_search (
  post_id TEXT PRIMARY KEY,
  author_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
  created_at TIMESTAMPTZ NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_community_post_search_created
  ON community_post_search (created_at DESC);

CREATE TABLE IF NOT EXISTS private_conversations (
  conversation_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('DIRECT', 'SUPPORT')),
  status TEXT NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN', 'IN_PROGRESS', 'WAITING_USER', 'RESOLVED', 'CLOSED')),
  subject TEXT CHECK (subject IS NULL OR char_length(subject) BETWEEN 3 AND 160),
  created_by_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  requester_uid TEXT REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  assigned_support_uid TEXT REFERENCES access_accounts(firebase_uid) ON DELETE SET NULL,
  direct_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_message_at TIMESTAMPTZ,
  CHECK (
    (kind = 'DIRECT' AND direct_key IS NOT NULL AND requester_uid IS NULL AND subject IS NULL)
    OR
    (kind = 'SUPPORT' AND direct_key IS NULL AND requester_uid IS NOT NULL AND subject IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS private_conversation_members (
  conversation_id TEXT NOT NULL REFERENCES private_conversations(conversation_id) ON DELETE CASCADE,
  firebase_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (conversation_id, firebase_uid)
);

CREATE INDEX IF NOT EXISTS idx_private_conversation_members_uid
  ON private_conversation_members (firebase_uid, conversation_id);

CREATE TABLE IF NOT EXISTS private_messages (
  message_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES private_conversations(conversation_id) ON DELETE CASCADE,
  sender_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  client_message_id TEXT NOT NULL CHECK (char_length(client_message_id) BETWEEN 8 AND 100),
  body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (sender_uid, client_message_id)
);

CREATE INDEX IF NOT EXISTS idx_private_messages_conversation
  ON private_messages (conversation_id, created_at, message_id);

CREATE TABLE IF NOT EXISTS private_conversation_reads (
  conversation_id TEXT NOT NULL REFERENCES private_conversations(conversation_id) ON DELETE CASCADE,
  firebase_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  read_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (conversation_id, firebase_uid)
);

CREATE TABLE IF NOT EXISTS message_blocks (
  blocker_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  blocked_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (blocker_uid, blocked_uid),
  CHECK (blocker_uid <> blocked_uid)
);

INSERT INTO account_permissions (firebase_uid, permission)
SELECT a.firebase_uid, permission
  FROM access_accounts a
  CROSS JOIN LATERAL unnest(
    CASE
      WHEN a.role IN ('visitor', 'entrepreneur', 'institution') THEN
        ARRAY['directory.search', 'messaging.use', 'support.requests.create']::TEXT[]
      WHEN a.role = 'support' THEN
        ARRAY['directory.search']::TEXT[]
      ELSE
        ARRAY[]::TEXT[]
    END
  ) AS permissions(permission)
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('008_directory_messaging')
ON CONFLICT (version) DO NOTHING;

COMMIT;
