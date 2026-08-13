#define COBJMACROS
#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shobjidl.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static void print_utf8_path(const WCHAR *path)
{
    char utf8[4096];
    int length = WideCharToMultiByte(CP_UTF8, 0, path, -1, utf8, sizeof(utf8), NULL, NULL);

    if (!length)
    {
        printf("path-conversion-error=%lu\n", GetLastError());
        return;
    }
    printf("path=%s\n", utf8);
}

static void trace_step(const char *step)
{
    printf("probe-step=%s\n", step);
}

static int run_message_probe(void)
{
    int result = MessageBoxW(NULL, L"中文与 English 渲染测试", L"MacWin Native UI Probe",
                             MB_OKCANCEL | MB_ICONINFORMATION);

    printf("message-result=%d\n", result);
    return result == IDOK ? 0 : 2;
}

static int run_file_probe(BOOL save, BOOL filtered)
{
    static const WCHAR filter[] = L"Text files\0*.txt;*.md\0All files\0*.*\0\0";
    OPENFILENAMEW dialog = {0};
    WCHAR path[4096];
    BOOL result;

    wcscpy(path, save ? L"native-ui-save-中文.txt" : L"native-ui-open-中文.txt");
    if (!save)
    {
        HANDLE file = CreateFileW(L"C:\\native-ui-open-中文.txt", GENERIC_WRITE, 0, NULL,
                                  CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    }

    dialog.lStructSize = sizeof(dialog);
    dialog.lpstrFile = path;
    dialog.nMaxFile = sizeof(path) / sizeof(path[0]);
    dialog.lpstrInitialDir = L"C:\\";
    dialog.lpstrFilter = filtered ? filter : NULL;
    dialog.nFilterIndex = 1;
    dialog.lpstrDefExt = save && filtered ? L"txt" : NULL;
    dialog.lpstrTitle = save ? L"MacWin 原生保存对话框" : L"MacWin 原生打开对话框";
    dialog.Flags = OFN_EXPLORER | OFN_NOCHANGEDIR | (save ? OFN_OVERWRITEPROMPT : OFN_FILEMUSTEXIST);

    result = save ? GetSaveFileNameW(&dialog) : GetOpenFileNameW(&dialog);
    printf("file-dialog-result=%d\n", result);
    if (!result)
    {
        printf("commdlg-error=%lu\n", CommDlgExtendedError());
        return 2;
    }

    print_utf8_path(path);
    return 0;
}

static LONG legacy_fallback_hook_count;

static UINT_PTR CALLBACK legacy_fallback_hook(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam)
{
    HWND dialog;

    UNREFERENCED_PARAMETER(wparam);
    UNREFERENCED_PARAMETER(lparam);
    if (message != WM_INITDIALOG) return 0;

    InterlockedIncrement(&legacy_fallback_hook_count);
    dialog = GetParent(hwnd);
    if (!dialog) dialog = hwnd;
    PostMessageW(dialog, WM_COMMAND, MAKEWPARAM(IDCANCEL, BN_CLICKED),
                 (LPARAM)GetDlgItem(dialog, IDCANCEL));
    return 0;
}

static int run_legacy_fallback_probe(void)
{
    OPENFILENAMEW dialog = {0};
    WCHAR path[4096] = L"C:\\native-ui-open-中文.txt";
    DWORD error;
    BOOL result;

    legacy_fallback_hook_count = 0;
    dialog.lStructSize = sizeof(dialog);
    dialog.lpstrFile = path;
    dialog.nMaxFile = ARRAYSIZE(path);
    dialog.lpstrInitialDir = L"C:\\";
    dialog.lpstrTitle = L"MacWin Wine 回退验证";
    dialog.Flags = OFN_EXPLORER | OFN_ENABLEHOOK | OFN_FILEMUSTEXIST;
    dialog.lpfnHook = legacy_fallback_hook;

    result = GetOpenFileNameW(&dialog);
    error = CommDlgExtendedError();
    printf("legacy-fallback-result=%d hook-count=%ld commdlg-error=%lu\n",
           result, legacy_fallback_hook_count, error);
    return !result && !error && legacy_fallback_hook_count > 0 ? 0 : 1;
}

static void print_shell_item(IShellItem *item)
{
    PWSTR path = NULL;
    HRESULT hr = IShellItem_GetDisplayName(item, SIGDN_FILESYSPATH, &path);

    printf("modern-item-path-hr=0x%08lx\n", (unsigned long)hr);
    if (SUCCEEDED(hr) && path)
    {
        print_utf8_path(path);
        CoTaskMemFree(path);
    }
}

static int run_modern_file_probe(BOOL save, BOOL pick_folders, BOOL multi_select)
{
    static const COMDLG_FILTERSPEC filters[] = {
        { L"文本文件 / Text files", L"*.txt;*.md" },
        { L"所有文件 / All files", L"*.*" },
    };
    IFileDialog *dialog = NULL;
    IShellItemArray *results = NULL;
    IShellItem *result = NULL;
    FILEOPENDIALOGOPTIONS options;
    HRESULT hr;
    BOOL initialized = FALSE;
    DWORD count;
    UINT i;

    trace_step("modern-coinitialize");
    hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (SUCCEEDED(hr)) initialized = TRUE;
    else if (hr != RPC_E_CHANGED_MODE)
    {
        printf("modern-dialog-coinit-hr=0x%08lx\n", (unsigned long)hr);
        return 1;
    }

    trace_step("modern-cocreateinstance");
    hr = CoCreateInstance(save ? &CLSID_FileSaveDialog : &CLSID_FileOpenDialog, NULL,
                          CLSCTX_INPROC_SERVER,
                          save ? &IID_IFileSaveDialog : &IID_IFileOpenDialog,
                          (void **)&dialog);
    printf("modern-dialog-create-hr=0x%08lx\n", (unsigned long)hr);
    if (FAILED(hr)) goto done;

    trace_step("modern-set-title");
    IFileDialog_SetTitle(dialog, save ? L"MacWin 原生保存对话框" :
                          (pick_folders ? L"MacWin 原生选择文件夹" : L"MacWin 原生打开对话框"));
    trace_step("modern-set-file-types");
    IFileDialog_SetFileTypes(dialog, ARRAYSIZE(filters), filters);
    trace_step("modern-set-file-type-index");
    IFileDialog_SetFileTypeIndex(dialog, 1);
    trace_step("modern-set-default-extension");
    IFileDialog_SetDefaultExtension(dialog, L"txt");
    trace_step("modern-set-file-name");
    IFileDialog_SetFileName(dialog, save ? L"native-modern-save-中文.txt" : L"native-modern-open-中文.txt");

    trace_step("modern-get-options");
    hr = IFileDialog_GetOptions(dialog, &options);
    printf("modern-dialog-get-options-hr=0x%08lx options=0x%08lx\n",
           (unsigned long)hr, SUCCEEDED(hr) ? (unsigned long)options : 0UL);
    if (FAILED(hr)) goto done;
    options |= FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR;
    if (save)
        options |= FOS_NOREADONLYRETURN | FOS_OVERWRITEPROMPT;
    else
        options |= FOS_FILEMUSTEXIST;
    if (pick_folders)
    {
        options |= FOS_PICKFOLDERS;
        options &= ~FOS_FILEMUSTEXIST;
    }
    if (multi_select && !save) options |= FOS_ALLOWMULTISELECT;
    trace_step("modern-set-options");
    hr = IFileDialog_SetOptions(dialog, options);
    printf("modern-dialog-set-options-hr=0x%08lx options=0x%08lx\n",
           (unsigned long)hr, (unsigned long)options);
    if (FAILED(hr)) goto done;

    trace_step("modern-show");
    hr = IFileDialog_Show(dialog, NULL);
    printf("modern-dialog-show-hr=0x%08lx\n", (unsigned long)hr);
    if (hr == HRESULT_FROM_WIN32(ERROR_CANCELLED))
    {
        hr = S_FALSE;
        goto done;
    }
    if (FAILED(hr)) goto done;

    if (!save && (options & FOS_ALLOWMULTISELECT))
    {
        hr = IFileOpenDialog_GetResults((IFileOpenDialog *)dialog, &results);
        if (FAILED(hr)) goto done;
        hr = IShellItemArray_GetCount(results, &count);
        if (FAILED(hr)) goto done;
        printf("modern-item-count=%lu\n", (unsigned long)count);
        for (i = 0; i < count; i++)
        {
            hr = IShellItemArray_GetItemAt(results, i, &result);
            if (FAILED(hr)) goto done;
            print_shell_item(result);
            IShellItem_Release(result);
            result = NULL;
        }
    }
    else
    {
        if (save)
            hr = IFileSaveDialog_GetResult((IFileSaveDialog *)dialog, &result);
        else
            hr = IFileOpenDialog_GetResult((IFileOpenDialog *)dialog, &result);
        if (FAILED(hr)) goto done;
        printf("modern-item-count=1\n");
        print_shell_item(result);
    }

done:
    if (result) IShellItem_Release(result);
    if (results) IShellItemArray_Release(results);
    if (dialog) IFileDialog_Release(dialog);
    if (initialized) CoUninitialize();
    if (hr == S_FALSE) return 2;
    if (FAILED(hr))
    {
        printf("modern-dialog-result-hr=0x%08lx\n", (unsigned long)hr);
        return 1;
    }
    return 0;
}

static int run_task_probe(void)
{
    static const TASKDIALOG_BUTTON buttons[] = {
        { IDOK, L"确定" },
        { IDCANCEL, L"取消" },
    };
    TASKDIALOGCONFIG config = {0};
    int button = 0, radio = 0;
    BOOL verification_checked = FALSE;
    HRESULT hr;

    config.cbSize = sizeof(config);
    config.pszWindowTitle = L"MacWin 原生任务对话框";
    config.pszMainInstruction = L"现代 Windows API -> macOS NSAlert";
    config.pszContent = L"验证按钮、默认按钮和复选框状态的转换。";
    config.pszVerificationText = L"记住这个选择";
    config.dwFlags = TDF_ALLOW_DIALOG_CANCELLATION | TDF_VERIFICATION_FLAG_CHECKED;
    config.cButtons = ARRAYSIZE(buttons);
    config.pButtons = buttons;

    hr = TaskDialogIndirect(&config, &button, &radio, &verification_checked);
    printf("task-dialog-hr=0x%08lx button=%d radio=%d verification=%d\n",
           (unsigned long)hr, button, radio, verification_checked);
    if (FAILED(hr)) return 1;
    return button == IDOK ? 0 : 2;
}

static LONG task_fallback_callback_count;

static HRESULT CALLBACK task_fallback_callback(HWND hwnd, UINT notification,
                                                WPARAM wparam, LPARAM lparam, LONG_PTR ref_data)
{
    UNREFERENCED_PARAMETER(wparam);
    UNREFERENCED_PARAMETER(lparam);
    UNREFERENCED_PARAMETER(ref_data);
    if (notification == TDN_CREATED)
    {
        InterlockedIncrement(&task_fallback_callback_count);
        PostMessageW(hwnd, TDM_CLICK_BUTTON, IDOK, 0);
    }
    return S_OK;
}

static int run_task_fallback_probe(void)
{
    TASKDIALOGCONFIG config = {0};
    int button = 0;
    HRESULT hr;

    task_fallback_callback_count = 0;
    config.cbSize = sizeof(config);
    config.pszWindowTitle = L"MacWin Wine 任务对话框回退验证";
    config.pszMainInstruction = L"此对话框必须由 Wine 原实现处理";
    config.pszContent = L"回调会在创建后自动点击确定。";
    config.dwCommonButtons = TDCBF_OK_BUTTON;
    config.pfCallback = task_fallback_callback;

    hr = TaskDialogIndirect(&config, &button, NULL, NULL);
    printf("task-fallback-hr=0x%08lx button=%d callback-count=%ld\n",
           (unsigned long)hr, button, task_fallback_callback_count);
    return SUCCEEDED(hr) && button == IDOK && task_fallback_callback_count > 0 ? 0 : 1;
}

int wmain(int argc, WCHAR **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    SetConsoleOutputCP(CP_UTF8);

    if (argc == 2 && !wcscmp(argv[1], L"--message")) return run_message_probe();
    if (argc == 2 && !wcscmp(argv[1], L"--open")) return run_file_probe(FALSE, FALSE);
    if (argc == 2 && !wcscmp(argv[1], L"--save")) return run_file_probe(TRUE, FALSE);
    if (argc == 2 && !wcscmp(argv[1], L"--filtered-open")) return run_file_probe(FALSE, TRUE);
    if (argc == 2 && !wcscmp(argv[1], L"--filtered-save")) return run_file_probe(TRUE, TRUE);
    if (argc == 2 && !wcscmp(argv[1], L"--legacy-fallback")) return run_legacy_fallback_probe();
    if (argc == 2 && !wcscmp(argv[1], L"--modern-open")) return run_modern_file_probe(FALSE, FALSE, FALSE);
    if (argc == 2 && !wcscmp(argv[1], L"--modern-save")) return run_modern_file_probe(TRUE, FALSE, FALSE);
    if (argc == 2 && !wcscmp(argv[1], L"--modern-open-multi")) return run_modern_file_probe(FALSE, FALSE, TRUE);
    if (argc == 2 && !wcscmp(argv[1], L"--modern-folder")) return run_modern_file_probe(FALSE, TRUE, FALSE);
    if (argc == 2 && !wcscmp(argv[1], L"--task")) return run_task_probe();
    if (argc == 2 && !wcscmp(argv[1], L"--task-fallback")) return run_task_fallback_probe();

    fprintf(stderr, "usage: native-ui-probe.exe --message|--open|--save|--filtered-open|--filtered-save|--legacy-fallback|--modern-open|--modern-save|--modern-open-multi|--modern-folder|--task|--task-fallback\n");
    return 64;
}
