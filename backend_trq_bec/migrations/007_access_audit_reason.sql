BEGIN;

ALTER TABLE access_audit_events
  ADD COLUMN IF NOT EXISTS reason TEXT;

UPDATE access_audit_events
   SET reason = 'Registro legado sem motivo detalhado.'
 WHERE reason IS NULL;

ALTER TABLE access_audit_events
  ALTER COLUMN reason SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_constraint
     WHERE conname = 'access_audit_events_reason_length_chk'
  ) THEN
    ALTER TABLE access_audit_events
      ADD CONSTRAINT access_audit_events_reason_length_chk
      CHECK (char_length(reason) BETWEEN 10 AND 500);
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION reject_access_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'access audit ledger is append-only';
END;
$$;

DROP TRIGGER IF EXISTS access_audit_events_no_update ON access_audit_events;
CREATE TRIGGER access_audit_events_no_update
BEFORE UPDATE OR DELETE ON access_audit_events
FOR EACH ROW EXECUTE FUNCTION reject_access_audit_mutation();

INSERT INTO schema_migrations(version) VALUES ('007_access_audit_reason')
ON CONFLICT (version) DO NOTHING;

COMMIT;
