#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>

static void print_path(const char *label, const WCHAR *path)
{
    char utf8[MAX_PATH * 4];

    if (!WideCharToMultiByte(CP_UTF8, 0, path, -1, utf8, sizeof(utf8), NULL, NULL))
        lstrcpyA(utf8, "<conversion failed>");
    printf("%s=%s\n", label, utf8);
}

int main(void)
{
    WCHAR direct[MAX_PATH] = {0};
    WCHAR from_pidl[MAX_PATH] = {0};
    PIDLIST_ABSOLUTE pidl = NULL;
    HRESULT hr;
    BOOL direct_ok, pidl_ok;

    SetConsoleOutputCP(CP_UTF8);
    direct_ok = SHGetSpecialFolderPathW(NULL, direct, CSIDL_PERSONAL, FALSE);
    printf("DIRECT_OK=%s ERROR=%lu\n", direct_ok ? "true" : "false", GetLastError());
    if (direct_ok) print_path("DIRECT_PATH", direct);

    hr = SHGetSpecialFolderLocation(NULL, CSIDL_PERSONAL, &pidl);
    printf("LOCATION_HR=0x%08lx\n", hr);
    if (FAILED(hr)) return 2;

    SetLastError(ERROR_SUCCESS);
    pidl_ok = SHGetPathFromIDListW(pidl, from_pidl);
    printf("PIDL_OK=%s ERROR=%lu\n", pidl_ok ? "true" : "false", GetLastError());
    if (pidl_ok) print_path("PIDL_PATH", from_pidl);
    CoTaskMemFree(pidl);

    if (!direct_ok || !pidl_ok) return 3;
    printf("MATCH=%s\n", lstrcmpiW(direct, from_pidl) == 0 ? "true" : "false");
    return lstrcmpiW(direct, from_pidl) == 0 ? 0 : 4;
}
