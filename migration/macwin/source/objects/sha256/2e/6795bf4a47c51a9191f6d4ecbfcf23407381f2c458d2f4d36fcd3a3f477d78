#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <stdio.h>

typedef struct WindowSearch {
    DWORD process_id;
    HWND candidate;
    HWND main_window;
} WindowSearch;

typedef struct DialogSearch {
    DWORD process_id;
    const wchar_t *title;
    HWND warning;
} DialogSearch;

static wchar_t window_diagnostics[32768] = L"";
static int click_default_action(HWND window);

static void append_window_diagnostic(HWND window, const wchar_t *kind) {
    wchar_t title[512] = L"";
    wchar_t class_name[128] = L"";
    wchar_t entry[1400];
    RECT rect = {0};
    LONG_PTR style = GetWindowLongPtrW(window, GWL_STYLE);
    LONG_PTR extended_style = GetWindowLongPtrW(window, GWL_EXSTYLE);
    GetWindowTextW(window, title, 512);
    GetClassNameW(window, class_name, 128);
    GetWindowRect(window, &rect);
    _snwprintf(entry, 1400,
               L"[%ls HWND=%p ID=%d CLASS=%ls TITLE=%ls VISIBLE=%d "
               L"ENABLED=%d OWNER=%p PARENT=%p RECT=%ld,%ld,%ld,%ld "
               L"STYLE=0x%Ix EXSTYLE=0x%Ix]",
               kind, window, GetDlgCtrlID(window), class_name, title,
               IsWindowVisible(window), IsWindowEnabled(window),
               GetWindow(window, GW_OWNER), GetParent(window), rect.left,
               rect.top, rect.right, rect.bottom, style, extended_style);
    if (wcslen(window_diagnostics) + wcslen(entry) + 1 < 32768) {
        wcscat(window_diagnostics, entry);
    }
}

static BOOL CALLBACK collect_child_window(HWND window, LPARAM parameter) {
    (void)parameter;
    append_window_diagnostic(window, L"CHILD");
    return TRUE;
}

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

static BOOL CALLBACK find_window(HWND window, LPARAM parameter) {
    WindowSearch *search = (WindowSearch *)parameter;
    DWORD process_id = 0;
    wchar_t title[512] = L"";
    BOOL contains_mdi = FALSE;
    GetWindowThreadProcessId(window, &process_id);
    if (process_id != search->process_id || !IsWindowVisible(window)) return TRUE;
    if (GetWindowTextW(window, title, 512) <= 0) return TRUE;
    EnumChildWindows(window, has_mdi_client, (LPARAM)&contains_mdi);
    if (contains_mdi) {
        search->main_window = window;
        return FALSE;
    }
    if (!search->candidate) search->candidate = window;
    return TRUE;
}

static void enumerate_windows(WindowSearch *search) {
    EnumWindows(find_window, (LPARAM)search);
    EnumChildWindows(GetDesktopWindow(), find_window, (LPARAM)search);
}

static BOOL CALLBACK close_process_window(HWND window, LPARAM parameter) {
    DWORD process_id = 0;
    DWORD target_process_id = (DWORD)parameter;
    GetWindowThreadProcessId(window, &process_id);
    if (process_id == target_process_id) {
        PostMessageW(window, WM_CLOSE, 0, 0);
    }
    return TRUE;
}

static void close_process_windows(DWORD process_id) {
    EnumWindows(close_process_window, (LPARAM)process_id);
}

static int capture_window(HWND window, const wchar_t *path) {
    RECT rect;
    HDC window_dc = NULL, memory_dc = NULL;
    HBITMAP bitmap = NULL, old_bitmap = NULL;
    BITMAPINFOHEADER header = {0};
    BITMAPFILEHEADER file_header = {0};
    BYTE *pixels = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    DWORD pixel_bytes, written;
    int width, height, ok = 0;

    if (!GetWindowRect(window, &rect)) return 0;
    width = rect.right - rect.left;
    height = rect.bottom - rect.top;
    if (width <= 0 || height <= 0) return 0;
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

static BOOL CALLBACK find_warning_dialog(HWND window, LPARAM parameter) {
    DialogSearch *search = (DialogSearch *)parameter;
    DWORD process_id = 0;
    wchar_t title[128] = L"";
    wchar_t class_name[128] = L"";
    GetWindowThreadProcessId(window, &process_id);
    if (process_id != search->process_id || !IsWindowVisible(window) ||
        !IsWindowEnabled(window)) return TRUE;
    GetWindowTextW(window, title, 128);
    GetClassNameW(window, class_name, 128);
    if (_wcsicmp(class_name, L"SMDIALOG") == 0 &&
        _wcsicmp(title, search->title) == 0) {
        search->warning = window;
        return FALSE;
    }
    return TRUE;
}

static int dismiss_save_warning(DWORD process_id) {
    DialogSearch search = {process_id, L"Warning", NULL};
    RECT client;
    LPARAM point;
    for (int attempt = 0; attempt < 40 && !search.warning; ++attempt) {
        EnumWindows(find_warning_dialog, (LPARAM)&search);
        if (!search.warning) Sleep(250);
    }
    if (!search.warning) return 0;
    capture_window(search.warning,
                   L"C:\\MacWinTests\\freeoffice-warning.bmp");
    SetForegroundWindow(search.warning);
    if (GetClientRect(search.warning, &client)) {
        point = MAKELPARAM(70, client.bottom - 66);
        SendMessageW(search.warning, WM_MOUSEMOVE, 0, point);
        SendMessageW(search.warning, WM_LBUTTONDOWN, MK_LBUTTON, point);
        SendMessageW(search.warning, WM_LBUTTONUP, 0, point);
        point = MAKELPARAM(client.right - 45, client.bottom - 28);
        SendMessageW(search.warning, WM_MOUSEMOVE, 0, point);
        SendMessageW(search.warning, WM_LBUTTONDOWN, MK_LBUTTON, point);
        SendMessageW(search.warning, WM_LBUTTONUP, 0, point);
    }
    SendMessageW(search.warning, WM_KEYDOWN, 'N', 0);
    SendMessageW(search.warning, WM_CHAR, 'n', 0);
    SendMessageW(search.warning, WM_KEYUP, 'N', 0);
    SendMessageW(search.warning, WM_COMMAND, MAKEWPARAM(IDNO, BN_CLICKED), 0);
    return 1;
}

static int dismiss_user_info(DWORD process_id) {
    DialogSearch search = {process_id, L"User info", NULL};
    for (int attempt = 0; attempt < 40 && !search.warning; ++attempt) {
        EnumWindows(find_warning_dialog, (LPARAM)&search);
        if (!search.warning) Sleep(250);
    }
    if (!search.warning) return 0;
    {
        RECT client;
        LPARAM point;
        const wchar_t *name = L"MacWin";
        DWORD target_thread = GetWindowThreadProcessId(search.warning, NULL);
        DWORD current_thread = GetCurrentThreadId();
        if (!GetClientRect(search.warning, &client)) return 0;
        AttachThreadInput(current_thread, target_thread, TRUE);
        SetForegroundWindow(search.warning);
        SetActiveWindow(search.warning);
        SetFocus(search.warning);
        point = MAKELPARAM(415, 86);
        SendMessageW(search.warning, WM_MOUSEMOVE, 0, point);
        SendMessageW(search.warning, WM_LBUTTONDOWN, MK_LBUTTON, point);
        SendMessageW(search.warning, WM_LBUTTONUP, 0, point);
        for (const wchar_t *character = name; *character; ++character) {
            INPUT input[2] = {0};
            input[0].type = INPUT_KEYBOARD;
            input[0].ki.wScan = *character;
            input[0].ki.dwFlags = KEYEVENTF_UNICODE;
            input[1] = input[0];
            input[1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
            SendInput(2, input, sizeof(INPUT));
        }
        Sleep(250);
        point = MAKELPARAM(client.right - 65, 32);
        SendMessageW(search.warning, WM_MOUSEMOVE, 0, point);
        SendMessageW(search.warning, WM_LBUTTONDOWN, MK_LBUTTON, point);
        SendMessageW(search.warning, WM_LBUTTONUP, 0, point);
        AttachThreadInput(current_thread, target_thread, FALSE);
    }
    return 1;
}

static BOOL CALLBACK collect_process_window(HWND window, LPARAM parameter) {
    DWORD process_id = 0;
    DWORD target_process_id = (DWORD)parameter;
    GetWindowThreadProcessId(window, &process_id);
    if (process_id != target_process_id) return TRUE;
    append_window_diagnostic(window, L"TOP");
    EnumChildWindows(window, collect_child_window, 0);
    return TRUE;
}

static int click_default_action(HWND window) {
    RECT client;
    LPARAM point;
    if (!GetClientRect(window, &client)) return 0;

    /* Select the first ribbon preset, then confirm with the left footer button. */
    point = MAKELPARAM(client.right * 18 / 100, client.bottom * 27 / 100);
    SendMessageW(window, WM_MOUSEMOVE, 0, point);
    SendMessageW(window, WM_LBUTTONDOWN, MK_LBUTTON, point);
    SendMessageW(window, WM_LBUTTONUP, 0, point);
    Sleep(250);
    point = MAKELPARAM(client.right * 76 / 100, client.bottom - 28);
    SendMessageW(window, WM_MOUSEMOVE, 0, point);
    SendMessageW(window, WM_LBUTTONDOWN, MK_LBUTTON, point);
    SendMessageW(window, WM_LBUTTONUP, 0, point);
    return 1;
}

static int write_result(const wchar_t *path, const wchar_t *initial_title,
                        int dismissed, int main_ready, int warning_dismissed,
                        int info_dismissed, int closed) {
    wchar_t wide[36864];
    char utf8[147456];
    HANDLE file;
    DWORD written;
    int length;
    _snwprintf(wide, 36864,
               L"INITIAL_TITLE=%ls\r\nDISMISSED=%s\r\nMAIN_READY=%s\r\n"
               L"WARNING_DISMISSED=%s\r\nINFO_DISMISSED=%s\r\n"
               L"CLOSED=%s\r\nWINDOWS=%ls\r\n",
               initial_title, dismissed ? L"true" : L"false",
               main_ready ? L"true" : L"false",
               warning_dismissed ? L"true" : L"false",
               info_dismissed ? L"true" : L"false",
               closed ? L"true" : L"false",
               window_diagnostics);
    length = WideCharToMultiByte(CP_UTF8, 0, wide, -1, utf8, sizeof(utf8),
                                 NULL, NULL);
    if (length <= 1) return 0;
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                       FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    WriteFile(file, utf8, (DWORD)(length - 1), &written, NULL);
    CloseHandle(file);
    return written == (DWORD)(length - 1);
}

int wmain(int argc, wchar_t **argv) {
    const wchar_t *application =
        L"C:\\Program Files (x86)\\SoftMaker FreeOffice 2024\\TextMaker.exe";
    wchar_t command[1024];
    wchar_t initial_title[512] = L"";
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    WindowSearch search = {0};
    int dismissed = 0, main_ready = 0, warning_dismissed = 0;
    int info_dismissed = 0, closed = 0;

    if (argc != 2) return 2;
    _snwprintf(command, 1024, L"\"%ls\" -N", application);
    startup.cb = sizeof(startup);
    if (!CreateProcessW(application, command, NULL, NULL, FALSE, 0, NULL, NULL,
                        &startup, &process)) return 3;
    search.process_id = process.dwProcessId;
    WaitForInputIdle(process.hProcess, 30000);
    for (int attempt = 0; attempt < 160 && !search.candidate && !search.main_window;
         ++attempt) {
        enumerate_windows(&search);
        if (!search.candidate && !search.main_window) Sleep(250);
    }
    if (search.main_window) {
        GetWindowTextW(search.main_window, initial_title, 512);
        main_ready = 1;
    } else if (search.candidate) {
        GetWindowTextW(search.candidate, initial_title, 512);
        EnumWindows(collect_process_window, (LPARAM)process.dwProcessId);
        if (_wcsicmp(initial_title, L"User interface") == 0 &&
            click_default_action(search.candidate)) {
            dismissed = 1;
        }
    }

    if (!main_ready) {
        for (int attempt = 0; attempt < 480 && !search.main_window; ++attempt) {
            search.candidate = NULL;
            enumerate_windows(&search);
            if (!search.main_window) Sleep(250);
        }
        main_ready = search.main_window != NULL;
    }
    if (main_ready) {
        DWORD_PTR ignored;
        info_dismissed = dismiss_user_info(process.dwProcessId);
        Sleep(5000);
        SendMessageTimeoutW(search.main_window, WM_CLOSE, 0, 0,
                            SMTO_ABORTIFHUNG, 5000, &ignored);
        warning_dismissed = dismiss_save_warning(process.dwProcessId);
        if (WaitForSingleObject(process.hProcess, 5000) == WAIT_TIMEOUT) {
            SendMessageTimeoutW(search.main_window, WM_SYSCOMMAND, SC_CLOSE, 0,
                                SMTO_ABORTIFHUNG, 5000, &ignored);
            warning_dismissed =
                dismiss_save_warning(process.dwProcessId) || warning_dismissed;
        }
    } else {
        close_process_windows(process.dwProcessId);
    }
    if (WaitForSingleObject(process.hProcess, 10000) == WAIT_TIMEOUT) {
        close_process_windows(process.dwProcessId);
        warning_dismissed =
            dismiss_save_warning(process.dwProcessId) || warning_dismissed;
        if (warning_dismissed) {
            info_dismissed = dismiss_user_info(process.dwProcessId);
            PostMessageW(search.main_window, WM_CLOSE, 0, 0);
        }
    }
    if (WaitForSingleObject(process.hProcess, 20000) == WAIT_OBJECT_0) {
        closed = 1;
    } else {
        EnumWindows(collect_process_window, (LPARAM)process.dwProcessId);
        TerminateProcess(process.hProcess, 4);
    }
    write_result(argv[1], initial_title, dismissed, main_ready,
                 warning_dismissed, info_dismissed, closed);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return main_ready && closed ? 0 : 4;
}
