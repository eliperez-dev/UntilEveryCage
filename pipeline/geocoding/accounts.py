"""Named geocoder accounts and explicit attribution of legacy usage."""
from __future__ import annotations

LOCATIONIQ_KEY_ENVS = {
    "primary": "LOCATIONIQ_API_KEY",
    "secondary": "LOCATIONIQ_SECONDARY_API_KEY",
}


def account_for_provider(provider: str, account: str | None) -> str | None:
    if provider != "locationiq":
        if account is not None:
            raise ValueError("named accounts are currently enabled only for LocationIQ")
        return None
    account = account or "primary"
    if account not in LOCATIONIQ_KEY_ENVS:
        raise ValueError("unknown LocationIQ account")
    return account


def attribute_history(connection, *, budget_date, secondary_workers: tuple[str, ...]) -> dict:
    """Explicit operator reconciliation; never rewrite old reservations.

    The operator must identify every secondary-key worker for this day.
    Other historical LocationIQ reservations are assigned to the primary key.
    Run only after workers stop; aggregate counts must match before commit.
    """
    if not secondary_workers or len(set(secondary_workers)) != len(secondary_workers):
        raise ValueError("explicit unique secondary worker identities required")
    with connection.transaction():
        if connection.execute("SELECT current_database()").fetchone()[0] != "uec_launch_sources_test_20261025":
            raise ValueError("wrong_disposable_database")
        if connection.execute("""SELECT 1 FROM uec.geocode_job_current
            WHERE provider_id='locationiq' AND event_type='started' LIMIT 1""").fetchone():
            raise ValueError("account attribution requires stopped workers")
        aggregate = connection.execute("""SELECT reserved_requests FROM uec.geocode_provider_budgets
            WHERE provider_id='locationiq' AND budget_date=%s FOR UPDATE""", (budget_date,)).fetchone()
        if aggregate is None:
            raise ValueError("historical provider budget missing")
        rows = connection.execute("""
            SELECT reservation.reservation_id, started.worker_id, reservation.reserved_at,
                   attribution.account_id
              FROM uec.geocode_request_reservations reservation
              LEFT JOIN uec.geocode_request_account_attributions attribution USING(reservation_id)
              LEFT JOIN LATERAL (
                SELECT CASE WHEN count(DISTINCT event.worker_id)=1
                       THEN min(event.worker_id) END AS worker_id
                  FROM uec.geocode_job_events event
                 WHERE event.job_id=reservation.job_id AND event.event_type='started'
                   AND event.attempt_number=reservation.attempt_number
              ) started ON true
             WHERE reservation.provider_id='locationiq' AND reservation.budget_date=%s
        """, (budget_date,)).fetchall()
        if len(rows) != aggregate[0] or any(worker is None for _, worker, _, _ in rows):
            raise ValueError("historical reservations cannot be fully reconciled")
        if any(account not in (None,"secondary") and worker in secondary_workers
               for _,worker,_,account in rows):
            raise ValueError("historical account attribution conflict")
        assignments = {reservation: account or ("secondary" if worker in secondary_workers else "primary")
                       for reservation,worker,_,account in rows}
        counts = {account: sum(value == account for value in assignments.values())
                  for account in LOCATIONIQ_KEY_ENVS}
        if any(value > 5000 for value in counts.values()):
            raise ValueError("historical account allowance exceeded")
        for account in LOCATIONIQ_KEY_ENVS:
            connection.execute("""INSERT INTO uec.geocode_account_budgets
                (provider_id,account_id,budget_date,daily_limit)
                VALUES('locationiq',%s,%s,5000) ON CONFLICT DO NOTHING""", (account,budget_date))
        with connection.cursor() as cursor:
            cursor.executemany("""INSERT INTO uec.geocode_request_account_attributions
                (reservation_id,provider_id,budget_date,account_id,attribution_method)
                VALUES(%s,'locationiq',%s,%s,'operator_history') ON CONFLICT DO NOTHING""",
                [(reservation,budget_date,account) for reservation,account in assignments.items()])
        for account,count in counts.items():
            last = max((time for reservation,_,time,_ in rows
                        if assignments[reservation] == account), default=None)
            updated = connection.execute("""UPDATE uec.geocode_account_budgets
                SET reserved_requests=%s,last_reserved_at=%s
                WHERE provider_id='locationiq' AND account_id=%s AND budget_date=%s
                  AND reserved_requests<=%s RETURNING reserved_requests""",
                (count,last,account,budget_date,count)).fetchone()
            if updated is None:
                raise ValueError("account attribution would reset usage")
        connection.execute("""UPDATE uec.geocode_provider_budgets SET daily_limit=10000
            WHERE provider_id='locationiq' AND budget_date=%s AND daily_limit<=10000""", (budget_date,))
    return {"provider": "locationiq", "accounts": counts, "requests_rewritten": 0}
