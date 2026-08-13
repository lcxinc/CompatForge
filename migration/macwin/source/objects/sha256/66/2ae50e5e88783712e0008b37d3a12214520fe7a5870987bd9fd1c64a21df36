#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>

typedef struct WindowSearch {
    DWORD process_id;
    HWND window;
} WindowSearch;

typedef struct DropFilesPayload {
    DWORD pFiles;
    POINT point;
    BOOL nonClient;
    BOOL wide;
} DropFilesPayload;

typedef struct ButtonSearch {
    HWND button;
} ButtonSearch;

typedef struct DocumentSearch {
    HWND mdi;
    HWND document;
} DocumentSearch;

typedef struct NamedDocumentSearch {
    HWND window;
    DWORD process_id;
} NamedDocumentSearch;

static wchar_t control_diagnostics[4096] = L"";

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

static void write_failure(const wchar_t *path, const wchar_t *stage,
                          DWORD process_id, DWORD error) {
    wchar_t wide[512];
    char utf8[2048];
    HANDLE file;
    DWORD written;
    int length;
    _snwprintf(wide, 512,
               L"PROCESS_ID=%lu\r\nSTAGE=%ls\r\nWIN32_ERROR=%lu\r\n"
               L"SAVED=false\r\n",
               process_id, stage, error);
    length = WideCharToMultiByte(CP_UTF8, 0, wide, -1, utf8, sizeof(utf8),
                                 NULL, NULL);
    if (length <= 1) return;
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    WriteFile(file, utf8, (DWORD)(length - 1), &written, NULL);
    CloseHandle(file);
}

static int click_default_action(HWND window) {
    RECT client;
    LPARAM point;
    if (!GetClientRect(window, &client)) return 0;
    point = MAKELPARAM(client.right - 72, client.bottom - 28);
    SendMessageW(window, WM_MOUSEMOVE, 0, point);
    SendMessageW(window, WM_LBUTTONDOWN, MK_LBUTTON, point);
    SendMessageW(window, WM_LBUTTONUP, 0, point);
    return 1;
}

static int click_client_point(HWND window, int x, int y) {
    LPARAM point = MAKELPARAM(x, y);
    SendMessageW(window, WM_MOUSEMOVE, 0, point);
    SendMessageW(window, WM_LBUTTONDOWN, MK_LBUTTON, point);
    SendMessageW(window, WM_LBUTTONUP, 0, point);
    return 1;
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

static int capture_window(HWND window, const wchar_t *result_path) {
    RECT rect;
    HDC window_dc = NULL, memory_dc = NULL;
    HBITMAP bitmap = NULL, old_bitmap = NULL;
    BITMAPINFOHEADER header = {0};
    BITMAPFILEHEADER file_header = {0};
    BYTE *pixels = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    wchar_t path[2048];
    DWORD pixel_bytes, written;
    int width, height, ok = 0;

    if (!GetWindowRect(window, &rect)) return 0;
    width = rect.right - rect.left;
    height = rect.bottom - rect.top;
    if (width <= 0 || height <= 0) return 0;
    _snwprintf(path, 2048, L"%ls.bmp", result_path);

    window_dc = GetWindowDC(window);
    memory_dc = CreateCompatibleDC(window_dc);
    bitmap = CreateCompatibleBitmap(window_dc, width, height);
    if (!window_dc || !memory_dc || !bitmap) goto cleanup;
    old_bitmap = SelectObject(memory_dc, bitmap);
    if (!PrintWindow(window, memory_dc, 2) &&
        !BitBlt(memory_dc, 0, 0, width, height, window_dc, 0, 0, SRCCOPY)) {
        goto cleanup;
    }

    pixel_bytes = (DWORD)(((width * 32 + 31) / 32) * 4 * height);
    pixels = HeapAlloc(GetProcessHeap(), 0, pixel_bytes);
    if (!pixels) goto cleanup;
    header.biSize = sizeof(header);
    header.biWidth = width;
    header.biHeight = height;
    header.biPlanes = 1;
    header.biBitCount = 32;
    header.biCompression = BI_RGB;
    if (!GetDIBits(memory_dc, bitmap, 0, height, pixels,
                   (BITMAPINFO *)&header, DIB_RGB_COLORS)) goto cleanup;

    file_header.bfType = 0x4d42;
    file_header.bfOffBits = sizeof(file_header) + sizeof(header);
    file_header.bfSize = file_header.bfOffBits + pixel_bytes;
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) goto cleanup;
    if (!WriteFile(file, &file_header, sizeof(file_header), &written, NULL) ||
        written != sizeof(file_header)) goto cleanup;
    if (!WriteFile(file, &header, sizeof(header), &written, NULL) ||
        written != sizeof(header)) goto cleanup;
    if (!WriteFile(file, pixels, pixel_bytes, &written, NULL) ||
        written != pixel_bytes) goto cleanup;
    ok = 1;

cleanup:
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    if (pixels) HeapFree(GetProcessHeap(), 0, pixels);
    if (old_bitmap) SelectObject(memory_dc, old_bitmap);
    if (bitmap) DeleteObject(bitmap);
    if (memory_dc) DeleteDC(memory_dc);
    if (window_dc) ReleaseDC(window, window_dc);
    return ok;
}

static BOOL CALLBACK find_process_window(HWND window, LPARAM parameter) {
    WindowSearch *search = (WindowSearch *)parameter;
    DWORD process_id = 0;
    wchar_t title[512];
    wchar_t class_name[128] = L"";
    BOOL contains_mdi = FALSE;
    GetWindowThreadProcessId(window, &process_id);
    if ((search->process_id && process_id != search->process_id) ||
        !IsWindowVisible(window)) return TRUE;
    if (GetWindowTextW(window, title, 512) <= 0) return TRUE;
    GetClassNameW(window, class_name, 128);
    if (_wcsicmp(class_name, L"SMDIALOG") == 0 ||
        _wcsicmp(title, L"User interface") == 0 ||
        _wcsicmp(title, L"User info") == 0 ||
        _wcsicmp(title, L"Warning") == 0) {
        search->window = window;
        return FALSE;
    }
    EnumChildWindows(window, has_mdi_client, (LPARAM)&contains_mdi);
    if (contains_mdi) {
        search->window = window;
        return FALSE;
    }
    if (!search->window) search->window = window;
    return TRUE;
}

static void enumerate_process_windows(WindowSearch *search) {
    EnumWindows(find_process_window, (LPARAM)search);
    EnumChildWindows(GetDesktopWindow(), find_process_window,
                     (LPARAM)search);
}

static BOOL CALLBACK find_ok_button(HWND window, LPARAM parameter) {
    ButtonSearch *search = (ButtonSearch *)parameter;
    wchar_t title[128] = L"";
    wchar_t class_name[128] = L"";
    GetWindowTextW(window, title, 128);
    GetClassNameW(window, class_name, 128);
    if (GetDlgCtrlID(window) == IDOK ||
        ((wcscmp(class_name, L"Button") == 0 || wcsstr(class_name, L"BUTTON")) &&
         (_wcsicmp(title, L"OK") == 0 || _wcsicmp(title, L"&OK") == 0))) {
        search->button = window;
        return FALSE;
    }
    return TRUE;
}

static BOOL CALLBACK collect_controls(HWND window, LPARAM parameter) {
    wchar_t title[128] = L"";
    wchar_t class_name[128] = L"";
    wchar_t entry[320];
    size_t used;
    (void)parameter;
    GetWindowTextW(window, title, 128);
    GetClassNameW(window, class_name, 128);
    _snwprintf(entry, 320, L"[%ls|%ls|%ld]", class_name, title,
               (long)GetDlgCtrlID(window));
    used = wcslen(control_diagnostics);
    if (used + wcslen(entry) + 1 < 4096) wcscat(control_diagnostics, entry);
    return TRUE;
}

static BOOL CALLBACK find_document_window(HWND window, LPARAM parameter) {
    DocumentSearch *search = (DocumentSearch *)parameter;
    wchar_t class_name[128] = L"";
    GetClassNameW(window, class_name, 128);
    if (wcscmp(class_name, L"SMMDICLIENT") == 0) {
        search->mdi = window;
        search->document = GetWindow(window, GW_CHILD);
        return FALSE;
    }
    return TRUE;
}

static BOOL CALLBACK find_named_document_frame(HWND window, LPARAM parameter) {
    NamedDocumentSearch *search = (NamedDocumentSearch *)parameter;
    wchar_t title[512] = L"";
    wchar_t class_name[128] = L"";
    if (!IsWindowVisible(window)) return TRUE;
    GetWindowTextW(window, title, 512);
    GetClassNameW(window, class_name, 128);
    if (_wcsicmp(class_name, L"tmwMdiFrame") == 0 &&
        wcsstr(title, L"freeoffice-roundtrip") != NULL) {
        search->window = window;
        GetWindowThreadProcessId(window, &search->process_id);
        return FALSE;
    }
    return TRUE;
}

static int send_virtual_key(WORD key, BOOL control) {
    INPUT input[4] = {0};
    UINT count = 0;
    if (control) {
        input[count].type = INPUT_KEYBOARD;
        input[count++].ki.wVk = VK_CONTROL;
    }
    input[count].type = INPUT_KEYBOARD;
    input[count++].ki.wVk = key;
    input[count].type = INPUT_KEYBOARD;
    input[count].ki.wVk = key;
    input[count++].ki.dwFlags = KEYEVENTF_KEYUP;
    if (control) {
        input[count].type = INPUT_KEYBOARD;
        input[count].ki.wVk = VK_CONTROL;
        input[count++].ki.dwFlags = KEYEVENTF_KEYUP;
    }
    return SendInput(count, input, sizeof(INPUT)) == count;
}

static int send_unicode_input(const wchar_t *text) {
    while (*text) {
        INPUT input[2] = {0};
        input[0].type = INPUT_KEYBOARD;
        input[0].ki.wScan = *text;
        input[0].ki.dwFlags = KEYEVENTF_UNICODE;
        input[1] = input[0];
        input[1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
        if (SendInput(2, input, sizeof(INPUT)) != 2) return 0;
        ++text;
    }
    return 1;
}

static int file_write_time(const wchar_t *path, FILETIME *time, DWORD *size) {
    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExW(path, GetFileExInfoStandard, &data)) return 0;
    *time = data.ftLastWriteTime;
    *size = data.nFileSizeLow;
    return 1;
}

static int write_result(const wchar_t *path, const wchar_t *title, DWORD process_id,
                        DWORD old_size, DWORD new_size, int document_ready, int saved) {
    wchar_t wide[6000];
    char utf8[24000];
    int length;
    HANDLE file;
    DWORD written;
    _snwprintf(wide, 6000,
               L"PROCESS_ID=%lu\r\nWINDOW=%ls\r\nINPUT=unicode\r\n"
               L"OLD_SIZE=%lu\r\nNEW_SIZE=%lu\r\nMDI_READY=%s\r\n"
               L"SAVED=%s\r\nCONTROLS=%ls\r\n",
               process_id, title, old_size, new_size,
               document_ready ? L"true" : L"false", saved ? L"true" : L"false",
               control_diagnostics);
    length = WideCharToMultiByte(CP_UTF8, 0, wide, -1, utf8, sizeof(utf8), NULL, NULL);
    if (length <= 1) return 0;
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    WriteFile(file, utf8, (DWORD)(length - 1), &written, NULL);
    CloseHandle(file);
    return written == (DWORD)(length - 1);
}

int wmain(int argc, wchar_t **argv) {
    const wchar_t *application = L"C:\\Program Files (x86)\\SoftMaker FreeOffice 2024\\TextMaker.exe";
    const wchar_t *inserted = L"TextMaker \u4fdd\u5b58\u5f80\u8fd4\u6b63\u5e38 | 2026";
    wchar_t command[2048];
    wchar_t title[512] = L"";
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    WindowSearch search = {0};
    DocumentSearch document_search = {0};
    GUITHREADINFO gui = {0};
    DWORD target_thread;
    DWORD actual_process_id = 0;
    DWORD current_thread = GetCurrentThreadId();
    FILETIME before = {0}, after = {0};
    DWORD old_size = 0, new_size = 0;
    int saw_user_interface = 0;
    int stable_main_samples = 0;
    int saved = 0;

    if (argc != 3) {
        fwprintf(stderr, L"usage: result document\n");
        return 2;
    }
    if (!file_write_time(argv[2], &before, &old_size)) return 3;
    _snwprintf(command, 2048, L"\"%ls\" \"%ls\"", application, argv[2]);
    startup.cb = sizeof(startup);
    if (!CreateProcessW(application, command, NULL, NULL, FALSE, 0, NULL, NULL,
                        &startup, &process)) {
        write_failure(argv[1], L"create-process", 0, GetLastError());
        return 4;
    }
    write_failure(argv[1], L"process-created", process.dwProcessId, 0);
    WaitForInputIdle(process.hProcess, 30000);
    search.process_id = process.dwProcessId;
    for (int attempt = 0; attempt < 120 && !search.window; ++attempt) {
        enumerate_process_windows(&search);
        if (!search.window) Sleep(250);
    }
    if (!search.window) {
        write_failure(argv[1], L"initial-window", process.dwProcessId,
                      GetLastError());
        TerminateProcess(process.hProcess, 5);
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        return 5;
    }
    write_failure(argv[1], L"initial-window-found", process.dwProcessId, 0);

    capture_window(search.window, argv[1]);

    for (int dialog_attempt = 0; dialog_attempt < 40; ++dialog_attempt) {
        wchar_t class_name[128] = L"";
        wchar_t dialog_title[512] = L"";
        ButtonSearch button_search = {0};
        RECT client = {0};
        int is_dialog;
        GetClassNameW(search.window, class_name, 128);
        GetWindowTextW(search.window, dialog_title, 512);
        EnumChildWindows(search.window, collect_controls, 0);
        EnumChildWindows(search.window, find_ok_button, (LPARAM)&button_search);
        is_dialog = button_search.button || wcscmp(class_name, L"#32770") == 0 ||
                    _wcsicmp(class_name, L"SMDIALOG") == 0 ||
                    _wcsicmp(dialog_title, L"User interface") == 0 ||
                    _wcsicmp(dialog_title, L"User info") == 0 ||
                    _wcsicmp(dialog_title, L"Warning") == 0;
        if (!is_dialog) {
            if (++stable_main_samples >= 10) break;
            Sleep(500);
            search.window = NULL;
            enumerate_process_windows(&search);
            continue;
        }
        stable_main_samples = 0;
        if (button_search.button) {
            SendMessageW(button_search.button, BM_CLICK, 0, 0);
        } else if (_wcsicmp(dialog_title, L"User interface") == 0) {
            saw_user_interface = 1;
            click_default_action(search.window);
        } else if (_wcsicmp(dialog_title, L"User info") == 0 &&
                   GetClientRect(search.window, &client)) {
            click_client_point(search.window, client.right - 65, 67);
        } else if (_wcsicmp(dialog_title, L"Warning") == 0 &&
                   GetClientRect(search.window, &client)) {
            click_client_point(search.window, 70, client.bottom - 66);
            click_client_point(search.window, client.right - 123,
                               client.bottom - 28);
        } else {
            SendMessageW(search.window, WM_COMMAND, MAKEWPARAM(IDOK, BN_CLICKED), 0);
        }
        Sleep(1000);
        search.window = NULL;
        for (int attempt = 0; attempt < 20 && !search.window; ++attempt) {
            enumerate_process_windows(&search);
            if (!search.window) Sleep(250);
        }
        if (!search.window) break;
    }
    if (!search.window) {
        write_failure(argv[1], L"dialog-transition", process.dwProcessId,
                      GetLastError());
        TerminateProcess(process.hProcess, 12);
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        return 12;
    }
    write_failure(argv[1], L"dialog-complete", process.dwProcessId, 0);

    search.window = NULL;
    for (int attempt = 0; attempt < 120 && !search.window; ++attempt) {
        enumerate_process_windows(&search);
        if (!search.window) Sleep(250);
    }
    if (!search.window) {
        write_failure(argv[1], L"document-window", process.dwProcessId,
                      GetLastError());
        TerminateProcess(process.hProcess, 13);
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        return 13;
    }
    write_failure(argv[1], L"document-frame-found", process.dwProcessId, 0);
    if (saw_user_interface) {
        STARTUPINFOW reopen_startup = {0};
        PROCESS_INFORMATION reopen_process = {0};
        reopen_startup.cb = sizeof(reopen_startup);
        if (CreateProcessW(application, command, NULL, NULL, FALSE, 0, NULL, NULL,
                           &reopen_startup, &reopen_process)) {
            WaitForInputIdle(reopen_process.hProcess, 15000);
            CloseHandle(reopen_process.hThread);
            CloseHandle(reopen_process.hProcess);
            Sleep(5000);
        }
    }
    ShellExecuteW(NULL, L"open", argv[2], NULL, NULL, SW_SHOWNORMAL);
    {
        NamedDocumentSearch named = {0};
        for (int attempt = 0; attempt < 60 && !named.window; ++attempt) {
            EnumWindows(find_named_document_frame, (LPARAM)&named);
            if (!named.window) Sleep(250);
        }
        if (named.window) {
            search.window = named.window;
            search.process_id = named.process_id;
        }
    }
    drop_file(search.window, argv[2]);
    Sleep(5000);
    search.window = NULL;
    for (int attempt = 0; attempt < 40 && !search.window; ++attempt) {
        enumerate_process_windows(&search);
        if (!search.window) Sleep(250);
    }
    if (!search.window) {
        write_failure(argv[1], L"document-reopen-window", process.dwProcessId,
                      GetLastError());
        TerminateProcess(process.hProcess, 14);
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
        return 14;
    }
    GetWindowTextW(search.window, title, 512);
    GetWindowThreadProcessId(search.window, &actual_process_id);
    for (int attempt = 0; attempt < 20 && !document_search.document; ++attempt) {
        document_search.mdi = NULL;
        EnumChildWindows(search.window, find_document_window,
                         (LPARAM)&document_search);
        if (!document_search.document) Sleep(250);
    }
    if (!document_search.document && document_search.mdi) {
        document_search.document = document_search.mdi;
    }
    if (!document_search.document && drop_file(search.window, argv[2])) {
        for (int attempt = 0; attempt < 120 && !document_search.document; ++attempt) {
            document_search.mdi = NULL;
            EnumChildWindows(search.window, find_document_window,
                             (LPARAM)&document_search);
            if (!document_search.document) Sleep(250);
        }
    }
    control_diagnostics[0] = L'\0';
    EnumChildWindows(search.window, collect_controls, 0);
    write_failure(argv[1], L"document-target-ready", process.dwProcessId, 0);
    target_thread = GetWindowThreadProcessId(search.window, NULL);
    gui.cbSize = sizeof(gui);
    GetGUIThreadInfo(target_thread, &gui);
    AttachThreadInput(current_thread, target_thread, TRUE);
    ShowWindow(search.window, SW_RESTORE);
    BringWindowToTop(search.window);
    SetForegroundWindow(search.window);
    if (document_search.document) SetFocus(document_search.document);
    else if (gui.hwndFocus) SetFocus(gui.hwndFocus);
    Sleep(1000);
    write_failure(argv[1], L"focus-ready", process.dwProcessId, 0);

    gui.cbSize = sizeof(gui);
    if (GetGUIThreadInfo(target_thread, &gui) && gui.hwndFocus &&
        IsWindow(gui.hwndFocus)) {
        document_search.document = gui.hwndFocus;
    } else {
        document_search.mdi = NULL;
        document_search.document = NULL;
        EnumChildWindows(search.window, find_document_window,
                         (LPARAM)&document_search);
        if (!document_search.document) document_search.document = document_search.mdi;
    }
    if (!document_search.document || !IsWindow(document_search.document)) {
        document_search.document = search.window;
    }
    BringWindowToTop(search.window);
    SetForegroundWindow(search.window);
    SetFocus(document_search.document);
    if (!send_virtual_key(VK_END, TRUE)) {
        write_failure(argv[1], L"post-end", process.dwProcessId, GetLastError());
        return 6;
    }
    if (!send_virtual_key(VK_RETURN, FALSE)) {
        write_failure(argv[1], L"post-enter", process.dwProcessId, GetLastError());
        return 7;
    }
    if (document_search.document) {
        if (!send_unicode_input(inserted)) {
            write_failure(argv[1], L"post-unicode", process.dwProcessId,
                          GetLastError());
            return 8;
        }
    } else {
        return 8;
    }
    Sleep(500);
    if (!send_virtual_key('S', TRUE)) {
        write_failure(argv[1], L"post-save", process.dwProcessId, GetLastError());
        return 9;
    }
    AttachThreadInput(current_thread, target_thread, FALSE);
    write_failure(argv[1], L"save-requested", process.dwProcessId, 0);

    for (int attempt = 0; attempt < 60; ++attempt) {
        Sleep(250);
        if (!file_write_time(argv[2], &after, &new_size)) continue;
        if (CompareFileTime(&after, &before) > 0) {
            saved = 1;
            break;
        }
    }
    PostMessageW(search.window, WM_CLOSE, 0, 0);
    write_failure(argv[1], L"close-requested", process.dwProcessId, 0);
    if (WaitForSingleObject(process.hProcess, 10000) == WAIT_TIMEOUT) {
        PostMessageW(search.window, WM_CLOSE, 0, 0);
        if (WaitForSingleObject(process.hProcess, 5000) == WAIT_TIMEOUT) {
            TerminateProcess(process.hProcess, 10);
        }
    }
    write_result(argv[1], title, actual_process_id, old_size, new_size,
                 document_search.document != NULL, saved);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return saved ? 0 : 11;
}
