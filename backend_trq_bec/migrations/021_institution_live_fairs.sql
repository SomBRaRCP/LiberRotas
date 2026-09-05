BEGIN;

-- Permite que instituicoes ativas publiquem e administrem somente as feiras
-- das quais sao autoras. A propriedade continua validada no Firestore.
INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'locations.publish'
  FROM access_accounts
 WHERE role = 'institution'
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('021_institution_live_fairs')
ON CONFLICT (version) DO NOTHING;

COMMIT;
