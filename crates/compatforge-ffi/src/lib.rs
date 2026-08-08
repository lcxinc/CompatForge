//! Stable C ABI used by Swift first and by other frontends later.

#![deny(unsafe_op_in_unsafe_fn)]

use compatforge_domain::{CoreConfig, LaunchRequest};
use compatforge_orchestrator::PolicyEngine;
use std::cell::RefCell;
use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;

const API_VERSION: &[u8] = b"0.2.0\0";

thread_local! {
    static LAST_ERROR: RefCell<Option<CString>> = const { RefCell::new(None) };
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u32)]
pub enum CfStatus {
    Ok = 0,
    NullPointer = 1,
    InvalidUtf8 = 2,
    InvalidJson = 3,
    InvalidArgument = 4,
    PlanningFailed = 5,
    Panic = 255,
}

#[repr(C)]
pub struct CfContext {
    config: CoreConfig,
}

struct FfiFailure {
    status: CfStatus,
    message: String,
}

impl FfiFailure {
    fn new(status: CfStatus, message: impl Into<String>) -> Self {
        Self {
            status,
            message: message.into(),
        }
    }
}

/// Return the semantic API version as a process-lifetime C string.
#[must_use]
#[no_mangle]
pub extern "C" fn cf_api_version() -> *const c_char {
    API_VERSION.as_ptr().cast()
}

/// Return the stable C ABI major version.
#[must_use]
#[no_mangle]
pub const extern "C" fn cf_abi_version() -> u32 {
    1
}

/// Create a planning context from a UTF-8 JSON configuration.
///
/// # Safety
///
/// `config_json` must point to a valid NUL-terminated string. `out_context`
/// must be valid for one pointer write and must later be released exactly once
/// with [`cf_context_release`].
#[no_mangle]
pub unsafe extern "C" fn cf_context_create(config_json: *const c_char, out_context: *mut *mut CfContext) -> CfStatus {
    ffi_boundary(|| {
        if out_context.is_null() {
            return Err(FfiFailure::new(CfStatus::NullPointer, "out_context is null"));
        }
        unsafe { ptr::write(out_context, ptr::null_mut()) };
        let config_text = unsafe { read_utf8(config_json, "config_json") }?;
        let config: CoreConfig = serde_json::from_str(&config_text)
            .map_err(|error| FfiFailure::new(CfStatus::InvalidJson, format!("invalid config JSON: {error}")))?;
        config
            .validate()
            .map_err(|error| FfiFailure::new(CfStatus::InvalidArgument, format!("invalid config: {error}")))?;

        let context = Box::into_raw(Box::new(CfContext { config }));
        unsafe { ptr::write(out_context, context) };
        Ok(())
    })
}

/// Compile a UTF-8 launch request into an owned UTF-8 launch-plan string.
///
/// # Safety
///
/// `context` must be a live pointer created by [`cf_context_create`].
/// `request_json` must point to a valid NUL-terminated string. `out_plan_json`
/// must be valid for one pointer write; a non-null result must be released with
/// [`cf_string_free`].
#[no_mangle]
pub unsafe extern "C" fn cf_compile_launch(
    context: *const CfContext,
    request_json: *const c_char,
    out_plan_json: *mut *mut c_char,
) -> CfStatus {
    ffi_boundary(|| {
        if context.is_null() || out_plan_json.is_null() {
            return Err(FfiFailure::new(
                CfStatus::NullPointer,
                "context or out_plan_json is null",
            ));
        }
        unsafe { ptr::write(out_plan_json, ptr::null_mut()) };
        let request_text = unsafe { read_utf8(request_json, "request_json") }?;
        let request: LaunchRequest = serde_json::from_str(&request_text)
            .map_err(|error| FfiFailure::new(CfStatus::InvalidJson, format!("invalid launch request JSON: {error}")))?;
        let context = unsafe { &*context };
        let plan = PolicyEngine::compile(&context.config, &request)
            .map_err(|error| FfiFailure::new(CfStatus::PlanningFailed, format!("planning failed: {error}")))?;
        let json = serde_json::to_string_pretty(&plan).map_err(|error| {
            FfiFailure::new(CfStatus::PlanningFailed, format!("plan serialization failed: {error}"))
        })?;
        unsafe { write_owned_string(json, out_plan_json) }
    })
}

/// Copy the current thread's last structured FFI error into an owned string.
///
/// # Safety
///
/// `out_error_json` must be valid for one pointer write. A non-null result must
/// be released with [`cf_string_free`].
#[no_mangle]
pub unsafe extern "C" fn cf_last_error_json(out_error_json: *mut *mut c_char) -> CfStatus {
    if out_error_json.is_null() {
        return CfStatus::NullPointer;
    }
    unsafe { ptr::write(out_error_json, ptr::null_mut()) };
    let value = LAST_ERROR.with(|slot| {
        slot.borrow()
            .as_ref()
            .map(|error| error.to_string_lossy().into_owned())
            .unwrap_or_else(|| r#"{"status":0,"message":""}"#.into())
    });
    match unsafe { write_owned_string(value, out_error_json) } {
        Ok(()) => CfStatus::Ok,
        Err(error) => error.status,
    }
}

/// Release a string returned by CompatForge.
///
/// # Safety
///
/// `value` must be null or a pointer returned by this library that has not
/// already been released.
#[no_mangle]
pub unsafe extern "C" fn cf_string_free(value: *mut c_char) {
    if !value.is_null() {
        let _ = catch_unwind(AssertUnwindSafe(|| unsafe {
            drop(CString::from_raw(value));
        }));
    }
}

/// Release a context returned by CompatForge.
///
/// # Safety
///
/// `context` must be null or a pointer returned by [`cf_context_create`] that
/// has not already been released.
#[no_mangle]
pub unsafe extern "C" fn cf_context_release(context: *mut CfContext) {
    if !context.is_null() {
        let _ = catch_unwind(AssertUnwindSafe(|| unsafe {
            drop(Box::from_raw(context));
        }));
    }
}

fn ffi_boundary(operation: impl FnOnce() -> Result<(), FfiFailure>) -> CfStatus {
    let _ = LAST_ERROR.with(|slot| slot.borrow_mut().take());
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(Ok(())) => CfStatus::Ok,
        Ok(Err(error)) => {
            set_last_error(error.status, &error.message);
            error.status
        }
        Err(_) => {
            set_last_error(CfStatus::Panic, "panic contained at the C ABI boundary");
            CfStatus::Panic
        }
    }
}

unsafe fn read_utf8(value: *const c_char, name: &'static str) -> Result<String, FfiFailure> {
    if value.is_null() {
        return Err(FfiFailure::new(CfStatus::NullPointer, format!("{name} is null")));
    }
    unsafe { CStr::from_ptr(value) }
        .to_str()
        .map(str::to_owned)
        .map_err(|error| FfiFailure::new(CfStatus::InvalidUtf8, format!("{name} is not UTF-8: {error}")))
}

unsafe fn write_owned_string(value: String, output: *mut *mut c_char) -> Result<(), FfiFailure> {
    if output.is_null() {
        return Err(FfiFailure::new(CfStatus::NullPointer, "output pointer is null"));
    }
    let value = CString::new(value)
        .map_err(|_| FfiFailure::new(CfStatus::InvalidArgument, "output contains an interior NUL"))?;
    unsafe { ptr::write(output, value.into_raw()) };
    Ok(())
}

fn set_last_error(status: CfStatus, message: &str) {
    let json = serde_json::json!({
        "status": status as u32,
        "message": message,
    })
    .to_string();
    if let Ok(error) = CString::new(json) {
        LAST_ERROR.with(|slot| {
            let _ = slot.borrow_mut().replace(error);
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use compatforge_domain::LaunchPlan;

    #[test]
    fn reports_stable_versions() {
        assert_eq!(cf_abi_version(), 1);
        assert!(!cf_api_version().is_null());
    }

    #[test]
    fn compiles_a_launch_plan_across_the_c_abi() {
        let config = CString::new(include_str!("../../../examples/context-config.linux-arm64.json")).unwrap();
        let request = CString::new(include_str!("../../../examples/launch-request.json")).unwrap();
        let mut context = ptr::null_mut();
        let mut output = ptr::null_mut();

        unsafe {
            assert_eq!(cf_context_create(config.as_ptr(), &mut context), CfStatus::Ok);
            assert_eq!(cf_compile_launch(context, request.as_ptr(), &mut output), CfStatus::Ok);
            let plan_text = CStr::from_ptr(output).to_str().unwrap();
            let plan: LaunchPlan = serde_json::from_str(plan_text).unwrap();
            assert_eq!(plan.request_id, "018fe3cb-9d12-7b52-b334-1cce0e857fc9");
            cf_string_free(output);
            cf_context_release(context);
        }
    }

    #[test]
    fn contains_json_errors_without_unwinding() {
        let config = CString::new(include_str!("../../../examples/context-config.linux-arm64.json")).unwrap();
        let invalid_request = CString::new("{").unwrap();
        let mut context = ptr::null_mut();
        let mut output = ptr::null_mut();
        let mut error_output = ptr::null_mut();

        unsafe {
            assert_eq!(cf_context_create(config.as_ptr(), &mut context), CfStatus::Ok);
            assert_eq!(
                cf_compile_launch(context, invalid_request.as_ptr(), &mut output),
                CfStatus::InvalidJson
            );
            assert!(output.is_null());
            assert_eq!(cf_last_error_json(&mut error_output), CfStatus::Ok);
            let error_text = CStr::from_ptr(error_output).to_str().unwrap();
            assert!(error_text.contains("invalid launch request JSON"));
            cf_string_free(error_output);
            cf_context_release(context);
        }
    }
}
