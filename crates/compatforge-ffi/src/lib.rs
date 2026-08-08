//! Stable C ABI entry points used by Swift, Kotlin/JNI, Qt, and other clients.

#![forbid(unsafe_code)]

use std::ffi::c_char;

const API_VERSION: &[u8] = b"0.1.0\0";

/// Return the semantic version of the Rust API as a process-lifetime C string.
#[must_use]
#[no_mangle]
pub extern "C" fn cf_api_version() -> *const c_char {
    API_VERSION.as_ptr().cast()
}

/// Return the major C ABI version.
#[must_use]
#[no_mangle]
pub const extern "C" fn cf_abi_version() -> u32 {
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn abi_version_is_stable() {
        assert_eq!(cf_abi_version(), 1);
        assert!(!cf_api_version().is_null());
    }
}
