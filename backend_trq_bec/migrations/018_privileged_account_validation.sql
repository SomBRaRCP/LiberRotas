BEGIN;

-- A função declarada na conta não é suficiente para liberar um painel
-- privilegiado. Esta tabela registra a origem e a validação humana da
-- autoridade de administradores, suporte e segurança.
CREATE TABLE IF NOT EXISTS privileged_account_validations (
  firebase_uid TEXT PRIMARY KEY
    REFERENCES access_accounts(firebase_uid) ON DELETE CASCADE,
  requested_role TEXT NOT NULL
    CHECK (requested_role IN ('admin', 'support', 'security')),
  validation_state TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (validation_state IN ('PENDING', 'APPROVED', 'REJECTED', 'REVOKED')),
  protection_level TEXT NOT NULL DEFAULT 'PRIVILEGED'
    CHECK (protection_level IN ('SYSTEM', 'PRIVILEGED')),
  account_origin TEXT NOT NULL
    CHECK (account_origin IN ('BOOTSTRAP', 'ADMIN_INVITATION')),
  created_by_uid TEXT NOT NULL,
  validated_by_uid TEXT,
  validation_reason TEXT,
  validated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (
      validation_state = 'APPROVED'
      AND validated_by_uid IS NOT NULL
      AND validation_reason IS NOT NULL
      AND char_length(validation_reason) BETWEEN 10 AND 500
      AND validated_at IS NOT NULL
    )
    OR
    (
      validation_state <> 'APPROVED'
      AND validated_at IS NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS idx_privileged_account_validations_state
  ON privileged_account_validations(validation_state, requested_role, updated_at DESC);

-- As únicas contas privilegiadas já existentes foram confirmadas pelo
-- responsável do projeto. Elas ficam protegidas como contas oficiais do
-- sistema, sem depender de comparação de e-mail durante as autorizações.
INSERT INTO privileged_account_validations (
  firebase_uid,
  requested_role,
  validation_state,
  protection_level,
  account_origin,
  created_by_uid,
  validated_by_uid,
  validation_reason,
  validated_at
)
SELECT
  firebase_uid,
  role,
  'APPROVED',
  'SYSTEM',
  'BOOTSTRAP',
  'system:official-bootstrap',
  'system:official-bootstrap',
  'Conta oficial existente confirmada pelo responsável do projeto LiberRotas.',
  now()
FROM access_accounts
WHERE
  (lower(email) = 'administrador@liberrotas.com.br' AND role = 'admin')
  OR (lower(email) = 'suporte@liberrotas.com.br' AND role = 'support')
  OR (lower(email) = 'seguranca@liberrotas.com.br' AND role = 'security')
ON CONFLICT (firebase_uid) DO NOTHING;

-- Amplia o vocabulário fechado do ledger de acesso antes de registrar os
-- novos tipos. O ledger continua append-only pelo gatilho da migração 007.
ALTER TABLE access_audit_events
  DROP CONSTRAINT IF EXISTS access_audit_events_event_type_check;

ALTER TABLE access_audit_events
  ADD CONSTRAINT access_audit_events_event_type_check
  CHECK (
    event_type IN (
      'INSTITUTION_PROVISIONED',
      'ACCOUNT_STATUS_CHANGED',
      'OFFICIAL_ACCOUNT_VALIDATED',
      'STAFF_ACCOUNT_CREATED',
      'STAFF_ACCOUNT_VALIDATED'
    )
  );

INSERT INTO access_audit_events (
  event_id,
  actor_uid,
  target_uid,
  event_type,
  previous_status,
  new_status,
  reason
)
SELECT
  'official-account:' || validation.firebase_uid,
  'system:official-bootstrap',
  validation.firebase_uid,
  'OFFICIAL_ACCOUNT_VALIDATED',
  'ACTIVE',
  'ACTIVE',
  'Conta oficial existente confirmada pelo responsável do projeto LiberRotas.'
FROM privileged_account_validations AS validation
WHERE validation.protection_level = 'SYSTEM'
  AND validation.account_origin = 'BOOTSTRAP'
ON CONFLICT (event_id) DO NOTHING;

-- Permissões novas possuem escopo mínimo e não reutilizam permissões amplas.
INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'admin.staff_accounts.manage'
FROM access_accounts
WHERE role = 'admin'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'security.trq_bec.monitor'
FROM access_accounts
WHERE role = 'security'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('018_privileged_account_validation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
