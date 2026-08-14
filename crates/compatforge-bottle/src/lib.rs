//! Offline, read-only Bottle migration contracts.

#![forbid(unsafe_code)]

pub mod contract;
mod digest;
pub mod error;
pub mod snapshot;

pub use contract::{
    LegacyBottleManifest, LegacyLauncher, LegacyWineArch, MAX_ARGUMENTS, MAX_ENV_OVERRIDES, MAX_LAUNCHERS,
    MAX_MANIFEST_BYTES, MAX_TEXT_BYTES,
};
pub use error::{BottleMigrationError, DiagnosticCode};
pub use snapshot::{BottleSnapshot, BottleStore, SnapshotEntry, SnapshotReceipt};
