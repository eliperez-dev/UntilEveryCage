-- Keep the provider/day ledger as an aggregate; enforce named account quotas
-- separately. Historical request rows remain immutable and are attributed by
-- an explicit operator bootstrap, never by guessing inside this migration.
CREATE TABLE uec.geocode_provider_accounts (
    provider_id TEXT NOT NULL,
    account_id TEXT NOT NULL CHECK (account_id ~ '^[a-z][a-z0-9_-]{0,31}$'),
    daily_limit INTEGER NOT NULL CHECK (daily_limit > 0),
    minimum_interval DOUBLE PRECISION NOT NULL CHECK (minimum_interval > 0),
    PRIMARY KEY(provider_id,account_id)
);
INSERT INTO uec.geocode_provider_accounts VALUES
    ('locationiq','primary',5000,1.05),
    ('locationiq','secondary',5000,1.05);

CREATE TABLE uec.geocode_account_budgets (
    provider_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    budget_date DATE NOT NULL,
    daily_limit INTEGER NOT NULL CHECK (daily_limit > 0),
    reserved_requests INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_requests >= 0 AND reserved_requests <= daily_limit),
    last_reserved_at TIMESTAMPTZ,
    PRIMARY KEY(provider_id,account_id,budget_date),
    FOREIGN KEY(provider_id,account_id)
        REFERENCES uec.geocode_provider_accounts(provider_id,account_id)
);
ALTER TABLE uec.geocode_request_reservations
    ADD CONSTRAINT geocode_reservation_account_identity
    UNIQUE(reservation_id,provider_id,budget_date);
CREATE TABLE uec.geocode_request_account_attributions (
    reservation_id UUID PRIMARY KEY,
    provider_id TEXT NOT NULL,
    budget_date DATE NOT NULL,
    account_id TEXT NOT NULL,
    attribution_method TEXT NOT NULL CHECK (attribution_method IN ('worker','operator_history')),
    attributed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY(reservation_id,provider_id,budget_date)
        REFERENCES uec.geocode_request_reservations(reservation_id,provider_id,budget_date),
    FOREIGN KEY(provider_id,account_id,budget_date)
        REFERENCES uec.geocode_account_budgets(provider_id,account_id,budget_date)
);
CREATE INDEX geocode_request_account_day_idx ON uec.geocode_request_account_attributions
    (provider_id,account_id,budget_date);
CREATE TRIGGER geocode_request_account_attributions_append_only
    BEFORE UPDATE OR DELETE ON uec.geocode_request_account_attributions
    FOR EACH ROW EXECUTE FUNCTION uec.reject_evidence_mutation();

CREATE FUNCTION uec.reserve_geocode_account_request(
    requested_provider TEXT, requested_account TEXT, requested_job UUID,
    requested_attempt INTEGER, requested_retry INTEGER,
    requested_daily_limit INTEGER, requested_interval DOUBLE PRECISION)
RETURNS TABLE(reservation_id UUID, reason TEXT) LANGUAGE plpgsql AS $$
DECLARE
    today DATE := (clock_timestamp() AT TIME ZONE 'UTC')::DATE;
    account_config uec.geocode_provider_accounts%ROWTYPE;
    account_budget uec.geocode_account_budgets%ROWTYPE;
    reservation UUID := gen_random_uuid();
    combined_limit INTEGER;
BEGIN
    SELECT * INTO STRICT account_config FROM uec.geocode_provider_accounts
      WHERE provider_id=requested_provider AND account_id=requested_account;
    IF requested_daily_limit < 1 OR requested_daily_limit > account_config.daily_limit
       OR requested_interval < account_config.minimum_interval
       OR requested_interval IS NULL OR requested_daily_limit IS NULL THEN
        RAISE EXCEPTION 'invalid account request limits' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM uec.geocode_jobs
                  WHERE job_id=requested_job AND provider_id=requested_provider) THEN
        RAISE EXCEPTION 'account request provider mismatch' USING ERRCODE='23514';
    END IF;
    -- An account-aware worker must not silently start at zero over legacy use.
    IF EXISTS(SELECT 1 FROM uec.geocode_request_reservations existing
               LEFT JOIN uec.geocode_request_account_attributions attribution
                 ON attribution.reservation_id=existing.reservation_id
              WHERE existing.provider_id=requested_provider AND existing.budget_date=today
                AND attribution.reservation_id IS NULL) THEN
        RAISE EXCEPTION 'account history attribution required' USING ERRCODE='23514';
    END IF;
    INSERT INTO uec.geocode_account_budgets(provider_id,account_id,budget_date,daily_limit)
    VALUES(requested_provider,requested_account,today,account_config.daily_limit)
    ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT account_budget FROM uec.geocode_account_budgets
      WHERE provider_id=requested_provider AND account_id=requested_account AND budget_date=today
      FOR UPDATE;
    IF account_budget.reserved_requests >= LEAST(account_budget.daily_limit,requested_daily_limit) THEN
        RETURN QUERY SELECT NULL::UUID,'budget'::TEXT; RETURN;
    END IF;
    IF account_budget.last_reserved_at > clock_timestamp() - requested_interval * interval '1 second' THEN
        RETURN QUERY SELECT NULL::UUID,'rate_limited'::TEXT; RETURN;
    END IF;
    -- No retry or second credential may reserve the same job attempt twice.
    IF EXISTS(SELECT 1 FROM uec.geocode_request_reservations existing
               WHERE existing.job_id=requested_job AND existing.attempt_number=requested_attempt
                 AND existing.retry_number=requested_retry) THEN
        RAISE EXCEPTION 'duplicate geocode request attempt' USING ERRCODE='23505';
    END IF;
    UPDATE uec.geocode_account_budgets
       SET reserved_requests=reserved_requests+1,last_reserved_at=clock_timestamp()
     WHERE provider_id=requested_provider AND account_id=requested_account AND budget_date=today;
    SELECT sum(daily_limit)::INTEGER INTO combined_limit FROM uec.geocode_provider_accounts
      WHERE provider_id=requested_provider;
    INSERT INTO uec.geocode_provider_budgets(provider_id,budget_date,daily_limit)
    VALUES(requested_provider,today,combined_limit)
    ON CONFLICT(provider_id,budget_date) DO UPDATE
      SET daily_limit=GREATEST(uec.geocode_provider_budgets.daily_limit,EXCLUDED.daily_limit);
    UPDATE uec.geocode_provider_budgets
       SET reserved_requests=reserved_requests+1,last_reserved_at=clock_timestamp()
     WHERE provider_id=requested_provider AND budget_date=today;
    INSERT INTO uec.geocode_request_reservations
        (reservation_id,provider_id,budget_date,job_id,attempt_number,retry_number)
    VALUES(reservation,requested_provider,today,requested_job,requested_attempt,requested_retry);
    INSERT INTO uec.geocode_request_account_attributions
        (reservation_id,provider_id,budget_date,account_id,attribution_method)
    VALUES(reservation,requested_provider,today,requested_account,'worker');
    RETURN QUERY SELECT reservation,NULL::TEXT;
END;
$$;
