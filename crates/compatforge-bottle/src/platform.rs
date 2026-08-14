use std::ffi::OsStr;
use std::fs::{File, Metadata, OpenOptions};
use std::io;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct FileIdentity {
    object: ObjectIdentity,
    len: u64,
    modified: Option<std::time::SystemTime>,
}

#[cfg(unix)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ObjectIdentity {
    device: u64,
    inode: u64,
    mode: u32,
}

#[cfg(windows)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ObjectIdentity {
    volume: Option<u32>,
    index: Option<u64>,
    attributes: u32,
}

pub(crate) fn bind_regular(path: &Path) -> io::Result<(File, FileIdentity)> {
    let file = open_no_follow(path)?;
    let identity = file_identity(&file)?;
    Ok((file, identity))
}

pub(crate) fn bind_directory(path: &Path) -> io::Result<(File, FileIdentity)> {
    let file = open_directory_no_follow(path)?;
    let metadata = file.metadata()?;
    if !metadata.file_type().is_dir() || metadata_is_link_or_reparse(&metadata) {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "source directory is unsafe"));
    }
    let identity = FileIdentity {
        object: object_identity(&file, &metadata)?,
        len: metadata.len(),
        modified: metadata.modified().ok(),
    };
    Ok((file, identity))
}

#[cfg(windows)]
pub(crate) fn bind_regular_at(_parent: &File, _name: &OsStr, path: &Path) -> io::Result<(File, FileIdentity)> {
    bind_regular(path)
}

#[cfg(windows)]
pub(crate) fn bind_directory_at(_parent: &File, _name: &OsStr, path: &Path) -> io::Result<(File, FileIdentity)> {
    bind_directory(path)
}

#[cfg(windows)]
pub(crate) fn bind_link_at(
    _parent: &File,
    _name: &OsStr,
    path: &Path,
) -> io::Result<(Option<File>, FileIdentity, std::path::PathBuf)> {
    bind_link_impl(path)
}

#[cfg(unix)]
pub(crate) fn bind_regular_at(parent: &File, name: &OsStr, _path: &Path) -> io::Result<(File, FileIdentity)> {
    let file = openat_no_follow(parent, name, libc::O_RDONLY | libc::O_NONBLOCK)?;
    let identity = file_identity(&file)?;
    Ok((file, identity))
}

#[cfg(unix)]
pub(crate) fn bind_directory_at(parent: &File, name: &OsStr, _path: &Path) -> io::Result<(File, FileIdentity)> {
    let file = openat_no_follow(parent, name, libc::O_RDONLY | libc::O_DIRECTORY)?;
    let metadata = file.metadata()?;
    if !metadata.file_type().is_dir() || metadata_is_link_or_reparse(&metadata) {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "source directory is unsafe"));
    }
    let identity = FileIdentity {
        object: object_identity(&file, &metadata)?,
        len: metadata.len(),
        modified: metadata.modified().ok(),
    };
    Ok((file, identity))
}

#[cfg(unix)]
pub(crate) fn bind_link_at(
    parent: &File,
    name: &OsStr,
    _path: &Path,
) -> io::Result<(Option<File>, FileIdentity, std::path::PathBuf)> {
    use std::os::unix::ffi::{OsStrExt as _, OsStringExt as _};
    use std::os::unix::io::AsRawFd as _;

    let name = std::ffi::CString::new(name.as_bytes())?;
    let before = link_stat_at(parent, &name)?;
    let mut buffer = vec![0_u8; 4097];
    // SAFETY: the parent fd and NUL-terminated name are valid; `buffer` is a
    // live writable region of the supplied length.
    let read = unsafe {
        libc::readlinkat(
            parent.as_raw_fd(),
            name.as_ptr(),
            buffer.as_mut_ptr().cast(),
            buffer.len(),
        )
    };
    if read < 0 {
        return Err(io::Error::last_os_error());
    }
    let read = usize::try_from(read).map_err(|_| io::Error::other("negative link length"))?;
    if read == buffer.len() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "source link target is oversized",
        ));
    }
    buffer.truncate(read);
    let after = link_stat_at(parent, &name)?;
    if before != after {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "source link changed"));
    }
    Ok((None, before, std::ffi::OsString::from_vec(buffer).into()))
}

#[cfg(unix)]
fn openat_no_follow(parent: &File, name: &OsStr, flags: i32) -> io::Result<File> {
    use std::os::fd::{AsRawFd as _, FromRawFd as _};
    use std::os::unix::ffi::OsStrExt as _;

    let name = std::ffi::CString::new(name.as_bytes())?;
    // SAFETY: the held directory fd and NUL-terminated child name are valid;
    // success returns a new owned descriptor transferred to `File` once.
    let descriptor = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if descriptor < 0 {
        Err(io::Error::last_os_error())
    } else {
        // SAFETY: `openat` returned a fresh descriptor now uniquely owned here.
        Ok(unsafe { File::from_raw_fd(descriptor) })
    }
}

#[cfg(unix)]
fn link_stat_at(parent: &File, name: &std::ffi::CStr) -> io::Result<FileIdentity> {
    use std::os::fd::AsRawFd as _;

    let mut stat = std::mem::MaybeUninit::<libc::stat>::uninit();
    // SAFETY: the parent fd/name are valid and `stat` is a correctly sized
    // output location initialized by a successful `fstatat` call.
    let result = unsafe {
        libc::fstatat(
            parent.as_raw_fd(),
            name.as_ptr(),
            stat.as_mut_ptr(),
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if result != 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: successful `fstatat` initialized every field of `stat`.
    let stat = unsafe { stat.assume_init() };
    if stat.st_mode & libc::S_IFMT != libc::S_IFLNK {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "source entry is not a link"));
    }
    Ok(link_identity_from_stat(&stat))
}

#[cfg(unix)]
fn link_identity_from_stat(stat: &libc::stat) -> FileIdentity {
    FileIdentity {
        object: ObjectIdentity {
            device: u64::try_from(stat.st_dev).unwrap_or(u64::MAX),
            inode: u64::try_from(stat.st_ino).unwrap_or(u64::MAX),
            mode: u32::from(stat.st_mode),
        },
        len: u64::try_from(stat.st_size).unwrap_or(u64::MAX),
        modified: None,
    }
}

pub(crate) fn verify_regular(file: &File, expected: FileIdentity) -> io::Result<()> {
    if file_identity(file)? == expected {
        Ok(())
    } else {
        Err(io::Error::new(io::ErrorKind::InvalidData, "source identity changed"))
    }
}

fn file_identity(file: &File) -> io::Result<FileIdentity> {
    let metadata = file.metadata()?;
    if !metadata.file_type().is_file() || metadata_is_link_or_reparse(&metadata) {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "source leaf is not regular"));
    }
    Ok(FileIdentity {
        object: object_identity(file, &metadata)?,
        len: metadata.len(),
        modified: metadata.modified().ok(),
    })
}

#[cfg(unix)]
fn object_identity(_file: &File, metadata: &Metadata) -> io::Result<ObjectIdentity> {
    use std::os::unix::fs::MetadataExt as _;

    Ok(ObjectIdentity {
        device: metadata.dev(),
        inode: metadata.ino(),
        mode: metadata.mode(),
    })
}

#[cfg(windows)]
fn object_identity(file: &File, metadata: &Metadata) -> io::Result<ObjectIdentity> {
    use std::os::windows::fs::MetadataExt as _;
    use std::os::windows::io::AsRawHandle as _;

    #[repr(C)]
    #[derive(Clone, Copy, Default)]
    struct FileTime {
        low: u32,
        high: u32,
    }

    #[repr(C)]
    #[derive(Default)]
    struct ByHandleFileInformation {
        attributes: u32,
        creation_time: FileTime,
        last_access_time: FileTime,
        last_write_time: FileTime,
        volume_serial_number: u32,
        file_size_high: u32,
        file_size_low: u32,
        number_of_links: u32,
        file_index_high: u32,
        file_index_low: u32,
    }

    #[link(name = "Kernel32")]
    extern "system" {
        #[link_name = "GetFileInformationByHandle"]
        fn get_file_information_by_handle(
            file: *mut core::ffi::c_void,
            information: *mut ByHandleFileInformation,
        ) -> i32;
    }

    let mut information = ByHandleFileInformation::default();
    // SAFETY: `file` owns a valid Windows handle and `information` points to a
    // live, correctly sized `BY_HANDLE_FILE_INFORMATION` representation.
    let succeeded =
        unsafe { get_file_information_by_handle(file.as_raw_handle().cast(), std::ptr::addr_of_mut!(information)) };
    if succeeded == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(ObjectIdentity {
        volume: Some(information.volume_serial_number),
        index: Some((u64::from(information.file_index_high) << 32) | u64::from(information.file_index_low)),
        attributes: metadata.file_attributes(),
    })
}

#[cfg(unix)]
fn open_no_follow(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt as _;

    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
}

#[cfg(unix)]
fn open_directory_no_follow(path: &Path) -> io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt as _;

    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
}

#[cfg(windows)]
fn open_no_follow(path: &Path) -> io::Result<File> {
    use std::os::windows::fs::OpenOptionsExt as _;

    const FILE_SHARE_READ: u32 = 0x0000_0001;
    const FILE_SHARE_WRITE: u32 = 0x0000_0002;
    const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
    OpenOptions::new()
        .read(true)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
}

#[cfg(windows)]
fn open_directory_no_follow(path: &Path) -> io::Result<File> {
    use std::os::windows::fs::OpenOptionsExt as _;

    const FILE_SHARE_READ: u32 = 0x0000_0001;
    const FILE_SHARE_WRITE: u32 = 0x0000_0002;
    const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;
    const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
    OpenOptions::new()
        .read(true)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)
        .open(path)
}

#[cfg(windows)]
fn bind_link_impl(path: &Path) -> io::Result<(Option<File>, FileIdentity, std::path::PathBuf)> {
    let file = open_directory_no_follow(path)?;
    let metadata = file.metadata()?;
    if !metadata_is_link_or_reparse(&metadata) || !metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "source reparse point is unsafe",
        ));
    }
    let identity = FileIdentity {
        object: object_identity(&file, &metadata)?,
        len: metadata.len(),
        modified: metadata.modified().ok(),
    };
    Ok((Some(file), identity, std::fs::read_link(path)?))
}

#[cfg(unix)]
fn metadata_is_link_or_reparse(metadata: &Metadata) -> bool {
    metadata.file_type().is_symlink()
}

#[cfg(windows)]
fn metadata_is_link_or_reparse(metadata: &Metadata) -> bool {
    use std::os::windows::fs::MetadataExt as _;

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0000_0400;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(any(unix, windows)))]
compile_error!("compatforge-bottle requires held no-follow source handles");
