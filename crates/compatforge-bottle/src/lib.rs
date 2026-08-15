//! Offline, read-only Bottle migration contracts.

#![deny(unsafe_op_in_unsafe_fn)]

pub mod contract;
mod digest;
pub mod error;
mod path;
pub mod plan;
mod platform;
pub mod snapshot;

pub use contract::{
    LegacyBottleManifest, LegacyLauncher, LegacyWineArch, MAX_ARGUMENTS, MAX_ENV_OVERRIDES, MAX_LAUNCHERS,
    MAX_MANIFEST_BYTES, MAX_TEXT_BYTES,
};
pub use error::{BottleMigrationError, DiagnosticCode};
pub use plan::{BottleMigrationPlan, EnvironmentEntry, MigrationLauncher, RuntimeMap, RuntimeMapping};
pub use snapshot::{BottleSnapshot, BottleStore, SnapshotEntry, SnapshotReceipt};
