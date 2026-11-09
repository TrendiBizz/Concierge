//! Hermes gateway: the only path from Hermes's proposals to Concierge's executors.
//!
//! Hermes is an *untrusted planner*. It receives a short-lived, tenant-scoped capability and returns a typed plan.
//! Nothing it says is believed: the tenant comes from the capability, recipients must already belong to the case,
//! prices must appear in business evidence, sends respect consent, quiet hours, human takeover and approval, and every
//! mutation carries an idempotency key and the case version it was planned against. A plan with any rejected part
//! executes nothing.

pub mod backend;
pub mod capability;
pub mod ledger;
pub mod ops;
pub mod plan;
pub mod policy;
pub mod server;
