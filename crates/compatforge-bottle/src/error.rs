use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiagnosticCode {
    SourceChanged,
    UnsafeEntry,
    InvalidManifest,
    RuntimeUnmapped,
    RuntimeMismatch,
    SnapshotCorrupt,
    TargetCollision,
    TransactionFailed,
    RollbackUnavailable,
    RollbackCorrupt,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BottleMigrationError {
    code: DiagnosticCode,
}

impl BottleMigrationError {
    #[must_use]
    pub const fn new(code: DiagnosticCode) -> Self {
        Self { code }
    }

    #[must_use]
    pub const fn code(&self) -> DiagnosticCode {
        self.code
    }

    #[must_use]
    pub const fn message(&self) -> &'static str {
        match self.code {
            DiagnosticCode::SourceChanged => "Bottle source changed during migration",
            DiagnosticCode::UnsafeEntry => "Bottle source contains an unsafe entry",
            DiagnosticCode::InvalidManifest => "Bottle manifest is invalid",
            DiagnosticCode::RuntimeUnmapped => "Bottle runtime is not mapped",
            DiagnosticCode::RuntimeMismatch => "Bottle runtime does not match",
            DiagnosticCode::SnapshotCorrupt => "Bottle snapshot is corrupt",
            DiagnosticCode::TargetCollision => "Bottle target already exists",
            DiagnosticCode::TransactionFailed => "Bottle migration transaction failed",
            DiagnosticCode::RollbackUnavailable => "Bottle rollback is unavailable",
            DiagnosticCode::RollbackCorrupt => "Bottle rollback data is corrupt",
        }
    }
}

impl fmt::Display for BottleMigrationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.message())
    }
}

impl std::error::Error for BottleMigrationError {}
