BEGIN;

CREATE TABLE IF NOT EXISTS institutional_profiles (
  firebase_uid TEXT PRIMARY KEY REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  email TEXT NOT NULL,
  name TEXT NOT NULL CHECK (char_length(name) BETWEEN 2 AND 160),
  description TEXT CHECK (description IS NULL OR char_length(description) <= 1000),
  city TEXT CHECK (city IS NULL OR char_length(city) BETWEEN 2 AND 120),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_institutional_profiles_email_ci
  ON institutional_profiles(lower(email));

-- Mantem utilizaveis as contas institution provisionadas antes desta tabela.
INSERT INTO institutional_profiles (firebase_uid, email, name)
SELECT firebase_uid,
       COALESCE(NULLIF(email, ''), firebase_uid || '@pending.invalid'),
       COALESCE(NULLIF(split_part(email, '@', 1), ''), 'Instituicao LiberRotas')
  FROM access_accounts
 WHERE role = 'institution'
ON CONFLICT (firebase_uid) DO NOTHING;

CREATE TABLE IF NOT EXISTS institution_groups (
  group_id TEXT PRIMARY KEY,
  owner_uid TEXT NOT NULL REFERENCES institutional_profiles(firebase_uid) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK (char_length(name) BETWEEN 2 AND 160),
  description TEXT CHECK (description IS NULL OR char_length(description) <= 1000),
  city TEXT CHECK (city IS NULL OR char_length(city) BETWEEN 2 AND 120),
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CLOSED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ,
  CHECK (
    (status = 'ACTIVE' AND closed_at IS NULL)
    OR (status = 'CLOSED' AND closed_at IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_institution_groups_owner_status_created
  ON institution_groups(owner_uid, status, created_at DESC);

CREATE TABLE IF NOT EXISTS access_audit_events (
  event_id TEXT PRIMARY KEY,
  actor_uid TEXT NOT NULL,
  target_uid TEXT NOT NULL,
  event_type TEXT NOT NULL
    CHECK (event_type IN ('INSTITUTION_PROVISIONED', 'ACCOUNT_STATUS_CHANGED')),
  previous_status TEXT CHECK (
    previous_status IS NULL
    OR previous_status IN ('ACTIVE', 'PENDING', 'SUSPENDED', 'DISABLED')
  ),
  new_status TEXT NOT NULL
    CHECK (new_status IN ('ACTIVE', 'PENDING', 'SUSPENDED', 'DISABLED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_access_audit_events_created
  ON access_audit_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_access_audit_events_target_created
  ON access_audit_events(target_uid, created_at DESC);

INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'institution.groups.manage'
  FROM access_accounts
 WHERE role = 'institution'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version) VALUES ('005_institution_management')
ON CONFLICT (version) DO NOTHING;

COMMIT;
