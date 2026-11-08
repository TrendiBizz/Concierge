//! SQLite-backed tenant-scoped social drafts and single-use approvals.
use crate::guardrails::Rules;
use crate::model::{NewPost, Post, Status};
use rand::RngCore;
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use std::sync::Mutex;
use time::OffsetDateTime;

pub type Result<T> = std::result::Result<T, String>;

pub struct Store {
    db: Mutex<Connection>,
}

pub type RefreshCandidate = (String, String, String, Option<String>, Option<i64>);

pub struct VerifiedAccount<'a> {
    pub customer: &'a str,
    pub network: &'a str,
    pub external_id: &'a str,
    pub display_name: &'a str,
    pub token_enc: &'a str,
    pub refresh_enc: Option<&'a str>,
    pub expires_at: Option<i64>,
    pub granted_scopes: &'a str,
}

fn random_id() -> String {
    let mut b = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut b);
    use base64::Engine;
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(b)
}

fn now() -> i64 {
    OffsetDateTime::now_utc().unix_timestamp()
}

impl Store {
    pub fn open(path: &str) -> Result<Self> {
        let conn = Connection::open(path).map_err(|e| e.to_string())?;
        Self::init(conn)
    }

    pub fn open_memory() -> Result<Self> {
        Self::init(Connection::open_in_memory().map_err(|e| e.to_string())?)
    }

    fn init(conn: Connection) -> Result<Self> {
        conn.execute_batch(
            "PRAGMA foreign_keys=ON;
             PRAGMA busy_timeout=5000;
             CREATE TABLE IF NOT EXISTS customers(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, rules TEXT NOT NULL,
                approval_contact TEXT NOT NULL, created_at INTEGER NOT NULL);
             CREATE TABLE IF NOT EXISTS posts(
                id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                body TEXT NOT NULL, status TEXT NOT NULL, scheduled_at INTEGER,
                revision INTEGER NOT NULL, approved_revision INTEGER);
             CREATE INDEX IF NOT EXISTS idx_posts_due ON posts(status,scheduled_at);
             CREATE INDEX IF NOT EXISTS idx_posts_tenant ON posts(customer_id);
             CREATE TABLE IF NOT EXISTS approvals(
                token_hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
                post_id TEXT NOT NULL, revision INTEGER NOT NULL, scheduled_at INTEGER,
                expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
             CREATE INDEX IF NOT EXISTS idx_approvals_post ON approvals(post_id);
             CREATE TABLE IF NOT EXISTS customer_agents(
                customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL);
             CREATE TABLE IF NOT EXISTS accounts(
                id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                network TEXT NOT NULL, external_id TEXT NOT NULL, display_name TEXT NOT NULL,
                token_enc TEXT NOT NULL, refresh_enc TEXT, needs_reauth INTEGER NOT NULL DEFAULT 0);
             CREATE TABLE IF NOT EXISTS account_consents(
                account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                granted_scopes TEXT NOT NULL, authorized_at INTEGER NOT NULL,
                disconnected_at INTEGER);
             CREATE TABLE IF NOT EXISTS account_expiries(
                account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                expires_at INTEGER);
             CREATE TABLE IF NOT EXISTS oauth_pending(
                state_hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                network TEXT NOT NULL, verifier_enc TEXT NOT NULL,
                expires_at INTEGER NOT NULL);
             CREATE INDEX IF NOT EXISTS oauth_expiry ON oauth_pending(expires_at);
             CREATE TABLE IF NOT EXISTS post_results(
                post_id TEXT NOT NULL, account_id TEXT NOT NULL, external_post_id TEXT,
                error TEXT, at INTEGER NOT NULL, ok INTEGER NOT NULL,
                PRIMARY KEY(post_id,account_id,ok));
             CREATE TABLE IF NOT EXISTS events(
                at INTEGER NOT NULL, customer_id TEXT NOT NULL, post_id TEXT,
                kind TEXT NOT NULL, detail TEXT NOT NULL);",
        )
        .map_err(|e| e.to_string())?;
        Ok(Self {
            db: Mutex::new(conn),
        })
    }

    pub fn create_customer(&self, id: &str, name: &str, approval_contact: &str) -> Result<()> {
        if id.trim().is_empty() || name.trim().is_empty() {
            return Err("Missing customer identity".into());
        }
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.execute("INSERT INTO customers(id,name,rules,approval_contact,created_at) VALUES (?1,?2,?3,?4,?5)",
                     params![id,name,serde_json::to_string(&Rules::default()).map_err(|e|e.to_string())?, approval_contact,now()])
            .map_err(|e|e.to_string())?;
        Ok(())
    }

    pub fn rules(&self, customer: &str) -> Result<Rules> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let raw: String = conn
            .query_row("SELECT rules FROM customers WHERE id=?1", [customer], |r| {
                r.get(0)
            })
            .map_err(|_| "Customer not found")?;
        serde_json::from_str(&raw).map_err(|e| e.to_string())
    }

    pub fn update_rules(&self, customer: &str, rules: &Rules) -> Result<()> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let n = conn
            .execute(
                "UPDATE customers SET rules=?2 WHERE id=?1",
                params![
                    customer,
                    serde_json::to_string(rules).map_err(|e| e.to_string())?
                ],
            )
            .map_err(|e| e.to_string())?;
        if n != 1 {
            return Err("Customer not found".into());
        }
        Ok(())
    }

    pub fn add_account(
        &self,
        customer: &str,
        network: &str,
        external_id: &str,
        display_name: &str,
        token_enc: &str,
        refresh_enc: Option<&str>,
    ) -> Result<String> {
        if network.is_empty() || external_id.is_empty() || token_enc.is_empty() {
            return Err("Invalid account".into());
        }
        let id = random_id();
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.execute("INSERT INTO accounts(id,customer_id,network,external_id,display_name,token_enc,refresh_enc)
            VALUES(?1,?2,?3,?4,?5,?6,?7)",params![id,customer,network,external_id,
            display_name,token_enc,refresh_enc]).map_err(|e|e.to_string())?;
        Ok(id)
    }

    /// A re-authorized identity keeps its account id, avoiding duplicate entries.
    /// The optional expiration applies to expiring OAuth providers.
    pub fn upsert_verified_account(&self, account: VerifiedAccount<'_>) -> Result<String> {
        if account.network.is_empty()
            || account.external_id.is_empty()
            || account.token_enc.is_empty()
        {
            return Err("Invalid account".into());
        }
        let mut conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        let existing:Option<String>=tx.query_row(
            "SELECT id FROM accounts WHERE customer_id=?1 AND network=?2 AND external_id=?3 LIMIT 1",
            params![account.customer,account.network,account.external_id],|r|r.get(0))
            .optional().map_err(|e|e.to_string())?;
        let id = existing.unwrap_or_else(random_id);
        tx.execute(
            "INSERT INTO accounts(id,customer_id,network,external_id,display_name,token_enc,refresh_enc)
             VALUES(?1,?2,?3,?4,?5,?6,?7)
             ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                 token_enc=excluded.token_enc,refresh_enc=excluded.refresh_enc,needs_reauth=0",
            params![id,account.customer,account.network,account.external_id,account.display_name,account.token_enc,account.refresh_enc])
            .map_err(|e|e.to_string())?;
        tx.execute(
            "INSERT INTO account_expiries(account_id,expires_at) VALUES(?1,?2)
             ON CONFLICT(account_id) DO UPDATE SET expires_at=excluded.expires_at",
            params![id, account.expires_at],
        )
        .map_err(|e| e.to_string())?;
        tx.execute(
            "INSERT INTO account_consents(account_id,granted_scopes,authorized_at,disconnected_at)
             VALUES(?1,?2,?3,NULL)
             ON CONFLICT(account_id) DO UPDATE SET
               granted_scopes=excluded.granted_scopes,
               authorized_at=excluded.authorized_at,disconnected_at=NULL",
            params![id, account.granted_scopes, now()],
        )
        .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(id)
    }

    /// OAuth state is hashed; the short-lived PKCE verifier is encrypted.
    pub fn oauth_begin(
        &self,
        customer: &str,
        network: &str,
        state: &str,
        verifier_enc: &str,
        ttl_seconds: i64,
    ) -> Result<()> {
        if ttl_seconds <= 0 || ttl_seconds > 900 || state.len() < 32 || verifier_enc.is_empty() {
            return Err("Invalid OAuth request".into());
        }
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.execute("DELETE FROM oauth_pending WHERE expires_at<=?1", [now()])
            .map_err(|e| e.to_string())?;
        conn.execute(
            "INSERT INTO oauth_pending(state_hash,customer_id,network,verifier_enc,expires_at)
          VALUES(?1,?2,?3,?4,?5)",
            params![
                token_hash(state),
                customer,
                network,
                verifier_enc,
                now() + ttl_seconds
            ],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    /// Atomic one-use state; expired or cross-tenant callbacks never return the verifier.
    pub fn oauth_consume(&self, customer: &str, network: &str, state: &str) -> Result<String> {
        if state.len() < 32 || state.len() > 256 {
            return Err("Invalid OAuth state".into());
        }
        let mut conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        let encrypted: Option<String> = tx
            .query_row(
                "SELECT verifier_enc FROM oauth_pending
            WHERE state_hash=?1 AND customer_id=?2 AND network=?3 AND expires_at>?4",
                params![token_hash(state), customer, network, now()],
                |row| row.get(0),
            )
            .optional()
            .map_err(|e| e.to_string())?;
        let encrypted = encrypted.ok_or("OAuth state expired or invalid")?;
        tx.execute(
            "DELETE FROM oauth_pending WHERE state_hash=?1",
            [token_hash(state)],
        )
        .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(encrypted)
    }

    pub fn account(
        &self,
        customer: &str,
        id: &str,
    ) -> Result<(String, String, String, Option<String>)> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.query_row(
            "SELECT network,external_id,token_enc,refresh_enc FROM accounts
                  WHERE id=?1 AND customer_id=?2 AND needs_reauth=0
                    AND NOT EXISTS (
                      SELECT 1 FROM account_expiries x
                      WHERE x.account_id=accounts.id AND x.expires_at<=?3)",
            params![id, customer, now()],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .map_err(|_| "Account not found or requires login".into())
    }

    /// Require a tenant-owned, active provider grant before publishing.
    pub fn account_has_scope(&self, customer: &str, id: &str, scope: &str) -> Result<bool> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let granted: Option<String> = conn
            .query_row(
                "SELECT c.granted_scopes FROM accounts a
                 JOIN account_consents c ON c.account_id=a.id
                 WHERE a.id=?1 AND a.customer_id=?2 AND a.needs_reauth=0
                   AND c.disconnected_at IS NULL",
                params![id, customer],
                |row| row.get(0),
            )
            .optional()
            .map_err(|e| e.to_string())?;
        Ok(granted.is_some_and(|scopes| scopes.split_whitespace().any(|s| s == scope)))
    }

    /// Read expiring credentials only for an authenticated customer's refresh operation.
    /// A revoked account is never returned, even when its encrypted token remains in backup.
    pub fn refresh_candidate(&self, customer: &str, id: &str) -> Result<RefreshCandidate> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.query_row(
            "SELECT a.network,a.external_id,a.token_enc,a.refresh_enc,x.expires_at
             FROM accounts a LEFT JOIN account_expiries x ON x.account_id=a.id
             WHERE a.id=?1 AND a.customer_id=?2 AND a.needs_reauth=0 AND a.token_enc<>''",
            params![id, customer],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
        )
        .map_err(|_| "Account not found or disconnected".into())
    }

    /// Compare-and-swap encrypted credentials, so concurrent disconnect/reauthorization
    /// cannot be overwritten by an in-flight refresh.
    pub fn update_refreshed_token(
        &self,
        customer: &str,
        id: &str,
        old_enc: &str,
        new_enc: &str,
        new_refresh: Option<&str>,
        expires_at: i64,
    ) -> Result<()> {
        if new_enc.is_empty() || expires_at <= now() {
            return Err("Invalid refreshed token".into());
        }
        let mut conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        let changed = tx
            .execute(
                "UPDATE accounts SET token_enc=?1,refresh_enc=COALESCE(?2,refresh_enc)
             WHERE id=?3 AND customer_id=?4 AND needs_reauth=0 AND token_enc=?5",
                params![new_enc, new_refresh, id, customer, old_enc],
            )
            .map_err(|e| e.to_string())?;
        if changed != 1 {
            return Err("Account changed or disconnected during refresh".into());
        }
        tx.execute(
            "INSERT INTO account_expiries(account_id,expires_at) VALUES(?1,?2)
                    ON CONFLICT(account_id) DO UPDATE SET expires_at=excluded.expires_at",
            params![id, expires_at],
        )
        .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(())
    }

    pub fn list_accounts(&self, customer: &str) -> Result<Vec<crate::model::Account>> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let mut stmt = conn
            .prepare(
                "SELECT a.id,a.network,a.display_name,a.external_id,
                       (a.needs_reauth=1 OR (x.expires_at IS NOT NULL AND x.expires_at<=?2)),
                       x.expires_at FROM accounts a
                       LEFT JOIN account_expiries x ON x.account_id=a.id
                       WHERE a.customer_id=?1",
            )
            .map_err(|e| e.to_string())?;
        let output = stmt
            .query_map(params![customer, now()], |r| {
                Ok(crate::model::Account {
                    id: r.get(0)?,
                    customer_id: customer.to_string(),
                    network: r.get(1)?,
                    display_name: r.get(2)?,
                    external_id: r.get(3)?,
                    needs_reauth: r.get::<_, i64>(4)? != 0,
                    expires_at: r.get(5)?,
                })
            })
            .map_err(|e| e.to_string())?;
        let result = output
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| e.to_string())?;
        Ok(result)
    }

    /// Retain a non-secret account audit row while erasing all local credentials.
    /// Previously prepared posts referencing this account cannot publish again.
    pub fn disconnect_account(&self, customer: &str, account: &str) -> Result<()> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let changed = conn
            .execute(
                "UPDATE accounts SET needs_reauth=1, token_enc='', refresh_enc=NULL
             WHERE id=?1 AND customer_id=?2",
                params![account, customer],
            )
            .map_err(|e| e.to_string())?;
        if changed == 1 {
            conn.execute(
                "UPDATE account_consents SET disconnected_at=?2 WHERE account_id=?1",
                params![account, now()],
            )
            .map_err(|e| e.to_string())?;
            Ok(())
        } else {
            Err("Account not found".into())
        }
    }

    /// On a restart, publishing may have succeeded remotely before we crashed.
    /// Mark as uncertain: never replay without an operator reconciling the remote post.
    pub fn quarantine_interrupted(&self) -> Result<usize> {
        let mut conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        let records: Vec<Post> = {
            let mut query = tx
                .prepare("SELECT body FROM posts WHERE status='publishing'")
                .map_err(|e| e.to_string())?;
            let rows = query
                .query_map([], |r| r.get::<_, String>(0))
                .map_err(|e| e.to_string())?;
            rows.map(|r| {
                serde_json::from_str::<Post>(&r.map_err(|e| e.to_string())?)
                    .map_err(|e| e.to_string())
            })
            .collect::<Result<Vec<_>>>()?
        };
        for mut p in records.iter().cloned() {
            p.status = Status::Failed;
            p.last_error =
                Some("Interrupted while publishing: reconcile with network before retry".into());
            p.updated_at = now();
            tx.execute("UPDATE posts SET body=?1,status='failed' WHERE id=?2 AND customer_id=?3 AND status='publishing'",
                params![serde_json::to_string(&p).map_err(|e|e.to_string())?,p.id,p.customer_id])
                .map_err(|e|e.to_string())?;
            tx.execute("INSERT INTO events(at,customer_id,post_id,kind,detail) VALUES(?1,?2,?3,'interrupted','manual reconciliation required')",
                params![now(),p.customer_id,p.id]).map_err(|e|e.to_string())?;
        }
        tx.commit().map_err(|e| e.to_string())?;
        Ok(records.len())
    }

    pub fn claim_due(&self, at: i64) -> Result<Vec<Post>> {
        let due = self.scheduled(at)?;
        let mut claimed = Vec::new();
        for mut p in due {
            if !p.may_publish(at) {
                continue;
            }
            p.status = Status::Publishing;
            p.attempts += 1;
            if self
                .move_post(&p.customer_id, p.clone(), Status::Scheduled)
                .is_ok()
            {
                claimed.push(p);
            }
        }
        Ok(claimed)
    }

    pub fn finish(
        &self,
        customer: &str,
        id: &str,
        outcome: Status,
        error: Option<String>,
        retry_at: Option<i64>,
    ) -> Result<()> {
        let mut p = self.get_post(customer, id)?;
        if p.status != Status::Publishing {
            return Err("Post is not publishing".into());
        }
        if !matches!(
            outcome,
            Status::Published | Status::Failed | Status::Scheduled
        ) {
            return Err("Bad result".into());
        }
        p.status = outcome;
        p.last_error = error;
        p.scheduled_at = retry_at.or(p.scheduled_at);
        self.move_post(customer, p, Status::Publishing)
    }

    pub fn result_exists(&self, post: &str, account: &str) -> Result<bool> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let n: i64 = conn
            .query_row(
                "SELECT count(*) FROM post_results WHERE post_id=?1 AND account_id=?2 AND ok=1",
                params![post, account],
                |r| r.get(0),
            )
            .map_err(|e| e.to_string())?;
        Ok(n > 0)
    }

    pub fn record_result(
        &self,
        post: &str,
        account: &str,
        success: bool,
        external_id: Option<&str>,
        error: Option<&str>,
    ) -> Result<()> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.execute(
            "INSERT OR IGNORE INTO post_results(post_id,account_id,ok,external_post_id,error,at)
               VALUES(?1,?2,?3,?4,?5,?6)",
            params![post, account, success as i32, external_id, error, now()],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    pub fn mark_reauth(&self, customer: &str, id: &str) -> Result<()> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let n = conn
            .execute(
                "UPDATE accounts SET needs_reauth=1 WHERE customer_id=?1 AND id=?2",
                params![customer, id],
            )
            .map_err(|e| e.to_string())?;
        if n == 1 {
            Ok(())
        } else {
            Err("Account not found".into())
        }
    }

    /// Rotate and return a customer-scoped agent credential. The plaintext is returned once.
    /// A single replacement revokes the previous credential without touching any other tenant.
    pub fn rotate_agent_key(&self, customer: &str) -> Result<String> {
        let token = random_id();
        let hash = token_hash(&token);
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let exists: i64 = conn
            .query_row(
                "SELECT count(*) FROM customers WHERE id=?1",
                [customer],
                |r| r.get(0),
            )
            .map_err(|e| e.to_string())?;
        if exists != 1 {
            return Err("Customer not found".into());
        }
        conn.execute(
            "INSERT INTO customer_agents(customer_id,token_hash) VALUES(?1,?2)
             ON CONFLICT(customer_id) DO UPDATE SET token_hash=excluded.token_hash",
            params![customer, hash],
        )
        .map_err(|e| e.to_string())?;
        Ok(token)
    }

    /// Verify only the named customer's agent credential.
    pub fn verify_agent_key(&self, customer: &str, token: &str) -> bool {
        if token.len() < 30 || token.len() > 256 {
            return false;
        }
        let Ok(conn) = self.db.lock() else {
            return false;
        };
        let stored: std::result::Result<String, _> = conn.query_row(
            "SELECT token_hash FROM customer_agents WHERE customer_id=?1",
            [customer],
            |r| r.get(0),
        );
        if let Ok(stored) = stored {
            let expected = token_hash(token);
            let mut bad = 0u8;
            for (a, b) in stored.bytes().zip(expected.bytes()) {
                bad |= a ^ b;
            }
            return stored.len() == expected.len() && bad == 0;
        }
        false
    }

    pub fn create_post(&self, customer: &str, new: NewPost) -> Result<Post> {
        if new.content.trim().is_empty() || new.account_ids.is_empty() {
            return Err("Content and at least one account are required".into());
        }
        let t = now();
        let post = Post {
            id: random_id(),
            customer_id: customer.into(),
            content: new.content,
            link: new.link,
            hashtags: new.hashtags,
            account_ids: new.account_ids,
            media: new.media,
            status: Status::Draft,
            scheduled_at: None,
            revision: 1,
            approved_revision: None,
            attempts: 0,
            last_error: None,
            created_at: t,
            updated_at: t,
        };
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.execute(
            "INSERT INTO posts(id,customer_id,body,status,scheduled_at,revision,approved_revision)
            VALUES(?1,?2,?3,'draft',NULL,1,NULL)",
            params![
                post.id,
                customer,
                serde_json::to_string(&post).map_err(|e| e.to_string())?
            ],
        )
        .map_err(|e| e.to_string())?;
        Ok(post)
    }

    pub fn get_post(&self, customer: &str, id: &str) -> Result<Post> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let s: String = conn
            .query_row(
                "SELECT body FROM posts WHERE customer_id=?1 AND id=?2",
                params![customer, id],
                |r| r.get(0),
            )
            .map_err(|_| "Post not found")?;
        serde_json::from_str(&s).map_err(|e| e.to_string())
    }

    pub fn list_posts(&self, customer: &str) -> Result<Vec<Post>> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let mut stmt = conn
            .prepare("SELECT body FROM posts WHERE customer_id=?1 ORDER BY rowid DESC")
            .map_err(|e| e.to_string())?;
        let output = stmt
            .query_map([customer], |r| r.get::<_, String>(0))
            .map_err(|e| e.to_string())?;
        output
            .map(|x| {
                serde_json::from_str(&x.map_err(|e| e.to_string())?).map_err(|e| e.to_string())
            })
            .collect::<Result<Vec<Post>>>()
    }

    /// Conditional update is scoped to both customer and prior revision/status.
    pub fn move_post(&self, customer: &str, mut post: Post, from: Status) -> Result<()> {
        if !from.can_move_to(post.status) {
            return Err("Invalid transition".into());
        }
        post.updated_at = now();
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let n=conn.execute("UPDATE posts SET body=?3,status=?4,revision=?5,approved_revision=?6,scheduled_at=?7
            WHERE customer_id=?1 AND id=?2 AND revision=?8 AND status=?9",
            params![customer,post.id,serde_json::to_string(&post).map_err(|e|e.to_string())?,
                serde_json::to_value(post.status).map_err(|e|e.to_string())?.as_str().unwrap_or(""),
                post.revision as i64,post.approved_revision.map(|n|n as i64),post.scheduled_at,
                post.revision as i64,serde_json::to_value(from).map_err(|e|e.to_string())?.as_str().unwrap_or("")])
            .map_err(|e|e.to_string())?;
        if n != 1 {
            return Err("Conflict: state changed".into());
        }
        Ok(())
    }

    pub fn edit_post(&self, customer: &str, id: &str, content: String) -> Result<Post> {
        let mut p = self.get_post(customer, id)?;
        let old = p.status;
        let revision = p.revision;
        p.edit(content, now()).map_err(str::to_owned)?;
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let n=conn.execute("UPDATE posts SET body=?3,status='draft',revision=?4,
               approved_revision=NULL,scheduled_at=NULL WHERE customer_id=?1 AND id=?2 AND revision=?5 AND status=?6",
            params![customer,id,serde_json::to_string(&p).map_err(|e|e.to_string())?,
                p.revision as i64,revision as i64,
                serde_json::to_value(old).map_err(|e|e.to_string())?.as_str().unwrap_or("")])
            .map_err(|e|e.to_string())?;
        if n != 1 {
            return Err("Conflict: edit not applied".into());
        }
        Ok(p)
    }

    pub fn submit(&self, customer: &str, id: &str) -> Result<Post> {
        let mut p = self.get_post(customer, id)?;
        if p.status != Status::Draft {
            return Err("Not a draft".into());
        }
        let rules = self.rules(customer)?;
        let mut nets = Vec::new();
        {
            let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
            for account in &p.account_ids {
                let net: Option<String> = conn
                    .query_row(
                        "SELECT network FROM accounts WHERE id=?1 AND customer_id=?2",
                        params![account, customer],
                        |r| r.get(0),
                    )
                    .optional()
                    .map_err(|e| e.to_string())?;
                nets.push(net.ok_or("Account not found for customer")?);
            }
        }
        let checked = crate::guardrails::check_post(
            &crate::guardrails::PostInput {
                content: p.content.clone(),
                link: p.link.clone(),
                hashtags: p.hashtags.clone(),
                networks: nets,
                media_count: p.media.len(),
            },
            &rules,
        );
        if !checked.ok {
            return Err(format!("Guardrails blocked: {:?}", checked.errors));
        }
        p.status = Status::PendingApproval;
        self.move_post(customer, p.clone(), Status::Draft)?;
        Ok(p)
    }

    pub fn create_approval(
        &self,
        customer: &str,
        id: &str,
        scheduled_at: i64,
        expires_at: i64,
    ) -> Result<String> {
        let p = self.get_post(customer, id)?;
        if p.status != Status::PendingApproval {
            return Err("Post must be pending approval".into());
        }
        if expires_at <= now() {
            return Err("Approval expiry is in the past".into());
        }
        let token = random_id();
        let hash = token_hash(&token);
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        conn.execute(
            "DELETE FROM approvals WHERE customer_id=?1 AND post_id=?2 AND used=0",
            params![customer, id],
        )
        .map_err(|e| e.to_string())?;
        conn.execute(
            "INSERT INTO approvals(token_hash,customer_id,post_id,revision,scheduled_at,expires_at)
              VALUES(?1,?2,?3,?4,?5,?6)",
            params![
                hash,
                customer,
                id,
                p.revision as i64,
                scheduled_at,
                expires_at
            ],
        )
        .map_err(|e| e.to_string())?;
        Ok(token)
    }

    pub fn decide(&self, customer: &str, token: &str, approve: bool, at: i64) -> Result<Post> {
        let mut conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        let record: Option<(String, i64, i64, i64, i64)> = tx
            .query_row(
                "SELECT post_id,revision,scheduled_at,expires_at,used FROM approvals
             WHERE customer_id=?1 AND token_hash=?2",
                params![customer, token_hash(token)],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
            )
            .optional()
            .map_err(|e| e.to_string())?;
        let (id, rev, scheduled, expiry, used) = record.ok_or("Approval token not found")?;
        if used != 0 || expiry <= at {
            return Err("Approval token used or expired".into());
        }
        let body: String = tx
            .query_row(
                "SELECT body FROM posts WHERE id=?1 AND customer_id=?2",
                params![id, customer],
                |r| r.get(0),
            )
            .map_err(|_| "Post missing")?;
        let mut p: Post = serde_json::from_str(&body).map_err(|e| e.to_string())?;
        if p.status != Status::PendingApproval || p.revision as i64 != rev {
            return Err("Approval revision conflict".into());
        }
        p.status = if approve {
            Status::Scheduled
        } else {
            Status::Rejected
        };
        if approve {
            p.approved_revision = Some(p.revision);
            p.scheduled_at = Some(scheduled.max(at));
        }
        p.updated_at = at;
        let n = tx
            .execute(
                "UPDATE posts SET body=?3,status=?4,approved_revision=?5,scheduled_at=?6
                WHERE customer_id=?1 AND id=?2 AND status='pending_approval' AND revision=?7",
                params![
                    customer,
                    id,
                    serde_json::to_string(&p).map_err(|e| e.to_string())?,
                    if approve { "scheduled" } else { "rejected" },
                    p.approved_revision.map(|x| x as i64),
                    p.scheduled_at,
                    rev
                ],
            )
            .map_err(|e| e.to_string())?;
        if n != 1 {
            return Err("Concurrent approval conflict".into());
        }
        tx.execute(
            "UPDATE approvals SET used=1 WHERE token_hash=?1",
            [token_hash(token)],
        )
        .map_err(|e| e.to_string())?;
        tx.execute("INSERT INTO events(at,customer_id,post_id,kind,detail) VALUES(?1,?2,?3,?4,'customer decision')",
           params![at,customer,id,if approve{"approved"}else{"rejected"}]).map_err(|e|e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(p)
    }

    pub fn scheduled(&self, at: i64) -> Result<Vec<Post>> {
        let conn = self.db.lock().map_err(|_| "DB mutex poisoned")?;
        let mut st = conn
            .prepare("SELECT body FROM posts WHERE status='scheduled' AND scheduled_at<=?1")
            .map_err(|e| e.to_string())?;
        let output = st
            .query_map([at], |r| r.get::<_, String>(0))
            .map_err(|e| e.to_string())?;
        output
            .map(|x| {
                serde_json::from_str(&x.map_err(|e| e.to_string())?).map_err(|e| e.to_string())
            })
            .collect::<Result<Vec<Post>>>()
    }
}

// Only a digest is retained in the database, never the approval token itself.
fn token_hash(token: &str) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(token.as_bytes()))
}
