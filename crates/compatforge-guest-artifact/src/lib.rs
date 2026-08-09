//! Immutable, content-addressed storage for inspected Windows guest programs.

#![forbid(unsafe_code)]

use compatforge_domain::{ContractError, CpuArchitecture, GuestArtifactBinding, SCHEMA_VERSION_V1};
use compatforge_inspect::{
    inspect_bytes, InspectionError, PeArchitecture, PeImageKind, PeInspectionReport, PeSubsystem, MAX_PE_FILE_BYTES,
};
use sha2::{Digest, Sha256};
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreparedGuestArtifact {
    pub binding: GuestArtifactBinding,
    pub inspection: PeInspectionReport,
}

#[derive(Debug, Clone)]
pub struct GuestArtifactStore {
    root: PathBuf,
}

impl GuestArtifactStore {
    #[must_use]
    pub fn new(storage_root: impl AsRef<Path>) -> Self {
        Self {
            root: storage_root.as_ref().join("guest-artifacts"),
        }
    }

    /// Read an absolute regular file once, inspect those exact bytes, and
    /// publish the bytes under their SHA-256 digest.
    pub fn prepare(&self, source: &Path) -> Result<PreparedGuestArtifact, GuestArtifactError> {
        if !self.root.is_absolute() {
            return Err(GuestArtifactError::RelativeStorageRoot(self.root.clone()));
        }
        let (bytes, original_name) = read_source(source)?;
        let inspection = inspect_bytes(&bytes).map_err(GuestArtifactError::Inspection)?;
        validate_supported_inspection(&inspection)?;
        let architecture = map_architecture(inspection.architecture)?;
        let target = self.object_path(&inspection.file_digest)?;
        publish_object(&target, &bytes, &inspection.file_digest)?;

        let binding = GuestArtifactBinding {
            digest: inspection.file_digest.clone(),
            size_bytes: inspection.file_size_bytes,
            stored_path: target.to_string_lossy().into_owned(),
            original_name,
            architecture,
            image_kind: "executable".into(),
            subsystem: "windowsConsole".into(),
            inspection_schema_version: SCHEMA_VERSION_V1.into(),
        };
        self.verify(&binding)?;
        Ok(PreparedGuestArtifact { binding, inspection })
    }

    pub fn verify(&self, binding: &GuestArtifactBinding) -> Result<(), GuestArtifactError> {
        binding.validate().map_err(GuestArtifactError::InvalidBinding)?;
        let expected = self.object_path(&binding.digest)?;
        if Path::new(&binding.stored_path) != expected {
            return Err(GuestArtifactError::UnexpectedObjectPath {
                expected,
                actual: PathBuf::from(&binding.stored_path),
            });
        }
        verify_binding_contents(binding)
    }

    fn object_path(&self, digest: &str) -> Result<PathBuf, GuestArtifactError> {
        let hex = digest
            .strip_prefix("sha256:")
            .ok_or_else(|| GuestArtifactError::InvalidDigest(digest.into()))?;
        if hex.len() != 64 || !hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(GuestArtifactError::InvalidDigest(digest.into()));
        }
        Ok(self.root.join("objects").join("sha256").join(hex.to_ascii_lowercase()))
    }
}

/// Re-hash a serialized binding immediately before a process is created.
pub fn verify_binding_contents(binding: &GuestArtifactBinding) -> Result<(), GuestArtifactError> {
    binding.validate().map_err(GuestArtifactError::InvalidBinding)?;
    let path = Path::new(&binding.stored_path);
    if !path.is_absolute() {
        return Err(GuestArtifactError::RelativeObjectPath(path.to_owned()));
    }
    let metadata = fs::symlink_metadata(path).map_err(|source| GuestArtifactError::Filesystem {
        path: path.to_owned(),
        source,
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(GuestArtifactError::NotRegularFile(path.to_owned()));
    }
    if metadata.len() != binding.size_bytes {
        return Err(GuestArtifactError::SizeMismatch {
            expected: binding.size_bytes,
            actual: metadata.len(),
        });
    }
    let actual = digest_file(path)?;
    if !actual.eq_ignore_ascii_case(&binding.digest) {
        return Err(GuestArtifactError::DigestMismatch {
            expected: binding.digest.clone(),
            actual,
        });
    }
    Ok(())
}

fn read_source(source: &Path) -> Result<(Vec<u8>, String), GuestArtifactError> {
    if !source.is_absolute() {
        return Err(GuestArtifactError::RelativeSource(source.to_owned()));
    }
    if source
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(GuestArtifactError::AmbiguousSource(source.to_owned()));
    }
    let metadata = fs::symlink_metadata(source).map_err(|error| GuestArtifactError::Filesystem {
        path: source.to_owned(),
        source: error,
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(GuestArtifactError::NotRegularFile(source.to_owned()));
    }
    if metadata.len() > MAX_PE_FILE_BYTES {
        return Err(GuestArtifactError::FileTooLarge(metadata.len()));
    }
    let original_name = source
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty() && !matches!(*name, "." | ".."))
        .ok_or_else(|| GuestArtifactError::InvalidFileName(source.to_owned()))?
        .to_owned();
    let mut file = File::open(source).map_err(|error| GuestArtifactError::Filesystem {
        path: source.to_owned(),
        source: error,
    })?;
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(0));
    Read::by_ref(&mut file)
        .take(MAX_PE_FILE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| GuestArtifactError::Filesystem {
            path: source.to_owned(),
            source: error,
        })?;
    if bytes.len() as u64 > MAX_PE_FILE_BYTES {
        return Err(GuestArtifactError::FileTooLarge(bytes.len() as u64));
    }
    Ok((bytes, original_name))
}

fn validate_supported_inspection(report: &PeInspectionReport) -> Result<(), GuestArtifactError> {
    if report.image_kind != PeImageKind::Executable {
        return Err(GuestArtifactError::UnsupportedImageKind(report.image_kind));
    }
    if report.subsystem != PeSubsystem::WindowsConsole {
        return Err(GuestArtifactError::UnsupportedSubsystem(report.subsystem));
    }
    map_architecture(report.architecture).map(|_| ())
}

fn map_architecture(architecture: PeArchitecture) -> Result<CpuArchitecture, GuestArtifactError> {
    match architecture {
        PeArchitecture::X86 => Ok(CpuArchitecture::I386),
        PeArchitecture::X86_64 => Ok(CpuArchitecture::X86_64),
        PeArchitecture::Arm | PeArchitecture::Arm64 => Err(GuestArtifactError::UnsupportedArchitecture(architecture)),
    }
}

fn publish_object(target: &Path, bytes: &[u8], digest: &str) -> Result<(), GuestArtifactError> {
    if target.exists() {
        return verify_existing(target, bytes.len() as u64, digest);
    }
    let parent = target.parent().expect("content object always has a parent");
    fs::create_dir_all(parent).map_err(|source| GuestArtifactError::Filesystem {
        path: parent.to_owned(),
        source,
    })?;
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(".guest-artifact-{}-{sequence}.tmp", std::process::id()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|source| GuestArtifactError::Filesystem {
            path: temp.clone(),
            source,
        })?;
    if let Err(source) = file.write_all(bytes).and_then(|()| file.sync_all()) {
        drop(file);
        let _ = fs::remove_file(&temp);
        return Err(GuestArtifactError::Filesystem { path: temp, source });
    }
    drop(file);
    match fs::rename(&temp, target) {
        Ok(()) => {
            let mut permissions = fs::metadata(target)
                .map_err(|source| GuestArtifactError::Filesystem {
                    path: target.to_owned(),
                    source,
                })?
                .permissions();
            permissions.set_readonly(true);
            fs::set_permissions(target, permissions).map_err(|source| GuestArtifactError::Filesystem {
                path: target.to_owned(),
                source,
            })?;
            verify_existing(target, bytes.len() as u64, digest)
        }
        Err(_source) if target.exists() => {
            let _ = fs::remove_file(&temp);
            verify_existing(target, bytes.len() as u64, digest)
        }
        Err(source) => {
            let _ = fs::remove_file(&temp);
            Err(GuestArtifactError::Filesystem {
                path: target.to_owned(),
                source,
            })
        }
    }
}

fn verify_existing(path: &Path, size: u64, digest: &str) -> Result<(), GuestArtifactError> {
    let metadata = fs::symlink_metadata(path).map_err(|source| GuestArtifactError::Filesystem {
        path: path.to_owned(),
        source,
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(GuestArtifactError::NotRegularFile(path.to_owned()));
    }
    if metadata.len() != size {
        return Err(GuestArtifactError::ObjectCollision(digest.into()));
    }
    if !digest_file(path)?.eq_ignore_ascii_case(digest) {
        return Err(GuestArtifactError::ObjectCollision(digest.into()));
    }
    Ok(())
}

fn digest_file(path: &Path) -> Result<String, GuestArtifactError> {
    let mut file = File::open(path).map_err(|source| GuestArtifactError::Filesystem {
        path: path.to_owned(),
        source,
    })?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|source| GuestArtifactError::Filesystem {
                path: path.to_owned(),
                source,
            })?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    let mut value = String::with_capacity(71);
    value.push_str("sha256:");
    for byte in hasher.finalize() {
        use std::fmt::Write as _;
        write!(value, "{byte:02x}").expect("writing to String cannot fail");
    }
    Ok(value)
}

#[derive(Debug)]
pub enum GuestArtifactError {
    RelativeStorageRoot(PathBuf),
    RelativeSource(PathBuf),
    AmbiguousSource(PathBuf),
    RelativeObjectPath(PathBuf),
    InvalidFileName(PathBuf),
    NotRegularFile(PathBuf),
    FileTooLarge(u64),
    InvalidDigest(String),
    InvalidBinding(ContractError),
    Inspection(InspectionError),
    UnsupportedArchitecture(PeArchitecture),
    UnsupportedImageKind(PeImageKind),
    UnsupportedSubsystem(PeSubsystem),
    UnexpectedObjectPath { expected: PathBuf, actual: PathBuf },
    SizeMismatch { expected: u64, actual: u64 },
    DigestMismatch { expected: String, actual: String },
    ObjectCollision(String),
    Filesystem { path: PathBuf, source: io::Error },
}

impl fmt::Display for GuestArtifactError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RelativeStorageRoot(path) => write!(
                formatter,
                "guest artifact storage root must be absolute: {}",
                path.display()
            ),
            Self::RelativeSource(path) => write!(formatter, "guest source path must be absolute: {}", path.display()),
            Self::AmbiguousSource(path) => write!(
                formatter,
                "guest source path contains parent traversal: {}",
                path.display()
            ),
            Self::RelativeObjectPath(path) => {
                write!(formatter, "guest object path must be absolute: {}", path.display())
            }
            Self::InvalidFileName(path) => write!(
                formatter,
                "guest source has no valid UTF-8 file name: {}",
                path.display()
            ),
            Self::NotRegularFile(path) => write!(
                formatter,
                "guest artifact is not a regular non-symlink file: {}",
                path.display()
            ),
            Self::FileTooLarge(size) => write!(formatter, "guest artifact exceeds the inspection limit: {size} bytes"),
            Self::InvalidDigest(digest) => write!(formatter, "invalid guest artifact digest: {digest}"),
            Self::InvalidBinding(error) => write!(formatter, "invalid guest artifact binding: {error}"),
            Self::Inspection(error) => write!(formatter, "guest artifact inspection failed: {error}"),
            Self::UnsupportedArchitecture(value) => write!(formatter, "unsupported guest architecture: {value:?}"),
            Self::UnsupportedImageKind(value) => write!(formatter, "unsupported guest image kind: {value:?}"),
            Self::UnsupportedSubsystem(value) => write!(formatter, "unsupported guest subsystem: {value:?}"),
            Self::UnexpectedObjectPath { expected, actual } => write!(
                formatter,
                "guest object path mismatch: expected {}, got {}",
                expected.display(),
                actual.display()
            ),
            Self::SizeMismatch { expected, actual } => write!(
                formatter,
                "guest artifact size mismatch: expected {expected}, got {actual}"
            ),
            Self::DigestMismatch { expected, actual } => write!(
                formatter,
                "guest artifact digest mismatch: expected {expected}, got {actual}"
            ),
            Self::ObjectCollision(digest) => write!(formatter, "guest artifact object collision at {digest}"),
            Self::Filesystem { path, source } => write!(
                formatter,
                "guest artifact filesystem error at {}: {source}",
                path.display()
            ),
        }
    }
}

impl std::error::Error for GuestArtifactError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::InvalidBinding(error) => Some(error),
            Self::Inspection(error) => Some(error),
            Self::Filesystem { source, .. } => Some(source),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root(label: &str) -> PathBuf {
        let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let root = std::env::temp_dir().join(format!("compatforge-{label}-{}-{nonce}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        root
    }

    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/hello-x86_64.exe")
            .canonicalize()
            .unwrap()
    }

    fn make_writable(path: &Path) {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(path).unwrap().permissions();
            permissions.set_mode(0o600);
            fs::set_permissions(path, permissions).unwrap();
        }
        #[cfg(windows)]
        {
            let status = std::process::Command::new("attrib")
                .arg("-R")
                .arg(path)
                .status()
                .unwrap();
            assert!(status.success());
        }
    }

    #[test]
    fn prepares_and_verifies_a_console_executable() {
        let root = temp_root("guest-store");
        let store = GuestArtifactStore::new(&root);
        let prepared = store.prepare(&fixture()).unwrap();
        assert_eq!(prepared.binding.architecture, CpuArchitecture::X86_64);
        assert_eq!(prepared.binding.original_name, "hello-x86_64.exe");
        assert!(Path::new(&prepared.binding.stored_path).starts_with(root.join("guest-artifacts")));
        store.verify(&prepared.binding).unwrap();
        make_writable(Path::new(&prepared.binding.stored_path));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn source_changes_do_not_change_the_materialized_object() {
        let root = temp_root("guest-source-change");
        let source = root.join("hello.exe");
        fs::copy(fixture(), &source).unwrap();
        let store = GuestArtifactStore::new(root.join("store"));
        let prepared = store.prepare(&source).unwrap();
        fs::write(&source, b"replaced after inspection").unwrap();
        store.verify(&prepared.binding).unwrap();
        make_writable(Path::new(&prepared.binding.stored_path));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_tampered_objects() {
        let root = temp_root("guest-tamper");
        let store = GuestArtifactStore::new(&root);
        let prepared = store.prepare(&fixture()).unwrap();
        let path = Path::new(&prepared.binding.stored_path);
        make_writable(path);
        fs::write(path, b"tampered").unwrap();
        assert!(matches!(
            store.verify(&prepared.binding),
            Err(GuestArtifactError::SizeMismatch { .. })
        ));
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symbolic_link_sources() {
        use std::os::unix::fs::symlink;
        let root = temp_root("guest-symlink");
        let source = root.join("hello.exe");
        symlink(fixture(), &source).unwrap();
        let store = GuestArtifactStore::new(root.join("store"));
        assert!(matches!(
            store.prepare(&source),
            Err(GuestArtifactError::NotRegularFile(_))
        ));
        fs::remove_dir_all(root).unwrap();
    }
}
