BEGIN;

CREATE TABLE IF NOT EXISTS access_accounts (
  firebase_uid TEXT PRIMARY KEY,
  email TEXT,
  role TEXT NOT NULL
    CHECK (role IN ('admin', 'support', 'security', 'institution', 'entrepreneur', 'visitor')),
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('ACTIVE', 'PENDING', 'SUSPENDED', 'DISABLED')),
  allow_entrepreneur_fallback BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_access_accounts_role_status
  ON access_accounts(role, status);

CREATE TABLE IF NOT EXISTS account_permissions (
  firebase_uid TEXT NOT NULL REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  permission TEXT NOT NULL CHECK (permission ~ '^[a-z][a-z0-9_.:-]{2,95}$'),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (firebase_uid, permission)
);

-- Contas comerciais já aprovadas continuam utilizáveis após a migração. A
-- claim Firebase ainda precisa ser role=entrepreneur; o banco não a substitui.
INSERT INTO access_accounts (firebase_uid, role, status)
SELECT firebase_uid, 'entrepreneur', status
  FROM merchant_accounts
ON CONFLICT (firebase_uid) DO NOTHING;

INSERT INTO account_permissions (firebase_uid, permission)
SELECT merchant.firebase_uid, permission
  FROM merchant_accounts AS merchant
 CROSS JOIN unnest(ARRAY[
   'entrepreneur.panel.access',
   'marketplace.manage',
   'profile.manage',
   'locations.publish'
 ]) AS permission
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version) VALUES ('003_access_control')
ON CONFLICT (version) DO NOTHING;

COMMIT;
