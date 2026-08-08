//! Read-only, platform-neutral host capability probing.

#![deny(unsafe_op_in_unsafe_fn)]

use compatforge_domain::{
    CapabilityObservation, CapabilityReport, CapabilityValue, CoreConfig, CpuArchitecture, HostDescriptor, HostOs,
    ProbeSource, ProbeStatus, ProviderDescriptor, SCHEMA_VERSION_V1,
};
use std::collections::BTreeMap;
use std::fmt;
use std::fs;

pub const PROBE_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProbeError {
    UnsupportedOperatingSystem(String),
    UnsupportedArchitecture(String),
    InvalidReport(String),
}

impl fmt::Display for ProbeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedOperatingSystem(os) => write!(formatter, "unsupported host operating system: {os}"),
            Self::UnsupportedArchitecture(architecture) => {
                write!(formatter, "unsupported host architecture: {architecture}")
            }
            Self::InvalidReport(error) => write!(formatter, "invalid capability report: {error}"),
        }
    }
}

impl std::error::Error for ProbeError {}

pub struct HostProbe;

/// Pure, context-backed capability report construction for stable API clients.
///
/// This query intentionally accepts only an already validated in-memory
/// [`CoreConfig`]. It cannot discover providers, touch the filesystem, access
/// the network, execute a process, or inspect a guest executable.
pub struct ContextCapabilityQuery;

impl ContextCapabilityQuery {
    /// Build the public, privacy-bounded capability projection held by a context.
    pub fn report(config: &CoreConfig) -> Result<CapabilityReport, ProbeError> {
        let source = &config.capabilities;
        let mut report = CapabilityReport {
            schema_version: SCHEMA_VERSION_V1.into(),
            host: HostDescriptor {
                os: source.host.os,
                os_version: "configured".into(),
                architecture: source.host.architecture,
                kernel: None,
                device_model: None,
            },
            runtime_providers: public_providers(&source.runtime_providers, ProviderClass::Runtime)?,
            translators: public_providers(&source.translators, ProviderClass::Translator)?,
            graphics_backends: public_providers(&source.graphics_backends, ProviderClass::Graphics)?,
            observations: public_observations(source),
            features: public_features(&source.features),
        };
        canonicalize_report(&mut report);
        report
            .validate()
            .map_err(|error| ProbeError::InvalidReport(error.to_string()))?;
        Ok(report)
    }
}

impl HostProbe {
    /// Build a read-only snapshot from operating-system data and Rust target facts.
    ///
    /// This baseline probe never searches `PATH` or executes discovered provider
    /// binaries. Runtime, translator, and graphics providers beyond native
    /// execution must be supplied by later verified Runtime Pack probes.
    pub fn probe() -> Result<CapabilityReport, ProbeError> {
        let os = map_os(std::env::consts::OS)?;
        let architecture = map_architecture(std::env::consts::ARCH)?;
        let os_version = os_version(os);
        let kernel = kernel_version(os);
        let device_model = device_model(os);
        let logical_cpu_count = std::thread::available_parallelism().map_or(1, |count| count.get());

        let mut observations = vec![
            detected(
                "host.os",
                "host",
                ProbeSource::RustStandardLibrary,
                CapabilityValue::String(host_os_name(os).into()),
            ),
            detected(
                "host.architecture",
                "host",
                ProbeSource::RustStandardLibrary,
                CapabilityValue::String(architecture_name(architecture).into()),
            ),
            detected(
                "host.logical-cpu-count",
                "host",
                ProbeSource::OperatingSystemApi,
                CapabilityValue::from(u64::try_from(logical_cpu_count).unwrap_or(u64::MAX)),
            ),
            detected(
                "translator.native",
                "translator",
                ProbeSource::BuiltIn,
                CapabilityValue::Boolean(true),
            ),
        ];
        observations.push(fact_observation("host.os-version", "host", &os_version));
        observations.push(optional_fact_observation("host.kernel", "host", &kernel));
        observations.push(optional_fact_observation("host.device-model", "host", &device_model));

        let mut features = BTreeMap::new();
        features.insert("probeVersion".into(), CapabilityValue::String(PROBE_VERSION.into()));
        features.insert(
            "logicalCpuCount".into(),
            CapabilityValue::from(u64::try_from(logical_cpu_count).unwrap_or(u64::MAX)),
        );
        features.insert(
            "pointerWidth".into(),
            CapabilityValue::from((std::mem::size_of::<usize>() * 8) as u64),
        );
        features.insert(
            "endianness".into(),
            CapabilityValue::String(
                if cfg!(target_endian = "little") {
                    "little"
                } else {
                    "big"
                }
                .into(),
            ),
        );

        let report = CapabilityReport {
            schema_version: SCHEMA_VERSION_V1.into(),
            host: HostDescriptor {
                os,
                os_version: os_version.value.clone().unwrap_or_else(|| "unknown".into()),
                architecture,
                kernel: kernel.value.clone(),
                device_model: device_model.value.clone(),
            },
            runtime_providers: Vec::new(),
            translators: vec![ProviderDescriptor {
                id: "native-host".into(),
                kind: "native".into(),
                version: "host".into(),
                available: true,
                reason: None,
                capabilities: native_capabilities(architecture),
            }],
            graphics_backends: Vec::new(),
            observations,
            features,
        };
        report
            .validate()
            .map_err(|error| ProbeError::InvalidReport(error.to_string()))?;
        Ok(report)
    }
}

fn canonicalize_report(report: &mut CapabilityReport) {
    canonicalize_providers(&mut report.runtime_providers);
    canonicalize_providers(&mut report.translators);
    canonicalize_providers(&mut report.graphics_backends);
    report.observations.sort_by(|left, right| left.id.cmp(&right.id));
}

fn canonicalize_providers(providers: &mut [ProviderDescriptor]) {
    for provider in providers.iter_mut() {
        provider.capabilities.sort();
    }
    providers.sort_by(|left, right| left.id.cmp(&right.id));
}

#[derive(Debug, Clone, Copy)]
enum ProviderClass {
    Runtime,
    Translator,
    Graphics,
}

impl ProviderClass {
    fn accepts(self, kind: &str) -> bool {
        match self {
            Self::Runtime => matches!(kind, "wine" | "virtual-machine" | "remote"),
            Self::Translator => matches!(kind, "native" | "rosetta" | "fex" | "box64" | "qemu" | "remote"),
            Self::Graphics => matches!(
                kind,
                "wined3d" | "dxvk" | "vkd3d-proton" | "d3dmetal" | "moltenvk" | "virtualized" | "remote"
            ),
        }
    }
}

fn public_providers(
    providers: &[ProviderDescriptor],
    class: ProviderClass,
) -> Result<Vec<ProviderDescriptor>, ProbeError> {
    providers
        .iter()
        .map(|provider| {
            if !class.accepts(&provider.kind) {
                return Err(ProbeError::InvalidReport(format!(
                    "provider {} has a non-public kind",
                    provider.id
                )));
            }
            Ok(ProviderDescriptor {
                id: provider.id.clone(),
                kind: provider.kind.clone(),
                // Configuration text is not a trusted public evidence source.
                // Runtime-pack probes can publish a verified version separately.
                version: "configured".into(),
                available: provider.available,
                reason: (!provider.available).then(|| "configured provider is unavailable".into()),
                capabilities: provider
                    .capabilities
                    .iter()
                    .filter(|capability| is_public_capability(capability))
                    .cloned()
                    .collect(),
            })
        })
        .collect()
}

fn is_public_capability(capability: &str) -> bool {
    matches!(
        capability,
        "win32"
            | "win64"
            | "new-wow64"
            | "remoteapp"
            | "guest-i386"
            | "guest-x86_64"
            | "guest-arm64"
            | "i386-on-i386"
            | "i386-on-x86_64"
            | "x86_64-on-x86_64"
            | "arm64-on-arm64"
            | "i386-on-arm64"
            | "x86_64-on-arm64"
            | "d3d8"
            | "d3d9"
            | "d3d10"
            | "d3d11"
            | "d3d12"
            | "opengl"
            | "vulkan"
            | "metal"
    )
}

fn public_features(features: &BTreeMap<String, CapabilityValue>) -> BTreeMap<String, CapabilityValue> {
    features
        .iter()
        .filter_map(|(name, value)| {
            let public_value = match (name.as_str(), value) {
                ("vulkan" | "ntsync", CapabilityValue::Boolean(value)) => CapabilityValue::Boolean(*value),
                ("logicalCpuCount", CapabilityValue::Number(value))
                    if value.as_u64().is_some_and(|value| (1..=1_048_576).contains(&value)) =>
                {
                    CapabilityValue::Number(value.clone())
                }
                ("pointerWidth", CapabilityValue::Number(value)) if matches!(value.as_u64(), Some(32 | 64)) => {
                    CapabilityValue::Number(value.clone())
                }
                ("endianness", CapabilityValue::String(value)) if matches!(value.as_str(), "little" | "big") => {
                    CapabilityValue::String(value.clone())
                }
                ("probeVersion", _) => CapabilityValue::String(PROBE_VERSION.into()),
                _ => return None,
            };
            Some((name.clone(), public_value))
        })
        .collect()
}

fn public_observations(source: &CapabilityReport) -> Vec<CapabilityObservation> {
    vec![
        detected(
            "host.os",
            "host",
            ProbeSource::Configuration,
            CapabilityValue::String(host_os_name(source.host.os).into()),
        ),
        detected(
            "host.architecture",
            "host",
            ProbeSource::Configuration,
            CapabilityValue::String(architecture_name(source.host.architecture).into()),
        ),
    ]
}

#[derive(Debug, Clone)]
struct ProbeFact {
    value: Option<String>,
    source: ProbeSource,
    reason: &'static str,
}

impl ProbeFact {
    fn detected(value: String, source: ProbeSource) -> Self {
        Self {
            value: Some(value),
            source,
            reason: "",
        }
    }

    const fn unknown(source: ProbeSource, reason: &'static str) -> Self {
        Self {
            value: None,
            source,
            reason,
        }
    }
}

fn detected(id: &str, category: &str, source: ProbeSource, value: CapabilityValue) -> CapabilityObservation {
    CapabilityObservation {
        id: id.into(),
        category: category.into(),
        status: ProbeStatus::Detected,
        source,
        value: Some(value),
        reason: None,
    }
}

fn fact_observation(id: &str, category: &str, fact: &ProbeFact) -> CapabilityObservation {
    match &fact.value {
        Some(value) => detected(id, category, fact.source, CapabilityValue::String(value.clone())),
        None => CapabilityObservation {
            id: id.into(),
            category: category.into(),
            status: ProbeStatus::Unknown,
            source: fact.source,
            value: None,
            reason: Some(fact.reason.into()),
        },
    }
}

fn optional_fact_observation(id: &str, category: &str, fact: &ProbeFact) -> CapabilityObservation {
    fact_observation(id, category, fact)
}

fn map_os(os: &str) -> Result<HostOs, ProbeError> {
    match os {
        "macos" => Ok(HostOs::MacOs),
        "linux" => Ok(HostOs::Linux),
        "android" => Ok(HostOs::Android),
        "windows" => Ok(HostOs::Windows),
        other => Err(ProbeError::UnsupportedOperatingSystem(other.into())),
    }
}

fn map_architecture(architecture: &str) -> Result<CpuArchitecture, ProbeError> {
    match architecture {
        "x86" => Ok(CpuArchitecture::I386),
        "x86_64" => Ok(CpuArchitecture::X86_64),
        "aarch64" => Ok(CpuArchitecture::Arm64),
        other => Err(ProbeError::UnsupportedArchitecture(other.into())),
    }
}

const fn host_os_name(os: HostOs) -> &'static str {
    match os {
        HostOs::MacOs => "macos",
        HostOs::Linux => "linux",
        HostOs::Android => "android",
        HostOs::Windows => "windows",
    }
}

const fn architecture_name(architecture: CpuArchitecture) -> &'static str {
    match architecture {
        CpuArchitecture::I386 => "i386",
        CpuArchitecture::X86_64 => "x86_64",
        CpuArchitecture::Arm64 => "arm64",
        CpuArchitecture::Unknown => "unknown",
    }
}

fn native_capabilities(architecture: CpuArchitecture) -> Vec<String> {
    match architecture {
        CpuArchitecture::I386 => vec!["i386-on-i386".into()],
        CpuArchitecture::X86_64 => vec!["i386-on-x86_64".into(), "x86_64-on-x86_64".into()],
        CpuArchitecture::Arm64 => vec!["arm64-on-arm64".into()],
        CpuArchitecture::Unknown => Vec::new(),
    }
}

fn os_version(os: HostOs) -> ProbeFact {
    match os {
        HostOs::Linux => read_os_release("/etc/os-release").map_or_else(
            || {
                ProbeFact::unknown(
                    ProbeSource::OperatingSystemFile,
                    "/etc/os-release did not expose a version",
                )
            },
            |version| ProbeFact::detected(version, ProbeSource::OperatingSystemFile),
        ),
        HostOs::Android => read_build_property("/system/build.prop", "ro.build.version.release").map_or_else(
            || {
                ProbeFact::unknown(
                    ProbeSource::OperatingSystemFile,
                    "Android build properties were unavailable",
                )
            },
            |version| ProbeFact::detected(version, ProbeSource::OperatingSystemFile),
        ),
        HostOs::MacOs => macos_sysctl("kern.osproductversion")
            .or_else(|| read_plist_value("/System/Library/CoreServices/SystemVersion.plist", "ProductVersion"))
            .map_or_else(
                || ProbeFact::unknown(ProbeSource::OperatingSystemApi, "macOS product version was unavailable"),
                |version| ProbeFact::detected(version, ProbeSource::OperatingSystemApi),
            ),
        HostOs::Windows => windows_version().map_or_else(
            || ProbeFact::unknown(ProbeSource::OperatingSystemApi, "Windows version API was unavailable"),
            |version| ProbeFact::detected(version, ProbeSource::OperatingSystemApi),
        ),
    }
}

fn kernel_version(os: HostOs) -> ProbeFact {
    let value = match os {
        HostOs::Linux | HostOs::Android => read_trimmed("/proc/sys/kernel/osrelease"),
        HostOs::MacOs => macos_sysctl("kern.osrelease"),
        HostOs::Windows => windows_version(),
    };
    value.map_or_else(
        || ProbeFact::unknown(ProbeSource::OperatingSystemApi, "kernel version was unavailable"),
        |version| ProbeFact::detected(version, ProbeSource::OperatingSystemApi),
    )
}

fn device_model(os: HostOs) -> ProbeFact {
    let value = match os {
        HostOs::Linux => {
            read_trimmed("/sys/devices/virtual/dmi/id/product_name").or_else(|| read_trimmed("/proc/device-tree/model"))
        }
        HostOs::Android => read_build_property("/system/build.prop", "ro.product.model"),
        HostOs::MacOs => macos_sysctl("hw.model"),
        HostOs::Windows => None,
    };
    value.map_or_else(
        || ProbeFact::unknown(ProbeSource::OperatingSystemApi, "device model was unavailable"),
        |model| ProbeFact::detected(model, ProbeSource::OperatingSystemApi),
    )
}

fn read_trimmed(path: &str) -> Option<String> {
    fs::read_to_string(path)
        .ok()
        .map(|value| {
            value
                .trim_matches(|character: char| matches!(character, '\0' | '\n' | '\r' | ' '))
                .to_owned()
        })
        .filter(|value| !value.is_empty())
}

fn read_os_release(path: &str) -> Option<String> {
    let content = fs::read_to_string(path).ok()?;
    parse_key_value(&content, "PRETTY_NAME").or_else(|| {
        let id = parse_key_value(&content, "ID")?;
        let version = parse_key_value(&content, "VERSION_ID")?;
        Some(format!("{id} {version}"))
    })
}

fn read_build_property(path: &str, key: &str) -> Option<String> {
    parse_key_value(&fs::read_to_string(path).ok()?, key)
}

fn parse_key_value(content: &str, key: &str) -> Option<String> {
    content.lines().find_map(|line| {
        let (candidate, value) = line.split_once('=')?;
        if candidate.trim() != key {
            return None;
        }
        let value = value.trim();
        let value = value
            .strip_prefix('"')
            .and_then(|value| value.strip_suffix('"'))
            .unwrap_or(value);
        (!value.is_empty()).then(|| value.replace("\\\"", "\"").replace("\\\\", "\\"))
    })
}

fn read_plist_value(path: &str, key: &str) -> Option<String> {
    parse_plist_value(&fs::read_to_string(path).ok()?, key)
}

fn parse_plist_value(content: &str, key: &str) -> Option<String> {
    let key_marker = format!("<key>{key}</key>");
    let after_key = content.split_once(&key_marker)?.1;
    let after_string = after_key.split_once("<string>")?.1;
    let value = after_string.split_once("</string>")?.0.trim();
    (!value.is_empty()).then(|| value.to_owned())
}

#[cfg(target_os = "macos")]
fn macos_sysctl(name: &str) -> Option<String> {
    use std::ffi::{c_char, c_void, CString};
    use std::ptr;

    extern "C" {
        fn sysctlbyname(
            name: *const c_char,
            old_value: *mut c_void,
            old_length: *mut usize,
            new_value: *mut c_void,
            new_length: usize,
        ) -> i32;
    }

    let name = CString::new(name).ok()?;
    let mut length = 0_usize;
    if unsafe { sysctlbyname(name.as_ptr(), ptr::null_mut(), &mut length, ptr::null_mut(), 0) } != 0 || length == 0 {
        return None;
    }
    let mut buffer = vec![0_u8; length];
    if unsafe {
        sysctlbyname(
            name.as_ptr(),
            buffer.as_mut_ptr().cast(),
            &mut length,
            ptr::null_mut(),
            0,
        )
    } != 0
    {
        return None;
    }
    buffer.truncate(length);
    while buffer.last() == Some(&0) {
        buffer.pop();
    }
    String::from_utf8(buffer).ok().filter(|value| !value.is_empty())
}

#[cfg(not(target_os = "macos"))]
const fn macos_sysctl(_name: &str) -> Option<String> {
    None
}

#[cfg(windows)]
fn windows_version() -> Option<String> {
    #[repr(C)]
    struct OsVersionInfo {
        size: u32,
        major: u32,
        minor: u32,
        build: u32,
        platform: u32,
        service_pack: [u16; 128],
    }

    #[link(name = "ntdll")]
    extern "system" {
        fn RtlGetVersion(version: *mut OsVersionInfo) -> i32;
    }

    let mut version = OsVersionInfo {
        size: u32::try_from(std::mem::size_of::<OsVersionInfo>()).ok()?,
        major: 0,
        minor: 0,
        build: 0,
        platform: 0,
        service_pack: [0; 128],
    };
    (unsafe { RtlGetVersion(&mut version) } == 0)
        .then(|| format!("{}.{}.{}", version.major, version.minor, version.build))
}

#[cfg(not(windows))]
const fn windows_version() -> Option<String> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn context_config(architecture: CpuArchitecture) -> CoreConfig {
        let mut config: CoreConfig =
            serde_json::from_str(include_str!("../../../examples/context-config.linux-arm64.json")).unwrap();
        config.capabilities.host.architecture = architecture;
        config
    }

    #[test]
    fn probe_matches_the_compilation_target() {
        let report = HostProbe::probe().unwrap();
        report.validate().unwrap();
        assert_eq!(report.host.os, map_os(std::env::consts::OS).unwrap());
        assert_eq!(
            report.host.architecture,
            map_architecture(std::env::consts::ARCH).unwrap()
        );
        assert!(report.runtime_providers.is_empty());
        assert!(report.graphics_backends.is_empty());
        assert_eq!(report.translators.len(), 1);
        assert_eq!(report.translators[0].kind, "native");
        assert!(report
            .observations
            .iter()
            .any(|observation| observation.id == "host.architecture" && observation.status == ProbeStatus::Detected));
    }

    #[test]
    fn parses_linux_and_macos_version_sources() {
        assert_eq!(
            parse_key_value("NAME=Example\nPRETTY_NAME=\"Example Linux 1\"\n", "PRETTY_NAME"),
            Some("Example Linux 1".into())
        );
        assert_eq!(
            parse_plist_value(
                "<plist><dict><key>ProductVersion</key><string>27.0</string></dict></plist>",
                "ProductVersion"
            ),
            Some("27.0".into())
        );
    }

    #[test]
    fn native_capabilities_are_architecture_specific() {
        assert_eq!(native_capabilities(CpuArchitecture::I386), vec!["i386-on-i386"]);
        assert_eq!(
            native_capabilities(CpuArchitecture::X86_64),
            vec!["i386-on-x86_64", "x86_64-on-x86_64"]
        );
        assert_eq!(native_capabilities(CpuArchitecture::Arm64), vec!["arm64-on-arm64"]);
    }

    #[test]
    fn context_query_maps_linux_x86_64_and_arm64_hosts() {
        for architecture in [CpuArchitecture::X86_64, CpuArchitecture::Arm64] {
            let report = ContextCapabilityQuery::report(&context_config(architecture)).unwrap();
            assert_eq!(report.host.os, HostOs::Linux);
            assert_eq!(report.host.architecture, architecture);
            assert_eq!(report.schema_version, SCHEMA_VERSION_V1);
        }
    }

    #[test]
    fn context_query_preserves_empty_and_unavailable_providers() {
        let mut config = context_config(CpuArchitecture::Arm64);
        config.capabilities.runtime_providers.clear();
        config.capabilities.translators.clear();
        config.capabilities.graphics_backends.clear();

        let empty = ContextCapabilityQuery::report(&config).unwrap();
        assert!(empty.runtime_providers.is_empty());
        assert!(empty.translators.is_empty());
        assert!(empty.graphics_backends.is_empty());

        config.capabilities.runtime_providers.push(ProviderDescriptor {
            id: "wine-unavailable".into(),
            kind: "wine".into(),
            version: "pack-pinned".into(),
            available: false,
            reason: Some("runtime pack is not installed".into()),
            capabilities: vec!["win64".into(), "win32".into()],
        });
        let unavailable = ContextCapabilityQuery::report(&config).unwrap();
        assert!(!unavailable.runtime_providers[0].available);
        assert_eq!(
            unavailable.runtime_providers[0].reason.as_deref(),
            Some("configured provider is unavailable")
        );
    }

    #[test]
    fn context_query_canonicalizes_all_ordered_collections() {
        let mut config = context_config(CpuArchitecture::Arm64);
        config.capabilities.runtime_providers.push(ProviderDescriptor {
            id: "zzz-runtime".into(),
            kind: "virtual-machine".into(),
            version: "test".into(),
            available: true,
            reason: None,
            capabilities: vec!["guest-x86_64".into(), "guest-i386".into()],
        });
        config.capabilities.runtime_providers.reverse();
        config.capabilities.translators.reverse();
        config.capabilities.graphics_backends.reverse();
        config.capabilities.observations.reverse();
        for provider in config
            .capabilities
            .runtime_providers
            .iter_mut()
            .chain(config.capabilities.translators.iter_mut())
            .chain(config.capabilities.graphics_backends.iter_mut())
        {
            provider.capabilities.reverse();
        }

        let report = ContextCapabilityQuery::report(&config).unwrap();
        let second = ContextCapabilityQuery::report(&config).unwrap();
        assert_eq!(
            serde_json::to_string(&report).unwrap(),
            serde_json::to_string(&second).unwrap()
        );
        assert!(report
            .runtime_providers
            .windows(2)
            .all(|providers| providers[0].id < providers[1].id));
        assert!(report
            .observations
            .windows(2)
            .all(|observations| observations[0].id < observations[1].id));
        assert!(report.runtime_providers.iter().all(|provider| provider
            .capabilities
            .windows(2)
            .all(|capabilities| capabilities[0] < capabilities[1])));
    }

    #[test]
    fn context_query_uses_an_explicit_public_field_allowlist() {
        let mut config = context_config(CpuArchitecture::Arm64);
        config.capabilities.host.os_version = "/home/alice/private".into();
        config.capabilities.host.kernel = Some("token=host-secret".into());
        config.capabilities.host.device_model = Some("alice-workstation".into());
        config
            .capabilities
            .features
            .insert("authToken".into(), CapabilityValue::String("secret".into()));
        config
            .capabilities
            .features
            .insert("userPath".into(), CapabilityValue::String("/home/alice/private".into()));
        config.capabilities.observations.push(CapabilityObservation {
            id: "process.command-line".into(),
            category: "process".into(),
            status: ProbeStatus::Detected,
            source: ProbeSource::Configuration,
            value: Some(CapabilityValue::String("--token secret /home/alice/private".into())),
            reason: None,
        });
        config.capabilities.runtime_providers[0].version = "secret".into();
        config.capabilities.runtime_providers[0]
            .capabilities
            .push("private-token".into());

        config.validate().unwrap();
        let report = ContextCapabilityQuery::report(&config).unwrap();
        let json = serde_json::to_string(&report).unwrap();

        assert_eq!(report.host.os_version, "configured");
        assert!(report.host.kernel.is_none());
        assert!(report.host.device_model.is_none());
        assert!(!report.features.contains_key("authToken"));
        assert!(!report.features.contains_key("userPath"));
        assert!(report
            .observations
            .iter()
            .all(|observation| matches!(observation.id.as_str(), "host.os" | "host.architecture")));
        assert_eq!(report.runtime_providers[0].version, "configured");
        assert!(!report.runtime_providers[0]
            .capabilities
            .iter()
            .any(|capability| capability == "private-token"));
        assert!(!json.contains("secret"));
        assert!(!json.contains("/home/alice/private"));
        assert!(!json.contains("process.command-line"));
    }
}
