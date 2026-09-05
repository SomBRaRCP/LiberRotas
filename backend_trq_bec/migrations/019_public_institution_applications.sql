BEGIN;

-- Solicitações enviadas pela página pública. O registro nesta fila nunca cria
-- identidade Firebase, conta de acesso, função ou permissão institucional.
CREATE TABLE IF NOT EXISTS public_institution_applications (
  application_id UUID PRIMARY KEY,
  organization_type TEXT NOT NULL
    CHECK (organization_type IN ('COMPANY', 'NGO')),
  organization_name TEXT NOT NULL
    CHECK (char_length(organization_name) BETWEEN 2 AND 160),
  contact_name TEXT NOT NULL
    CHECK (char_length(contact_name) BETWEEN 3 AND 120),
  email TEXT NOT NULL
    CHECK (char_length(email) BETWEEN 5 AND 254),
  phone TEXT CHECK (phone IS NULL OR char_length(phone) BETWEEN 8 AND 30),
  registration_number TEXT
    CHECK (registration_number IS NULL OR char_length(registration_number) BETWEEN 3 AND 30),
  city TEXT NOT NULL CHECK (char_length(city) BETWEEN 2 AND 120),
  state TEXT NOT NULL CHECK (state ~ '^[A-Z]{2}$'),
  website_or_social TEXT
    CHECK (website_or_social IS NULL OR char_length(website_or_social) <= 500),
  description TEXT NOT NULL
    CHECK (char_length(description) BETWEEN 20 AND 2000),
  status TEXT NOT NULL DEFAULT 'NEW'
    CHECK (status IN ('NEW', 'IN_REVIEW', 'CONTACTED', 'APPROVED', 'REJECTED')),
  support_notes TEXT
    CHECK (support_notes IS NULL OR char_length(support_notes) <= 1000),
  reviewed_by_uid TEXT REFERENCES access_accounts(firebase_uid) ON DELETE SET NULL,
  -- Mantém a referência histórica sem impedir uma futura exclusão da conta.
  provisioned_uid TEXT,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (status <> 'APPROVED' OR provisioned_uid IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_public_institution_applications_queue
  ON public_institution_applications(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_public_institution_applications_email
  ON public_institution_applications(lower(email), created_at DESC);

INSERT INTO schema_migrations(version)
VALUES ('019_public_institution_applications')
ON CONFLICT (version) DO NOTHING;

COMMIT;
