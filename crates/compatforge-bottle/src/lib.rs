//! Offline, read-only Bottle migration contracts.

#![forbid(unsafe_code)]

pub mod contract;
pub mod error;

pub use contract::{
    LegacyBottleManifest, LegacyLauncher, LegacyWineArch, MAX_ARGUMENTS, MAX_ENV_OVERRIDES, MAX_LAUNCHERS,
    MAX_MANIFEST_BYTES, MAX_TEXT_BYTES,
};
pub use error::{BottleMigrationError, DiagnosticCode};
