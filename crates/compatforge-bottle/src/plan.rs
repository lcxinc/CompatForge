//! Deterministic planning from an authenticated Bottle snapshot.
//!
//! Planning is deliberately pure with respect to the legacy source: the only
//! bytes read by this module are the immutable snapshot manifest, its
//! content-addressed `manifest.json` object, and a previously verified Runtime
//! Pack manifest.  No current directory, process environment, or source path
//! is consulted.

use crate::contract::{LegacyBottleManifest, LegacyLauncher, LegacyWineArch, MAX_LAUNCHERS};
use crate::snapshot::BottleStore;
use crate::{BottleMigrationError, DiagnosticCode};
use compatforge_domain::{
    validate_digest, validate_id, BottleGuest, BottleManifest, BottleState, BottleStorage, CpuArchitecture,
    RuntimePackReference, WindowsVersion, SCHEMA_VERSION_V1,
};
use compatforge_runtime::{sha256_digest_bytes, RuntimePackStore};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::BTreeSet;

const LEGACY_FORMAT: &str = "macwin-bottle-v1";
const MAX_RUNTIME_MAPPINGS: usize = 4096;
const MAX_PLAN_LAUNCHERS: usize = 512;
const MAX_DIAGNOSTICS: usize = 16;
const MAX_ID_BYTES: usize = 128;
const MAX_RUNTIME_MAP_BYTES: usize = 2 * 1024 * 1024;

/// An explicit legacy Wine engine to Runtime Pack binding.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeMapping {
    pub legacy_engine_id: String,
    pub runtime_pack_id: String,
    pub runtime_pack_digest: String,
}

impl RuntimeMapping {
    fn validate(&self) -> Result<(), BottleMigrationError> {
        validate_legacy_engine_id(&self.legacy_engine_id)?;
        validate_plan_id("runtimeMap.runtimePackId", &self.runtime_pack_id)?;
        validate_canonical_digest("runtimeMap.runtimePackDigest", &self.runtime_pack_digest)
            .map_err(|_| invalid_manifest())?;
        Ok(())
    }
}

/// Closed, bounded mapping input supplied by the caller.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeMap {
    pub schema_version: String,
    pub mappings: Vec<RuntimeMapping>,
}

impl RuntimeMap {
    #[must_use]
    pub fn new(mappings: Vec<RuntimeMapping>) -> Self {
        Self {
            schema_version: SCHEMA_VERSION_V1.into(),
            mappings,
        }
    }

    #[must_use]
    pub fn mappings(&self) -> &[RuntimeMapping] {
        &self.mappings
    }

    pub fn from_json(json: &str) -> Result<Self, BottleMigrationError> {
        if json.len() > MAX_RUNTIME_MAP_BYTES {
            return Err(invalid_manifest());
        }
        let map: Self = serde_json::from_str(json).map_err(|_| invalid_manifest())?;
        map.validate()?;
        Ok(map)
    }

    pub fn validate(&self) -> Result<(), BottleMigrationError> {
        if self.schema_version != SCHEMA_VERSION_V1
            || self.mappings.is_empty()
            || self.mappings.len() > MAX_RUNTIME_MAPPINGS
        {
            return Err(invalid_manifest());
        }
        let mut engine_ids = BTreeSet::new();
        for mapping in &self.mappings {
            mapping.validate()?;
            if !engine_ids.insert(mapping.legacy_engine_id.as_str()) {
                return Err(invalid_manifest());
            }
        }
        if !is_sorted_unique(self.mappings.iter().map(|mapping| mapping.legacy_engine_id.as_str())) {
            return Err(invalid_manifest());
        }
        Ok(())
    }
}

/// A canonical environment entry used in a migration plan.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EnvironmentEntry {
    pub name: String,
    pub value: String,
}

/// Closed launcher planning input.  Legacy launchers never become Recipe
/// references: they remain explicit planning records until a later reviewed
/// Recipe import exists.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MigrationLauncher {
    pub id: String,
    pub app_id: String,
    pub bottle_id: String,
    pub display_name: String,
    pub executable: String,
    pub arguments: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub icon_path: Option<String>,
    pub environment: Vec<EnvironmentEntry>,
    pub show_in_home: bool,
}

/// A sealed, deterministic migration plan.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BottleMigrationPlan {
    pub schema_version: String,
    pub snapshot_digest: String,
    pub legacy_format: String,
    pub legacy_engine_id: String,
    pub bottle: BottleManifest,
    pub bottle_digest: String,
    pub runtime_pack: RuntimePackReference,
    pub launchers: Vec<MigrationLauncher>,
    pub diagnostics: Vec<String>,
    pub plan_digest: String,
}

impl BottleMigrationPlan {
    /// Validate all closed fields and the cryptographic seal.
    pub fn validate(&self) -> Result<(), BottleMigrationError> {
        self.validate_content()?;
        let expected_bottle = digest_serialized(&self.bottle)?;
        if !same_digest(&expected_bottle, &self.bottle_digest) {
            return Err(snapshot_corrupt());
        }
        let expected_plan = unsigned_plan_digest(self)?;
        if !same_digest(&expected_plan, &self.plan_digest) {
            return Err(snapshot_corrupt());
        }
        validate_canonical_digest("migration.planDigest", &self.plan_digest).map_err(|_| snapshot_corrupt())?;
        Ok(())
    }

    /// Return compact canonical JSON with recursively sorted object keys.
    pub fn canonical_json(&self) -> Result<Vec<u8>, BottleMigrationError> {
        canonical_json(self).map_err(|_| snapshot_corrupt())
    }

    /// Return the plan digest recomputed from the unsigned canonical form.
    pub fn recomputed_digest(&self) -> Result<String, BottleMigrationError> {
        unsigned_plan_digest(self)
    }

    fn validate_content(&self) -> Result<(), BottleMigrationError> {
        if self.schema_version != SCHEMA_VERSION_V1
            || self.legacy_format != LEGACY_FORMAT
            || self.diagnostics.len() > MAX_DIAGNOSTICS
            || !is_sorted_unique(self.diagnostics.iter().map(String::as_str))
        {
            return Err(invalid_manifest());
        }
        validate_canonical_digest("migration.snapshotDigest", &self.snapshot_digest).map_err(|_| snapshot_corrupt())?;
        validate_legacy_engine_id(&self.legacy_engine_id)?;
        if self.bottle.name.is_empty() || self.bottle.name.len() > crate::MAX_TEXT_BYTES {
            return Err(invalid_manifest());
        }
        if !matches!(
            self.bottle.guest.architecture,
            CpuArchitecture::I386 | CpuArchitecture::X86_64
        ) || !matches!(self.bottle.storage.state, BottleState::Ready)
            || !self.bottle.recipes.is_empty()
            || self.bottle.created_at.len() > crate::MAX_TEXT_BYTES
            || self.bottle.updated_at.len() > crate::MAX_TEXT_BYTES
        {
            return Err(invalid_manifest());
        }
        validate_plan_id("migration.bottle.id", &self.bottle.id)?;
        self.bottle.validate().map_err(|_| invalid_manifest())?;
        validate_canonical_digest("migration.bottleDigest", &self.bottle_digest).map_err(|_| snapshot_corrupt())?;
        validate_plan_id("migration.runtimePack.id", &self.runtime_pack.id)?;
        validate_canonical_digest("migration.runtimePack.digest", &self.runtime_pack.digest)
            .map_err(|_| runtime_mismatch())?;
        if self.bottle.runtime_pack != self.runtime_pack {
            return Err(runtime_mismatch());
        }
        if self.launchers.len() > MAX_PLAN_LAUNCHERS {
            return Err(invalid_manifest());
        }
        let mut launcher_ids = BTreeSet::new();
        for launcher in &self.launchers {
            validate_plan_id("migration.launcher.id", &launcher.id)?;
            validate_plan_id("migration.launcher.appId", &launcher.app_id)?;
            if launcher.bottle_id != self.bottle.id {
                return Err(invalid_manifest());
            }
            if !launcher_ids.insert(launcher.id.as_str()) {
                return Err(invalid_manifest());
            }
            if launcher.display_name.trim().is_empty() || launcher.display_name.len() > crate::MAX_TEXT_BYTES {
                return Err(invalid_manifest());
            }
            validate_guest_path(&launcher.executable)?;
            if let Some(icon) = &launcher.icon_path {
                validate_guest_path(icon)?;
            }
            if launcher.arguments.len() > crate::MAX_ARGUMENTS
                || launcher
                    .arguments
                    .iter()
                    .any(|argument| argument.len() > crate::MAX_TEXT_BYTES)
            {
                return Err(invalid_manifest());
            }
            validate_environment_entries(&launcher.environment)?;
        }
        if !is_sorted_unique(self.launchers.iter().map(|launcher| launcher.id.as_str())) {
            return Err(invalid_manifest());
        }
        for diagnostic in &self.diagnostics {
            if !matches!(
                diagnostic.as_str(),
                "source-changed"
                    | "unsafe-entry"
                    | "invalid-manifest"
                    | "runtime-unmapped"
                    | "runtime-mismatch"
                    | "snapshot-corrupt"
                    | "target-collision"
                    | "transaction-failed"
                    | "rollback-unavailable"
                    | "rollback-corrupt"
            ) {
                return Err(invalid_manifest());
            }
        }
        Ok(())
    }
}

impl BottleStore {
    /// Build a migration plan from a verified snapshot and an exact Runtime
    /// Pack mapping.  This method never reads the legacy source directory.
    pub fn plan(
        &self,
        snapshot_digest: &str,
        runtime_store: &RuntimePackStore,
        runtime_map: &RuntimeMap,
    ) -> Result<BottleMigrationPlan, BottleMigrationError> {
        validate_digest("migration.snapshotDigest", snapshot_digest).map_err(|_| snapshot_corrupt())?;
        runtime_map.validate()?;

        let snapshot = self.verify_snapshot(snapshot_digest)?;
        if snapshot.legacy_format != LEGACY_FORMAT {
            return Err(snapshot_corrupt());
        }
        let legacy = self.read_legacy_manifest_object(&snapshot)?;
        if legacy.id != snapshot.bottle_id {
            return Err(snapshot_corrupt());
        }

        let matching = runtime_map
            .mappings
            .iter()
            .filter(|mapping| mapping.legacy_engine_id == legacy.engine_id)
            .collect::<Vec<_>>();
        let mapping = match matching.as_slice() {
            [] => return Err(runtime_unmapped()),
            [mapping] => *mapping,
            _ => return Err(runtime_mismatch()),
        };
        let runtime_manifest = runtime_store
            .verified_manifest(&mapping.runtime_pack_digest)
            .map_err(|_| runtime_mismatch())?;
        if runtime_manifest.id != mapping.runtime_pack_id
            || !same_digest(&runtime_manifest.digest, &mapping.runtime_pack_digest)
        {
            return Err(runtime_mismatch());
        }

        let bottle = build_bottle(&legacy, &mapping.runtime_pack_id, &mapping.runtime_pack_digest)?;
        let bottle_digest = digest_serialized(&bottle)?;
        let launchers = build_launchers(&legacy)?;
        let mut plan = BottleMigrationPlan {
            schema_version: SCHEMA_VERSION_V1.into(),
            snapshot_digest: normalize_digest(snapshot_digest),
            legacy_format: snapshot.legacy_format,
            legacy_engine_id: legacy.engine_id,
            bottle,
            bottle_digest,
            runtime_pack: RuntimePackReference {
                id: mapping.runtime_pack_id.clone(),
                digest: normalize_digest(&mapping.runtime_pack_digest),
            },
            launchers,
            diagnostics: Vec::new(),
            plan_digest: String::new(),
        };
        plan.plan_digest = unsigned_plan_digest(&plan)?;
        plan.validate()?;
        Ok(plan)
    }
}

fn build_bottle(
    legacy: &LegacyBottleManifest,
    runtime_id: &str,
    runtime_digest: &str,
) -> Result<BottleManifest, BottleMigrationError> {
    let windows_version = match legacy.windows_version.as_str() {
        "win7" => WindowsVersion::Win7,
        "win10" => WindowsVersion::Win10,
        "win11" => WindowsVersion::Win11,
        _ => return Err(invalid_manifest()),
    };
    let architecture = match legacy.arch {
        LegacyWineArch::Win32 => CpuArchitecture::I386,
        LegacyWineArch::Win64 => CpuArchitecture::X86_64,
    };
    let bottle = BottleManifest {
        schema_version: SCHEMA_VERSION_V1.into(),
        id: legacy.id.clone(),
        name: legacy.name.clone(),
        guest: BottleGuest {
            windows_version,
            architecture,
        },
        runtime_pack: RuntimePackReference {
            id: runtime_id.into(),
            digest: normalize_digest(runtime_digest),
        },
        recipes: Vec::new(),
        storage: BottleStorage {
            layout_version: 1,
            state: BottleState::Ready,
        },
        created_at: legacy.created_at.clone(),
        updated_at: legacy.updated_at.clone(),
    };
    bottle.validate().map_err(|_| invalid_manifest())?;
    Ok(bottle)
}

fn build_launchers(legacy: &LegacyBottleManifest) -> Result<Vec<MigrationLauncher>, BottleMigrationError> {
    if legacy.installed_apps.len() > MAX_PLAN_LAUNCHERS || legacy.installed_apps.len() > MAX_LAUNCHERS {
        return Err(invalid_manifest());
    }
    let mut launchers = legacy
        .installed_apps
        .iter()
        .map(|launcher| build_launcher(legacy, launcher))
        .collect::<Result<Vec<_>, _>>()?;
    launchers.sort_by(|left, right| left.id.cmp(&right.id));
    Ok(launchers)
}

fn build_launcher(
    bottle: &LegacyBottleManifest,
    legacy: &LegacyLauncher,
) -> Result<MigrationLauncher, BottleMigrationError> {
    validate_guest_path(&legacy.exe_path)?;
    if let Some(icon) = &legacy.icon_path {
        validate_guest_path(icon)?;
    }
    let mut merged = bottle.env_overrides.clone();
    merged.extend(legacy.env_overrides.clone());
    let environment: Vec<EnvironmentEntry> = merged
        .into_iter()
        .map(|(name, value)| EnvironmentEntry { name, value })
        .collect();
    Ok(MigrationLauncher {
        id: legacy.id.clone(),
        app_id: legacy.app_id.clone(),
        bottle_id: legacy.bottle_id.clone(),
        display_name: legacy.display_name.clone(),
        executable: legacy.exe_path.clone(),
        arguments: legacy.args.clone(),
        icon_path: legacy.icon_path.clone(),
        environment,
        show_in_home: legacy.show_in_home,
    })
}

fn validate_environment_entries(entries: &[EnvironmentEntry]) -> Result<(), BottleMigrationError> {
    if entries.len() > crate::MAX_ENV_OVERRIDES || !is_sorted_unique(entries.iter().map(|entry| entry.name.as_str())) {
        return Err(invalid_manifest());
    }
    for entry in entries {
        if entry.name.trim().is_empty()
            || entry.name.len() > crate::MAX_TEXT_BYTES
            || entry.value.len() > crate::MAX_TEXT_BYTES
        {
            return Err(invalid_manifest());
        }
    }
    Ok(())
}

fn validate_guest_path(value: &str) -> Result<(), BottleMigrationError> {
    crate::path::validate_relative_path(value).map_err(|_| unsafe_entry())
}

fn is_sorted_unique<'a>(values: impl Iterator<Item = &'a str>) -> bool {
    let values = values.collect::<Vec<_>>();
    values.windows(2).all(|window| window[0] < window[1])
}

fn validate_legacy_engine_id(value: &str) -> Result<(), BottleMigrationError> {
    if value.is_empty()
        || value.len() > MAX_ID_BYTES
        || !value.as_bytes()[0].is_ascii_alphanumeric()
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'+' | b'-'))
    {
        return Err(invalid_manifest());
    }
    Ok(())
}

fn validate_plan_id(field: &'static str, value: &str) -> Result<(), BottleMigrationError> {
    if value.len() > MAX_ID_BYTES {
        return Err(invalid_manifest());
    }
    validate_id(field, value).map_err(|_| invalid_manifest())
}

fn validate_canonical_digest(field: &'static str, value: &str) -> Result<(), BottleMigrationError> {
    validate_digest(field, value).map_err(|_| invalid_manifest())?;
    if normalize_digest(value) != value {
        return Err(invalid_manifest());
    }
    Ok(())
}

fn digest_serialized<T: Serialize>(value: &T) -> Result<String, BottleMigrationError> {
    let bytes = canonical_json(value).map_err(|_| snapshot_corrupt())?;
    Ok(sha256_digest_bytes(&bytes))
}

fn unsigned_plan_digest(plan: &BottleMigrationPlan) -> Result<String, BottleMigrationError> {
    let mut value = serde_json::to_value(plan).map_err(|_| snapshot_corrupt())?;
    if let Value::Object(object) = &mut value {
        object.remove("planDigest");
    } else {
        return Err(snapshot_corrupt());
    }
    let bytes = canonical_value_bytes(&value).map_err(|_| snapshot_corrupt())?;
    Ok(sha256_digest_bytes(&bytes))
}

fn canonical_json<T: Serialize>(value: &T) -> Result<Vec<u8>, serde_json::Error> {
    let value = serde_json::to_value(value)?;
    canonical_value_bytes(&value)
}

fn canonical_value_bytes(value: &Value) -> Result<Vec<u8>, serde_json::Error> {
    serde_json::to_vec(&canonicalize(value))
}

fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Object(object) => {
            let mut entries = object.iter().collect::<Vec<_>>();
            entries.sort_by(|left, right| left.0.cmp(right.0));
            let mut sorted = Map::new();
            for (key, item) in entries {
                sorted.insert(key.clone(), canonicalize(item));
            }
            Value::Object(sorted)
        }
        Value::Array(items) => Value::Array(items.iter().map(canonicalize).collect()),
        scalar => scalar.clone(),
    }
}

fn same_digest(left: &str, right: &str) -> bool {
    left.eq_ignore_ascii_case(right)
}

fn normalize_digest(value: &str) -> String {
    let mut normalized = value.to_ascii_lowercase();
    if !normalized.starts_with("sha256:") {
        normalized.insert_str(0, "sha256:");
    }
    normalized
}

fn invalid_manifest() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::InvalidManifest)
}

fn snapshot_corrupt() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::SnapshotCorrupt)
}

fn unsafe_entry() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::UnsafeEntry)
}

fn runtime_unmapped() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::RuntimeUnmapped)
}

fn runtime_mismatch() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::RuntimeMismatch)
}

#[cfg(all(test, not(target_os = "macos")))]
type LegacyManifestBytesHook = Box<dyn FnOnce(&mut Vec<u8>)>;

#[cfg(all(test, not(target_os = "macos")))]
thread_local! {
    static LEGACY_MANIFEST_READ_HOOK: std::cell::RefCell<Option<Box<dyn FnOnce()>>> = const {
        std::cell::RefCell::new(None)
    };
    static LEGACY_MANIFEST_AFTER_BYTES_HOOK: std::cell::RefCell<Option<LegacyManifestBytesHook>> = const {
        std::cell::RefCell::new(None)
    };
}

#[cfg(all(test, not(target_os = "macos")))]
pub(crate) fn set_legacy_manifest_read_hook(hook: Box<dyn FnOnce()>) {
    LEGACY_MANIFEST_READ_HOOK.with(|value| *value.borrow_mut() = Some(hook));
}

#[cfg(all(test, not(target_os = "macos")))]
pub(crate) fn run_legacy_manifest_read_hook() {
    let hook = LEGACY_MANIFEST_READ_HOOK.with(|value| value.borrow_mut().take());
    if let Some(hook) = hook {
        hook();
    }
}

#[cfg(all(test, not(target_os = "macos")))]
pub(crate) fn set_legacy_manifest_after_bytes_hook(hook: LegacyManifestBytesHook) {
    LEGACY_MANIFEST_AFTER_BYTES_HOOK.with(|value| *value.borrow_mut() = Some(hook));
}

#[cfg(all(test, not(target_os = "macos")))]
pub(crate) fn run_legacy_manifest_after_bytes_hook(bytes: &mut Vec<u8>) {
    let hook = LEGACY_MANIFEST_AFTER_BYTES_HOOK.with(|value| value.borrow_mut().take());
    if let Some(hook) = hook {
        hook(bytes);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(target_os = "macos")]
    use crate::DiagnosticCode;
    #[cfg(not(target_os = "macos"))]
    use crate::{BottleSnapshot, BottleStore, DiagnosticCode};
    #[cfg(not(target_os = "macos"))]
    use compatforge_domain::{HostOs, LaunchPlan, RuntimeChannel, RuntimeComponent, RuntimeHost, RuntimePackManifest};
    #[cfg(not(target_os = "macos"))]
    use compatforge_runtime::{RejectAllSignatures, RuntimePackStore};
    #[cfg(not(target_os = "macos"))]
    use serde_json::json;
    #[cfg(not(target_os = "macos"))]
    use std::collections::BTreeMap;
    #[cfg(not(target_os = "macos"))]
    use std::fs;
    #[cfg(not(target_os = "macos"))]
    use std::path::{Path, PathBuf};
    #[cfg(not(target_os = "macos"))]
    use std::time::{SystemTime, UNIX_EPOCH};

    #[cfg(not(target_os = "macos"))]
    struct TestDirectory(PathBuf);

    #[cfg(not(target_os = "macos"))]
    impl TestDirectory {
        fn new(name: &str) -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock should be after Unix epoch")
                .as_nanos();
            let path =
                std::env::temp_dir().join(format!("compatforge-bottle-plan-{name}-{}-{nonce}", std::process::id()));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    #[cfg(not(target_os = "macos"))]
    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[cfg(not(target_os = "macos"))]
    fn setup_inputs(
        executable: &str,
        windows_version: &str,
        arch: &str,
    ) -> (TestDirectory, BottleStore, RuntimePackStore, RuntimeMap, String) {
        let temporary = TestDirectory::new("setup");
        let source = temporary.path().join("source");
        fs::create_dir_all(source.join("drive_c/Example")).unwrap();
        fs::create_dir_all(source.join("icons")).unwrap();
        fs::write(source.join("drive_c/Example/example.exe"), b"fixture executable").unwrap();
        fs::write(source.join("icons/example.png"), b"fixture icon").unwrap();
        let manifest = json!({
            "id": "bottle-fixture",
            "name": "Fixture Bottle",
            "windowsVersion": windows_version,
            "arch": arch,
            "engineId": "wine-9",
            "envOverrides": {"SHARED": "bottle", "BOTTLE": "yes"},
            "installedApps": [{
                "id": "launcher-z",
                "appId": "app-fixture",
                "bottleId": "bottle-fixture",
                "displayName": "Fixture",
                "exePath": executable,
                "args": ["--safe"],
                "iconPath": "icons/example.png",
                "envOverrides": {"SHARED": "launcher", "LAUNCHER": "yes"},
                "showInHome": true
            }],
            "createdAt": "2026-08-08T00:00:00Z",
            "updatedAt": "2026-08-08T00:00:01Z"
        });
        fs::write(
            source.join("manifest.json"),
            serde_json::to_vec_pretty(&manifest).unwrap(),
        )
        .unwrap();

        let bottle_store = BottleStore::new(temporary.path().join("store"));
        let receipt = bottle_store.snapshot(&source).unwrap();

        let bundle = temporary.path().join("runtime-bundle");
        fs::create_dir_all(bundle.join("components")).unwrap();
        let artifact = b"fixture-runtime";
        fs::write(bundle.join("components/runtime.blob"), artifact).unwrap();
        let mut runtime_manifest = RuntimePackManifest {
            schema_version: SCHEMA_VERSION_V1.into(),
            id: "fixture-runtime".into(),
            version: "1.0.0".into(),
            channel: Some(RuntimeChannel::Preview),
            host: RuntimeHost {
                os: HostOs::Linux,
                architecture: CpuArchitecture::X86_64,
                minimum_version: None,
            },
            components: vec![RuntimeComponent {
                name: "runtime".into(),
                version: "1.0.0".into(),
                license: "MIT".into(),
                source: None,
                artifact: Some("components/runtime.blob".into()),
                digest: sha256_digest_bytes(artifact),
                entrypoints: BTreeMap::new(),
            }],
            capabilities: vec!["guest-x86_64".into()],
            digest: "sha256:0000000000000000000000000000000000000000000000000000000000000000".into(),
            signature: None,
            sbom: None,
        };
        runtime_manifest.digest = sha256_digest_bytes(&runtime_manifest.canonical_unsigned_bytes().unwrap());
        let runtime_store = RuntimePackStore::new(temporary.path().join("runtime-store"));
        runtime_store
            .install(&bundle, &runtime_manifest, &RejectAllSignatures)
            .unwrap();
        let runtime_map = RuntimeMap::new(vec![RuntimeMapping {
            legacy_engine_id: "wine-9".into(),
            runtime_pack_id: "fixture-runtime".into(),
            runtime_pack_digest: runtime_manifest.digest,
        }]);
        (
            temporary,
            bottle_store,
            runtime_store,
            runtime_map,
            receipt.snapshot_digest,
        )
    }

    #[cfg(not(target_os = "macos"))]
    fn setup_case(executable: &str, windows_version: &str, arch: &str) -> (TestDirectory, BottleMigrationPlan) {
        let (temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs(executable, windows_version, arch);
        let plan = bottle_store
            .plan(&snapshot_digest, &runtime_store, &runtime_map)
            .unwrap();
        (temporary, plan)
    }

    #[test]
    #[cfg(not(target_os = "macos"))]
    fn planning_binds_the_exact_runtime_pack_and_merges_launcher_environment() {
        let (_temporary, plan) = setup_case("drive_c/Example/example.exe", "win10", "win64");
        assert_eq!(plan.runtime_pack.id, "fixture-runtime");
        assert!(plan.runtime_pack.digest.starts_with("sha256:"));
        assert_eq!(plan.launchers[0].environment[0].name, "BOTTLE");
        assert_eq!(plan.launchers[0].environment[1].name, "LAUNCHER");
        assert_eq!(plan.launchers[0].environment[2].value, "launcher");
        assert_eq!(plan.bottle.created_at, "2026-08-08T00:00:00Z");
        assert_eq!(plan.bottle.updated_at, "2026-08-08T00:00:01Z");
        plan.validate().unwrap();
        assert_eq!(plan.recomputed_digest().unwrap(), plan.plan_digest);
    }

    #[test]
    fn runtime_mapping_requires_one_exact_legacy_engine_record() {
        let mapping = RuntimeMap::new(vec![
            RuntimeMapping {
                legacy_engine_id: "wine-9".into(),
                runtime_pack_id: "runtime-a".into(),
                runtime_pack_digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
            },
            RuntimeMapping {
                legacy_engine_id: "wine-9".into(),
                runtime_pack_id: "runtime-b".into(),
                runtime_pack_digest: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
            },
        ]);
        assert_eq!(mapping.validate().unwrap_err().code(), DiagnosticCode::InvalidManifest);
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn planning_rejects_wrong_runtime_binding_and_unsafe_guest_paths() {
        let (_temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs("../outside.exe", "win10", "win64");
        let error = bottle_store
            .plan(&snapshot_digest, &runtime_store, &runtime_map)
            .unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn planning_rejects_missing_or_mismatched_runtime_mapping() {
        let (_temporary, bottle_store, runtime_store, _runtime_map, snapshot_digest) =
            setup_inputs("drive_c/Example/example.exe", "win10", "win64");
        let missing = RuntimeMap::new(vec![RuntimeMapping {
            legacy_engine_id: "wine-other".into(),
            runtime_pack_id: "fixture-runtime".into(),
            runtime_pack_digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
        }]);
        assert_eq!(
            bottle_store
                .plan(&snapshot_digest, &runtime_store, &missing)
                .unwrap_err()
                .code(),
            DiagnosticCode::RuntimeUnmapped
        );

        let wrong_id = RuntimeMap::new(vec![RuntimeMapping {
            legacy_engine_id: "wine-9".into(),
            runtime_pack_id: "other-runtime".into(),
            runtime_pack_digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".into(),
        }]);
        assert_eq!(
            bottle_store
                .plan(&snapshot_digest, &runtime_store, &wrong_id)
                .unwrap_err()
                .code(),
            DiagnosticCode::RuntimeMismatch
        );
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn planning_rejects_unsupported_legacy_guest_and_corrupt_runtime_or_snapshot() {
        let (_temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs("drive_c/Example/example.exe", "winxp", "win64");
        assert_eq!(
            bottle_store
                .plan(&snapshot_digest, &runtime_store, &runtime_map)
                .unwrap_err()
                .code(),
            DiagnosticCode::InvalidManifest
        );

        let (_temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs("drive_c/Example/example.exe", "win10", "win64");
        let manifest_path = fs::read_dir(runtime_store.root().join("manifests/sha256"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        fs::write(manifest_path, b"{}\n").unwrap();
        assert_eq!(
            bottle_store
                .plan(&snapshot_digest, &runtime_store, &runtime_map)
                .unwrap_err()
                .code(),
            DiagnosticCode::RuntimeMismatch
        );

        let (_temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs("drive_c/Example/example.exe", "win10", "win64");
        let snapshot_path = bottle_store
            .root()
            .join("snapshots/sha256")
            .join(format!("{}.json", snapshot_digest.trim_start_matches("sha256:")));
        fs::write(snapshot_path, b"{}\n").unwrap();
        assert_eq!(
            bottle_store
                .plan(&snapshot_digest, &runtime_store, &runtime_map)
                .unwrap_err()
                .code(),
            DiagnosticCode::SnapshotCorrupt
        );
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn sealed_plan_validation_rejects_schema_widening_mutants() {
        let (_temporary, mut plan) = setup_case("drive_c/Example/example.exe", "win10", "win64");
        plan.bottle.guest.architecture = CpuArchitecture::Arm64;
        plan.bottle_digest = digest_serialized(&plan.bottle).unwrap();
        plan.plan_digest = unsigned_plan_digest(&plan).unwrap();
        assert_eq!(plan.validate().unwrap_err().code(), DiagnosticCode::InvalidManifest);

        let (_temporary, mut plan) = setup_case("drive_c/Example/example.exe", "win10", "win64");
        plan.bottle.name = "x".repeat(crate::MAX_TEXT_BYTES + 1);
        plan.bottle_digest = digest_serialized(&plan.bottle).unwrap();
        plan.plan_digest = unsigned_plan_digest(&plan).unwrap();
        assert_eq!(plan.validate().unwrap_err().code(), DiagnosticCode::InvalidManifest);
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn sealed_plan_validation_rejects_oversized_guest_path_components() {
        let (_temporary, mut plan) = setup_case("drive_c/Example/example.exe", "win10", "win64");
        plan.launchers[0].executable = format!("drive_c/{}", "x".repeat(256));
        plan.plan_digest = unsigned_plan_digest(&plan).unwrap();
        assert_eq!(plan.validate().unwrap_err().code(), DiagnosticCode::UnsafeEntry);
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn planning_rejects_same_size_manifest_mutation_after_snapshot_authentication() {
        let (_temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs("drive_c/Example/example.exe", "win10", "win64");
        let snapshot_path = bottle_store
            .root()
            .join("snapshots/sha256")
            .join(format!("{}.json", snapshot_digest.trim_start_matches("sha256:")));
        let snapshot: BottleSnapshot = serde_json::from_slice(&fs::read(&snapshot_path).unwrap()).unwrap();
        let object_digest = snapshot
            .entries
            .iter()
            .find_map(|entry| match entry {
                crate::SnapshotEntry::File { path, digest, .. } if path == "manifest.json" => Some(digest.clone()),
                _ => None,
            })
            .unwrap();
        let object_path = bottle_store
            .root()
            .join("objects/sha256")
            .join(object_digest.trim_start_matches("sha256:"));
        let mut tampered = fs::read(&object_path).unwrap();
        let original = b"Fixture Bottle";
        let replacement = b"Nixture Bottle";
        let start = tampered
            .windows(original.len())
            .position(|window| window == original)
            .unwrap();
        tampered[start..start + replacement.len()].copy_from_slice(replacement);
        set_legacy_manifest_read_hook(Box::new(move || fs::write(&object_path, &tampered).unwrap()));

        let error = bottle_store
            .plan(&snapshot_digest, &runtime_store, &runtime_map)
            .unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn planning_rejects_manifest_buffer_mutation_before_second_readback() {
        let (_temporary, bottle_store, runtime_store, runtime_map, snapshot_digest) =
            setup_inputs("drive_c/Example/example.exe", "win10", "win64");
        set_legacy_manifest_after_bytes_hook(Box::new(|bytes| {
            let original = b"Fixture Bottle";
            let replacement = b"Nixture Bottle";
            let start = bytes
                .windows(original.len())
                .position(|window| window == original)
                .unwrap();
            bytes[start..start + replacement.len()].copy_from_slice(replacement);
        }));

        let error = bottle_store
            .plan(&snapshot_digest, &runtime_store, &runtime_map)
            .unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn planning_golden_matches_independent_fixture_and_launch_schema() {
        let fixture_root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/bottle-migration");
        let runtime_fixture = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/runtime-packs/basic-v2");
        let temporary = TestDirectory::new("planning-golden");
        let runtime_store = RuntimePackStore::new(temporary.path().join("runtime-store"));
        runtime_store
            .install_bundle(&runtime_fixture, "manifest.json", &RejectAllSignatures)
            .unwrap();
        let runtime_map =
            RuntimeMap::from_json(&fs::read_to_string(fixture_root.join("runtime-map.json")).unwrap()).unwrap();

        for case in ["win64", "win32"] {
            let source = temporary.path().join(case);
            copy_fixture_tree(&fixture_root.join(case), &source);
            let bottle_store = BottleStore::new(temporary.path().join(format!("store-{case}")));
            let receipt = bottle_store.snapshot(&source).unwrap();
            let plan = bottle_store
                .plan(&receipt.snapshot_digest, &runtime_store, &runtime_map)
                .unwrap();
            let expected: BottleMigrationPlan = serde_json::from_slice(
                &fs::read(fixture_root.join("goldens").join(format!("{case}-migration-plan.json"))).unwrap(),
            )
            .unwrap();
            assert_eq!(plan, expected, "migration golden mismatch for {case}");
            expected.validate().unwrap();

            let launch: LaunchPlan = serde_json::from_slice(
                &fs::read(fixture_root.join("goldens").join(format!("{case}-launch-plan.json"))).unwrap(),
            )
            .unwrap();
            launch.validate().unwrap();
        }
    }

    #[cfg(not(target_os = "macos"))]
    fn copy_fixture_tree(source: &Path, destination: &Path) {
        fs::create_dir_all(destination).unwrap();
        for entry in fs::read_dir(source).unwrap() {
            let entry = entry.unwrap();
            let source_path = entry.path();
            let destination_path = destination.join(entry.file_name());
            if source_path.is_dir() {
                copy_fixture_tree(&source_path, &destination_path);
            } else {
                fs::copy(source_path, destination_path).unwrap();
            }
        }
    }
}
