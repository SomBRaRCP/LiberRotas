BEGIN;

ALTER TABLE institution_groups
  ADD COLUMN badge_green_percent INTEGER,
  ADD COLUMN badge_yellow_percent INTEGER,
  ADD COLUMN badge_red_percent INTEGER,
  ADD CONSTRAINT institution_badge_percentages_valid CHECK (
    (badge_green_percent IS NULL AND badge_yellow_percent IS NULL AND badge_red_percent IS NULL)
    OR (badge_green_percent IS NOT NULL AND badge_yellow_percent IS NOT NULL AND badge_red_percent IS NOT NULL
      AND badge_green_percent BETWEEN 0 AND 100 AND badge_yellow_percent BETWEEN 0 AND 100
      AND badge_red_percent BETWEEN 0 AND 100
      AND badge_green_percent + badge_yellow_percent + badge_red_percent = 100)
  );

ALTER TABLE institution_group_memberships
  ADD COLUMN support_badge TEXT CHECK (support_badge IN ('GREEN', 'YELLOW', 'RED'));

-- Preserva a regra e as classificações utilizadas, mesmo após reclassificações.
ALTER TABLE institution_funded_events ADD COLUMN badge_distribution JSONB;

INSERT INTO schema_migrations(version) VALUES ('022_institution_support_badges');
COMMIT;
