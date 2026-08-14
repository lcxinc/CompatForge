use crate::{BottleMigrationError, DiagnosticCode};
use compatforge_domain::validate_rfc3339;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const MAX_MANIFEST_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_TEXT_BYTES: usize = 4096;
pub const MAX_LAUNCHERS: usize = 1024;
pub const MAX_ARGUMENTS: usize = 256;
pub const MAX_ENV_OVERRIDES: usize = 256;

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LegacyBottleManifest {
    pub id: String,
    pub name: String,
    pub windows_version: String,
    pub arch: LegacyWineArch,
    pub engine_id: String,
    pub env_overrides: BTreeMap<String, String>,
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
    pub args: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub icon_path: Option<String>,
    pub env_overrides: BTreeMap<String, String>,
    pub show_in_home: bool,
}

impl LegacyLauncher {
    fn validate(&self, bottle_id: &str) -> Result<(), BottleMigrationError> {
        for value in [
            &self.id,
            &self.app_id,
            &self.bottle_id,
            &self.display_name,
            &self.exe_path,
        ] {
            validate_required_text(value)?;
        }
        if self.bottle_id != bottle_id || self.args.len() > MAX_ARGUMENTS {
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
        DiagnosticCode, LegacyBottleManifest, LegacyWineArch, MAX_ARGUMENTS, MAX_ENV_OVERRIDES, MAX_LAUNCHERS,
        MAX_TEXT_BYTES,
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
    fn diagnostic_codes_are_closed() {
        let diagnostics = [
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
