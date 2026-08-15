//! Immutable, content-addressed storage for inspected Windows guest programs.

#![forbid(unsafe_code)]

use compatforge_domain::{
    BottleExecutableBinding, ContractError, CpuArchitecture, GuestArtifactBinding, SCHEMA_VERSION_V1,
};
use compatforge_inspect::{
    inspect_bytes, inspect_path, InspectionError, PeArchitecture, PeImageKind, PeInspectionReport, PeSubsystem,
    MAX_PE_FILE_BYTES,
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

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreparedBottleExecutable {
    pub binding: BottleExecutableBinding,
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
            subsystem: subsystem_name(inspection.subsystem).into(),
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

    /// Inspect and bind an executable in the Bottle's Wine `drive_c` tree
    /// without copying it. The complete path is checked for symlinks and the
    /// resulting digest/size is revalidated immediately before spawn.
    pub fn prepare_bottle_in_place(
        &self,
        bottle_id: &str,
        source: &Path,
    ) -> Result<PreparedBottleExecutable, GuestArtifactError> {
        let storage_root = self
            .root
            .parent()
            .ok_or_else(|| GuestArtifactError::RelativeStorageRoot(self.root.clone()))?;
        let bottle_root = storage_root
            .join("bottles")
            .join(bottle_id)
            .join("prefix")
            .join("drive_c");
        validate_bottle_path(storage_root, &bottle_root, source)?;
        let inspection = inspect_path(source).map_err(GuestArtifactError::Inspection)?;
        validate_supported_inspection(&inspection)?;
        let architecture = map_architecture(inspection.architecture)?;
        let original_name = source
            .file_name()
            .and_then(|name| name.to_str())
            .filter(|name| !name.is_empty() && !matches!(*name, "." | ".."))
            .ok_or_else(|| GuestArtifactError::InvalidFileName(source.to_owned()))?
            .to_owned();
        let binding = BottleExecutableBinding {
            bottle_id: bottle_id.to_owned(),
            digest: inspection.file_digest.clone(),
            size_bytes: inspection.file_size_bytes,
            path: source.to_string_lossy().into_owned(),
            original_name,
            architecture,
            image_kind: "executable".into(),
            subsystem: subsystem_name(inspection.subsystem).into(),
            inspection_schema_version: SCHEMA_VERSION_V1.into(),
        };
        verify_bottle_binding_contents(storage_root, &binding)?;
        Ok(PreparedBottleExecutable { binding, inspection })
    }

    pub fn verify_bottle(&self, binding: &BottleExecutableBinding) -> Result<(), GuestArtifactError> {
        let storage_root = self
            .root
            .parent()
            .ok_or_else(|| GuestArtifactError::RelativeStorageRoot(self.root.clone()))?;
        verify_bottle_binding_contents(storage_root, binding)
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

/// Re-hash an in-place Bottle executable immediately before a process is
/// created. This intentionally does not claim to sandbox sibling resources.
pub fn verify_bottle_binding_contents(
    storage_root: &Path,
    binding: &BottleExecutableBinding,
) -> Result<(), GuestArtifactError> {
    binding.validate().map_err(GuestArtifactError::InvalidBottleBinding)?;
    let bottle_root = storage_root
        .join("bottles")
        .join(&binding.bottle_id)
        .join("prefix")
        .join("drive_c");
    let path = Path::new(&binding.path);
    validate_bottle_path(storage_root, &bottle_root, path)?;
    verify_in_place_binding_contents(binding)
}

/// Re-hash an in-place binding without making assumptions about the storage
/// root. Policy authorization is responsible for the Bottle boundary; this
/// final check closes the symlink/race window immediately before spawn.
pub fn verify_in_place_binding_contents(binding: &BottleExecutableBinding) -> Result<(), GuestArtifactError> {
    binding.validate().map_err(GuestArtifactError::InvalidBottleBinding)?;
    let path = Path::new(&binding.path);
    if !path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(GuestArtifactError::AmbiguousSource(path.to_owned()));
    }
    let components = path.components().collect::<Vec<_>>();
    let drive_c_index = components
        .windows(4)
        .position(|window| {
            window[0].as_os_str() == std::ffi::OsStr::new("bottles")
                && window[2].as_os_str() == std::ffi::OsStr::new("prefix")
                && window[3].as_os_str() == std::ffi::OsStr::new("drive_c")
        })
        .map(|index| index + 3)
        .ok_or_else(|| GuestArtifactError::BottlePathOutsideRoot {
            root: PathBuf::from("<bottle>/prefix/drive_c"),
            actual: path.to_owned(),
        })?;
    let mut cursor = PathBuf::new();
    for (index, component) in components.iter().enumerate() {
        cursor.push(component.as_os_str());
        if index < drive_c_index {
            continue;
        }
        let metadata = fs::symlink_metadata(&cursor).map_err(|source| GuestArtifactError::Filesystem {
            path: cursor.clone(),
            source,
        })?;
        if metadata.file_type().is_symlink() {
            return Err(GuestArtifactError::SymbolicLink(cursor));
        }
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

fn validate_bottle_path(storage_root: &Path, bottle_root: &Path, source: &Path) -> Result<(), GuestArtifactError> {
    if !storage_root.is_absolute() || !source.is_absolute() {
        return Err(GuestArtifactError::RelativeSource(source.to_owned()));
    }
    if source
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(GuestArtifactError::AmbiguousSource(source.to_owned()));
    }
    if !source.starts_with(bottle_root) || source == bottle_root {
        return Err(GuestArtifactError::BottlePathOutsideRoot {
            root: bottle_root.to_owned(),
            actual: source.to_owned(),
        });
    }
    let storage_metadata =
        fs::symlink_metadata(storage_root).map_err(|source_error| GuestArtifactError::Filesystem {
            path: storage_root.to_owned(),
            source: source_error,
        })?;
    if storage_metadata.file_type().is_symlink() || !storage_metadata.is_dir() {
        return Err(GuestArtifactError::SymbolicLink(storage_root.to_owned()));
    }
    let relative = source
        .strip_prefix(storage_root)
        .map_err(|_| GuestArtifactError::BottlePathOutsideRoot {
            root: bottle_root.to_owned(),
            actual: source.to_owned(),
        })?;
    let mut cursor = storage_root.to_owned();
    for component in relative.components() {
        cursor.push(component.as_os_str());
        let metadata = fs::symlink_metadata(&cursor).map_err(|source_error| GuestArtifactError::Filesystem {
            path: cursor.clone(),
            source: source_error,
        })?;
        if metadata.file_type().is_symlink() {
            return Err(GuestArtifactError::SymbolicLink(cursor));
        }
    }
    let metadata = fs::symlink_metadata(source).map_err(|source_error| GuestArtifactError::Filesystem {
        path: source.to_owned(),
        source: source_error,
    })?;
    if !metadata.is_file() {
        return Err(GuestArtifactError::NotRegularFile(source.to_owned()));
    }
    if metadata.len() > MAX_PE_FILE_BYTES {
        return Err(GuestArtifactError::FileTooLarge(metadata.len()));
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
    if !matches!(report.subsystem, PeSubsystem::WindowsConsole | PeSubsystem::WindowsGui) {
        return Err(GuestArtifactError::UnsupportedSubsystem(report.subsystem));
    }
    map_architecture(report.architecture).map(|_| ())
}

fn subsystem_name(subsystem: PeSubsystem) -> &'static str {
    match subsystem {
        PeSubsystem::WindowsConsole => "windowsConsole",
        PeSubsystem::WindowsGui => "windowsGui",
        _ => "unknown",
    }
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
    InvalidBottleBinding(ContractError),
    Inspection(InspectionError),
    UnsupportedArchitecture(PeArchitecture),
    UnsupportedImageKind(PeImageKind),
    UnsupportedSubsystem(PeSubsystem),
    UnexpectedObjectPath { expected: PathBuf, actual: PathBuf },
    SizeMismatch { expected: u64, actual: u64 },
    DigestMismatch { expected: String, actual: String },
    ObjectCollision(String),
    BottlePathOutsideRoot { root: PathBuf, actual: PathBuf },
    SymbolicLink(PathBuf),
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
            Self::InvalidBottleBinding(error) => write!(formatter, "invalid Bottle executable binding: {error}"),
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
            Self::BottlePathOutsideRoot { root, actual } => write!(
                formatter,
                "Bottle executable path {} is outside authorized drive_c root {}",
                actual.display(),
                root.display()
            ),
            Self::SymbolicLink(path) => write!(
                formatter,
                "Bottle executable path contains a symbolic link: {}",
                path.display()
            ),
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
            Self::InvalidBinding(error) | Self::InvalidBottleBinding(error) => Some(error),
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

    fn gui_fixture_bytes() -> Vec<u8> {
        let path = fixture();
        let mut bytes = fs::read(path).unwrap();
        // PE32+ optional header subsystem field: 0x98 + 68.
        bytes[0xdc..0xde].copy_from_slice(&2_u16.to_le_bytes());
        bytes
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
    fn binds_gui_executable_in_place_and_rejects_tampering_or_escape() {
        let root = temp_root("bottle-in-place");
        let storage = root.join("storage");
        let executable = storage.join("bottles/gui-test/prefix/drive_c/Program Files/Example/Example.exe");
        fs::create_dir_all(executable.parent().unwrap()).unwrap();
        fs::write(&executable, gui_fixture_bytes()).unwrap();
        let store = GuestArtifactStore::new(&storage);
        let prepared = store.prepare_bottle_in_place("gui-test", &executable).unwrap();
        assert_eq!(prepared.binding.subsystem, "windowsGui");
        assert_eq!(prepared.binding.path, executable.to_string_lossy());
        store.verify_bottle(&prepared.binding).unwrap();

        fs::write(&executable, b"tampered").unwrap();
        assert!(matches!(
            store.verify_bottle(&prepared.binding),
            Err(GuestArtifactError::SizeMismatch { .. }) | Err(GuestArtifactError::DigestMismatch { .. })
        ));
        let outside = root.join("outside.exe");
        fs::write(&outside, gui_fixture_bytes()).unwrap();
        let escaped = BottleExecutableBinding {
            path: outside.to_string_lossy().into_owned(),
            ..prepared.binding
        };
        assert!(matches!(
            store.verify_bottle(&escaped),
            Err(GuestArtifactError::BottlePathOutsideRoot { .. })
        ));
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
