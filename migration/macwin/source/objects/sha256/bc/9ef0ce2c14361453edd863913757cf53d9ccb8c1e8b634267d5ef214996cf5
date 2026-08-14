#include <windows.h>

#include <stdio.h>
#include <stdlib.h>

#ifndef LOAD_LIBRARY_SEARCH_DEFAULT_DIRS
#define LOAD_LIBRARY_SEARCH_DEFAULT_DIRS 0x00001000
#endif
#ifndef LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR
#define LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR 0x00000100
#endif
#ifndef LOAD_LIBRARY_SEARCH_USER_DIRS
#define LOAD_LIBRARY_SEARCH_USER_DIRS 0x00000400
#endif

typedef void *qpdf_data;
typedef unsigned int qpdf_oh;
typedef int qpdf_status;

typedef qpdf_data (*qpdf_init_fn)(void);
typedef void (*qpdf_cleanup_fn)(qpdf_data *);
typedef qpdf_status (*qpdf_empty_pdf_fn)(qpdf_data);
typedef qpdf_status (*qpdf_read_fn)(qpdf_data, const char *, const char *);
typedef int (*qpdf_get_num_pages_fn)(qpdf_data);
typedef qpdf_oh (*qpdf_get_page_n_fn)(qpdf_data, size_t);
typedef qpdf_status (*qpdf_add_page_fn)(qpdf_data, qpdf_data, qpdf_oh, int);
typedef qpdf_status (*qpdf_init_write_fn)(qpdf_data, const char *);
typedef qpdf_status (*qpdf_write_fn)(qpdf_data);
typedef const char *(*qpdf_get_qpdf_version_fn)(void);
typedef DLL_DIRECTORY_COOKIE (WINAPI *add_dll_directory_fn)(PCWSTR);
typedef BOOL (WINAPI *remove_dll_directory_fn)(DLL_DIRECTORY_COOKIE);
typedef BOOL (WINAPI *set_default_dll_directories_fn)(DWORD);

struct qpdf_api {
    qpdf_init_fn init;
    qpdf_cleanup_fn cleanup;
    qpdf_empty_pdf_fn empty_pdf;
    qpdf_read_fn read;
    qpdf_get_num_pages_fn get_num_pages;
    qpdf_get_page_n_fn get_page_n;
    qpdf_add_page_fn add_page;
    qpdf_init_write_fn init_write;
    qpdf_write_fn write;
    qpdf_get_qpdf_version_fn get_version;
};

static FARPROC load_symbol(HMODULE module, const char *name) {
    FARPROC symbol = GetProcAddress(module, name);
    if (!symbol) {
        fprintf(stderr, "missing qpdf symbol: %s error=%lu\n", name, GetLastError());
    }
    return symbol;
}

static int load_api(HMODULE module, struct qpdf_api *api) {
    api->init = (qpdf_init_fn)load_symbol(module, "qpdf_init");
    api->cleanup = (qpdf_cleanup_fn)load_symbol(module, "qpdf_cleanup");
    api->empty_pdf = (qpdf_empty_pdf_fn)load_symbol(module, "qpdf_empty_pdf");
    api->read = (qpdf_read_fn)load_symbol(module, "qpdf_read");
    api->get_num_pages = (qpdf_get_num_pages_fn)load_symbol(module, "qpdf_get_num_pages");
    api->get_page_n = (qpdf_get_page_n_fn)load_symbol(module, "qpdf_get_page_n");
    api->add_page = (qpdf_add_page_fn)load_symbol(module, "qpdf_add_page");
    api->init_write = (qpdf_init_write_fn)load_symbol(module, "qpdf_init_write");
    api->write = (qpdf_write_fn)load_symbol(module, "qpdf_write");
    api->get_version = (qpdf_get_qpdf_version_fn)load_symbol(module, "qpdf_get_qpdf_version");
    return api->init && api->cleanup && api->empty_pdf && api->read &&
        api->get_num_pages && api->get_page_n && api->add_page &&
        api->init_write && api->write && api->get_version;
}

static int has_error(qpdf_status status) {
    return (status & 2) != 0;
}

static int append_document(struct qpdf_api *api, qpdf_data output, qpdf_data input) {
    int pages = api->get_num_pages(input);
    int index;

    if (pages < 1) {
        fprintf(stderr, "input has no pages\n");
        return 0;
    }
    for (index = 0; index < pages; ++index) {
        qpdf_oh page = api->get_page_n(input, (size_t)index);
        if (!page || has_error(api->add_page(output, input, page, 0))) {
            fprintf(stderr, "failed to append page %d\n", index);
            return 0;
        }
    }
    return pages;
}

static DLL_DIRECTORY_COOKIE add_search_directory(
    add_dll_directory_fn add_directory,
    const char *path
) {
    wchar_t wide_path[32768];
    int length = MultiByteToWideChar(
        CP_ACP,
        MB_ERR_INVALID_CHARS,
        path,
        -1,
        wide_path,
        (int)(sizeof(wide_path) / sizeof(wide_path[0]))
    );

    if (!length) {
        fprintf(stderr, "invalid DLL search path: %s error=%lu\n", path, GetLastError());
        return NULL;
    }
    return add_directory(wide_path);
}

int main(int argc, char **argv) {
    struct qpdf_api api = {0};
    HMODULE kernel32;
    HMODULE module = NULL;
    add_dll_directory_fn add_directory;
    remove_dll_directory_fn remove_directory;
    set_default_dll_directories_fn set_default_directories;
    DLL_DIRECTORY_COOKIE app_cookie = NULL;
    DLL_DIRECTORY_COOKIE lib_cookie = NULL;
    qpdf_data output = NULL;
    qpdf_data first = NULL;
    qpdf_data second = NULL;
    int first_pages;
    int second_pages;
    int result = 1;

    if (argc != 7) {
        fprintf(
            stderr,
            "usage: probe.exe <app-dir> <lib-dir> <qpdf-dll> <input-a> <input-b> <output>\n"
        );
        return 2;
    }
    kernel32 = GetModuleHandleA("kernel32.dll");
    add_directory = (add_dll_directory_fn)GetProcAddress(kernel32, "AddDllDirectory");
    remove_directory = (remove_dll_directory_fn)GetProcAddress(kernel32, "RemoveDllDirectory");
    set_default_directories = (set_default_dll_directories_fn)GetProcAddress(
        kernel32,
        "SetDefaultDllDirectories"
    );
    if (!add_directory || !remove_directory || !set_default_directories) {
        fprintf(stderr, "secure DLL directory APIs are unavailable\n");
        return 3;
    }
    if (!set_default_directories(
            LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_USER_DIRS
        )) {
        fprintf(stderr, "SetDefaultDllDirectories failed: %lu\n", GetLastError());
        return 3;
    }
    app_cookie = add_search_directory(add_directory, argv[1]);
    lib_cookie = add_search_directory(add_directory, argv[2]);
    if (!app_cookie || !lib_cookie) {
        fprintf(stderr, "AddDllDirectory failed: %lu\n", GetLastError());
        result = 3;
        goto done;
    }
    module = LoadLibraryExA(
        argv[3],
        NULL,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
            LOAD_LIBRARY_SEARCH_DEFAULT_DIRS |
            LOAD_LIBRARY_SEARCH_USER_DIRS
    );
    if (!module) {
        fprintf(stderr, "LoadLibraryEx failed: %lu\n", GetLastError());
        result = 4;
        goto done;
    }
    if (!load_api(module, &api)) {
        result = 5;
        goto done;
    }

    output = api.init();
    first = api.init();
    second = api.init();
    if (!output || !first || !second) {
        result = 6;
        goto done;
    }
    if (has_error(api.empty_pdf(output)) ||
        has_error(api.read(first, argv[4], "")) ||
        has_error(api.read(second, argv[5], ""))) {
        result = 7;
        goto done;
    }

    first_pages = append_document(&api, output, first);
    second_pages = append_document(&api, output, second);
    if (!first_pages || !second_pages) {
        result = 8;
        goto done;
    }
    if (has_error(api.init_write(output, argv[6])) || has_error(api.write(output))) {
        result = 9;
        goto done;
    }

    printf("qpdf.version=%s\n", api.get_version());
    printf("input.pages=%d+%d\n", first_pages, second_pages);
    printf("output.pages=%d\n", api.get_num_pages(output));
    printf("PASS pdfarranger_qpdf_merge\n");
    result = 0;

done:
    if (api.cleanup) {
        if (second) api.cleanup(&second);
        if (first) api.cleanup(&first);
        if (output) api.cleanup(&output);
    }
    if (module) FreeLibrary(module);
    if (lib_cookie) remove_directory(lib_cookie);
    if (app_cookie) remove_directory(app_cookie);
    return result;
}
