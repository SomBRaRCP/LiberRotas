BEGIN;

-- Autoriza explicitamente apenas os dois perfis sociais a publicar no Feed.
-- O status ACTIVE e a Custom Claim correspondente continuam sendo validados
-- pelo endpoint antes de qualquer escrita administrativa no Firestore.
INSERT INTO account_permissions (firebase_uid, permission)
SELECT firebase_uid, 'feed.publish'
  FROM access_accounts
 WHERE role IN ('entrepreneur', 'visitor')
ON CONFLICT (firebase_uid, permission) DO NOTHING;

INSERT INTO schema_migrations(version) VALUES ('004_community_posts')
ON CONFLICT (version) DO NOTHING;

COMMIT;
