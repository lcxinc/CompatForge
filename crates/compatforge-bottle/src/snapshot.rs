use crate::contract::{LegacyBottleManifest, MAX_MANIFEST_BYTES};
use crate::digest::{canonical_compact_json, canonical_pretty_json_lf, copy_and_digest, digest_reader, sha256_bytes};
use crate::{BottleMigrationError, DiagnosticCode};
use compatforge_domain::validate_id;
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

pub const MAX_PATH_BYTES: usize = 4096;
pub const MAX_PATH_DEPTH: usize = 128;
pub const MAX_ENTRIES: usize = 100_000;
pub const MAX_FILE_BYTES: u64 = 64 * 1024 * 1024 * 1024;
pub const MAX_TOTAL_FILE_BYTES: u64 = 1024 * 1024 * 1024 * 1024;
pub const MAX_SNAPSHOT_MANIFEST_BYTES: usize = 64 * 1024 * 1024;

const SCHEMA_VERSION: &str = "1";
const LEGACY_FORMAT: &str = "macwin-bottle-v1";
static TEMPORARY_FILE_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BottleSnapshot {
    pub schema_version: String,
    pub legacy_format: String,
    pub bottle_id: String,
    pub entries: Vec<SnapshotEntry>,
    pub entry_count: usize,
    pub total_file_bytes: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase", deny_unknown_fields)]
pub enum SnapshotEntry {
    File { path: String, size: u64, digest: String },
    Directory { path: String },
}

impl SnapshotEntry {
    fn path(&self) -> &str {
        match self {
            Self::File { path, .. } | Self::Directory { path } => path,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SnapshotReceipt {
    pub bottle_id: String,
    pub snapshot_digest: String,
    pub entry_count: usize,
    pub total_file_bytes: u64,
}

#[derive(Debug, Clone)]
pub struct BottleStore {
    root: PathBuf,
}

#[derive(Debug)]
struct SourceFile {
    source_path: PathBuf,
    relative_path: String,
    size: u64,
}

#[derive(Debug)]
enum SourceEntry {
    File(SourceFile),
    Directory(String),
}

impl SourceEntry {
    fn path(&self) -> &str {
        match self {
            Self::File(file) => &file.relative_path,
            Self::Directory(path) => path,
        }
    }
}

impl BottleStore {
    #[must_use]
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn snapshot(&self, source: &Path) -> Result<SnapshotReceipt, BottleMigrationError> {
        let root_metadata = fs::symlink_metadata(source).map_err(|_| unsafe_entry())?;
        if !root_metadata.file_type().is_dir() || root_metadata.file_type().is_symlink() {
            return Err(unsafe_entry());
        }

        let source_root = fs::canonicalize(source).map_err(|_| unsafe_entry())?;
        let store_root = resolve_store_root_without_writing(&self.root)?;
        if store_root == source_root || store_root.starts_with(&source_root) || source_root.starts_with(&store_root) {
            return Err(unsafe_entry());
        }
        let store = Self { root: store_root };

        let mut source_entries = Vec::new();
        let mut total_file_bytes = 0_u64;
        collect_source_entries(&source_root, &source_root, &mut source_entries, &mut total_file_bytes)?;
        source_entries.sort_by(|left, right| left.path().cmp(right.path()));

        let manifest_source = source_entries
            .iter()
            .find_map(|entry| match entry {
                SourceEntry::File(file) if file.relative_path == "manifest.json" => Some(file),
                _ => None,
            })
            .ok_or_else(invalid_manifest)?;
        if manifest_source.size > u64::try_from(MAX_MANIFEST_BYTES).expect("manifest bound fits u64") {
            return Err(invalid_manifest());
        }
        let manifest_bytes =
            read_bounded(&manifest_source.source_path, MAX_MANIFEST_BYTES).map_err(|_| invalid_manifest())?;
        let manifest_json = std::str::from_utf8(&manifest_bytes).map_err(|_| invalid_manifest())?;
        let legacy_manifest = LegacyBottleManifest::from_json(manifest_json)?;
        validate_id("legacyBottle.id", &legacy_manifest.id).map_err(|_| invalid_manifest())?;

        let mut snapshot_entries = Vec::with_capacity(source_entries.len());
        for source_entry in source_entries {
            match source_entry {
                SourceEntry::Directory(path) => snapshot_entries.push(SnapshotEntry::Directory { path }),
                SourceEntry::File(file) => {
                    let digest = store.publish_object(&file)?;
                    snapshot_entries.push(SnapshotEntry::File {
                        path: file.relative_path,
                        size: file.size,
                        digest,
                    });
                }
            }
        }

        let snapshot = BottleSnapshot {
            schema_version: SCHEMA_VERSION.into(),
            legacy_format: LEGACY_FORMAT.into(),
            bottle_id: legacy_manifest.id,
            entry_count: snapshot_entries.len(),
            entries: snapshot_entries,
            total_file_bytes,
        };
        snapshot.validate().map_err(|_| unsafe_entry())?;
        store
            .verify_legacy_manifest_object(&snapshot)
            .map_err(|_| source_changed())?;

        let compact = canonical_compact_json(&snapshot).map_err(|_| transaction_failed())?;
        let snapshot_digest = sha256_bytes(&compact);
        let published = canonical_pretty_json_lf(&snapshot).map_err(|_| transaction_failed())?;
        if published.len() > MAX_SNAPSHOT_MANIFEST_BYTES {
            return Err(unsafe_entry());
        }
        store.publish_snapshot(&snapshot_digest, &published)?;
        store.verify_snapshot(&snapshot_digest)?;

        Ok(SnapshotReceipt {
            bottle_id: snapshot.bottle_id,
            snapshot_digest,
            entry_count: snapshot.entry_count,
            total_file_bytes: snapshot.total_file_bytes,
        })
    }

    pub fn verify_snapshot(&self, digest: &str) -> Result<BottleSnapshot, BottleMigrationError> {
        let digest_hex = digest_hex(digest).ok_or_else(snapshot_corrupt)?;
        let path = self
            .root
            .join("snapshots")
            .join("sha256")
            .join(format!("{digest_hex}.json"));
        let metadata = fs::symlink_metadata(&path).map_err(|_| snapshot_corrupt())?;
        if !metadata.file_type().is_file()
            || metadata.file_type().is_symlink()
            || metadata.len() > u64::try_from(MAX_SNAPSHOT_MANIFEST_BYTES).expect("manifest bound fits u64")
        {
            return Err(snapshot_corrupt());
        }
        let bytes = fs::read(&path).map_err(|_| snapshot_corrupt())?;
        let snapshot: BottleSnapshot = serde_json::from_slice(&bytes).map_err(|_| snapshot_corrupt())?;
        snapshot.validate()?;

        let compact = canonical_compact_json(&snapshot).map_err(|_| snapshot_corrupt())?;
        if sha256_bytes(&compact) != digest {
            return Err(snapshot_corrupt());
        }
        let canonical = canonical_pretty_json_lf(&snapshot).map_err(|_| snapshot_corrupt())?;
        if bytes != canonical {
            return Err(snapshot_corrupt());
        }

        for entry in &snapshot.entries {
            if let SnapshotEntry::File { size, digest, .. } = entry {
                self.verify_object(digest, *size)?;
            }
        }
        self.verify_legacy_manifest_object(&snapshot)?;
        Ok(snapshot)
    }

    fn publish_object(&self, source: &SourceFile) -> Result<String, BottleMigrationError> {
        let object_directory = self.root.join("objects").join("sha256");
        fs::create_dir_all(&object_directory).map_err(|_| transaction_failed())?;
        let temporary = temporary_path(&object_directory, "object");
        let result = (|| {
            let mut input = File::open(&source.source_path).map_err(|_| source_changed())?;
            let mut output = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&temporary)
                .map_err(|_| transaction_failed())?;
            let (digest, copied) = copy_and_digest(&mut input, &mut output).map_err(|_| source_changed())?;
            if copied != source.size || copied > MAX_FILE_BYTES {
                return Err(source_changed());
            }
            output.sync_all().map_err(|_| transaction_failed())?;
            let digest_hex = digest_hex(&digest).ok_or_else(transaction_failed)?;
            let target = object_directory.join(digest_hex);
            if target.exists() {
                self.verify_object(&digest, copied)?;
                fs::remove_file(&temporary).map_err(|_| transaction_failed())?;
                return Ok(digest);
            }
            fs::rename(&temporary, &target).map_err(|_| transaction_failed())?;
            sync_directory(&object_directory)?;
            self.verify_object(&digest, copied)?;
            Ok(digest)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
        }
        result
    }

    fn verify_object(&self, digest: &str, size: u64) -> Result<(), BottleMigrationError> {
        let digest_hex = digest_hex(digest).ok_or_else(snapshot_corrupt)?;
        let path = self.root.join("objects").join("sha256").join(digest_hex);
        let metadata = fs::symlink_metadata(&path).map_err(|_| snapshot_corrupt())?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() || metadata.len() != size {
            return Err(snapshot_corrupt());
        }
        let mut file = File::open(path).map_err(|_| snapshot_corrupt())?;
        let (actual, actual_size) = digest_reader(&mut file).map_err(|_| snapshot_corrupt())?;
        if actual != digest || actual_size != size {
            return Err(snapshot_corrupt());
        }
        Ok(())
    }

    fn publish_snapshot(&self, digest: &str, bytes: &[u8]) -> Result<(), BottleMigrationError> {
        let digest_hex = digest_hex(digest).ok_or_else(transaction_failed)?;
        let directory = self.root.join("snapshots").join("sha256");
        fs::create_dir_all(&directory).map_err(|_| transaction_failed())?;
        let target = directory.join(format!("{digest_hex}.json"));
        if target.exists() {
            let existing = fs::read(&target).map_err(|_| snapshot_corrupt())?;
            return if existing == bytes {
                Ok(())
            } else {
                Err(snapshot_corrupt())
            };
        }

        let temporary = temporary_path(&directory, "snapshot");
        let result = (|| {
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&temporary)
                .map_err(|_| transaction_failed())?;
            file.write_all(bytes).map_err(|_| transaction_failed())?;
            file.sync_all().map_err(|_| transaction_failed())?;
            fs::rename(&temporary, &target).map_err(|_| transaction_failed())?;
            sync_directory(&directory)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
        }
        result
    }

    fn verify_legacy_manifest_object(&self, snapshot: &BottleSnapshot) -> Result<(), BottleMigrationError> {
        let (size, digest) = snapshot
            .entries
            .iter()
            .find_map(|entry| match entry {
                SnapshotEntry::File { path, size, digest } if path == "manifest.json" => Some((*size, digest)),
                _ => None,
            })
            .ok_or_else(snapshot_corrupt)?;
        if size > u64::try_from(MAX_MANIFEST_BYTES).expect("manifest bound fits u64") {
            return Err(snapshot_corrupt());
        }
        let digest_hex = digest_hex(digest).ok_or_else(snapshot_corrupt)?;
        let bytes = read_bounded(
            &self.root.join("objects").join("sha256").join(digest_hex),
            MAX_MANIFEST_BYTES,
        )
        .map_err(|_| snapshot_corrupt())?;
        let json = std::str::from_utf8(&bytes).map_err(|_| snapshot_corrupt())?;
        let manifest = LegacyBottleManifest::from_json(json).map_err(|_| snapshot_corrupt())?;
        if manifest.id != snapshot.bottle_id {
            return Err(snapshot_corrupt());
        }
        Ok(())
    }
}

impl BottleSnapshot {
    fn validate(&self) -> Result<(), BottleMigrationError> {
        if self.schema_version != SCHEMA_VERSION
            || self.legacy_format != LEGACY_FORMAT
            || validate_id("snapshot.bottleId", &self.bottle_id).is_err()
            || self.entries.is_empty()
            || self.entries.len() > MAX_ENTRIES
            || self.entry_count != self.entries.len()
        {
            return Err(snapshot_corrupt());
        }

        let mut previous: Option<&str> = None;
        let mut total = 0_u64;
        for entry in &self.entries {
            let path = entry.path();
            validate_basic_path(path).map_err(|_| snapshot_corrupt())?;
            if previous.is_some_and(|value| value >= path) {
                return Err(snapshot_corrupt());
            }
            previous = Some(path);
            if let SnapshotEntry::File { size, digest, .. } = entry {
                if *size > MAX_FILE_BYTES || digest_hex(digest).is_none() {
                    return Err(snapshot_corrupt());
                }
                total = total.checked_add(*size).ok_or_else(snapshot_corrupt)?;
                if total > MAX_TOTAL_FILE_BYTES {
                    return Err(snapshot_corrupt());
                }
            }
        }
        if total != self.total_file_bytes {
            return Err(snapshot_corrupt());
        }
        Ok(())
    }
}

fn collect_source_entries(
    root: &Path,
    directory: &Path,
    entries: &mut Vec<SourceEntry>,
    total_file_bytes: &mut u64,
) -> Result<(), BottleMigrationError> {
    let children = fs::read_dir(directory).map_err(|_| unsafe_entry())?;
    for child in children {
        let child = child.map_err(|_| unsafe_entry())?;
        let path = child.path();
        let relative_path = portable_relative_path(root, &path)?;
        let metadata = fs::symlink_metadata(&path).map_err(|_| unsafe_entry())?;
        let file_type = metadata.file_type();
        if file_type.is_symlink() {
            return Err(unsafe_entry());
        }
        if file_type.is_dir() {
            push_entry(entries, SourceEntry::Directory(relative_path))?;
            collect_source_entries(root, &path, entries, total_file_bytes)?;
        } else if file_type.is_file() {
            let size = metadata.len();
            checked_regular_file_size(size, total_file_bytes)?;
            push_entry(
                entries,
                SourceEntry::File(SourceFile {
                    source_path: path,
                    relative_path,
                    size,
                }),
            )?;
        } else {
            return Err(unsafe_entry());
        }
    }
    Ok(())
}

fn resolve_store_root_without_writing(root: &Path) -> Result<PathBuf, BottleMigrationError> {
    if root.as_os_str().is_empty() {
        return Err(unsafe_entry());
    }
    let absolute = if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir().map_err(|_| unsafe_entry())?.join(root)
    };
    let normalized = normalize_absolute_path(&absolute)?;

    let mut existing = normalized.clone();
    let mut missing = Vec::new();
    loop {
        match fs::symlink_metadata(&existing) {
            Ok(metadata) => {
                if !metadata.file_type().is_dir() {
                    return Err(unsafe_entry());
                }
                let mut resolved = fs::canonicalize(&existing).map_err(|_| unsafe_entry())?;
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                let component = existing.file_name().ok_or_else(unsafe_entry)?.to_owned();
                missing.push(component);
                if !existing.pop() {
                    return Err(unsafe_entry());
                }
            }
            Err(_) => return Err(unsafe_entry()),
        }
    }
}

fn normalize_absolute_path(path: &Path) -> Result<PathBuf, BottleMigrationError> {
    if !path.is_absolute() {
        return Err(unsafe_entry());
    }
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(_) | Component::RootDir | Component::Normal(_) => {
                normalized.push(component.as_os_str());
            }
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return Err(unsafe_entry());
                }
            }
        }
    }
    if normalized.is_absolute() {
        Ok(normalized)
    } else {
        Err(unsafe_entry())
    }
}

fn checked_regular_file_size(size: u64, total: &mut u64) -> Result<(), BottleMigrationError> {
    if size > MAX_FILE_BYTES {
        return Err(unsafe_entry());
    }
    let next = total.checked_add(size).ok_or_else(unsafe_entry)?;
    if next > MAX_TOTAL_FILE_BYTES {
        return Err(unsafe_entry());
    }
    *total = next;
    Ok(())
}

fn push_entry(entries: &mut Vec<SourceEntry>, entry: SourceEntry) -> Result<(), BottleMigrationError> {
    if entries.len() == MAX_ENTRIES {
        return Err(unsafe_entry());
    }
    entries.push(entry);
    Ok(())
}

fn portable_relative_path(root: &Path, path: &Path) -> Result<String, BottleMigrationError> {
    let relative = path.strip_prefix(root).map_err(|_| unsafe_entry())?;
    let mut components = Vec::new();
    for component in relative.components() {
        let value = component.as_os_str().to_str().ok_or_else(unsafe_entry)?;
        if value.is_empty()
            || value == "."
            || value == ".."
            || value.ends_with([' ', '.'])
            || value
                .chars()
                .any(|character| character.is_control() || "<>:\"\\|?*".contains(character))
        {
            return Err(unsafe_entry());
        }
        components.push(value);
    }
    let value = components.join("/");
    validate_basic_path(&value)?;
    Ok(value)
}

fn validate_basic_path(value: &str) -> Result<(), BottleMigrationError> {
    let depth = value.split('/').count();
    if value.is_empty()
        || value.len() > MAX_PATH_BYTES
        || depth > MAX_PATH_DEPTH
        || value
            .split('/')
            .any(|component| component.is_empty() || matches!(component, "." | ".."))
    {
        return Err(unsafe_entry());
    }
    Ok(())
}

fn read_bounded(path: &Path, maximum: usize) -> io::Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > u64::try_from(maximum).expect("read bound fits u64")
    {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "bounded file rejected"));
    }
    let mut file = File::open(path)?;
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(maximum));
    Read::by_ref(&mut file)
        .take(u64::try_from(maximum).expect("read bound fits u64") + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > maximum {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "bounded file rejected"));
    }
    Ok(bytes)
}

fn digest_hex(digest: &str) -> Option<&str> {
    let hex = digest.strip_prefix("sha256:")?;
    (hex.len() == 64
        && hex
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f')))
    .then_some(hex)
}

fn temporary_path(directory: &Path, label: &str) -> PathBuf {
    let counter = TEMPORARY_FILE_COUNTER.fetch_add(1, Ordering::Relaxed);
    directory.join(format!(".{label}.tmp-{}-{counter}", std::process::id()))
}

#[cfg(unix)]
fn sync_directory(path: &Path) -> Result<(), BottleMigrationError> {
    File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|_| transaction_failed())
}

#[cfg(not(unix))]
fn sync_directory(_path: &Path) -> Result<(), BottleMigrationError> {
    Ok(())
}

const fn unsafe_entry() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::UnsafeEntry)
}

const fn invalid_manifest() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::InvalidManifest)
}

const fn source_changed() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::SourceChanged)
}

const fn snapshot_corrupt() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::SnapshotCorrupt)
}

const fn transaction_failed() -> BottleMigrationError {
    BottleMigrationError::new(DiagnosticCode::TransactionFailed)
}

#[cfg(test)]
mod tests {
    use super::{
        checked_regular_file_size, BottleSnapshot, BottleStore, SnapshotEntry, MAX_FILE_BYTES, MAX_TOTAL_FILE_BYTES,
    };
    use crate::DiagnosticCode;
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::SystemTime;

    const MANIFEST: &[u8] = br#"{"id":"bottle-1","name":"Example Bottle","windowsVersion":"win10","arch":"win64","engineId":"wine-9","envOverrides":{},"installedApps":[],"createdAt":"2026-08-08T00:00:00Z","updatedAt":"2026-08-08T00:00:01Z"}
"#;
    const PAYLOAD: &[u8] = b"public fixture\n";
    const MANIFEST_DIGEST: &str = "sha256:fded28721427e68a8055a2f21a3de49f18f6f40eef790ddd0e8aeae7679b64bd";
    const PAYLOAD_DIGEST: &str = "sha256:d3b26e1f1ce13bde26578063b679fab4dbba401f23bc8ed938f8f4d5713f5048";
    const SNAPSHOT_DIGEST: &str = "sha256:8e363a6b4bbb9af21979ab56432b303eb069e8f410641cd2860ad4755cec6a37";
    const SORTED_PUBLISHED_SNAPSHOT: &[u8] = br#"{
  "bottleId": "bottle-1",
  "entries": [
    {
      "kind": "directory",
      "path": "empty"
    },
    {
      "digest": "sha256:fded28721427e68a8055a2f21a3de49f18f6f40eef790ddd0e8aeae7679b64bd",
      "kind": "file",
      "path": "manifest.json",
      "size": 209
    },
    {
      "digest": "sha256:d3b26e1f1ce13bde26578063b679fab4dbba401f23bc8ed938f8f4d5713f5048",
      "kind": "file",
      "path": "payload-copy.txt",
      "size": 15
    },
    {
      "digest": "sha256:d3b26e1f1ce13bde26578063b679fab4dbba401f23bc8ed938f8f4d5713f5048",
      "kind": "file",
      "path": "payload.txt",
      "size": 15
    }
  ],
  "entryCount": 4,
  "legacyFormat": "macwin-bottle-v1",
  "schemaVersion": "1",
  "totalFileBytes": 239
}
"#;

    static TEMPORARY_DIRECTORY_COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TemporaryDirectory(PathBuf);

    impl TemporaryDirectory {
        fn new(label: &str) -> Self {
            let counter = TEMPORARY_DIRECTORY_COUNTER.fetch_add(1, Ordering::Relaxed);
            let path =
                std::env::temp_dir().join(format!("compatforge-bottle-{label}-{}-{counter}", std::process::id()));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn new_in(parent: &Path, label: &str) -> Self {
            let counter = TEMPORARY_DIRECTORY_COUNTER.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(".compatforge-bottle-{label}-{}-{counter}", std::process::id()));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TemporaryDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[derive(Debug, PartialEq, Eq)]
    struct SourceLeaf {
        path: String,
        bytes: Option<Vec<u8>>,
        length: u64,
        modified: Option<SystemTime>,
    }

    fn create_regular_source(root: &Path) -> PathBuf {
        let source = root.join("source");
        fs::create_dir(&source).unwrap();
        fs::create_dir(source.join("empty")).unwrap();
        fs::write(source.join("manifest.json"), MANIFEST).unwrap();
        fs::write(source.join("payload.txt"), PAYLOAD).unwrap();
        fs::write(source.join("payload-copy.txt"), PAYLOAD).unwrap();
        source
    }

    fn source_inventory(root: &Path) -> Vec<SourceLeaf> {
        fn visit(root: &Path, current: &Path, leaves: &mut Vec<SourceLeaf>) {
            let mut children = fs::read_dir(current)
                .unwrap()
                .map(|entry| entry.unwrap())
                .collect::<Vec<_>>();
            children.sort_by_key(|entry| entry.file_name());
            for child in children {
                let path = child.path();
                let metadata = fs::symlink_metadata(&path).unwrap();
                let relative = path.strip_prefix(root).unwrap().to_string_lossy().replace('\\', "/");
                leaves.push(SourceLeaf {
                    path: relative,
                    bytes: metadata.is_file().then(|| fs::read(&path).unwrap()),
                    length: metadata.len(),
                    modified: metadata.modified().ok(),
                });
                if metadata.is_dir() {
                    visit(root, &path, leaves);
                }
            }
        }

        let mut leaves = Vec::new();
        visit(root, root, &mut leaves);
        leaves
    }

    fn object_count(store: &Path) -> usize {
        fs::read_dir(store.join("objects/sha256"))
            .unwrap()
            .map(|entry| entry.unwrap())
            .filter(|entry| entry.file_type().unwrap().is_file())
            .count()
    }

    #[test]
    fn snapshot_regular_files_are_content_addressed_and_source_read_only() {
        let temporary = TemporaryDirectory::new("snapshot-regular");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let source_before = source_inventory(&source);

        let receipt = BottleStore::new(&store).snapshot(&source).unwrap();

        assert_eq!(receipt.bottle_id, "bottle-1");
        assert_eq!(receipt.entry_count, 4);
        assert_eq!(receipt.total_file_bytes, 239);
        assert_eq!(receipt.snapshot_digest, SNAPSHOT_DIGEST);
        assert_eq!(object_count(&store), 2);
        assert_eq!(fs::read(source.join("payload.txt")).unwrap(), PAYLOAD);
        assert_eq!(source_inventory(&source), source_before);

        let snapshot = BottleStore::new(&store).verify_snapshot(SNAPSHOT_DIGEST).unwrap();
        assert_eq!(
            snapshot,
            BottleSnapshot {
                schema_version: "1".into(),
                legacy_format: "macwin-bottle-v1".into(),
                bottle_id: "bottle-1".into(),
                entries: vec![
                    SnapshotEntry::Directory { path: "empty".into() },
                    SnapshotEntry::File {
                        path: "manifest.json".into(),
                        size: 209,
                        digest: MANIFEST_DIGEST.into(),
                    },
                    SnapshotEntry::File {
                        path: "payload-copy.txt".into(),
                        size: 15,
                        digest: PAYLOAD_DIGEST.into(),
                    },
                    SnapshotEntry::File {
                        path: "payload.txt".into(),
                        size: 15,
                        digest: PAYLOAD_DIGEST.into(),
                    },
                ],
                entry_count: 4,
                total_file_bytes: 239,
            }
        );
    }

    #[test]
    fn snapshot_is_idempotent_and_verifies_objects() {
        let temporary = TemporaryDirectory::new("snapshot-object");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let bottle_store = BottleStore::new(&store);

        let first = bottle_store.snapshot(&source).unwrap();
        let first_bytes = serde_json::to_vec(&first).unwrap();
        let second = bottle_store.snapshot(&source).unwrap();

        assert_eq!(serde_json::to_vec(&second).unwrap(), first_bytes);
        assert_eq!(object_count(&store), 2);
        assert_eq!(
            bottle_store.verify_snapshot(SNAPSHOT_DIGEST).unwrap().bottle_id,
            "bottle-1"
        );

        let published = fs::read(
            store.join("snapshots/sha256/8e363a6b4bbb9af21979ab56432b303eb069e8f410641cd2860ad4755cec6a37.json"),
        )
        .unwrap();
        assert!(published.ends_with(b"\n"));
        assert_eq!(published, SORTED_PUBLISHED_SNAPSHOT);
    }

    #[test]
    fn object_corruption_is_rejected_with_a_closed_diagnostic() {
        let temporary = TemporaryDirectory::new("snapshot-object-corrupt");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let bottle_store = BottleStore::new(&store);
        bottle_store.snapshot(&source).unwrap();
        fs::write(
            store.join("objects/sha256/d3b26e1f1ce13bde26578063b679fab4dbba401f23bc8ed938f8f4d5713f5048"),
            b"tampered",
        )
        .unwrap();

        let error = bottle_store.verify_snapshot(SNAPSHOT_DIGEST).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(error.to_string(), "Bottle snapshot is corrupt");
    }

    #[test]
    fn snapshot_rejects_non_directory_source_and_invalid_manifest_before_store_creation() {
        let temporary = TemporaryDirectory::new("snapshot-invalid-source");
        let source_file = temporary.path().join("source-file");
        fs::write(&source_file, b"not a directory").unwrap();
        let first_store = temporary.path().join("first-store");

        let error = BottleStore::new(&first_store).snapshot(&source_file).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert!(!first_store.exists());

        let source = temporary.path().join("source");
        fs::create_dir(&source).unwrap();
        fs::write(source.join("manifest.json"), b"{}").unwrap();
        let second_store = temporary.path().join("second-store");
        let error = BottleStore::new(&second_store).snapshot(&source).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::InvalidManifest);
        assert!(!second_store.exists());
    }

    #[test]
    fn snapshot_rejects_relative_overlapping_roots_before_writing() {
        let current_before = std::env::current_dir().unwrap();
        let temporary = TemporaryDirectory::new_in(&current_before, "snapshot-overlap");

        for (case, store_relative) in [
            ("descendant", PathBuf::from("source/./nested/../store")),
            ("equal", PathBuf::from("source/.")),
            ("ancestor", PathBuf::from("source/../.")),
        ] {
            let case_root = temporary.path().join(case);
            fs::create_dir(&case_root).unwrap();
            let source = create_regular_source(&case_root);
            let relative_case_root = case_root.strip_prefix(&current_before).unwrap();
            let store = relative_case_root.join(store_relative);
            let source_before = source_inventory(&source);

            let error = BottleStore::new(store).snapshot(&source).unwrap_err();

            assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
            assert_eq!(source_inventory(&source), source_before);
            assert_eq!(std::env::current_dir().unwrap(), current_before);
            assert!(!case_root.join("objects").exists());
            assert!(!case_root.join("snapshots").exists());
            assert!(!source.join("objects").exists());
            assert!(!source.join("snapshots").exists());
            assert!(!source.join("store").exists());
        }
    }

    #[test]
    fn snapshot_rejects_oversized_regular_file_during_preflight() {
        let mut total = 0;
        let error = checked_regular_file_size(MAX_FILE_BYTES + 1, &mut total).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert_eq!(total, 0);
    }

    #[test]
    fn snapshot_rejects_total_regular_file_bytes_during_preflight() {
        let mut total = MAX_TOTAL_FILE_BYTES - MAX_FILE_BYTES;
        checked_regular_file_size(MAX_FILE_BYTES, &mut total).unwrap();
        assert_eq!(MAX_TOTAL_FILE_BYTES, 16 * MAX_FILE_BYTES);
        assert_eq!(total, MAX_TOTAL_FILE_BYTES);

        let error = checked_regular_file_size(1, &mut total).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert_eq!(total, MAX_TOTAL_FILE_BYTES);
    }
}
