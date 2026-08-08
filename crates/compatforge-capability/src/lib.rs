//! Read-only, platform-neutral host capability probing.

#![deny(unsafe_op_in_unsafe_fn)]

use compatforge_domain::{
    CapabilityObservation, CapabilityReport, CpuArchitecture, HostDescriptor, HostOs, ProbeSource, ProbeStatus,
    ProviderDescriptor, SCHEMA_VERSION_V1,
};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fmt;
use std::fs;

pub const PROBE_VERSION: &str = "0.5.0";

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
        let logical_cpu_count = std::thread::available_parallelism().map_or(1, std::num::NonZero::get);

        let mut observations = vec![
            detected(
                "host.os",
                "host",
                ProbeSource::RustStandardLibrary,
                Value::String(host_os_name(os).into()),
            ),
            detected(
                "host.architecture",
                "host",
                ProbeSource::RustStandardLibrary,
                Value::String(architecture_name(architecture).into()),
            ),
            detected(
                "host.logical-cpu-count",
                "host",
                ProbeSource::OperatingSystemApi,
                Value::from(u64::try_from(logical_cpu_count).unwrap_or(u64::MAX)),
            ),
            detected(
                "translator.native",
                "translator",
                ProbeSource::BuiltIn,
                Value::Bool(true),
            ),
        ];
        observations.push(fact_observation("host.os-version", "host", &os_version));
        observations.push(optional_fact_observation("host.kernel", "host", &kernel));
        observations.push(optional_fact_observation("host.device-model", "host", &device_model));

        let mut features = BTreeMap::new();
        features.insert("probeVersion".into(), Value::String(PROBE_VERSION.into()));
        features.insert(
            "logicalCpuCount".into(),
            Value::from(u64::try_from(logical_cpu_count).unwrap_or(u64::MAX)),
        );
        features.insert(
            "pointerWidth".into(),
            Value::from((std::mem::size_of::<usize>() * 8) as u64),
        );
        features.insert(
            "endianness".into(),
            Value::String(
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

fn detected(id: &str, category: &str, source: ProbeSource, value: Value) -> CapabilityObservation {
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
        Some(value) => detected(id, category, fact.source, Value::String(value.clone())),
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
}
