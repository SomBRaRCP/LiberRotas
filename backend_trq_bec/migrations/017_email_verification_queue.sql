BEGIN;

CREATE TABLE IF NOT EXISTS email_verification_queue (
  queue_id UUID PRIMARY KEY,
  -- A fila também aceita contas Firebase criadas antes do provisionamento no
  -- PostgreSQL. O UID continua vindo exclusivamente do Firebase Admin.
  firebase_uid TEXT NOT NULL,
  email TEXT NOT NULL CHECK (
    length(email) BETWEEN 5 AND 254
    AND email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
  ),
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  result_code TEXT,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_verification_queue_active_uid
  ON email_verification_queue(firebase_uid)
  WHERE status IN ('PENDING', 'PROCESSING');

CREATE INDEX IF NOT EXISTS idx_email_verification_queue_due
  ON email_verification_queue(status, next_attempt_at, created_at);

INSERT INTO schema_migrations(version) VALUES ('017_email_verification_queue')
ON CONFLICT (version) DO NOTHING;

COMMIT;
