use crate::contract::{LegacyBottleManifest, MAX_MANIFEST_BYTES};
use crate::digest::{copy_and_digest, digest_reader};
#[cfg(test)]
use crate::digest::{sha256_bytes, STREAM_BUFFER_BYTES};
use crate::path::{self, EntryKind};
use crate::platform::{self, FileIdentity};
use crate::{BottleMigrationError, DiagnosticCode};
use compatforge_domain::validate_id;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fmt::Write as _;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, Write};
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

#[cfg(test)]
thread_local! {
    static TEMPORARY_PATH_OVERRIDE: std::cell::RefCell<Option<(String, PathBuf)>> = const {
        std::cell::RefCell::new(None)
    };
    static SNAPSHOT_COMPARISON_BYTES_READ: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    static SNAPSHOT_STAGE_HOOK: std::cell::RefCell<Option<SnapshotTestHook>> = const { std::cell::RefCell::new(None) };
    static SNAPSHOT_MANIFEST_LIMIT_OVERRIDE: std::cell::Cell<Option<usize>> = const { std::cell::Cell::new(None) };
}

#[cfg(test)]
struct SnapshotTestHook {
    stage: SnapshotTestStage,
    path: String,
    hook: Box<dyn FnOnce()>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SnapshotTestStage {
    AfterRootBind,
    AfterSourcePreflight,
    AfterFileCopy,
    BeforeSourceRevalidation,
    AfterSourceRevalidation,
    AfterSnapshotManifestMeasurement,
    BeforeObjectPublish,
    BeforeSnapshotPublish,
    AfterSnapshotPublish,
    BeforeSnapshotReturn,
}

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
    Link { path: String, target: String },
}

impl SnapshotEntry {
    fn path(&self) -> &str {
        match self {
            Self::File { path, .. } | Self::Directory { path } | Self::Link { path, .. } => path,
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
    relative_path: String,
    size: u64,
    identity: FileIdentity,
    file: File,
    preflight_digest: String,
}

#[derive(Debug)]
enum SourceEntry {
    File(SourceFile),
    Directory {
        relative_path: String,
        identity: FileIdentity,
        _handle: File,
    },
    Link {
        relative_path: String,
        target: String,
        identity: FileIdentity,
        _handle: Option<File>,
    },
}

#[derive(Debug)]
struct OwnedTemporaryPath {
    path: PathBuf,
    name: Option<std::ffi::OsString>,
    directory: Option<File>,
    owned: bool,
}

#[derive(Debug)]
struct SnapshotPublication {
    target_name: std::ffi::OsString,
    created: bool,
    identity: Option<FileIdentity>,
}

impl OwnedTemporaryPath {
    #[cfg(test)]
    fn new(path: impl Into<PathBuf>) -> Self {
        Self {
            path: path.into(),
            name: None,
            directory: None,
            owned: false,
        }
    }

    fn new_bound(directory: &BoundDirectory, path: PathBuf) -> io::Result<Self> {
        let name = path
            .file_name()
            .ok_or_else(|| io::Error::other("temporary file has no name"))?
            .to_owned();
        Ok(Self {
            path,
            name: Some(name),
            directory: Some(directory.handle.try_clone()?),
            owned: false,
        })
    }

    fn create_new(&mut self) -> io::Result<File> {
        debug_assert!(!self.owned);
        let file = match (&self.directory, &self.name) {
            (Some(directory), Some(name)) => platform::create_regular_at(directory, name, &self.path)?,
            _ => OpenOptions::new().write(true).create_new(true).open(&self.path)?,
        };
        self.owned = true;
        Ok(file)
    }

    fn remove(&mut self) -> io::Result<()> {
        debug_assert!(self.owned);
        match (&self.directory, &self.name) {
            (Some(directory), Some(name)) => platform::remove_file_at(directory, name, &self.path.with_file_name(""))?,
            _ => fs::remove_file(&self.path)?,
        }
        self.owned = false;
        Ok(())
    }

    #[cfg(test)]
    fn disarm(&mut self) {
        self.owned = false;
    }
}

impl Drop for OwnedTemporaryPath {
    fn drop(&mut self) {
        if self.owned {
            let _ = match (&self.directory, &self.name) {
                (Some(directory), Some(name)) => {
                    platform::remove_file_at(directory, name, &self.path.with_file_name(""))
                }
                _ => fs::remove_file(&self.path),
            };
        }
    }
}

#[derive(Debug)]
struct BoundDirectory {
    path: PathBuf,
    handle: File,
    identity: FileIdentity,
}

impl BoundDirectory {
    fn bind(path: PathBuf) -> io::Result<Self> {
        let (handle, identity) = platform::bind_directory(&path)?;
        Ok(Self { path, handle, identity })
    }

    fn verify(&self) -> io::Result<()> {
        platform::verify_directory(&self.handle, self.identity)
    }

    fn bind_child(&self, name: &std::ffi::OsStr) -> io::Result<Self> {
        self.verify()?;
        let path = self.path.join(name);
        let (handle, identity) = platform::bind_directory_at(&self.handle, name, &path)?;
        Ok(Self { path, handle, identity })
    }

    fn create_child(&self, name: &std::ffi::OsStr) -> io::Result<Self> {
        self.verify()?;
        let path = self.path.join(name);
        let (handle, identity) = platform::create_directory_at(&self.handle, name, &path)?;
        Ok(Self { path, handle, identity })
    }

    fn bind_or_create_child(&self, name: &std::ffi::OsStr) -> io::Result<Self> {
        match self.bind_child(name) {
            Ok(child) => Ok(child),
            Err(error) if error.kind() == io::ErrorKind::NotFound => self.create_child(name),
            Err(error) => Err(error),
        }
    }

    fn bind_regular(&self, name: &std::ffi::OsStr) -> io::Result<(File, FileIdentity)> {
        self.verify()?;
        platform::bind_regular_at(&self.handle, name, &self.path.join(name))
    }

    fn hard_link(&self, source: &std::ffi::OsStr, target: &std::ffi::OsStr) -> io::Result<()> {
        self.verify()?;
        platform::hard_link_at(&self.handle, source, target, &self.path)
    }

    fn remove_file(&self, name: &std::ffi::OsStr) -> io::Result<()> {
        self.verify()?;
        platform::remove_file_at(&self.handle, name, &self.path)
    }

    fn sync(&self) -> Result<(), BottleMigrationError> {
        self.verify().map_err(|_| transaction_failed())?;
        platform::sync_directory(&self.handle).map_err(|_| transaction_failed())
    }
}

#[derive(Debug)]
struct PendingStoreRoot {
    ancestor: BoundDirectory,
    components: Vec<PendingStoreComponent>,
    root: PathBuf,
}

#[derive(Debug)]
struct PendingStoreComponent {
    name: std::ffi::OsString,
    existing_identity: Option<FileIdentity>,
}

#[derive(Debug)]
struct SelectedSource {
    parent_anchor: Option<(BoundDirectory, std::ffi::OsString)>,
    parent: BoundDirectory,
    name: std::ffi::OsString,
    path: PathBuf,
    root_handle: File,
    root_identity: FileIdentity,
}

impl SelectedSource {
    fn bind(source: &Path) -> Result<Self, BottleMigrationError> {
        let source_name = source.file_name().ok_or_else(unsafe_entry)?.to_owned();
        let source_parent = source
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        let canonical_parent = fs::canonicalize(source_parent).map_err(|_| unsafe_entry())?;
        let parent = BoundDirectory::bind(canonical_parent.clone()).map_err(|_| unsafe_entry())?;
        let parent_anchor = canonical_parent.file_name().and_then(|parent_name| {
            canonical_parent.parent().map(|grandparent| {
                BoundDirectory::bind(grandparent.to_path_buf())
                    .map(|bound| (bound, parent_name.to_owned()))
                    .map_err(|_| unsafe_entry())
            })
        });
        let parent_anchor = match parent_anchor {
            Some(anchor) => Some(anchor?),
            None => None,
        };
        let path = canonical_parent.join(&source_name);
        let (root_handle, root_identity) =
            platform::bind_directory_at(&parent.handle, &source_name, &path).map_err(|_| unsafe_entry())?;
        Ok(Self {
            parent_anchor,
            parent,
            name: source_name,
            path,
            root_handle,
            root_identity,
        })
    }

    fn verify(&self) -> Result<(), BottleMigrationError> {
        if let Some((anchor, parent_name)) = &self.parent_anchor {
            anchor.verify().map_err(|_| source_changed())?;
            let (parent, identity) = platform::bind_directory_at(&anchor.handle, parent_name, &self.parent.path)
                .map_err(|_| source_changed())?;
            if identity != self.parent.identity {
                return Err(source_changed());
            }
            drop(parent);
        }
        self.parent.verify().map_err(|_| source_changed())?;
        let (root, identity) =
            platform::bind_directory_at(&self.parent.handle, &self.name, &self.path).map_err(|_| source_changed())?;
        if identity != self.root_identity {
            return Err(source_changed());
        }
        platform::verify_directory(&self.root_handle, self.root_identity).map_err(|_| source_changed())?;
        drop(root);
        Ok(())
    }
}

impl PendingStoreRoot {
    fn bind(root: &Path) -> Result<Self, BottleMigrationError> {
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
                    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
                        return Err(unsafe_entry());
                    }
                    if existing == normalized {
                        let name = existing.file_name().ok_or_else(unsafe_entry)?.to_owned();
                        let parent_path = existing.parent().ok_or_else(unsafe_entry)?;
                        let resolved_parent = fs::canonicalize(parent_path).map_err(|_| unsafe_entry())?;
                        let ancestor = BoundDirectory::bind(resolved_parent.clone()).map_err(|_| unsafe_entry())?;
                        let child_path = resolved_parent.join(&name);
                        let (_, existing_identity) = platform::bind_directory_at(&ancestor.handle, &name, &child_path)
                            .map_err(|_| unsafe_entry())?;
                        return Ok(Self {
                            ancestor,
                            components: vec![PendingStoreComponent {
                                name,
                                existing_identity: Some(existing_identity),
                            }],
                            root: child_path,
                        });
                    }
                    let resolved = fs::canonicalize(&existing).map_err(|_| unsafe_entry())?;
                    let ancestor = BoundDirectory::bind(resolved.clone()).map_err(|_| unsafe_entry())?;
                    let mut bound_root = resolved;
                    for component in missing.iter().rev() {
                        bound_root.push(component);
                    }
                    return Ok(Self {
                        ancestor,
                        components: missing
                            .into_iter()
                            .rev()
                            .map(|name| PendingStoreComponent {
                                name,
                                existing_identity: None,
                            })
                            .collect(),
                        root: bound_root,
                    });
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    missing.push(existing.file_name().ok_or_else(unsafe_entry)?.to_owned());
                    if !existing.pop() {
                        return Err(unsafe_entry());
                    }
                }
                Err(_) => return Err(unsafe_entry()),
            }
        }
    }

    fn materialize(self) -> Result<StoreRootBinding, BottleMigrationError> {
        let mut chain = vec![self.ancestor];
        for component in self.components {
            let parent = chain.last().expect("a store chain has an ancestor");
            let child = if let Some(expected) = component.existing_identity {
                let child = parent.bind_child(&component.name).map_err(|_| unsafe_entry())?;
                if child.identity != expected {
                    return Err(unsafe_entry());
                }
                child
            } else {
                parent.create_child(&component.name).map_err(|_| unsafe_entry())?
            };
            chain.push(child);
        }
        if chain.last().expect("a store chain has a root").path != self.root {
            return Err(unsafe_entry());
        }
        Ok(StoreRootBinding { chain })
    }
}

#[derive(Debug)]
struct StoreRootBinding {
    chain: Vec<BoundDirectory>,
}

impl StoreRootBinding {
    fn root(&self) -> &BoundDirectory {
        self.chain.last().expect("a bound store has a root")
    }

    fn verify(&self) -> Result<(), BottleMigrationError> {
        for directory in &self.chain {
            directory.verify().map_err(|_| unsafe_entry())?;
        }
        for pair in self.chain.windows(2) {
            let parent = &pair[0];
            let child = &pair[1];
            let name = child.path.file_name().ok_or_else(unsafe_entry)?;
            let (handle, identity) =
                platform::bind_directory_at(&parent.handle, name, &child.path).map_err(|_| unsafe_entry())?;
            if identity != child.identity {
                return Err(unsafe_entry());
            }
            drop(handle);
        }
        Ok(())
    }
}

#[derive(Debug)]
struct SnapshotStoreBinding {
    root: StoreRootBinding,
    objects_parent: BoundDirectory,
    objects: BoundDirectory,
    snapshots_parent: Option<BoundDirectory>,
    snapshots: Option<BoundDirectory>,
}

impl SnapshotStoreBinding {
    fn materialize_objects(pending: PendingStoreRoot) -> Result<Self, BottleMigrationError> {
        let root = pending.materialize()?;
        root.verify()?;
        let objects_parent = root
            .root()
            .bind_or_create_child(std::ffi::OsStr::new("objects"))
            .map_err(|_| unsafe_entry())?;
        let objects = objects_parent
            .bind_or_create_child(std::ffi::OsStr::new("sha256"))
            .map_err(|_| unsafe_entry())?;
        let binding = Self {
            root,
            objects_parent,
            objects,
            snapshots_parent: None,
            snapshots: None,
        };
        binding.verify()?;
        Ok(binding)
    }

    fn bind_existing(path: &Path) -> Result<Self, BottleMigrationError> {
        let pending = PendingStoreRoot::bind(path).map_err(|_| snapshot_corrupt())?;
        if pending
            .components
            .iter()
            .any(|component| component.existing_identity.is_none())
        {
            return Err(snapshot_corrupt());
        }
        let root = pending.materialize().map_err(|_| snapshot_corrupt())?;
        let objects_parent = root
            .root()
            .bind_child(std::ffi::OsStr::new("objects"))
            .map_err(|_| snapshot_corrupt())?;
        let objects = objects_parent
            .bind_child(std::ffi::OsStr::new("sha256"))
            .map_err(|_| snapshot_corrupt())?;
        let snapshots_parent = root
            .root()
            .bind_child(std::ffi::OsStr::new("snapshots"))
            .map_err(|_| snapshot_corrupt())?;
        let snapshots = snapshots_parent
            .bind_child(std::ffi::OsStr::new("sha256"))
            .map_err(|_| snapshot_corrupt())?;
        Ok(Self {
            root,
            objects_parent,
            objects,
            snapshots_parent: Some(snapshots_parent),
            snapshots: Some(snapshots),
        })
    }

    fn materialize_snapshots(&mut self) -> Result<(), BottleMigrationError> {
        if self.snapshots.is_some() {
            return Ok(());
        }
        let snapshots_parent = self
            .root
            .root()
            .bind_or_create_child(std::ffi::OsStr::new("snapshots"))
            .map_err(|_| unsafe_entry())?;
        let snapshots = snapshots_parent
            .bind_or_create_child(std::ffi::OsStr::new("sha256"))
            .map_err(|_| unsafe_entry())?;
        self.snapshots_parent = Some(snapshots_parent);
        self.snapshots = Some(snapshots);
        self.verify()
    }

    fn snapshots(&self) -> Result<&BoundDirectory, BottleMigrationError> {
        self.snapshots.as_ref().ok_or_else(unsafe_entry)
    }

    fn verify(&self) -> Result<(), BottleMigrationError> {
        self.root.verify()?;
        verify_bound_child(self.root.root(), &self.objects_parent)?;
        verify_bound_child(&self.objects_parent, &self.objects)?;
        if let (Some(parent), Some(snapshots)) = (&self.snapshots_parent, &self.snapshots) {
            verify_bound_child(self.root.root(), parent)?;
            verify_bound_child(parent, snapshots)?;
        }
        Ok(())
    }
}

fn verify_bound_child(parent: &BoundDirectory, child: &BoundDirectory) -> Result<(), BottleMigrationError> {
    parent.verify().map_err(|_| unsafe_entry())?;
    child.verify().map_err(|_| unsafe_entry())?;
    let name = child.path.file_name().ok_or_else(unsafe_entry)?;
    let (handle, identity) =
        platform::bind_directory_at(&parent.handle, name, &child.path).map_err(|_| unsafe_entry())?;
    if identity != child.identity {
        return Err(unsafe_entry());
    }
    drop(handle);
    Ok(())
}

impl SourceEntry {
    fn path(&self) -> &str {
        match self {
            Self::File(file) => &file.relative_path,
            Self::Directory { relative_path, .. } | Self::Link { relative_path, .. } => relative_path,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SourceSignature {
    path: String,
    kind: SourceSignatureKind,
    identity: FileIdentity,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum SourceSignatureKind {
    File { size: u64, digest: String },
    Directory,
    Link(String),
}

impl From<&SourceEntry> for SourceSignature {
    fn from(entry: &SourceEntry) -> Self {
        match entry {
            SourceEntry::File(file) => Self {
                path: file.relative_path.clone(),
                kind: SourceSignatureKind::File {
                    size: file.size,
                    digest: file.preflight_digest.clone(),
                },
                identity: file.identity,
            },
            SourceEntry::Directory {
                relative_path,
                identity,
                ..
            } => Self {
                path: relative_path.clone(),
                kind: SourceSignatureKind::Directory,
                identity: *identity,
            },
            SourceEntry::Link {
                relative_path,
                target,
                identity,
                ..
            } => Self {
                path: relative_path.clone(),
                kind: SourceSignatureKind::Link(target.clone()),
                identity: *identity,
            },
        }
    }
}

impl BottleStore {
    #[must_use]
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn snapshot(&self, source: &Path) -> Result<SnapshotReceipt, BottleMigrationError> {
        let selected_source = SelectedSource::bind(source)?;
        let pending_store = PendingStoreRoot::bind(&self.root)?;
        run_snapshot_test_hook(SnapshotTestStage::AfterRootBind, "");
        selected_source.verify()?;
        let source_root = &selected_source.path;
        let store_root = &pending_store.root;
        if store_root == source_root || store_root.starts_with(source_root) || source_root.starts_with(store_root) {
            return Err(unsafe_entry());
        }

        let mut source_entries = Vec::new();
        let mut total_file_bytes = 0_u64;
        collect_source_entries(
            source_root,
            source_root,
            &selected_source.root_handle,
            &mut source_entries,
            &mut total_file_bytes,
        )?;
        source_entries.sort_by(|left, right| left.path().cmp(right.path()));
        validate_source_graph(&source_entries)?;
        let source_signatures = source_entries.iter().map(SourceSignature::from).collect::<Vec<_>>();
        run_snapshot_test_hook(SnapshotTestStage::AfterSourcePreflight, "");
        selected_source.verify()?;

        let manifest_source = source_entries
            .iter_mut()
            .find_map(|entry| match entry {
                SourceEntry::File(file) if file.relative_path == "manifest.json" => Some(file),
                _ => None,
            })
            .ok_or_else(invalid_manifest)?;
        if manifest_source.size > u64::try_from(MAX_MANIFEST_BYTES).expect("manifest bound fits u64") {
            return Err(invalid_manifest());
        }
        let manifest_bytes =
            read_bounded_file(&mut manifest_source.file, MAX_MANIFEST_BYTES).map_err(|_| invalid_manifest())?;
        manifest_source.file.rewind().map_err(|_| source_changed())?;
        let manifest_json = std::str::from_utf8(&manifest_bytes).map_err(|_| invalid_manifest())?;
        let legacy_manifest = LegacyBottleManifest::from_json(manifest_json)?;
        validate_id("legacyBottle.id", &legacy_manifest.id).map_err(|_| invalid_manifest())?;
        let mut store = SnapshotStoreBinding::materialize_objects(pending_store)?;

        let mut snapshot_entries = Vec::with_capacity(source_entries.len());
        for source_entry in &mut source_entries {
            match source_entry {
                SourceEntry::Directory { relative_path, .. } => snapshot_entries.push(SnapshotEntry::Directory {
                    path: relative_path.clone(),
                }),
                SourceEntry::Link {
                    relative_path, target, ..
                } => snapshot_entries.push(SnapshotEntry::Link {
                    path: relative_path.clone(),
                    target: target.clone(),
                }),
                SourceEntry::File(file) => {
                    let digest = self.publish_object(file, &store.objects)?;
                    snapshot_entries.push(SnapshotEntry::File {
                        path: file.relative_path.clone(),
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
        run_snapshot_test_hook(SnapshotTestStage::BeforeSourceRevalidation, "");
        verify_source_tree(&selected_source, &source_signatures, total_file_bytes)?;
        run_snapshot_test_hook(SnapshotTestStage::AfterSourceRevalidation, "");
        verify_source_tree(&selected_source, &source_signatures, total_file_bytes)?;
        self.verify_legacy_manifest_object_at(&snapshot, &store.objects)
            .map_err(|_| source_changed())?;

        let published_size = measure_snapshot_json(&snapshot, snapshot_manifest_limit()).map_err(|_| unsafe_entry())?;
        run_snapshot_test_hook(SnapshotTestStage::AfterSnapshotManifestMeasurement, "");
        checked_snapshot_manifest_size(published_size).map_err(|_| unsafe_entry())?;
        let snapshot_digest = digest_snapshot_json(&snapshot).map_err(|_| transaction_failed())?;
        verify_source_tree(&selected_source, &source_signatures, total_file_bytes)?;
        store.materialize_snapshots()?;
        store.verify()?;
        let publication = self.publish_snapshot(&snapshot_digest, &snapshot, store.snapshots()?)?;
        let post_publication = (|| {
            run_snapshot_test_hook(SnapshotTestStage::AfterSnapshotPublish, "");
            verify_source_tree(&selected_source, &source_signatures, total_file_bytes)?;
            store.verify()?;
            self.verify_snapshot_at(&snapshot_digest, store.snapshots()?, &store.objects)?;
            store.verify()?;
            run_snapshot_test_hook(SnapshotTestStage::BeforeSnapshotReturn, "");
            verify_source_tree(&selected_source, &source_signatures, total_file_bytes)?;
            store.verify()?;
            self.verify_snapshot_at(&snapshot_digest, store.snapshots()?, &store.objects)?;
            store.verify()?;
            Ok(())
        })();
        if let Err(error) = post_publication {
            self.rollback_snapshot(publication, &snapshot, store.snapshots()?)?;
            return Err(error);
        }

        Ok(SnapshotReceipt {
            bottle_id: snapshot.bottle_id,
            snapshot_digest,
            entry_count: snapshot.entry_count,
            total_file_bytes: snapshot.total_file_bytes,
        })
    }

    pub fn verify_snapshot(&self, digest: &str) -> Result<BottleSnapshot, BottleMigrationError> {
        let store = SnapshotStoreBinding::bind_existing(&self.root)?;
        store.verify().map_err(|_| snapshot_corrupt())?;
        self.verify_snapshot_at(
            digest,
            store.snapshots().map_err(|_| snapshot_corrupt())?,
            &store.objects,
        )
    }

    fn verify_snapshot_at(
        &self,
        digest: &str,
        snapshot_directory: &BoundDirectory,
        object_directory: &BoundDirectory,
    ) -> Result<BottleSnapshot, BottleMigrationError> {
        let digest_hex = digest_hex(digest).ok_or_else(snapshot_corrupt)?;
        let name = std::ffi::OsString::from(format!("{digest_hex}.json"));
        let (mut file, identity) = snapshot_directory.bind_regular(&name).map_err(|_| snapshot_corrupt())?;
        if file.metadata().map_err(|_| snapshot_corrupt())?.len()
            > u64::try_from(MAX_SNAPSHOT_MANIFEST_BYTES).expect("manifest bound fits u64")
        {
            return Err(snapshot_corrupt());
        }
        let bytes = read_bounded_file(&mut file, MAX_SNAPSHOT_MANIFEST_BYTES).map_err(|_| snapshot_corrupt())?;
        platform::verify_regular(&file, identity).map_err(|_| snapshot_corrupt())?;
        let snapshot: BottleSnapshot = serde_json::from_slice(&bytes).map_err(|_| snapshot_corrupt())?;
        snapshot.validate()?;

        if digest_snapshot_json(&snapshot).map_err(|_| snapshot_corrupt())? != digest {
            return Err(snapshot_corrupt());
        }
        if !snapshot_json_matches(&snapshot, &bytes).map_err(|_| snapshot_corrupt())? {
            return Err(snapshot_corrupt());
        }

        for entry in &snapshot.entries {
            if let SnapshotEntry::File { size, digest, .. } = entry {
                self.verify_object_at(object_directory, digest, *size)?;
            }
        }
        self.verify_legacy_manifest_object_at(&snapshot, object_directory)?;
        Ok(snapshot)
    }

    fn publish_object(
        &self,
        source: &mut SourceFile,
        object_directory: &BoundDirectory,
    ) -> Result<String, BottleMigrationError> {
        let mut temporary =
            OwnedTemporaryPath::new_bound(object_directory, temporary_path(&object_directory.path, "object"))
                .map_err(|_| transaction_failed())?;
        (|| {
            platform::verify_regular(&source.file, source.identity).map_err(|_| source_changed())?;
            let mut output = temporary.create_new().map_err(|_| transaction_failed())?;
            let (digest, copied) = copy_and_digest(&mut source.file, &mut output).map_err(|_| source_changed())?;
            if copied != source.size || copied > MAX_FILE_BYTES || digest != source.preflight_digest {
                return Err(source_changed());
            }
            run_snapshot_test_hook(SnapshotTestStage::AfterFileCopy, &source.relative_path);
            source.file.rewind().map_err(|_| source_changed())?;
            let (readback_digest, readback_size) = digest_reader(&mut source.file).map_err(|_| source_changed())?;
            if readback_digest != digest || readback_size != copied {
                return Err(source_changed());
            }
            platform::verify_regular(&source.file, source.identity).map_err(|_| source_changed())?;
            output.sync_all().map_err(|_| transaction_failed())?;
            drop(output);
            let digest_hex = digest_hex(&digest).ok_or_else(transaction_failed)?;
            let target_name = std::ffi::OsStr::new(digest_hex);
            match object_directory.bind_regular(target_name) {
                Ok((file, identity)) => {
                    self.verify_object_handle(file, identity, &digest, copied)?;
                    temporary.remove().map_err(|_| transaction_failed())?;
                    return Ok(digest);
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(_) => return Err(snapshot_corrupt()),
            }
            run_snapshot_test_hook(SnapshotTestStage::BeforeObjectPublish, &source.relative_path);
            let temporary_name = temporary.name.as_deref().ok_or_else(transaction_failed)?;
            match object_directory.hard_link(temporary_name, target_name) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                    self.verify_object_at(object_directory, &digest, copied)?;
                    temporary.remove().map_err(|_| transaction_failed())?;
                    return Ok(digest);
                }
                Err(_) => return Err(transaction_failed()),
            }
            temporary.remove().map_err(|_| transaction_failed())?;
            object_directory.sync()?;
            self.verify_object_at(object_directory, &digest, copied)?;
            Ok(digest)
        })()
    }

    fn verify_object_at(
        &self,
        directory: &BoundDirectory,
        digest: &str,
        size: u64,
    ) -> Result<(), BottleMigrationError> {
        let digest_hex = digest_hex(digest).ok_or_else(snapshot_corrupt)?;
        let (file, identity) = directory
            .bind_regular(std::ffi::OsStr::new(digest_hex))
            .map_err(|_| snapshot_corrupt())?;
        self.verify_object_handle(file, identity, digest, size)
    }

    fn verify_object_handle(
        &self,
        mut file: File,
        identity: FileIdentity,
        digest: &str,
        size: u64,
    ) -> Result<(), BottleMigrationError> {
        if file.metadata().map_err(|_| snapshot_corrupt())?.len() != size {
            return Err(snapshot_corrupt());
        }
        let (actual, actual_size) = digest_reader(&mut file).map_err(|_| snapshot_corrupt())?;
        if actual != digest || actual_size != size || platform::verify_regular(&file, identity).is_err() {
            return Err(snapshot_corrupt());
        }
        Ok(())
    }

    fn publish_snapshot(
        &self,
        digest: &str,
        snapshot: &BottleSnapshot,
        directory: &BoundDirectory,
    ) -> Result<SnapshotPublication, BottleMigrationError> {
        let digest_hex = digest_hex(digest).ok_or_else(transaction_failed)?;
        let target_name = std::ffi::OsString::from(format!("{digest_hex}.json"));
        match directory.bind_regular(&target_name) {
            Ok((file, identity)) => {
                compare_existing_snapshot_model_handle(file, identity, snapshot)?;
                return Ok(SnapshotPublication {
                    target_name,
                    created: false,
                    identity: None,
                });
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(_) => return Err(snapshot_corrupt()),
        }

        let mut temporary = OwnedTemporaryPath::new_bound(directory, temporary_path(&directory.path, "snapshot"))
            .map_err(|_| transaction_failed())?;
        (|| {
            let mut file = temporary.create_new().map_err(|_| transaction_failed())?;
            render_snapshot_json(snapshot, true, &mut file).map_err(|_| transaction_failed())?;
            file.write_all(b"\n").map_err(|_| transaction_failed())?;
            file.sync_all().map_err(|_| transaction_failed())?;
            drop(file);
            let temporary_name = temporary.name.as_deref().ok_or_else(transaction_failed)?;
            let (owned_handle, owned_identity) = directory
                .bind_regular(temporary_name)
                .map_err(|_| transaction_failed())?;
            run_snapshot_test_hook(SnapshotTestStage::BeforeSnapshotPublish, "");
            match directory.hard_link(temporary_name, &target_name) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                    let (file, identity) = directory.bind_regular(&target_name).map_err(|_| snapshot_corrupt())?;
                    compare_existing_snapshot_model_handle(file, identity, snapshot)?;
                    drop(owned_handle);
                    temporary.remove().map_err(|_| transaction_failed())?;
                    return Ok(SnapshotPublication {
                        target_name,
                        created: false,
                        identity: None,
                    });
                }
                Err(_) => return Err(transaction_failed()),
            }
            drop(owned_handle);
            temporary.remove().map_err(|_| transaction_failed())?;
            directory.sync()?;
            Ok(SnapshotPublication {
                target_name,
                created: true,
                identity: Some(owned_identity),
            })
        })()
    }

    fn rollback_snapshot(
        &self,
        publication: SnapshotPublication,
        snapshot: &BottleSnapshot,
        directory: &BoundDirectory,
    ) -> Result<(), BottleMigrationError> {
        if !publication.created {
            return Ok(());
        }
        let expected_identity = publication.identity.ok_or_else(snapshot_corrupt)?;
        let (mut target, actual_identity) = match directory.bind_regular(&publication.target_name) {
            Ok(bound) => bound,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
            Err(_) => return Err(snapshot_corrupt()),
        };
        if actual_identity != expected_identity {
            return Ok(());
        }
        let bytes = read_bounded_file(&mut target, MAX_SNAPSHOT_MANIFEST_BYTES).map_err(|_| snapshot_corrupt())?;
        platform::verify_regular(&target, expected_identity).map_err(|_| snapshot_corrupt())?;
        if !snapshot_json_matches(snapshot, &bytes).map_err(|_| snapshot_corrupt())? {
            return Err(snapshot_corrupt());
        }
        drop(target);
        directory
            .remove_file(&publication.target_name)
            .map_err(|_| snapshot_corrupt())?;
        directory.sync()
    }

    fn verify_legacy_manifest_object_at(
        &self,
        snapshot: &BottleSnapshot,
        object_directory: &BoundDirectory,
    ) -> Result<(), BottleMigrationError> {
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
        let (mut file, identity) = object_directory
            .bind_regular(std::ffi::OsStr::new(digest_hex))
            .map_err(|_| snapshot_corrupt())?;
        let bytes = read_bounded_file(&mut file, MAX_MANIFEST_BYTES).map_err(|_| snapshot_corrupt())?;
        platform::verify_regular(&file, identity).map_err(|_| snapshot_corrupt())?;
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
            } else if let SnapshotEntry::Link { target, .. } = entry {
                validate_basic_path(target).map_err(|_| snapshot_corrupt())?;
            }
        }
        if total != self.total_file_bytes {
            return Err(snapshot_corrupt());
        }
        path::validate_graph(self.entries.iter().map(|entry| match entry {
            SnapshotEntry::File { path, .. } => (path.as_str(), EntryKind::File),
            SnapshotEntry::Directory { path } => (path.as_str(), EntryKind::Directory),
            SnapshotEntry::Link { path, target } => (path.as_str(), EntryKind::Link(target)),
        }))
        .map_err(|_| snapshot_corrupt())?;
        Ok(())
    }
}

fn collect_source_entries(
    root: &Path,
    directory: &Path,
    directory_handle: &File,
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
            let (handle, identity, raw_target) =
                platform::bind_link_at(directory_handle, &child.file_name(), &path).map_err(|_| unsafe_entry())?;
            let target = path::normalize_link_target(&relative_path, &raw_target).map_err(|_| unsafe_entry())?;
            push_entry(
                entries,
                SourceEntry::Link {
                    relative_path,
                    target,
                    identity,
                    _handle: handle,
                },
            )?;
            continue;
        }
        if file_type.is_dir() {
            let (handle, identity) =
                platform::bind_directory_at(directory_handle, &child.file_name(), &path).map_err(|_| unsafe_entry())?;
            collect_source_entries(root, &path, &handle, entries, total_file_bytes)?;
            push_entry(
                entries,
                SourceEntry::Directory {
                    relative_path,
                    identity,
                    _handle: handle,
                },
            )?;
        } else if file_type.is_file() {
            let size = metadata.len();
            checked_regular_file_size(size, total_file_bytes)?;
            let (mut file, identity) =
                platform::bind_regular_at(directory_handle, &child.file_name(), &path).map_err(|_| unsafe_entry())?;
            let (preflight_digest, preflight_size) = digest_reader(&mut file).map_err(|_| source_changed())?;
            if preflight_size != size {
                return Err(source_changed());
            }
            file.rewind().map_err(|_| source_changed())?;
            platform::verify_regular(&file, identity).map_err(|_| source_changed())?;
            push_entry(
                entries,
                SourceEntry::File(SourceFile {
                    relative_path,
                    size,
                    identity,
                    file,
                    preflight_digest,
                }),
            )?;
        } else {
            return Err(unsafe_entry());
        }
    }
    Ok(())
}

fn validate_source_graph(entries: &[SourceEntry]) -> Result<(), BottleMigrationError> {
    path::validate_graph(entries.iter().map(|entry| match entry {
        SourceEntry::File(file) => (file.relative_path.as_str(), EntryKind::File),
        SourceEntry::Directory { relative_path, .. } => (relative_path.as_str(), EntryKind::Directory),
        SourceEntry::Link {
            relative_path, target, ..
        } => (relative_path.as_str(), EntryKind::Link(target)),
    }))
    .map_err(|_| unsafe_entry())
}

fn verify_source_tree(
    selected: &SelectedSource,
    expected_entries: &[SourceSignature],
    expected_total: u64,
) -> Result<(), BottleMigrationError> {
    selected.verify()?;
    let mut entries = Vec::new();
    let mut total = 0;
    collect_source_entries(
        &selected.path,
        &selected.path,
        &selected.root_handle,
        &mut entries,
        &mut total,
    )
    .map_err(|_| source_changed())?;
    entries.sort_by(|left, right| left.path().cmp(right.path()));
    validate_source_graph(&entries).map_err(|_| source_changed())?;
    let actual = entries.iter().map(SourceSignature::from).collect::<Vec<_>>();
    if actual != expected_entries || total != expected_total {
        return Err(source_changed());
    }
    selected.verify()?;
    Ok(())
}

struct BoundedCounter {
    length: usize,
    maximum: usize,
}

impl Write for BoundedCounter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let next = self
            .length
            .checked_add(bytes.len())
            .ok_or_else(|| io::Error::other("snapshot length overflow"))?;
        if next > self.maximum {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "snapshot manifest exceeds its size bound",
            ));
        }
        self.length = next;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

struct DigestWriter(Sha256);

impl Write for DigestWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0.update(bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

struct SliceComparisonWriter<'a> {
    expected: &'a [u8],
    offset: usize,
    matches: bool,
}

impl Write for SliceComparisonWriter<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let end = self.offset.saturating_add(bytes.len());
        if self.expected.get(self.offset..end) != Some(bytes) {
            self.matches = false;
        }
        self.offset = end;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn snapshot_manifest_limit() -> usize {
    #[cfg(test)]
    let maximum = SNAPSHOT_MANIFEST_LIMIT_OVERRIDE
        .with(|snapshot_manifest_limit| snapshot_manifest_limit.get().unwrap_or(MAX_SNAPSHOT_MANIFEST_BYTES));
    #[cfg(not(test))]
    let maximum = MAX_SNAPSHOT_MANIFEST_BYTES;
    maximum
}

fn measure_snapshot_json(snapshot: &BottleSnapshot, maximum: usize) -> io::Result<usize> {
    let mut counter = BoundedCounter { length: 0, maximum };
    render_snapshot_json(snapshot, true, &mut counter)?;
    counter.write_all(b"\n")?;
    Ok(counter.length)
}

fn digest_snapshot_json(snapshot: &BottleSnapshot) -> io::Result<String> {
    let mut output = DigestWriter(Sha256::new());
    render_snapshot_json(snapshot, false, &mut output)?;
    let mut digest = String::with_capacity(71);
    digest.push_str("sha256:");
    for byte in output.0.finalize() {
        write!(&mut digest, "{byte:02x}").expect("writing to a string cannot fail");
    }
    Ok(digest)
}

fn snapshot_json_matches(snapshot: &BottleSnapshot, expected: &[u8]) -> io::Result<bool> {
    let mut output = SliceComparisonWriter {
        expected,
        offset: 0,
        matches: true,
    };
    render_snapshot_json(snapshot, true, &mut output)?;
    output.write_all(b"\n")?;
    Ok(output.matches && output.offset == expected.len())
}

fn render_snapshot_json(snapshot: &BottleSnapshot, pretty: bool, output: &mut impl Write) -> io::Result<()> {
    output.write_all(b"{")?;
    write_member_prefix(output, "bottleId", 0, 1, pretty)?;
    write_json_string(output, &snapshot.bottle_id)?;
    write_member_prefix(output, "entries", 1, 1, pretty)?;
    output.write_all(b"[")?;
    for (index, entry) in snapshot.entries.iter().enumerate() {
        if index == 0 {
            if pretty {
                output.write_all(b"\n")?;
            }
        } else if pretty {
            output.write_all(b",\n")?;
        } else {
            output.write_all(b",")?;
        }
        write_indent(output, 2, pretty)?;
        render_snapshot_entry(entry, pretty, output)?;
    }
    if !snapshot.entries.is_empty() {
        if pretty {
            output.write_all(b"\n")?;
        }
        write_indent(output, 1, pretty)?;
    }
    output.write_all(b"]")?;
    write_member_prefix(output, "entryCount", 2, 1, pretty)?;
    write!(output, "{}", snapshot.entry_count)?;
    write_member_prefix(output, "legacyFormat", 3, 1, pretty)?;
    write_json_string(output, &snapshot.legacy_format)?;
    write_member_prefix(output, "schemaVersion", 4, 1, pretty)?;
    write_json_string(output, &snapshot.schema_version)?;
    write_member_prefix(output, "totalFileBytes", 5, 1, pretty)?;
    write!(output, "{}", snapshot.total_file_bytes)?;
    if pretty {
        output.write_all(b"\n")?;
    }
    output.write_all(b"}")
}

fn render_snapshot_entry(entry: &SnapshotEntry, pretty: bool, output: &mut impl Write) -> io::Result<()> {
    output.write_all(b"{")?;
    match entry {
        SnapshotEntry::File { path, size, digest } => {
            write_member_prefix(output, "digest", 0, 3, pretty)?;
            write_json_string(output, digest)?;
            write_member_prefix(output, "kind", 1, 3, pretty)?;
            write_json_string(output, "file")?;
            write_member_prefix(output, "path", 2, 3, pretty)?;
            write_json_string(output, path)?;
            write_member_prefix(output, "size", 3, 3, pretty)?;
            write!(output, "{size}")?;
        }
        SnapshotEntry::Directory { path } => {
            write_member_prefix(output, "kind", 0, 3, pretty)?;
            write_json_string(output, "directory")?;
            write_member_prefix(output, "path", 1, 3, pretty)?;
            write_json_string(output, path)?;
        }
        SnapshotEntry::Link { path, target } => {
            write_member_prefix(output, "kind", 0, 3, pretty)?;
            write_json_string(output, "link")?;
            write_member_prefix(output, "path", 1, 3, pretty)?;
            write_json_string(output, path)?;
            write_member_prefix(output, "target", 2, 3, pretty)?;
            write_json_string(output, target)?;
        }
    }
    if pretty {
        output.write_all(b"\n")?;
    }
    write_indent(output, 2, pretty)?;
    output.write_all(b"}")
}

fn write_member_prefix(output: &mut impl Write, key: &str, index: usize, depth: usize, pretty: bool) -> io::Result<()> {
    if index == 0 {
        if pretty {
            output.write_all(b"\n")?;
        }
    } else if pretty {
        output.write_all(b",\n")?;
    } else {
        output.write_all(b",")?;
    }
    write_indent(output, depth, pretty)?;
    write_json_string(output, key)?;
    if pretty {
        output.write_all(b": ")
    } else {
        output.write_all(b":")
    }
}

fn write_indent(output: &mut impl Write, depth: usize, pretty: bool) -> io::Result<()> {
    if pretty {
        for _ in 0..depth {
            output.write_all(b"  ")?;
        }
    }
    Ok(())
}

fn write_json_string(output: &mut impl Write, value: &str) -> io::Result<()> {
    serde_json::to_writer(output, value).map_err(io::Error::other)
}

fn compare_existing_snapshot_model_handle(
    mut file: File,
    identity: FileIdentity,
    snapshot: &BottleSnapshot,
) -> Result<(), BottleMigrationError> {
    let expected_size = measure_snapshot_json(snapshot, MAX_SNAPSHOT_MANIFEST_BYTES).map_err(|_| snapshot_corrupt())?;
    let bytes = read_bounded_file(&mut file, MAX_SNAPSHOT_MANIFEST_BYTES).map_err(|_| snapshot_corrupt())?;
    platform::verify_regular(&file, identity).map_err(|_| snapshot_corrupt())?;
    if bytes.len() != expected_size || !snapshot_json_matches(snapshot, &bytes).map_err(|_| snapshot_corrupt())? {
        return Err(snapshot_corrupt());
    }
    Ok(())
}

#[cfg(test)]
fn compare_existing_snapshot(path: &Path, expected: &[u8]) -> Result<(), BottleMigrationError> {
    if expected.len() > MAX_SNAPSHOT_MANIFEST_BYTES {
        return Err(snapshot_corrupt());
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| snapshot_corrupt())?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() != u64::try_from(expected.len()).expect("an in-memory length fits u64")
    {
        return Err(snapshot_corrupt());
    }

    let mut file = File::open(path).map_err(|_| snapshot_corrupt())?;
    let mut buffer = [0_u8; STREAM_BUFFER_BYTES];
    let mut offset = 0_usize;
    loop {
        let read = file.read(&mut buffer).map_err(|_| snapshot_corrupt())?;
        if read == 0 {
            return if offset == expected.len() {
                Ok(())
            } else {
                Err(snapshot_corrupt())
            };
        }
        #[cfg(test)]
        SNAPSHOT_COMPARISON_BYTES_READ.set(SNAPSHOT_COMPARISON_BYTES_READ.get().saturating_add(read));
        let end = offset.checked_add(read).ok_or_else(snapshot_corrupt)?;
        if expected.get(offset..end) != Some(&buffer[..read]) {
            return Err(snapshot_corrupt());
        }
        offset = end;
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
    checked_entry_count(entries.len())?;
    entries.push(entry);
    Ok(())
}

fn checked_entry_count(current: usize) -> Result<(), BottleMigrationError> {
    if current >= MAX_ENTRIES {
        Err(unsafe_entry())
    } else {
        Ok(())
    }
}

fn checked_snapshot_manifest_size(size: usize) -> Result<(), BottleMigrationError> {
    if size > snapshot_manifest_limit() {
        Err(unsafe_entry())
    } else {
        Ok(())
    }
}

fn portable_relative_path(root: &Path, path: &Path) -> Result<String, BottleMigrationError> {
    let relative = path.strip_prefix(root).map_err(|_| unsafe_entry())?;
    let mut components = Vec::new();
    for component in relative.components() {
        let value = component.as_os_str().to_str().ok_or_else(unsafe_entry)?;
        if path::validate_component(value).is_err() {
            return Err(unsafe_entry());
        }
        components.push(value);
    }
    let value = components.join("/");
    validate_basic_path(&value)?;
    Ok(value)
}

fn validate_basic_path(value: &str) -> Result<(), BottleMigrationError> {
    path::validate_relative_path(value).map_err(|_| unsafe_entry())
}

fn read_bounded_file(file: &mut File, maximum: usize) -> io::Result<Vec<u8>> {
    let metadata = file.metadata()?;
    if !metadata.file_type().is_file() || metadata.len() > u64::try_from(maximum).expect("read bound fits u64") {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "bounded file rejected"));
    }
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(maximum));
    Read::by_ref(file)
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
    #[cfg(test)]
    if let Some(path) = TEMPORARY_PATH_OVERRIDE.with(|slot| {
        let matches = slot
            .borrow()
            .as_ref()
            .is_some_and(|(expected_label, _)| expected_label == label);
        matches.then(|| slot.borrow_mut().take().expect("a matching override exists").1)
    }) {
        return path;
    }
    let counter = TEMPORARY_FILE_COUNTER.fetch_add(1, Ordering::Relaxed);
    directory.join(format!(".{label}.tmp-{}-{counter}", std::process::id()))
}

#[cfg(test)]
fn run_snapshot_test_hook(stage: SnapshotTestStage, path: &str) {
    let hook = SNAPSHOT_STAGE_HOOK.with(|slot| {
        let matches = slot
            .borrow()
            .as_ref()
            .is_some_and(|candidate| candidate.stage == stage && candidate.path == path);
        matches.then(|| slot.borrow_mut().take().expect("a matching snapshot hook exists").hook)
    });
    if let Some(hook) = hook {
        hook();
    }
}

#[cfg(not(test))]
fn run_snapshot_test_hook(_stage: SnapshotTestStage, _path: &str) {}

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
    use std::io::Write as _;
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

    fn override_next_temporary_path(label: &str, path: &Path) {
        super::TEMPORARY_PATH_OVERRIDE.with(|slot| {
            assert!(slot.replace(Some((label.to_owned(), path.to_path_buf()))).is_none());
        });
    }

    fn reset_snapshot_comparison_probe() {
        super::SNAPSHOT_COMPARISON_BYTES_READ.set(0);
    }

    fn snapshot_comparison_bytes_read() -> usize {
        super::SNAPSHOT_COMPARISON_BYTES_READ.get()
    }

    #[cfg(windows)]
    fn process_handle_count() -> u32 {
        #[link(name = "Kernel32")]
        extern "system" {
            #[link_name = "GetCurrentProcess"]
            fn get_current_process() -> *mut core::ffi::c_void;
            #[link_name = "GetProcessHandleCount"]
            fn get_process_handle_count(process: *mut core::ffi::c_void, count: *mut u32) -> i32;
        }

        let mut count = 0_u32;
        // SAFETY: the pseudo-handle returned by `GetCurrentProcess` is always
        // valid in this process and `count` is a live output location.
        let succeeded = unsafe { get_process_handle_count(get_current_process(), std::ptr::addr_of_mut!(count)) };
        assert_ne!(succeeded, 0);
        count
    }

    #[cfg(target_os = "linux")]
    fn process_file_descriptor_count() -> usize {
        fs::read_dir("/proc/self/fd").unwrap().count()
    }

    fn set_snapshot_hook(stage: super::SnapshotTestStage, path: &str, hook: impl FnOnce() + 'static) {
        super::SNAPSHOT_STAGE_HOOK.with(|slot| {
            assert!(slot
                .replace(Some(super::SnapshotTestHook {
                    stage,
                    path: path.into(),
                    hook: Box::new(hook),
                }))
                .is_none());
        });
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
            b"tampered bytes\n",
        )
        .unwrap();

        let error = bottle_store.verify_snapshot(SNAPSHOT_DIGEST).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(error.to_string(), "Bottle snapshot is corrupt");
    }

    #[test]
    fn object_temp_collision_preserves_the_unowned_sentinel() {
        let temporary = TemporaryDirectory::new("object-temp-collision");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let object_directory = store.join("objects/sha256");
        fs::create_dir_all(&object_directory).unwrap();
        let sentinel = super::temporary_path(&object_directory, "object");
        fs::write(&sentinel, b"foreign object sentinel").unwrap();
        override_next_temporary_path("object", &sentinel);

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::TransactionFailed);
        assert_eq!(fs::read(&sentinel).unwrap(), b"foreign object sentinel");
        assert!(!store.join("snapshots").exists());
    }

    #[test]
    fn snapshot_temp_collision_preserves_the_unowned_sentinel() {
        let temporary = TemporaryDirectory::new("snapshot-temp-collision");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let snapshot_directory = store.join("snapshots/sha256");
        fs::create_dir_all(&snapshot_directory).unwrap();
        let sentinel = super::temporary_path(&snapshot_directory, "snapshot");
        fs::write(&sentinel, b"foreign snapshot sentinel").unwrap();
        override_next_temporary_path("snapshot", &sentinel);

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::TransactionFailed);
        assert_eq!(fs::read(&sentinel).unwrap(), b"foreign snapshot sentinel");
        assert_eq!(
            fs::read_dir(&snapshot_directory).unwrap().count(),
            1,
            "no snapshot manifest may publish after the collision"
        );
    }

    #[test]
    fn owned_temp_guard_cleans_error_and_unwind_paths() {
        let temporary = TemporaryDirectory::new("owned-temp-cleanup");
        let error_path = temporary.path().join("error.tmp");
        {
            let mut guard = super::OwnedTemporaryPath::new(&error_path);
            let mut file = guard.create_new().unwrap();
            file.write_all(b"partial").unwrap();
        }
        assert!(!error_path.exists());

        let unwind_path = temporary.path().join("unwind.tmp");
        let result = std::panic::catch_unwind(|| {
            let mut guard = super::OwnedTemporaryPath::new(&unwind_path);
            let mut file = guard.create_new().unwrap();
            file.write_all(b"partial").unwrap();
            panic!("controlled unwind");
        });
        assert!(result.is_err());
        assert!(!unwind_path.exists());
    }

    #[test]
    fn disarmed_temp_guard_never_deletes_a_replacement() {
        let temporary = TemporaryDirectory::new("owned-temp-disarm");
        let temporary_path = temporary.path().join("owned.tmp");
        let published_path = temporary.path().join("published");
        let mut guard = super::OwnedTemporaryPath::new(&temporary_path);
        let mut file = guard.create_new().unwrap();
        file.write_all(b"published").unwrap();
        drop(file);
        fs::rename(&temporary_path, &published_path).unwrap();
        guard.disarm();
        fs::write(&temporary_path, b"foreign replacement").unwrap();
        drop(guard);

        assert_eq!(fs::read(&published_path).unwrap(), b"published");
        assert_eq!(fs::read(&temporary_path).unwrap(), b"foreign replacement");
    }

    #[test]
    fn existing_snapshot_comparison_rejects_oversize_and_nonregular_without_reading() {
        let temporary = TemporaryDirectory::new("snapshot-compare-preflight");
        let oversized = temporary.path().join("oversized.json");
        fs::File::create(&oversized)
            .unwrap()
            .set_len(u64::try_from(super::MAX_SNAPSHOT_MANIFEST_BYTES).unwrap() + 1)
            .unwrap();
        reset_snapshot_comparison_probe();
        let error = super::compare_existing_snapshot(&oversized, b"expected\n").unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(snapshot_comparison_bytes_read(), 0);

        let directory = temporary.path().join("directory.json");
        fs::create_dir(&directory).unwrap();
        reset_snapshot_comparison_probe();
        let error = super::compare_existing_snapshot(&directory, b"expected\n").unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(snapshot_comparison_bytes_read(), 0);
    }

    #[test]
    fn existing_snapshot_comparison_streams_exact_bytes_and_rejects_wrong_bytes() {
        const EXPECTED: &[u8] = b"canonical\n";
        let temporary = TemporaryDirectory::new("snapshot-compare-content");
        let target = temporary.path().join("snapshot.json");

        fs::write(&target, b"wrongbyte\n").unwrap();
        reset_snapshot_comparison_probe();
        let error = super::compare_existing_snapshot(&target, EXPECTED).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(snapshot_comparison_bytes_read(), EXPECTED.len());

        fs::write(&target, b"small").unwrap();
        reset_snapshot_comparison_probe();
        let error = super::compare_existing_snapshot(&target, EXPECTED).unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(snapshot_comparison_bytes_read(), 0);

        fs::write(&target, EXPECTED).unwrap();
        reset_snapshot_comparison_probe();
        super::compare_existing_snapshot(&target, EXPECTED).unwrap();
        assert_eq!(snapshot_comparison_bytes_read(), EXPECTED.len());
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

    #[cfg(windows)]
    #[test]
    fn snapshot_security_rejects_casefolded_store_overlap_before_writing() {
        let temporary = TemporaryDirectory::new("snapshot-casefold-overlap");
        let source = create_regular_source(temporary.path());
        let folded_source = temporary.path().join("SOURCE");
        let store = folded_source.join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert!(!source.join("store").exists());
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

    #[test]
    fn snapshot_security_accepts_a_safe_internal_link_contract() {
        let json = br#"{
            "schemaVersion":"1",
            "legacyFormat":"macwin-bottle-v1",
            "bottleId":"bottle-1",
            "entries":[
                {"kind":"file","path":"manifest.json","size":0,"digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000"},
                {"kind":"link","path":"payload-link","target":"manifest.json"}
            ],
            "entryCount":2,
            "totalFileBytes":0
        }"#;

        let parsed = serde_json::from_slice::<BottleSnapshot>(json);

        assert!(
            parsed.is_ok(),
            "safe internal links must be part of the closed snapshot contract"
        );
        parsed.unwrap().validate().unwrap();
    }

    #[test]
    fn snapshot_security_rejects_a_leaf_replaced_after_preflight() {
        let temporary = TemporaryDirectory::new("snapshot-leaf-replacement");
        let source_root = temporary.path().join("source");
        fs::create_dir(&source_root).unwrap();
        let source_path = source_root.join("payload.txt");
        fs::write(&source_path, b"original").unwrap();
        let mut entries = Vec::new();
        let mut total = 0;
        let (root_handle, _) = super::platform::bind_directory(&source_root).unwrap();
        super::collect_source_entries(&source_root, &source_root, &root_handle, &mut entries, &mut total).unwrap();
        let super::SourceEntry::File(source) = entries.pop().unwrap() else {
            panic!("the fixture is one regular file");
        };
        let original_identity = source.identity;
        drop(source);
        fs::remove_file(&source_path).unwrap();
        fs::write(&source_path, b"replaced").unwrap();
        let (file, _) =
            super::platform::bind_regular_at(&root_handle, std::ffi::OsStr::new("payload.txt"), &source_path).unwrap();
        let mut replaced_source = super::SourceFile {
            relative_path: "payload.txt".into(),
            size: 8,
            identity: original_identity,
            file,
            preflight_digest: super::sha256_bytes(b"original"),
        };
        let store = temporary.path().join("store");
        fs::create_dir(&store).unwrap();
        let object_directory = super::BoundDirectory::bind(store.clone()).unwrap();

        let error = BottleStore::new(store)
            .publish_object(&mut replaced_source, &object_directory)
            .unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
    }

    fn security_snapshot(entries: Vec<SnapshotEntry>) -> BottleSnapshot {
        let total_file_bytes = entries
            .iter()
            .map(|entry| match entry {
                SnapshotEntry::File { size, .. } => *size,
                SnapshotEntry::Directory { .. } | SnapshotEntry::Link { .. } => 0,
            })
            .sum();
        BottleSnapshot {
            schema_version: "1".into(),
            legacy_format: "macwin-bottle-v1".into(),
            bottle_id: "bottle-1".into(),
            entry_count: entries.len(),
            entries,
            total_file_bytes,
        }
    }

    fn security_file(path: &str) -> SnapshotEntry {
        SnapshotEntry::File {
            path: path.into(),
            size: 0,
            digest: "sha256:0000000000000000000000000000000000000000000000000000000000000000".into(),
        }
    }

    #[test]
    fn snapshot_security_rejects_collisions_ambiguous_components_and_unsafe_link_graphs() {
        let cases = [
            vec![security_file("Data"), security_file("data")],
            vec![
                security_file("Data/file"),
                SnapshotEntry::Directory { path: "data".into() },
            ],
            vec![security_file("strasse"), security_file("straße")],
            vec![security_file("Σ"), security_file("ς")],
            vec![security_file("leaf"), security_file("leaf/child")],
            vec![security_file("CON.txt")],
            vec![security_file("trailing.")],
            vec![security_file("control\u{1}")],
            vec![security_file("e\u{301}.txt")],
            vec![
                SnapshotEntry::Link {
                    path: "a".into(),
                    target: "b".into(),
                },
                SnapshotEntry::Link {
                    path: "b".into(),
                    target: "a".into(),
                },
            ],
            vec![SnapshotEntry::Link {
                path: "missing-link".into(),
                target: "missing-target".into(),
            }],
        ];

        for entries in cases {
            let error = security_snapshot(entries).validate().unwrap_err();
            assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        }
    }

    #[test]
    fn snapshot_security_rejects_same_size_mutation_with_restored_timestamp() {
        let temporary = TemporaryDirectory::new("snapshot-same-size-race");
        let source = create_regular_source(temporary.path());
        let payload = source.join("payload.txt");
        let original_modified = fs::metadata(&payload).unwrap().modified().unwrap();
        let raced_payload = payload.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterFileCopy, "payload.txt", move || {
            fs::write(&raced_payload, b"attacker bytes\n").unwrap();
            fs::File::options()
                .write(true)
                .open(&raced_payload)
                .unwrap()
                .set_times(std::fs::FileTimes::new().set_modified(original_modified))
                .unwrap();
        });

        let error = BottleStore::new(temporary.path().join("store"))
            .snapshot(&source)
            .unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!temporary.path().join("store/snapshots").exists());
    }

    #[test]
    fn snapshot_security_rejects_restored_timestamp_mutation_before_copy() {
        let temporary = TemporaryDirectory::new("snapshot-precopy-race");
        let source = create_regular_source(temporary.path());
        let payload = source.join("payload.txt");
        let original_modified = fs::metadata(&payload).unwrap().modified().unwrap();
        let raced_payload = payload.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourcePreflight, "", move || {
            fs::write(&raced_payload, b"attacker bytes\n").unwrap();
            fs::File::options()
                .write(true)
                .open(&raced_payload)
                .unwrap()
                .set_times(std::fs::FileTimes::new().set_modified(original_modified))
                .unwrap();
        });

        let error = BottleStore::new(temporary.path().join("store"))
            .snapshot(&source)
            .unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!temporary.path().join("store/snapshots").exists());
    }

    #[test]
    fn snapshot_security_rejects_a_late_child_before_publication() {
        let temporary = TemporaryDirectory::new("snapshot-late-child");
        let source = create_regular_source(temporary.path());
        let late_child = source.join("late.txt");
        set_snapshot_hook(super::SnapshotTestStage::BeforeSourceRevalidation, "", move || {
            fs::write(late_child, b"late child\n").unwrap();
        });

        let error = BottleStore::new(temporary.path().join("store"))
            .snapshot(&source)
            .unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!temporary.path().join("store/snapshots").exists());
    }

    #[test]
    fn snapshot_security_never_overwrites_an_object_store_race() {
        let temporary = TemporaryDirectory::new("snapshot-object-race");
        let source = create_regular_source(temporary.path());
        let target = temporary
            .path()
            .join("store/objects/sha256/fded28721427e68a8055a2f21a3de49f18f6f40eef790ddd0e8aeae7679b64bd");
        let raced_target = target.clone();
        set_snapshot_hook(
            super::SnapshotTestStage::BeforeObjectPublish,
            "manifest.json",
            move || {
                fs::write(raced_target, b"foreign object sentinel").unwrap();
            },
        );

        let error = BottleStore::new(temporary.path().join("store"))
            .snapshot(&source)
            .unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(fs::read(target).unwrap(), b"foreign object sentinel");
        assert!(!temporary.path().join("store/snapshots").exists());
    }

    #[test]
    fn snapshot_security_never_overwrites_a_snapshot_store_race() {
        let temporary = TemporaryDirectory::new("snapshot-manifest-race");
        let source = create_regular_source(temporary.path());
        let target = temporary
            .path()
            .join("store/snapshots/sha256/8e363a6b4bbb9af21979ab56432b303eb069e8f410641cd2860ad4755cec6a37.json");
        let raced_target = target.clone();
        set_snapshot_hook(super::SnapshotTestStage::BeforeSnapshotPublish, "", move || {
            fs::write(raced_target, b"foreign snapshot sentinel").unwrap();
        });

        let error = BottleStore::new(temporary.path().join("store"))
            .snapshot(&source)
            .unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SnapshotCorrupt);
        assert_eq!(fs::read(target).unwrap(), b"foreign snapshot sentinel");
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_never_follows_a_store_root_link_inserted_after_preflight() {
        use std::os::unix::fs::symlink;

        let temporary = TemporaryDirectory::new("snapshot-store-root-link-race");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let external = temporary.path().join("external");
        fs::create_dir(&external).unwrap();
        let sentinel = external.join("sentinel.txt");
        fs::write(&sentinel, b"external sentinel\n").unwrap();
        let raced_store = store.clone();
        let raced_external = external.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourcePreflight, "", move || {
            symlink(raced_external, raced_store).unwrap();
        });

        let result = BottleStore::new(&store).snapshot(&source);
        fs::remove_file(&store).unwrap();

        let error = result.unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert_eq!(fs::read(&sentinel).unwrap(), b"external sentinel\n");
        assert_eq!(fs::read_dir(&external).unwrap().count(), 1);
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_revalidates_a_present_store_root_by_parent_and_name() {
        use std::os::unix::fs::symlink;

        let temporary = TemporaryDirectory::new("snapshot-present-store-link-race");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        fs::create_dir(&store).unwrap();
        let moved_store = temporary.path().join("moved-store");
        let external = temporary.path().join("external");
        fs::create_dir(&external).unwrap();
        let sentinel = external.join("sentinel.txt");
        fs::write(&sentinel, b"external sentinel\n").unwrap();
        let raced_store = store.clone();
        let raced_moved = moved_store.clone();
        let raced_external = external.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourcePreflight, "", move || {
            fs::rename(&raced_store, &raced_moved).unwrap();
            symlink(raced_external, raced_store).unwrap();
        });

        let result = BottleStore::new(&store).snapshot(&source);
        fs::remove_file(&store).unwrap();

        let error = result.unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert_eq!(fs::read(&sentinel).unwrap(), b"external sentinel\n");
        assert_eq!(fs::read_dir(&external).unwrap().count(), 1);
        assert!(moved_store.is_dir());
    }

    #[cfg(windows)]
    #[test]
    fn snapshot_security_never_follows_a_store_root_junction_inserted_after_preflight() {
        let temporary = TemporaryDirectory::new("snapshot-store-root-junction-race");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let external = temporary.path().join("external");
        fs::create_dir(&external).unwrap();
        let sentinel = external.join("sentinel.txt");
        fs::write(&sentinel, b"external sentinel\n").unwrap();
        let raced_store = store.clone();
        let raced_external = external.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourcePreflight, "", move || {
            create_directory_junction(&raced_store, &raced_external);
        });

        let result = BottleStore::new(&store).snapshot(&source);
        fs::remove_dir(&store).unwrap();

        let error = result.unwrap_err();
        assert_eq!(fs::read(&sentinel).unwrap(), b"external sentinel\n");
        assert_eq!(fs::read_dir(&external).unwrap().count(), 1);
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
    }

    #[cfg(windows)]
    #[test]
    fn snapshot_security_revalidates_a_present_store_root_by_parent_and_name() {
        let temporary = TemporaryDirectory::new("snapshot-present-store-junction-race");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        fs::create_dir(&store).unwrap();
        let external = temporary.path().join("external");
        fs::create_dir(&external).unwrap();
        let sentinel = external.join("sentinel.txt");
        fs::write(&sentinel, b"external sentinel\n").unwrap();
        let raced_store = store.clone();
        let raced_external = external.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourcePreflight, "", move || {
            fs::remove_dir(&raced_store).unwrap();
            create_directory_junction(&raced_store, &raced_external);
        });

        let result = BottleStore::new(&store).snapshot(&source);
        fs::remove_dir(&store).unwrap();

        let error = result.unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert_eq!(fs::read(&sentinel).unwrap(), b"external sentinel\n");
        assert_eq!(fs::read_dir(&external).unwrap().count(), 1);
    }

    #[cfg(windows)]
    #[test]
    fn snapshot_security_holds_the_selected_source_name_against_windows_rename() {
        let temporary = TemporaryDirectory::new("snapshot-selected-source-held-windows");
        let source = create_regular_source(temporary.path());
        let moved = temporary.path().join("moved-source");
        let rename_was_denied = std::rc::Rc::new(std::cell::Cell::new(false));
        let observed = std::rc::Rc::clone(&rename_was_denied);
        let source_for_hook = source.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterRootBind, "", move || {
            observed.set(fs::rename(source_for_hook, moved).is_err());
        });

        let receipt = BottleStore::new(temporary.path().join("store"))
            .snapshot(&source)
            .unwrap();

        assert!(
            rename_was_denied.get(),
            "held source handles must deny rename/delete sharing"
        );
        assert_eq!(receipt.snapshot_digest, SNAPSHOT_DIGEST);
    }

    #[test]
    fn publication_consistency_rejects_source_change_after_revalidation_without_publishing_snapshot() {
        let temporary = TemporaryDirectory::new("snapshot-post-validation-race");
        let source = create_regular_source(temporary.path());
        let payload = source.join("payload.txt");
        let original_modified = fs::metadata(&payload).unwrap().modified().unwrap();
        let raced_payload = payload.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourceRevalidation, "", move || {
            fs::write(&raced_payload, b"attacker bytes\n").unwrap();
            fs::File::options()
                .write(true)
                .open(&raced_payload)
                .unwrap()
                .set_times(std::fs::FileTimes::new().set_modified(original_modified))
                .unwrap();
        });
        let store = temporary.path().join("store");
        let published =
            store.join("snapshots/sha256/8e363a6b4bbb9af21979ab56432b303eb069e8f410641cd2860ad4755cec6a37.json");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!published.exists());
    }

    #[test]
    fn publication_consistency_rolls_back_an_owned_snapshot_when_source_changes_after_publish() {
        let temporary = TemporaryDirectory::new("snapshot-post-publish-race");
        let source = create_regular_source(temporary.path());
        let payload = source.join("payload.txt");
        let original_modified = fs::metadata(&payload).unwrap().modified().unwrap();
        let raced_payload = payload.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSnapshotPublish, "", move || {
            fs::write(&raced_payload, b"attacker bytes\n").unwrap();
            fs::File::options()
                .write(true)
                .open(&raced_payload)
                .unwrap()
                .set_times(std::fs::FileTimes::new().set_modified(original_modified))
                .unwrap();
        });
        let store = temporary.path().join("store");
        let published =
            store.join("snapshots/sha256/8e363a6b4bbb9af21979ab56432b303eb069e8f410641cd2860ad4755cec6a37.json");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(
            !published.exists(),
            "a snapshot created by the failed call must be rolled back"
        );
    }

    #[test]
    fn publication_consistency_never_rolls_back_a_preexisting_snapshot_on_final_source_change() {
        let temporary = TemporaryDirectory::new("snapshot-final-return-race");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let receipt = BottleStore::new(&store).snapshot(&source).unwrap();
        let published = store.join(format!(
            "snapshots/sha256/{}.json",
            receipt.snapshot_digest.strip_prefix("sha256:").unwrap()
        ));
        let original_snapshot = fs::read(&published).unwrap();
        let payload = source.join("payload.txt");
        let original_modified = fs::metadata(&payload).unwrap().modified().unwrap();
        let raced_payload = payload.clone();
        set_snapshot_hook(super::SnapshotTestStage::BeforeSnapshotReturn, "", move || {
            fs::write(&raced_payload, b"attacker bytes\n").unwrap();
            fs::File::options()
                .write(true)
                .open(&raced_payload)
                .unwrap()
                .set_times(std::fs::FileTimes::new().set_modified(original_modified))
                .unwrap();
        });

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert_eq!(
            fs::read(published).unwrap(),
            original_snapshot,
            "a preexisting identical snapshot is never owned by the failed call"
        );
    }

    #[test]
    fn publication_rollback_never_deletes_a_replacement_it_does_not_own() {
        let temporary = TemporaryDirectory::new("snapshot-rollback-ownership-race");
        let source = create_regular_source(temporary.path());
        let store = temporary.path().join("store");
        let published =
            store.join("snapshots/sha256/8e363a6b4bbb9af21979ab56432b303eb069e8f410641cd2860ad4755cec6a37.json");
        let raced_target = published.clone();
        let payload = source.join("payload.txt");
        let original_modified = fs::metadata(&payload).unwrap().modified().unwrap();
        set_snapshot_hook(super::SnapshotTestStage::AfterSnapshotPublish, "", move || {
            fs::remove_file(&raced_target).unwrap();
            fs::write(&raced_target, b"foreign snapshot sentinel").unwrap();
            fs::write(&payload, b"attacker bytes\n").unwrap();
            fs::File::options()
                .write(true)
                .open(&payload)
                .unwrap()
                .set_times(std::fs::FileTimes::new().set_modified(original_modified))
                .unwrap();
        });

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert_eq!(fs::read(published).unwrap(), b"foreign snapshot sentinel");
    }

    #[test]
    fn snapshot_manifest_bound_is_checked_before_canonical_json_materialization() {
        let temporary = TemporaryDirectory::new("snapshot-canonical-resource-bound");
        let source = create_regular_source(temporary.path());
        let post_bound_work_started = std::rc::Rc::new(std::cell::Cell::new(false));
        let observed = std::rc::Rc::clone(&post_bound_work_started);
        set_snapshot_hook(
            super::SnapshotTestStage::AfterSnapshotManifestMeasurement,
            "",
            move || observed.set(true),
        );
        super::SNAPSHOT_MANIFEST_LIMIT_OVERRIDE.with(|limit| limit.set(Some(128)));

        let result = BottleStore::new(temporary.path().join("store")).snapshot(&source);
        super::SNAPSHOT_MANIFEST_LIMIT_OVERRIDE.with(|limit| limit.set(None));

        assert_eq!(result.unwrap_err().code(), DiagnosticCode::UnsafeEntry);
        assert!(
            !post_bound_work_started.get(),
            "the size bound must reject before a compact or pretty JSON buffer is materialized"
        );
    }

    #[test]
    fn snapshot_security_path_and_resource_bounds_are_exact() {
        let maximum_path = "a".repeat(super::MAX_PATH_BYTES);
        assert!(super::validate_basic_path(&maximum_path).is_ok());
        assert!(super::validate_basic_path(&format!("{maximum_path}a")).is_err());

        let maximum_depth = std::iter::repeat("a")
            .take(super::MAX_PATH_DEPTH)
            .collect::<Vec<_>>()
            .join("/");
        assert!(super::validate_basic_path(&maximum_depth).is_ok());
        assert!(super::validate_basic_path(&format!("{maximum_depth}/a")).is_err());

        let mut total = super::MAX_TOTAL_FILE_BYTES - super::MAX_FILE_BYTES;
        super::checked_regular_file_size(super::MAX_FILE_BYTES, &mut total).unwrap();
        assert_eq!(total, super::MAX_TOTAL_FILE_BYTES);
        assert!(super::checked_regular_file_size(1, &mut total).is_err());

        assert!(super::checked_entry_count(super::MAX_ENTRIES - 1).is_ok());
        assert!(super::checked_entry_count(super::MAX_ENTRIES).is_err());
        assert!(super::checked_snapshot_manifest_size(super::MAX_SNAPSHOT_MANIFEST_BYTES).is_ok());
        assert!(super::checked_snapshot_manifest_size(super::MAX_SNAPSHOT_MANIFEST_BYTES + 1).is_err());
        let mut bounded_counter = super::BoundedCounter {
            length: super::MAX_SNAPSHOT_MANIFEST_BYTES - 1,
            maximum: super::MAX_SNAPSHOT_MANIFEST_BYTES,
        };
        std::io::Write::write_all(&mut bounded_counter, b"x").unwrap();
        assert_eq!(bounded_counter.length, super::MAX_SNAPSHOT_MANIFEST_BYTES);
        assert!(std::io::Write::write_all(&mut bounded_counter, b"x").is_err());
        assert_eq!(
            bounded_counter.length,
            super::MAX_SNAPSHOT_MANIFEST_BYTES,
            "the rejecting write must not advance or allocate"
        );
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_accepts_safe_relative_symlink_and_never_follows_it() {
        use std::os::unix::fs::symlink;

        let temporary = TemporaryDirectory::new("snapshot-safe-link");
        let source = create_regular_source(temporary.path());
        symlink("payload.txt", source.join("payload-link")).unwrap();
        fs::create_dir(source.join("links")).unwrap();
        symlink("../payload.txt", source.join("links/nested-link")).unwrap();
        let store = temporary.path().join("store");

        let receipt = BottleStore::new(&store).snapshot(&source).unwrap();
        let snapshot = BottleStore::new(store)
            .verify_snapshot(&receipt.snapshot_digest)
            .unwrap();

        assert!(snapshot.entries.contains(&SnapshotEntry::Link {
            path: "payload-link".into(),
            target: "payload.txt".into(),
        }));
        assert!(snapshot.entries.contains(&SnapshotEntry::Link {
            path: "links/nested-link".into(),
            target: "payload.txt".into(),
        }));
        assert_eq!(snapshot.total_file_bytes, 239, "link target bytes are not copied twice");
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_source_root_replacement_before_canonicalization() {
        let temporary = TemporaryDirectory::new("snapshot-root-race");
        let source = create_regular_source(temporary.path());
        let original = source.clone();
        let moved = temporary.path().join("moved-source");
        set_snapshot_hook(super::SnapshotTestStage::AfterRootBind, "", move || {
            fs::rename(&original, moved).unwrap();
            fs::create_dir(&original).unwrap();
        });
        let store = temporary.path().join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!store.exists());
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_selected_source_name_replaced_by_link_to_the_same_directory() {
        use std::os::unix::fs::symlink;

        let temporary = TemporaryDirectory::new("snapshot-selected-root-link-race");
        let source = create_regular_source(temporary.path());
        let selected_name = source.clone();
        let moved = temporary.path().join("moved-source");
        let moved_for_hook = moved.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterRootBind, "", move || {
            fs::rename(&selected_name, &moved_for_hook).unwrap();
            symlink(&moved_for_hook, &selected_name).unwrap();
        });
        let store = temporary.path().join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!store.exists());
        fs::remove_file(&source).unwrap();
        assert!(moved.exists());
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_selected_source_parent_replacement() {
        let temporary = TemporaryDirectory::new("snapshot-selected-parent-race");
        let selected_parent = temporary.path().join("selected-parent");
        fs::create_dir(&selected_parent).unwrap();
        let source = create_regular_source(&selected_parent);
        let moved_parent = temporary.path().join("moved-parent");
        let selected_parent_for_hook = selected_parent.clone();
        let moved_parent_for_hook = moved_parent.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterRootBind, "", move || {
            fs::rename(&selected_parent_for_hook, &moved_parent_for_hook).unwrap();
            fs::create_dir(&selected_parent_for_hook).unwrap();
        });
        let store = temporary.path().join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!store.exists());
        assert!(moved_parent.join("source/manifest.json").is_file());
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_nested_directory_replaced_by_link_to_the_same_directory() {
        use std::os::unix::fs::symlink;

        let temporary = TemporaryDirectory::new("snapshot-nested-directory-race");
        let source = create_regular_source(temporary.path());
        let nested = source.join("nested");
        fs::create_dir(&nested).unwrap();
        fs::write(nested.join("nested.txt"), b"nested sentinel\n").unwrap();
        let moved = source.join("moved-nested");
        let nested_for_hook = nested.clone();
        let moved_for_hook = moved.clone();
        set_snapshot_hook(super::SnapshotTestStage::AfterSourcePreflight, "", move || {
            fs::rename(&nested_for_hook, &moved_for_hook).unwrap();
            symlink("moved-nested", &nested_for_hook).unwrap();
        });
        let store = temporary.path().join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!store.join("snapshots").exists());
        assert_eq!(fs::read(moved.join("nested.txt")).unwrap(), b"nested sentinel\n");
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_late_source_leaf_deletion() {
        let temporary = TemporaryDirectory::new("snapshot-late-deletion");
        let source = create_regular_source(temporary.path());
        let deleted = source.join("payload.txt");
        set_snapshot_hook(super::SnapshotTestStage::BeforeSourceRevalidation, "", move || {
            fs::remove_file(deleted).unwrap();
        });
        let store = temporary.path().join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::SourceChanged);
        assert!(!store.join("snapshots").exists());
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_absolute_escaping_and_cyclic_symlinks_before_store_write() {
        use std::os::unix::fs::symlink;

        for case in ["absolute", "escaping", "cycle"] {
            let temporary = TemporaryDirectory::new(case);
            let source = create_regular_source(temporary.path());
            let outside = temporary.path().join("outside.txt");
            fs::write(&outside, b"external sentinel\n").unwrap();
            match case {
                "absolute" => symlink(&outside, source.join("unsafe-link")).unwrap(),
                "escaping" => symlink("../outside.txt", source.join("unsafe-link")).unwrap(),
                "cycle" => {
                    symlink("cycle-b", source.join("cycle-a")).unwrap();
                    symlink("cycle-a", source.join("cycle-b")).unwrap();
                }
                _ => unreachable!(),
            }
            let store = temporary.path().join("store");

            let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

            assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
            assert_eq!(fs::read(&outside).unwrap(), b"external sentinel\n");
            assert!(!store.exists());
        }
    }

    #[cfg(unix)]
    #[test]
    fn snapshot_security_rejects_fifo_socket_and_non_utf8_entries() {
        use std::os::unix::ffi::OsStringExt as _;

        let fifo_case = TemporaryDirectory::new("snapshot-fifo");
        let fifo_source = create_regular_source(fifo_case.path());
        let fifo = fifo_source.join("unsafe-fifo");
        let fifo_name = std::ffi::CString::new(fifo.as_os_str().as_encoded_bytes()).unwrap();
        // SAFETY: `fifo_name` is a valid NUL-terminated pathname and the mode
        // contains only ordinary permission bits.
        assert_eq!(unsafe { libc::mkfifo(fifo_name.as_ptr(), 0o600) }, 0);
        let error = BottleStore::new(fifo_case.path().join("store"))
            .snapshot(&fifo_source)
            .unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);

        let socket_case = TemporaryDirectory::new("snapshot-socket");
        let socket_source = create_regular_source(socket_case.path());
        let _listener = std::os::unix::net::UnixListener::bind(socket_source.join("unsafe-socket")).unwrap();
        let error = BottleStore::new(socket_case.path().join("store"))
            .snapshot(&socket_source)
            .unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);

        let unicode_case = TemporaryDirectory::new("snapshot-invalid-unicode");
        let unicode_source = create_regular_source(unicode_case.path());
        let invalid_name = std::ffi::OsString::from_vec(vec![b'b', b'a', b'd', 0xff]);
        fs::write(unicode_source.join(invalid_name), b"invalid path\n").unwrap();
        let error = BottleStore::new(unicode_case.path().join("store"))
            .snapshot(&unicode_source)
            .unwrap_err();
        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
    }

    #[cfg(windows)]
    fn create_directory_junction(link: &Path, target: &Path) {
        use std::os::windows::ffi::OsStrExt as _;
        use std::os::windows::fs::OpenOptionsExt as _;
        use std::os::windows::io::AsRawHandle as _;

        const FILE_SHARE_READ: u32 = 0x0000_0001;
        const FILE_SHARE_WRITE: u32 = 0x0000_0002;
        const FILE_SHARE_DELETE: u32 = 0x0000_0004;
        const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;
        const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
        const FSCTL_SET_REPARSE_POINT: u32 = 0x0009_00a4;
        const IO_REPARSE_TAG_MOUNT_POINT: u32 = 0xa000_0003;

        #[link(name = "Kernel32")]
        extern "system" {
            #[link_name = "DeviceIoControl"]
            fn device_io_control(
                device: *mut core::ffi::c_void,
                control_code: u32,
                input: *mut core::ffi::c_void,
                input_size: u32,
                output: *mut core::ffi::c_void,
                output_size: u32,
                returned: *mut u32,
                overlapped: *mut core::ffi::c_void,
            ) -> i32;
        }

        fs::create_dir(link).unwrap();
        let canonical_target = fs::canonicalize(target).unwrap();
        let substitute = format!(r"\??\{}", canonical_target.display())
            .encode_utf16()
            .collect::<Vec<_>>();
        let print = canonical_target.as_os_str().encode_wide().collect::<Vec<_>>();
        let substitute_bytes = u16::try_from(substitute.len() * 2).unwrap();
        let print_offset = substitute_bytes + 2;
        let print_bytes = u16::try_from(print.len() * 2).unwrap();
        let data_length = 8_u16 + substitute_bytes + 2 + print_bytes + 2;
        let mut buffer = Vec::with_capacity(8 + usize::from(data_length));
        buffer.extend_from_slice(&IO_REPARSE_TAG_MOUNT_POINT.to_le_bytes());
        buffer.extend_from_slice(&data_length.to_le_bytes());
        buffer.extend_from_slice(&0_u16.to_le_bytes());
        buffer.extend_from_slice(&0_u16.to_le_bytes());
        buffer.extend_from_slice(&substitute_bytes.to_le_bytes());
        buffer.extend_from_slice(&print_offset.to_le_bytes());
        buffer.extend_from_slice(&print_bytes.to_le_bytes());
        for unit in substitute
            .iter()
            .chain(std::iter::once(&0))
            .chain(print.iter())
            .chain(std::iter::once(&0))
        {
            buffer.extend_from_slice(&unit.to_le_bytes());
        }
        let directory = fs::OpenOptions::new()
            .write(true)
            .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
            .open(link)
            .unwrap();
        let mut returned = 0_u32;
        // SAFETY: the owned directory handle is valid; the input points to a
        // fully initialized mount-point reparse buffer for the call duration;
        // no output buffer or overlapped operation is requested.
        let succeeded = unsafe {
            device_io_control(
                directory.as_raw_handle().cast(),
                FSCTL_SET_REPARSE_POINT,
                buffer.as_mut_ptr().cast(),
                u32::try_from(buffer.len()).unwrap(),
                std::ptr::null_mut(),
                0,
                std::ptr::addr_of_mut!(returned),
                std::ptr::null_mut(),
            )
        };
        assert_ne!(
            succeeded,
            0,
            "junction creation failed: {}",
            std::io::Error::last_os_error()
        );
    }

    #[cfg(windows)]
    #[test]
    fn snapshot_security_rejects_a_windows_junction_without_reading_the_target() {
        let temporary = TemporaryDirectory::new("snapshot-junction");
        let source = create_regular_source(temporary.path());
        let outside = temporary.path().join("outside");
        fs::create_dir(&outside).unwrap();
        fs::write(outside.join("sentinel.txt"), b"external sentinel\n").unwrap();
        let junction = source.join("unsafe-junction");
        create_directory_junction(&junction, &outside);
        let store = temporary.path().join("store");

        let error = BottleStore::new(&store).snapshot(&source).unwrap_err();

        assert_eq!(error.code(), DiagnosticCode::UnsafeEntry);
        assert_eq!(fs::read(outside.join("sentinel.txt")).unwrap(), b"external sentinel\n");
        assert!(!store.exists());
        fs::remove_dir(&junction).unwrap();
    }

    #[test]
    fn resource_cleanup_closes_held_source_handles_on_error_and_unwind() {
        if std::env::var_os("COMPATFORGE_HANDLE_COUNT_CHILD").is_none() {
            let status = std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "snapshot::tests::resource_cleanup_closes_held_source_handles_on_error_and_unwind",
                    "--nocapture",
                ])
                .env("COMPATFORGE_HANDLE_COUNT_CHILD", "1")
                .status()
                .unwrap();
            assert!(status.success());
            return;
        }

        let temporary = TemporaryDirectory::new("snapshot-held-cleanup");
        let source = create_regular_source(temporary.path());
        #[cfg(windows)]
        let handles_before = process_handle_count();
        #[cfg(target_os = "linux")]
        let descriptors_before = process_file_descriptor_count();
        let failure_source = temporary.path().join("failure-source");
        fs::create_dir(&failure_source).unwrap();
        fs::write(failure_source.join("manifest.json"), b"{}\n").unwrap();
        let failure = BottleStore::new(temporary.path().join("failure-store")).snapshot(&failure_source);
        assert_eq!(failure.unwrap_err().code(), DiagnosticCode::InvalidManifest);
        fs::remove_dir_all(&failure_source).unwrap();
        #[cfg(windows)]
        assert_eq!(process_handle_count(), handles_before);
        #[cfg(target_os = "linux")]
        assert_eq!(process_file_descriptor_count(), descriptors_before);
        let source_for_unwind = source.clone();
        let panic_hook = std::panic::take_hook();
        std::panic::set_hook(Box::new(|_| {}));
        let unwind = std::panic::catch_unwind(move || {
            let mut entries = Vec::new();
            let mut total = 0;
            let (root_handle, _) = super::platform::bind_directory(&source_for_unwind).unwrap();
            super::collect_source_entries(
                &source_for_unwind,
                &source_for_unwind,
                &root_handle,
                &mut entries,
                &mut total,
            )
            .unwrap();
            panic!("controlled held-handle unwind");
        });
        std::panic::set_hook(panic_hook);
        assert!(unwind.is_err());
        fs::remove_dir_all(&source).unwrap();
        assert!(!source.exists());
        #[cfg(windows)]
        assert_eq!(process_handle_count(), handles_before);
        #[cfg(target_os = "linux")]
        assert_eq!(process_file_descriptor_count(), descriptors_before);
    }
}
