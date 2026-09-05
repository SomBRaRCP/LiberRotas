BEGIN;

-- Contas de suporte existentes recebem somente a permissao especifica para
-- provisionar instituicoes. A funcao e as demais permissoes permanecem iguais.
INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'support.institutions.create'
  FROM access_accounts
 WHERE role = 'support'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version) VALUES ('006_support_institution_creation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
