//! Network connector interface and offline test connector.
//! Publishing accounts must be opt-in and posts must pass the approval scheduler.
use async_trait::async_trait;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

#[derive(Clone, Debug)]
pub struct PublishRequest {
    pub external_id: String,
    pub idempotency_key: String,
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub text: String,
    pub link: String,
    pub media: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct Published {
    pub external_id: String,
    pub url: Option<String>,
}

#[derive(Clone, Debug)]
pub enum ConnectorError {
    Retryable(String),
    Permanent(String),
    AuthExpired(String),
}

#[async_trait]
pub trait Connector: Send + Sync {
    fn network(&self) -> &'static str;
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError>;
}

#[derive(Default)]
pub struct Registry {
    connectors: HashMap<String, Arc<dyn Connector>>,
}
impl Registry {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn register(&mut self, c: Arc<dyn Connector>) {
        self.connectors.insert(c.network().into(), c);
    }
    pub fn get(&self, name: &str) -> Option<Arc<dyn Connector>> {
        self.connectors.get(name).cloned()
    }
}

pub struct MockConnector {
    pub requests: Mutex<Vec<PublishRequest>>,
    pub error: Mutex<Option<ConnectorError>>,
}
impl Default for MockConnector {
    fn default() -> Self {
        Self {
            requests: Mutex::new(Vec::new()),
            error: Mutex::new(None),
        }
    }
}
#[async_trait]
impl Connector for MockConnector {
    fn network(&self) -> &'static str {
        "bluesky"
    }
    async fn publish(&self, request: PublishRequest) -> Result<Published, ConnectorError> {
        self.requests.lock().unwrap().push(request);
        if let Some(err) = self.error.lock().unwrap().clone() {
            return Err(err);
        }
        Ok(Published {
            external_id: "mock-id".into(),
            url: None,
        })
    }
}
