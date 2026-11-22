"""Postgres Row-Level Security (RLS) tenant walls.

Every tenant-scoped table gets an idempotent `tenant_isolation` policy that restricts
SELECT/INSERT/UPDATE/DELETE to rows matching `current_setting('app.tenant_id', true)` whenever
`app.tenant_id` is set in the transaction. When `app.tenant_id` is unset/empty (background workers,
cross-tenant admin queries, or public token lookups), existing queries continue to work without
breakage, while any connection obtained via `db.tenant_conn(tenant_id)` is strictly walled off
by Postgres itself.
"""
from __future__ import annotations

TENANT_RLS_TABLES: tuple[str, ...] = (
    "chunks",
    "conversations",
    "messages",
    "leads",
    "voice_tokens",
    "appointments",
    "outbox",
    "sms_devices",
    "device_sms_jobs",
    "device_sms_inbound",
    "opt_outs",
    "campaigns",
    "tasks",
    "lead_events",
    "email_drafts",
    "phone_numbers",
    "phone_calls",
    "tenant_users",
    "tenant_invites",
    "inbound_mailboxes",
    "tenant_channel_authorizations",
    "tenant_channel_authorization_audit",
    "managed_phone_setups",
    "voice_sessions",
    "voice_recordings",
    "voice_recording_shares",
    "mobile_forwarding_connections",
    "call_forwarding_preferences",
    "quotations",
    "enquiry_sources",
    "calendar_connections",
    "calendar_oauth_states",
    "email_secretary_jobs",
    "customer_cases",
    "case_events",
    "customer_addresses",
    "inbound_sender_rules",
    "inbound_audit",
    "products",
    "product_stock_movements",
    "design_uploads",
    "media_brand",
    "media_assets",
    "design_links",
    "email_suppressions",
    "missed_call_recoveries",
    "call_insights",
    "invoices",
    "privacy_requests",
    "privacy_breaches",
    "privacy_audit_log",
    "platform_invoices",
    "tenant_webhooks",
    "webhook_events",
    "tenant_api_keys",
    "tenant_integrations",
    "integration_links",
    "billing_events",
)


def rls_migration_sql() -> str:
    """Return an idempotent DO block that enables and forces RLS on all tenant tables."""
    table_list = ", ".join(f"'{t}'" for t in TENANT_RLS_TABLES)
    return f"""
DO $$
DECLARE
    tbl text;
    has_col boolean;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[{table_list}]
    LOOP
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'tenant_id'
        ) INTO has_col;
        IF has_col THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tbl);
            EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', tbl);
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I '
                'USING ('
                '  current_setting(''app.tenant_id'', true) IS NULL '
                '  OR current_setting(''app.tenant_id'', true) = '''' '
                '  OR tenant_id::text = current_setting(''app.tenant_id'', true)'
                ') '
                'WITH CHECK ('
                '  current_setting(''app.tenant_id'', true) IS NULL '
                '  OR current_setting(''app.tenant_id'', true) = '''' '
                '  OR tenant_id::text = current_setting(''app.tenant_id'', true)'
                ')',
                tbl
            );
        END IF;
    END LOOP;
END $$;
"""
