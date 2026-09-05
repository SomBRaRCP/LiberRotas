BEGIN;

-- O e-mail passa a ser somente um alerta. Dispositivos adicionais são
-- liberados pelo backend após dez minutos, inclusive registros criados pelo
-- fluxo antigo que ainda possuíam uma validade de aprovação maior.
UPDATE device_keys
   SET approval_expires_at = LEAST(
         approval_expires_at,
         created_at + INTERVAL '10 minutes'
       )
 WHERE status = 'PENDING_APPROVAL'
   AND approval_expires_at IS NOT NULL;

INSERT INTO schema_migrations(version)
VALUES ('015_device_auto_activation_cooldown')
ON CONFLICT (version) DO NOTHING;

COMMIT;
