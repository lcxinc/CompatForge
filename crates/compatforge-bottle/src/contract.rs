use crate::{BottleMigrationError, DiagnosticCode};
use compatforge_domain::validate_rfc3339;
use serde::de::{DeserializeSeed, Error as _, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const MAX_MANIFEST_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_TEXT_BYTES: usize = 4096;
pub const MAX_LAUNCHERS: usize = 1024;
pub const MAX_ARGUMENTS: usize = 256;
pub const MAX_ENV_OVERRIDES: usize = 256;
pub const MAX_VERSION_HISTORY: usize = 32;
pub const MAX_VERSION_JSON_BYTES: usize = 2 * 1024 * 1024;

/// The only mutable pointer in a Bottle migration store.  Version targets
/// themselves are immutable and are addressed by their plan digest.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BottleActiveRef {
    pub schema_version: String,
    pub bottle_id: String,
    pub active_plan_digest: String,
    pub history: Vec<String>,
}

impl BottleActiveRef {
    pub fn from_json(json: &str) -> Result<Self, BottleMigrationError> {
        if json.len() > MAX_VERSION_JSON_BYTES {
            return Err(BottleMigrationError::new(DiagnosticCode::InvalidManifest));
        }
        let mut deserializer = serde_json::Deserializer::from_str(json);
        let raw = StrictJsonValueSeed
            .deserialize(&mut deserializer)
            .map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
        deserializer
            .end()
            .map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
        let value: Self =
            serde_json::from_value(raw).map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
        value.validate()?;
        Ok(value)
    }

    pub fn canonical_json(&self) -> Result<Vec<u8>, BottleMigrationError> {
        let value =
            serde_json::to_value(self).map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
        serde_json::to_vec(&canonicalize_contract_json(&value))
            .map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))
    }

    pub fn validate(&self) -> Result<(), BottleMigrationError> {
        if self.schema_version != compatforge_domain::SCHEMA_VERSION_V1 || self.history.len() > MAX_VERSION_HISTORY {
            return Err(BottleMigrationError::new(DiagnosticCode::InvalidManifest));
        }
        compatforge_domain::validate_id("bottle.activeRef.bottleId", &self.bottle_id)
            .map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
        compatforge_domain::validate_digest("bottle.activeRef.activePlanDigest", &self.active_plan_digest)
            .map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
        if self.active_plan_digest.to_ascii_lowercase() != self.active_plan_digest {
            return Err(BottleMigrationError::new(DiagnosticCode::InvalidManifest));
        }
        let mut seen = BTreeSet::new();
        for digest in &self.history {
            compatforge_domain::validate_digest("bottle.activeRef.history", digest)
                .map_err(|_| BottleMigrationError::new(DiagnosticCode::InvalidManifest))?;
            if digest.to_ascii_lowercase() != *digest {
                return Err(BottleMigrationError::new(DiagnosticCode::InvalidManifest));
            }
            if digest == &self.active_plan_digest || !seen.insert(digest.as_str()) {
                return Err(BottleMigrationError::new(DiagnosticCode::InvalidManifest));
            }
        }
        Ok(())
    }
}

struct StrictJsonValueSeed;

impl<'de> DeserializeSeed<'de> for StrictJsonValueSeed {
    type Value = serde_json::Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictJsonValueVisitor)
    }
}

struct StrictJsonValueVisitor;

impl<'de> Visitor<'de> for StrictJsonValueVisitor {
    type Value = serde_json::Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value without duplicate object keys")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Bool(value))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Number(value.into()))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Number(value.into()))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: serde::de::Error,
    {
        serde_json::Number::from_f64(value)
            .map(serde_json::Value::Number)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
        Ok(serde_json::Value::String(value.into()))
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(serde_json::Value::String(value))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Null)
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Null)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = sequence.next_element_seed(StrictJsonValueSeed)? {
            values.push(value);
        }
        Ok(serde_json::Value::Array(values))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = serde_json::Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(A::Error::custom("duplicate JSON object key"));
            }
            let value = map.next_value_seed(StrictJsonValueSeed)?;
            values.insert(key, value);
        }
        Ok(serde_json::Value::Object(values))
    }
}

fn canonicalize_contract_json(value: &serde_json::Value) -> serde_json::Value {
    match value {
        serde_json::Value::Object(object) => {
            let mut entries = object.iter().collect::<Vec<_>>();
            entries.sort_by(|left, right| left.0.cmp(right.0));
            let mut sorted = serde_json::Map::new();
            for (key, item) in entries {
                sorted.insert(key.clone(), canonicalize_contract_json(item));
            }
            serde_json::Value::Object(sorted)
        }
        serde_json::Value::Array(items) => {
            serde_json::Value::Array(items.iter().map(canonicalize_contract_json).collect())
        }
        scalar => scalar.clone(),
    }
}

/// Receipt returned after a version is published and the active ref is
/// atomically switched.  A repeated identical import is reported as a no-op.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportReceipt {
    pub schema_version: String,
    pub bottle_id: String,
    pub plan_digest: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub previous_plan_digest: Option<String>,
    pub activated: bool,
}

/// Rollback returns the same bounded activation receipt as import.  The alias
/// keeps the public operation names explicit without introducing a second,
/// drift-prone wire contract.
pub type RollbackReceipt = ImportReceipt;

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LegacyBottleManifest {
    pub id: String,
    pub name: String,
    pub windows_version: String,
    pub arch: LegacyWineArch,
    pub engine_id: String,
    #[serde(deserialize_with = "deserialize_environment")]
    pub env_overrides: BTreeMap<String, String>,
    #[serde(deserialize_with = "deserialize_launchers")]
    pub installed_apps: Vec<LegacyLauncher>,
    pub created_at: String,
    pub updated_at: String,
}

impl LegacyBottleManifest {
    pub fn from_json(json: &str) -> Result<Self, BottleMigrationError> {
        if json.len() > MAX_MANIFEST_BYTES {
            return Err(invalid_manifest());
        }
        let manifest: Self = serde_json::from_str(json).map_err(|_| invalid_manifest())?;
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn validate(&self) -> Result<(), BottleMigrationError> {
        validate_required_text(&self.id)?;
        validate_required_text(&self.name)?;
        validate_required_text(&self.windows_version)?;
        validate_required_text(&self.engine_id)?;
        validate_environment(&self.env_overrides)?;

        if self.installed_apps.len() > MAX_LAUNCHERS {
            return Err(invalid_manifest());
        }
        let mut launcher_ids = BTreeSet::new();
        for launcher in &self.installed_apps {
            launcher.validate(&self.id)?;
            if !launcher_ids.insert(launcher.id.as_str()) {
                return Err(invalid_manifest());
            }
        }

        validate_required_text(&self.created_at)?;
        validate_required_text(&self.updated_at)?;
        validate_rfc3339("legacyBottle.createdAt", &self.created_at).map_err(|_| invalid_manifest())?;
        validate_rfc3339("legacyBottle.updatedAt", &self.updated_at).map_err(|_| invalid_manifest())?;
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LegacyLauncher {
    pub id: String,
    pub app_id: String,
    pub bottle_id: String,
    pub display_name: String,
    pub exe_path: String,
    #[serde(deserialize_with = "deserialize_arguments")]
    pub args: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub icon_path: Option<String>,
    #[serde(deserialize_with = "deserialize_environment")]
    pub env_overrides: BTreeMap<String, String>,
    pub show_in_home: bool,
}

impl LegacyLauncher {
    fn validate(&self, bottle_id: &str) -> Result<(), BottleMigrationError> {
        self.validate_fields()?;
        if self.bottle_id != bottle_id {
            return Err(invalid_manifest());
        }
        Ok(())
    }

    fn validate_fields(&self) -> Result<(), BottleMigrationError> {
        for value in [
            &self.id,
            &self.app_id,
            &self.bottle_id,
            &self.display_name,
            &self.exe_path,
        ] {
            validate_required_text(value)?;
        }
        if self.args.len() > MAX_ARGUMENTS {
            return Err(invalid_manifest());
        }
        for argument in &self.args {
            validate_text(argument)?;
        }
        if let Some(icon_path) = &self.icon_path {
            validate_required_text(icon_path)?;
        }
        validate_environment(&self.env_overrides)
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum LegacyWineArch {
    Win32,
    Win64,
}

fn deserialize_arguments<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: Deserializer<'de>,
{
    struct ArgumentsVisitor;

    impl<'de> Visitor<'de> for ArgumentsVisitor {
        type Value = Vec<String>;

        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            formatter.write_str("an argument sequence")
        }

        fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
        where
            A: SeqAccess<'de>,
        {
            let mut arguments = Vec::new();
            while let Some(argument) = sequence.next_element::<String>()? {
                #[cfg(test)]
                record_argument_deserialized();
                if arguments.len() == MAX_ARGUMENTS {
                    return Err(A::Error::custom("too many launcher arguments"));
                }
                validate_text(&argument).map_err(|_| A::Error::custom("invalid launcher argument"))?;
                arguments.push(argument);
            }
            Ok(arguments)
        }
    }

    deserializer.deserialize_seq(ArgumentsVisitor)
}

fn deserialize_launchers<'de, D>(deserializer: D) -> Result<Vec<LegacyLauncher>, D::Error>
where
    D: Deserializer<'de>,
{
    struct LaunchersVisitor;

    impl<'de> Visitor<'de> for LaunchersVisitor {
        type Value = Vec<LegacyLauncher>;

        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            formatter.write_str("a launcher sequence")
        }

        fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
        where
            A: SeqAccess<'de>,
        {
            let mut launchers = Vec::new();
            while let Some(launcher) = sequence.next_element::<LegacyLauncher>()? {
                #[cfg(test)]
                record_launcher_deserialized();
                if launchers.len() == MAX_LAUNCHERS {
                    return Err(A::Error::custom("too many launchers"));
                }
                launcher
                    .validate_fields()
                    .map_err(|_| A::Error::custom("invalid launcher"))?;
                launchers.push(launcher);
            }
            Ok(launchers)
        }
    }

    deserializer.deserialize_seq(LaunchersVisitor)
}

fn deserialize_environment<'de, D>(deserializer: D) -> Result<BTreeMap<String, String>, D::Error>
where
    D: Deserializer<'de>,
{
    struct EnvironmentVisitor;

    impl<'de> Visitor<'de> for EnvironmentVisitor {
        type Value = BTreeMap<String, String>;

        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            formatter.write_str("a bounded environment map")
        }

        fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
        where
            A: MapAccess<'de>,
        {
            let mut environment = BTreeMap::new();
            while let Some(key) = map.next_key::<String>()? {
                #[cfg(test)]
                record_environment_entry_deserialized();
                if environment.len() == MAX_ENV_OVERRIDES {
                    return Err(A::Error::custom("too many environment entries"));
                }
                validate_required_text(&key).map_err(|_| A::Error::custom("invalid environment key"))?;
                if environment.contains_key(&key) {
                    return Err(A::Error::custom("duplicate environment key"));
                }
                let value = map.next_value::<String>()?;
                validate_text(&value).map_err(|_| A::Error::custom("invalid environment value"))?;
                environment.insert(key, value);
            }
            Ok(environment)
        }
    }

    deserializer.deserialize_map(EnvironmentVisitor)
}

#[cfg(test)]
thread_local! {
    static ARGUMENTS_DESERIALIZED: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    static LAUNCHERS_DESERIALIZED: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    static ENVIRONMENT_ENTRIES_DESERIALIZED: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

#[cfg(test)]
fn record_argument_deserialized() {
    ARGUMENTS_DESERIALIZED.set(ARGUMENTS_DESERIALIZED.get() + 1);
}

#[cfg(test)]
fn record_launcher_deserialized() {
    LAUNCHERS_DESERIALIZED.set(LAUNCHERS_DESERIALIZED.get() + 1);
}

#[cfg(test)]
fn record_environment_entry_deserialized() {
    ENVIRONMENT_ENTRIES_DESERIALIZED.set(ENVIRONMENT_ENTRIES_DESERIALIZED.get() + 1);
}

#[cfg(test)]
fn reset_deserialization_probes() {
    ARGUMENTS_DESERIALIZED.set(0);
    LAUNCHERS_DESERIALIZED.set(0);
    ENVIRONMENT_ENTRIES_DESERIALIZED.set(0);
}

#[cfg(test)]
fn deserialization_probe_counts() -> (usize, usize, usize) {
    (
        ARGUMENTS_DESERIALIZED.get(),
        LAUNCHERS_DESERIALIZED.get(),
        ENVIRONMENT_ENTRIES_DESERIALIZED.get(),
    )
}

fn validate_environment(environment: &BTreeMap<String, String>) -> Result<(), BottleMigrationError> {
    if environment.len() > MAX_ENV_OVERRIDES {
        return Err(invalid_manifest());
    }
    for (key, value) in environment {
        validate_required_text(key)?;
        validate_text(value)?;
    }
    Ok(())
}

fn validate_required_text(value: &str) -> Result<(), BottleMigrationError> {
    if value.trim().is_empty() {
        return Err(invalid_manifest());
    }
    validate_text(value)
}

fn validate_text(value: &str) -> Result<(), BottleMigrationError> {
    if value.len() <= MAX_TEXT_BYTES {
        Ok(())
    } else {
        Err(invalid_manifest())
    }
}

const fn invalid_manifest() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::InvalidManifest)
}

#[cfg(test)]
mod tests {
    use crate::{
        BottleActiveRef, DiagnosticCode, LegacyBottleManifest, LegacyWineArch, MAX_ARGUMENTS, MAX_ENV_OVERRIDES,
        MAX_LAUNCHERS, MAX_TEXT_BYTES, MAX_VERSION_HISTORY,
    };
    use serde_json::{json, Value};

    fn valid_manifest() -> Value {
        json!({
            "id": "bottle-1",
            "name": "Games",
            "windowsVersion": "win10",
            "arch": "win64",
            "engineId": "wine-9",
            "envOverrides": {"WINEDEBUG": "-all"},
            "installedApps": [{
                "id": "launcher-0",
                "appId": "app-1",
                "bottleId": "bottle-1",
                "displayName": "Example",
                "exePath": "drive_c/Example/example.exe",
                "args": ["--safe"],
                "iconPath": "icons/example.png",
                "envOverrides": {"LANG": "en_US.UTF-8"},
                "showInHome": true
            }],
            "createdAt": "2026-08-08T00:00:00Z",
            "updatedAt": "2026-08-08T00:00:01+00:00"
        })
    }

    fn parse(value: &Value) -> Result<LegacyBottleManifest, crate::BottleMigrationError> {
        LegacyBottleManifest::from_json(&serde_json::to_string(value).unwrap())
    }

    fn assert_invalid(value: &Value) {
        let error = parse(value).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::InvalidManifest);
        assert_eq!(error.to_string(), "Bottle manifest is invalid");
    }

    fn manifest_json_with_raw_environment(bottle_environment: &str, launcher_environment: &str) -> String {
        let mut value = valid_manifest();
        value["envOverrides"] = json!("__BOTTLE_ENVIRONMENT__");
        value["installedApps"][0]["envOverrides"] = json!("__LAUNCHER_ENVIRONMENT__");
        serde_json::to_string(&value)
            .unwrap()
            .replace("\"__BOTTLE_ENVIRONMENT__\"", &format!("{{{bottle_environment}}}"))
            .replace("\"__LAUNCHER_ENVIRONMENT__\"", &format!("{{{launcher_environment}}}"))
    }

    fn assert_invalid_json(json: &str) {
        let error = LegacyBottleManifest::from_json(json).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::InvalidManifest);
        assert_eq!(error.to_string(), "Bottle manifest is invalid");
    }

    #[test]
    fn active_ref_contract_is_closed_and_history_bounded() {
        let digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        let active = BottleActiveRef {
            schema_version: "1".into(),
            bottle_id: "bottle-1".into(),
            active_plan_digest: digest.into(),
            history: vec![],
        };
        assert_eq!(
            BottleActiveRef::from_json(&serde_json::to_string(&active).unwrap()).unwrap(),
            active
        );
        assert_eq!(active.canonical_json().unwrap(), br#"{"activePlanDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","bottleId":"bottle-1","history":[],"schemaVersion":"1"}"#);

        let mut unknown = serde_json::to_value(&active).unwrap();
        unknown["unexpected"] = Value::Bool(true);
        assert_eq!(
            BottleActiveRef::from_json(&serde_json::to_string(&unknown).unwrap())
                .unwrap_err()
                .code(),
            DiagnosticCode::InvalidManifest
        );
        let duplicate = r#"{"schemaVersion":"1","schemaVersion":"1","bottleId":"bottle-1","activePlanDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","history":[]}"#;
        assert_eq!(
            BottleActiveRef::from_json(duplicate).unwrap_err().code(),
            DiagnosticCode::InvalidManifest
        );

        let mut history = active.clone();
        history.history = (0..MAX_VERSION_HISTORY)
            .map(|index| format!("sha256:{index:064x}"))
            .collect();
        assert!(BottleActiveRef::from_json(&serde_json::to_string(&history).unwrap()).is_ok());
        history.history.push(digest.into());
        assert_eq!(history.validate().unwrap_err().code(), DiagnosticCode::InvalidManifest);
    }

    fn assert_duplicate_environment_cases(in_launcher: bool) {
        let duplicate_keys = r#""DUP":"first","DUP":"second""#;
        let repeated_keys = (0..=MAX_ENV_OVERRIDES)
            .map(|_| r#""DUP":"value""#)
            .collect::<Vec<_>>()
            .join(",");
        let oversized = "x".repeat(MAX_TEXT_BYTES + 1);
        let oversized_first = format!(r#""DUP":"{oversized}","DUP":"small""#);
        let oversized_last = format!(r#""DUP":"small","DUP":"{oversized}""#);

        for environment in [duplicate_keys, &repeated_keys, &oversized_first, &oversized_last] {
            let json = if in_launcher {
                manifest_json_with_raw_environment("", environment)
            } else {
                manifest_json_with_raw_environment(environment, "")
            };
            assert_invalid_json(&json);
        }
    }

    #[test]
    fn legacy_contract_is_closed_and_bounded() {
        let mut unknown = valid_manifest();
        unknown["unexpected"] = json!(true);
        assert_invalid(&unknown);

        let mut nested_unknown = valid_manifest();
        nested_unknown["installedApps"][0]["unexpected"] = json!(true);
        assert_invalid(&nested_unknown);

        let mut partial = valid_manifest();
        partial.as_object_mut().unwrap().remove("engineId");
        assert_invalid(&partial);

        let mut integer_boolean = valid_manifest();
        integer_boolean["installedApps"][0]["showInHome"] = json!(1);
        assert_invalid(&integer_boolean);

        let mut invalid_arch = valid_manifest();
        invalid_arch["arch"] = json!("x86_64");
        assert_invalid(&invalid_arch);
        for (arch, expected) in [("win32", LegacyWineArch::Win32), ("win64", LegacyWineArch::Win64)] {
            let mut value = valid_manifest();
            value["arch"] = json!(arch);
            assert_eq!(parse(&value).unwrap().arch, expected);
        }
    }

    #[test]
    fn legacy_contract_rejects_duplicate_or_foreign_launchers() {
        let mut duplicate = valid_manifest();
        let launcher = duplicate["installedApps"][0].clone();
        duplicate["installedApps"].as_array_mut().unwrap().push(launcher);
        assert_invalid(&duplicate);

        let mut foreign = valid_manifest();
        foreign["installedApps"][0]["bottleId"] = json!("bottle-2");
        assert_invalid(&foreign);
    }

    #[test]
    fn legacy_contract_rejects_duplicate_bottle_environment_keys() {
        assert_duplicate_environment_cases(false);
    }

    #[test]
    fn legacy_contract_rejects_duplicate_launcher_environment_keys() {
        assert_duplicate_environment_cases(true);
    }

    #[test]
    fn legacy_contract_rejects_empty_oversized_and_invalid_timestamps() {
        for pointer in ["/id", "/name", "/windowsVersion", "/engineId"] {
            let mut value = valid_manifest();
            *value.pointer_mut(pointer).unwrap() = json!("");
            assert_invalid(&value);
        }

        for pointer in [
            "/installedApps/0/id",
            "/installedApps/0/appId",
            "/installedApps/0/bottleId",
            "/installedApps/0/displayName",
            "/installedApps/0/exePath",
        ] {
            let mut value = valid_manifest();
            *value.pointer_mut(pointer).unwrap() = json!("");
            assert_invalid(&value);
        }

        let mut oversized = valid_manifest();
        oversized["name"] = json!("x".repeat(MAX_TEXT_BYTES + 1));
        assert_invalid(&oversized);

        let mut oversized_timestamp = valid_manifest();
        oversized_timestamp["createdAt"] = json!(format!("2026-08-08T00:00:00.{}Z", "0".repeat(MAX_TEXT_BYTES)));
        assert_invalid(&oversized_timestamp);

        for field in ["createdAt", "updatedAt"] {
            let mut invalid_timestamp = valid_manifest();
            invalid_timestamp[field] = json!("2026-02-30T25:61:00Z");
            assert_invalid(&invalid_timestamp);
        }
    }

    #[test]
    fn legacy_contract_rejects_non_digit_timestamp_components_without_panicking() {
        const TIMESTAMP: &str = "2026-08-08T00:00:00+08:30";
        const DIGIT_POSITIONS: [usize; 18] = [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18, 20, 21, 23, 24];

        for replacement in ["/", "é"] {
            for position in DIGIT_POSITIONS {
                let mut timestamp = TIMESTAMP.to_owned();
                timestamp.replace_range(position..position + 1, replacement);
                let mut value = valid_manifest();
                value["createdAt"] = json!(timestamp);
                assert_invalid(&value);
            }
        }
    }

    #[test]
    fn legacy_contract_enforces_exact_collection_bounds() {
        let mut at_launcher_limit = valid_manifest();
        let launchers = at_launcher_limit["installedApps"].as_array_mut().unwrap();
        let template = launchers[0].clone();
        for index in 1..MAX_LAUNCHERS {
            let mut launcher = template.clone();
            launcher["id"] = json!(format!("launcher-{index}"));
            launchers.push(launcher);
        }
        assert!(parse(&at_launcher_limit).is_ok());
        let mut extra_launcher = template.clone();
        extra_launcher["id"] = json!("launcher-over-limit");
        at_launcher_limit["installedApps"]
            .as_array_mut()
            .unwrap()
            .push(extra_launcher);
        assert_invalid(&at_launcher_limit);

        let mut at_argument_limit = valid_manifest();
        at_argument_limit["installedApps"][0]["args"] = json!(vec!["arg"; MAX_ARGUMENTS]);
        assert!(parse(&at_argument_limit).is_ok());
        at_argument_limit["installedApps"][0]["args"]
            .as_array_mut()
            .unwrap()
            .push(json!("extra"));
        assert_invalid(&at_argument_limit);

        let mut at_env_limit = valid_manifest();
        let env = at_env_limit["envOverrides"].as_object_mut().unwrap();
        env.clear();
        for index in 0..MAX_ENV_OVERRIDES {
            env.insert(format!("KEY_{index}"), json!("value"));
        }
        assert!(parse(&at_env_limit).is_ok());
        at_env_limit["envOverrides"]
            .as_object_mut()
            .unwrap()
            .insert("EXTRA".into(), json!("value"));
        assert_invalid(&at_env_limit);

        let mut launcher_env_over_limit = valid_manifest();
        let env = launcher_env_over_limit["installedApps"][0]["envOverrides"]
            .as_object_mut()
            .unwrap();
        env.clear();
        for index in 0..=MAX_ENV_OVERRIDES {
            env.insert(format!("KEY_{index}"), json!("value"));
        }
        assert_invalid(&launcher_env_over_limit);
    }

    #[test]
    fn bounded_argument_deserializer_stops_after_first_excess_item() {
        let mut at_limit = valid_manifest();
        at_limit["installedApps"][0]["args"] = json!(vec!["arg"; MAX_ARGUMENTS]);
        super::reset_deserialization_probes();
        assert!(parse(&at_limit).is_ok());
        assert_eq!(super::deserialization_probe_counts().0, MAX_ARGUMENTS);

        let mut over_limit = valid_manifest();
        over_limit["installedApps"][0]["args"] = json!(vec!["arg"; MAX_ARGUMENTS + 10]);
        super::reset_deserialization_probes();
        assert_invalid(&over_limit);
        assert_eq!(super::deserialization_probe_counts().0, MAX_ARGUMENTS + 1);
    }

    #[test]
    fn bounded_launcher_deserializer_stops_after_first_excess_item() {
        let manifest_with_launchers = |count: usize| {
            let mut value = valid_manifest();
            let template = value["installedApps"][0].clone();
            let launchers = value["installedApps"].as_array_mut().unwrap();
            launchers.clear();
            for index in 0..count {
                let mut launcher = template.clone();
                launcher["id"] = json!(format!("launcher-{index}"));
                launcher["args"] = json!([]);
                launcher["envOverrides"] = json!({});
                launchers.push(launcher);
            }
            value
        };

        let at_limit = manifest_with_launchers(MAX_LAUNCHERS);
        super::reset_deserialization_probes();
        assert!(parse(&at_limit).is_ok());
        assert_eq!(super::deserialization_probe_counts().1, MAX_LAUNCHERS);

        let over_limit = manifest_with_launchers(MAX_LAUNCHERS + 10);
        super::reset_deserialization_probes();
        assert_invalid(&over_limit);
        assert_eq!(super::deserialization_probe_counts().1, MAX_LAUNCHERS + 1);
    }

    #[test]
    fn bounded_environment_deserializer_stops_after_first_excess_entry() {
        let unique_environment = |count: usize| {
            (0..count)
                .map(|index| format!(r#""KEY_{index}":"value""#))
                .collect::<Vec<_>>()
                .join(",")
        };

        let at_limit = manifest_json_with_raw_environment(&unique_environment(MAX_ENV_OVERRIDES), "");
        super::reset_deserialization_probes();
        assert!(LegacyBottleManifest::from_json(&at_limit).is_ok());
        assert_eq!(super::deserialization_probe_counts().2, MAX_ENV_OVERRIDES);

        let over_limit = manifest_json_with_raw_environment(&unique_environment(MAX_ENV_OVERRIDES + 10), "");
        super::reset_deserialization_probes();
        assert_invalid_json(&over_limit);
        assert_eq!(super::deserialization_probe_counts().2, MAX_ENV_OVERRIDES + 1);
    }

    #[test]
    fn diagnostic_codes_are_closed() {
        let diagnostics = [
            (
                DiagnosticCode::UnsupportedPlatform,
                "Bottle snapshot is unsupported on this platform",
            ),
            (DiagnosticCode::SourceChanged, "Bottle source changed during migration"),
            (DiagnosticCode::UnsafeEntry, "Bottle source contains an unsafe entry"),
            (DiagnosticCode::InvalidManifest, "Bottle manifest is invalid"),
            (DiagnosticCode::RuntimeUnmapped, "Bottle runtime is not mapped"),
            (DiagnosticCode::RuntimeMismatch, "Bottle runtime does not match"),
            (DiagnosticCode::SnapshotCorrupt, "Bottle snapshot is corrupt"),
            (DiagnosticCode::TargetCollision, "Bottle target already exists"),
            (DiagnosticCode::TransactionFailed, "Bottle migration transaction failed"),
            (DiagnosticCode::RollbackUnavailable, "Bottle rollback is unavailable"),
            (DiagnosticCode::RollbackCorrupt, "Bottle rollback data is corrupt"),
        ];
        for (code, message) in diagnostics {
            let error = crate::BottleMigrationError::new(code);
            assert_eq!(error.code(), code);
            assert_eq!(error.to_string(), message);
        }
    }
}
