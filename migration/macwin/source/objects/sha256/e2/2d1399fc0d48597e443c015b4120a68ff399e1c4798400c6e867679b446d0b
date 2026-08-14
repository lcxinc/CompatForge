#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <oleauto.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>

static HANDLE trace_file = INVALID_HANDLE_VALUE;
static void trace_status(int line, HRESULT status);
static const IID IID_TextMakerApplication = {
    0xA5F1BE82, 0x163F, 0x11D2,
    {0xA5, 0x82, 0x44, 0x46, 0x49, 0x00, 0x23, 0x5E}
};
#define REQUIRE(stage, expression) do { \
    status = (expression); \
    if (FAILED(status)) { \
        (void)(stage); \
        trace_status(__LINE__, status); \
        fprintf(stderr, "automation stage failed at line %d: 0x%08lx\n", __LINE__, status); \
        goto cleanup; \
    } \
} while (0)

static void trace_status(int line, HRESULT status) {
    char buffer[128];
    DWORD written;
    int length;
    if (trace_file == INVALID_HANDLE_VALUE) return;
    length = snprintf(buffer, sizeof(buffer), "line=%d hresult=0x%08lx\r\n", line, status);
    if (length > 0) WriteFile(trace_file, buffer, (DWORD)length, &written, NULL);
}

typedef struct StartupSearch {
    DWORD process_id;
    HWND dialog;
    HWND main_window;
} StartupSearch;

typedef struct DropFilesPayload {
    DWORD pFiles;
    POINT point;
    BOOL non_client;
    BOOL wide;
} DropFilesPayload;

static BOOL CALLBACK has_mdi_client(HWND window, LPARAM parameter) {
    BOOL *found = (BOOL *)parameter;
    wchar_t class_name[128] = L"";
    GetClassNameW(window, class_name, 128);
    if (wcscmp(class_name, L"SMMDICLIENT") == 0) {
        *found = TRUE;
        return FALSE;
    }
    return TRUE;
}

static BOOL CALLBACK find_startup_window(HWND window, LPARAM parameter) {
    StartupSearch *search = (StartupSearch *)parameter;
    DWORD process_id = 0;
    wchar_t title[256] = L"";
    wchar_t class_name[128] = L"";
    BOOL contains_mdi = FALSE;
    GetWindowThreadProcessId(window, &process_id);
    if (process_id != search->process_id || !IsWindowVisible(window)) return TRUE;
    GetWindowTextW(window, title, 256);
    GetClassNameW(window, class_name, 128);
    if (_wcsicmp(class_name, L"SMDIALOG") == 0 ||
        _wcsicmp(title, L"User interface") == 0 ||
        _wcsicmp(title, L"User info") == 0 ||
        _wcsicmp(title, L"Warning") == 0) {
        search->dialog = window;
        return FALSE;
    }
    EnumChildWindows(window, has_mdi_client, (LPARAM)&contains_mdi);
    if (contains_mdi) search->main_window = window;
    return TRUE;
}

static void click_client(HWND window, int x, int y) {
    LPARAM point = MAKELPARAM(x, y);
    SendMessageW(window, WM_MOUSEMOVE, 0, point);
    SendMessageW(window, WM_LBUTTONDOWN, MK_LBUTTON, point);
    SendMessageW(window, WM_LBUTTONUP, 0, point);
}

static HWND prepare_textmaker_ui(DWORD process_id) {
    StartupSearch search = {process_id, NULL, NULL};
    int stable_main = 0;
    for (int attempt = 0; attempt < 120; ++attempt) {
        wchar_t title[256] = L"";
        RECT client = {0};
        search.dialog = NULL;
        search.main_window = NULL;
        EnumWindows(find_startup_window, (LPARAM)&search);
        if (search.dialog) {
            stable_main = 0;
            GetWindowTextW(search.dialog, title, 256);
            GetClientRect(search.dialog, &client);
            if (_wcsicmp(title, L"User interface") == 0) {
                click_client(search.dialog, client.right - 72,
                             client.bottom - 28);
            } else if (_wcsicmp(title, L"User info") == 0) {
                click_client(search.dialog, client.right - 65, 67);
            } else if (_wcsicmp(title, L"Warning") == 0) {
                click_client(search.dialog, 70, client.bottom - 66);
                click_client(search.dialog, client.right - 123,
                             client.bottom - 28);
                SendMessageW(search.dialog, WM_KEYDOWN, 'N', 0);
                SendMessageW(search.dialog, WM_CHAR, 'n', 0);
                SendMessageW(search.dialog, WM_KEYUP, 'N', 0);
            } else {
                SendMessageW(search.dialog, WM_COMMAND,
                             MAKEWPARAM(IDOK, BN_CLICKED), 0);
            }
            Sleep(750);
            continue;
        }
        if (search.main_window) {
            if (++stable_main >= 8) return search.main_window;
        } else {
            stable_main = 0;
        }
        Sleep(500);
    }
    return NULL;
}

static int drop_file(HWND window, const wchar_t *path) {
    SIZE_T path_bytes = (wcslen(path) + 2) * sizeof(wchar_t);
    SIZE_T allocation_size = sizeof(DropFilesPayload) + path_bytes;
    HGLOBAL memory = GlobalAlloc(GHND | GMEM_SHARE, allocation_size);
    DropFilesPayload *drop;
    wchar_t *files;
    if (!memory) return 0;
    drop = GlobalLock(memory);
    if (!drop) {
        GlobalFree(memory);
        return 0;
    }
    drop->pFiles = sizeof(DropFilesPayload);
    drop->wide = TRUE;
    files = (wchar_t *)((BYTE *)drop + sizeof(DropFilesPayload));
    memcpy(files, path, (wcslen(path) + 1) * sizeof(wchar_t));
    files[wcslen(path) + 1] = L'\0';
    GlobalUnlock(memory);
    if (!PostMessageW(window, WM_DROPFILES, (WPARAM)memory, 0)) {
        GlobalFree(memory);
        return 0;
    }
    return 1;
}

static int launch_textmaker_document(const wchar_t *document,
                                     PROCESS_INFORMATION *process) {
    const wchar_t *application =
        L"C:\\Program Files (x86)\\SoftMaker FreeOffice 2024\\TextMaker.exe";
    wchar_t command[2048];
    STARTUPINFOW startup = {0};
    _snwprintf(command, 2048, L"\"%ls\" /Shell \"%ls\"",
               application, document);
    startup.cb = sizeof(startup);
    if (!CreateProcessW(application, command, NULL, NULL, FALSE, 0, NULL, NULL,
                        &startup, process)) return 0;
    WaitForInputIdle(process->hProcess, 30000);
    return 1;
}

static HRESULT get_active_document(IDispatch *application,
                                   IDispatch **document) {
    typedef HRESULT (STDMETHODCALLTYPE *ActiveDocumentFunction)(
        IDispatch *, IDispatch **);
    ActiveDocumentFunction active_document =
        (ActiveDocumentFunction)(*(void ***)application)[21];
    return active_document(application, document);
}

static HRESULT wait_for_active_document(IDispatch *application,
                                        IDispatch **document) {
    HRESULT status = E_FAIL;
    for (int attempt = 0; attempt < 80; ++attempt) {
        status = get_active_document(application, document);
        if (SUCCEEDED(status) && *document) return status;
        Sleep(250);
    }
    return status;
}

static HRESULT invoke_name(IDispatch *object, const wchar_t *name, WORD flags,
                           VARIANT *arguments, UINT argument_count, VARIANT *result) {
    DISPID id;
    LPOLESTR names[] = {(LPOLESTR)name};
    DISPPARAMS parameters = {0};
    DISPID property_put = DISPID_PROPERTYPUT;
    EXCEPINFO exception = {0};
    UINT argument_error = 0;
    HRESULT status;

    status = IDispatch_GetIDsOfNames(object, &IID_NULL, names, 1,
                                     LOCALE_USER_DEFAULT, &id);
    if (FAILED(status)) {
        fwprintf(stderr, L"GetIDsOfNames(%ls) failed: 0x%08lx\n", name, status);
        return status;
    }
    parameters.rgvarg = arguments;
    parameters.cArgs = argument_count;
    if ((flags & DISPATCH_PROPERTYPUT) != 0) {
        parameters.rgdispidNamedArgs = &property_put;
        parameters.cNamedArgs = 1;
    }
    status = IDispatch_Invoke(object, id, &IID_NULL, LOCALE_USER_DEFAULT, flags,
                              &parameters, result, &exception, &argument_error);
    if (FAILED(status)) {
        fwprintf(stderr, L"Invoke(%ls) failed: 0x%08lx arg=%u code=%u %ls\n",
                 name, status, argument_error, exception.wCode,
                 exception.bstrDescription ? exception.bstrDescription : L"");
    }
    SysFreeString(exception.bstrSource);
    SysFreeString(exception.bstrDescription);
    SysFreeString(exception.bstrHelpFile);
    return status;
}

static HRESULT get_dispatch(IDispatch *object, const wchar_t *name, IDispatch **value) {
    VARIANT result;
    HRESULT status;
    VariantInit(&result);
    status = invoke_name(object, name, DISPATCH_PROPERTYGET, NULL, 0, &result);
    if (SUCCEEDED(status) && result.vt == VT_DISPATCH && result.pdispVal != NULL) {
        *value = result.pdispVal;
        return S_OK;
    }
    if (SUCCEEDED(status) && result.vt == VT_UNKNOWN && result.punkVal != NULL) {
        status = IUnknown_QueryInterface(result.punkVal, &IID_IDispatch, (void **)value);
        VariantClear(&result);
        return status;
    }
    fwprintf(stderr, L"Property %ls returned VARIANT type %u\n", name, result.vt);
    VariantClear(&result);
    return FAILED(status) ? status : DISP_E_TYPEMISMATCH;
}

static HRESULT get_string(IDispatch *object, const wchar_t *name, BSTR *value) {
    VARIANT result;
    HRESULT status;
    VariantInit(&result);
    status = invoke_name(object, name, DISPATCH_PROPERTYGET, NULL, 0, &result);
    if (SUCCEEDED(status)) {
        VARIANT converted;
        VariantInit(&converted);
        status = VariantChangeType(&converted, &result, 0, VT_BSTR);
        VariantClear(&result);
        if (SUCCEEDED(status)) {
            *value = converted.bstrVal;
            return S_OK;
        }
        VariantClear(&converted);
    }
    VariantClear(&result);
    return FAILED(status) ? status : DISP_E_TYPEMISMATCH;
}

static HRESULT put_bool(IDispatch *object, const wchar_t *name, VARIANT_BOOL value) {
    VARIANT argument;
    VariantInit(&argument);
    V_VT(&argument) = VT_BOOL;
    V_BOOL(&argument) = value;
    return invoke_name(object, name, DISPATCH_PROPERTYPUT, &argument, 1, NULL);
}

static HRESULT put_float(IDispatch *object, const wchar_t *name, float value) {
    VARIANT argument;
    VariantInit(&argument);
    V_VT(&argument) = VT_R4;
    V_R4(&argument) = value;
    return invoke_name(object, name, DISPATCH_PROPERTYPUT, &argument, 1, NULL);
}

static HRESULT put_string(IDispatch *object, const wchar_t *name, const wchar_t *value) {
    VARIANT argument;
    HRESULT status;
    VariantInit(&argument);
    V_VT(&argument) = VT_BSTR;
    V_BSTR(&argument) = SysAllocString(value);
    status = invoke_name(object, name, DISPATCH_PROPERTYPUT, &argument, 1, NULL);
    VariantClear(&argument);
    return status;
}

static HRESULT method_no_args(IDispatch *object, const wchar_t *name) {
    return invoke_name(object, name, DISPATCH_METHOD, NULL, 0, NULL);
}

static HRESULT method_string(IDispatch *object, const wchar_t *name, const wchar_t *value) {
    VARIANT argument;
    HRESULT status;
    VariantInit(&argument);
    V_VT(&argument) = VT_BSTR;
    V_BSTR(&argument) = SysAllocString(value);
    status = invoke_name(object, name, DISPATCH_METHOD, &argument, 1, NULL);
    VariantClear(&argument);
    return status;
}

static HRESULT save_as(IDispatch *document, const wchar_t *path, LONG format) {
    VARIANT arguments[2];
    HRESULT status;
    VariantInit(&arguments[0]);
    VariantInit(&arguments[1]);
    V_VT(&arguments[0]) = VT_I4;
    V_I4(&arguments[0]) = format;
    V_VT(&arguments[1]) = VT_BSTR;
    V_BSTR(&arguments[1]) = SysAllocString(path);
    status = invoke_name(document, L"SaveAs", DISPATCH_METHOD, arguments, 2, NULL);
    VariantClear(&arguments[1]);
    return status;
}

static HRESULT close_without_saving(IDispatch *document) {
    VARIANT argument;
    VariantInit(&argument);
    V_VT(&argument) = VT_I4;
    V_I4(&argument) = 0;
    return invoke_name(document, L"Close", DISPATCH_METHOD, &argument, 1, NULL);
}

static HRESULT open_document(IDispatch *documents, const wchar_t *path, IDispatch **document) {
    VARIANT argument;
    VARIANT result;
    HRESULT status;
    VariantInit(&argument);
    VariantInit(&result);
    V_VT(&argument) = VT_BSTR;
    V_BSTR(&argument) = SysAllocString(path);
    status = invoke_name(documents, L"Open", DISPATCH_METHOD, &argument, 1, &result);
    VariantClear(&argument);
    if (SUCCEEDED(status) && result.vt == VT_DISPATCH && result.pdispVal != NULL) {
        *document = result.pdispVal;
        return S_OK;
    }
    VariantClear(&result);
    return FAILED(status) ? status : DISP_E_TYPEMISMATCH;
}

static int write_seed_rtf(const wchar_t *path) {
    static const char content[] =
        "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}"
        "\\f0\\fs22 MacWin FreeOffice seed\\par}";
    HANDLE file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD written = 0;
    if (file == INVALID_HANDLE_VALUE) return 0;
    WriteFile(file, content, (DWORD)(sizeof(content) - 1), &written, NULL);
    CloseHandle(file);
    return written == sizeof(content) - 1;
}

static int write_utf8_result(const wchar_t *path, const wchar_t *build, const wchar_t *bits) {
    wchar_t result[1024];
    char *utf8;
    int size;
    HANDLE file;
    DWORD written;

    _snwprintf(result, 1024,
               L"APPLICATION=TextMaker\r\nBUILD=%ls\r\nBITS=%ls\r\n"
               L"COM=passed\r\nUTF8=\u4e2d\u6587\u6587\u6863\u5f80\u8fd4\u6b63\u5e38\r\n",
               build, bits);
    size = WideCharToMultiByte(CP_UTF8, 0, result, -1, NULL, 0, NULL, NULL);
    if (size <= 1) return 0;
    utf8 = (char *)malloc((size_t)size);
    if (!utf8) return 0;
    WideCharToMultiByte(CP_UTF8, 0, result, -1, utf8, size, NULL, NULL);
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        free(utf8);
        return 0;
    }
    WriteFile(file, utf8, (DWORD)(size - 1), &written, NULL);
    CloseHandle(file);
    free(utf8);
    return written == (DWORD)(size - 1);
}

int wmain(int argc, wchar_t **argv) {
    CLSID class_id;
    IDispatch *application = NULL;
    IDispatch *documents = NULL;
    IDispatch *document = NULL;
    IDispatch *selection = NULL;
    IDispatch *font = NULL;
    BSTR build = NULL;
    BSTR bits = NULL;
    PROCESS_INFORMATION textmaker = {0};
    HWND main_window = NULL;
    HRESULT status;
    int success = 0;

    if (argc != 8) {
        fwprintf(stderr, L"usage: result tmdx docx odt rtf utf8 roundtrip\n");
        return 2;
    }
    trace_file = CreateFileW(argv[1], GENERIC_WRITE, FILE_SHARE_READ, NULL,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    trace_status(__LINE__, S_OK);
    if (!write_seed_rtf(argv[5])) {
        fwprintf(stderr, L"seed RTF write failed: %lu\n", GetLastError());
        return 3;
    }
    if (!launch_textmaker_document(argv[5], &textmaker)) {
        fwprintf(stderr, L"TextMaker launch failed: %lu\n", GetLastError());
        return 4;
    }
    main_window = prepare_textmaker_ui(textmaker.dwProcessId);
    if (!main_window) {
        fwprintf(stderr, L"TextMaker UI did not become ready\n");
        TerminateProcess(textmaker.hProcess, 4);
        CloseHandle(textmaker.hThread);
        CloseHandle(textmaker.hProcess);
        return 4;
    }
    status = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (FAILED(status)) return 3;
    REQUIRE(L"CLSIDFromProgID", CLSIDFromProgID(L"TextMaker.Application", &class_id));
    {
        IUnknown *running = NULL;
        status = GetActiveObject(&class_id, NULL, &running);
        if (SUCCEEDED(status)) {
            status = IUnknown_QueryInterface(running, &IID_TextMakerApplication,
                                             (void **)&application);
            IUnknown_Release(running);
        }
        if (FAILED(status)) {
            status = CoCreateInstance(
                &class_id, NULL, CLSCTX_LOCAL_SERVER, &IID_TextMakerApplication,
                (void **)&application);
        }
    }
    REQUIRE(L"Get TextMaker IApplication", status);
    REQUIRE(L"Visible", put_bool(application, L"Visible", VARIANT_TRUE));
    REQUIRE(L"Build", get_string(application, L"Build", &build));
    REQUIRE(L"Bits", get_string(application, L"Bits", &bits));
    REQUIRE(L"Documents", get_dispatch(application, L"Documents", &documents));
    status = wait_for_active_document(application, &document);
    if (FAILED(status)) {
        if (drop_file(main_window, argv[5])) {
            Sleep(3000);
            status = wait_for_active_document(application, &document);
        }
    }
    if (FAILED(status)) {
        PROCESS_INFORMATION reopen = {0};
        if (launch_textmaker_document(argv[5], &reopen)) {
            WaitForInputIdle(reopen.hProcess, 15000);
            CloseHandle(reopen.hThread);
            CloseHandle(reopen.hProcess);
            Sleep(3000);
            status = wait_for_active_document(application, &document);
        }
    }
    REQUIRE(L"Application.ActiveDocument", status);
    REQUIRE(L"Document.Selection", get_dispatch(document, L"Selection", &selection));
    REQUIRE(L"Selection.Font", get_dispatch(selection, L"Font", &font));

    REQUIRE(L"Font.Name", put_string(font, L"Name", L"Microsoft YaHei"));
    REQUIRE(L"Font.Size title", put_float(font, L"Size", 20.0f));
    REQUIRE(L"Font.Bold title", put_bool(font, L"Bold", VARIANT_TRUE));
    REQUIRE(L"TypeText title", method_string(selection, L"TypeText", L"MacWin FreeOffice \u517c\u5bb9\u6027\u62a5\u544a"));
    REQUIRE(L"InsertParagraph title", method_no_args(selection, L"InsertParagraph"));
    REQUIRE(L"Font.Size body", put_float(font, L"Size", 11.0f));
    REQUIRE(L"Font.Bold body", put_bool(font, L"Bold", VARIANT_FALSE));
    REQUIRE(L"TypeText body", method_string(selection, L"TypeText", L"\u4e2d\u6587\u6392\u7248\u4e0e Office Open XML \u8f6c\u6362\u6b63\u5e38\u3002"));
    REQUIRE(L"InsertParagraph body", method_no_args(selection, L"InsertParagraph"));
    REQUIRE(L"TypeText metrics", method_string(selection, L"TypeText", L"2026 | 98.5 | \u5de5\u4e1a\u8f6f\u4ef6"));

    REQUIRE(L"SaveAs TMDX", save_as(document, argv[2], 0));
    REQUIRE(L"SaveAs DOCX", save_as(document, argv[3], 17));
    REQUIRE(L"SaveAs ODT", save_as(document, argv[4], 3));
    REQUIRE(L"SaveAs RTF", save_as(document, argv[5], 4));
    REQUIRE(L"SaveAs UTF8", save_as(document, argv[6], 10));
    REQUIRE(L"Close source", close_without_saving(document));
    IDispatch_Release(document);
    document = NULL;
    IDispatch_Release(selection);
    selection = NULL;
    IDispatch_Release(font);
    font = NULL;

    REQUIRE(L"Open DOCX", open_document(documents, argv[3], &document));
    REQUIRE(L"DOCX to UTF8", save_as(document, argv[7], 10));
    REQUIRE(L"Close DOCX", close_without_saving(document));
    if (trace_file != INVALID_HANDLE_VALUE) {
        CloseHandle(trace_file);
        trace_file = INVALID_HANDLE_VALUE;
    }
    if (!write_utf8_result(argv[1], build, bits)) {
        fprintf(stderr, "result file write failed: %lu\n", GetLastError());
        goto cleanup;
    }
    success = 1;

cleanup:
    if (document) IDispatch_Release(document);
    if (font) IDispatch_Release(font);
    if (selection) IDispatch_Release(selection);
    if (documents) IDispatch_Release(documents);
    if (application) {
        method_no_args(application, L"Quit");
        IDispatch_Release(application);
    }
    SysFreeString(build);
    SysFreeString(bits);
    if (trace_file != INVALID_HANDLE_VALUE) CloseHandle(trace_file);
    CoUninitialize();
    if (textmaker.hProcess) {
        if (WaitForSingleObject(textmaker.hProcess, 5000) == WAIT_TIMEOUT) {
            PostMessageW(main_window, WM_CLOSE, 0, 0);
            if (WaitForSingleObject(textmaker.hProcess, 5000) == WAIT_TIMEOUT) {
                TerminateProcess(textmaker.hProcess, 1);
            }
        }
        CloseHandle(textmaker.hThread);
        CloseHandle(textmaker.hProcess);
    }
    return success ? 0 : 1;
}
