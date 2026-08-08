#define _POSIX_C_SOURCE 200809L

#include "compatforge.h"

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef const char *(*api_version_fn)(void);
typedef uint32_t (*abi_version_fn)(void);
typedef cf_status_t (*inspect_fn)(const char *, char **);
typedef void (*string_free_fn)(char *);

static int load_function(void *library, const char *name, void *target,
                         size_t target_size) {
    const char *error;
    void *resolved;

    (void)dlerror();
    resolved = dlsym(library, name);
    error = dlerror();
    if (resolved == NULL || error != NULL || target_size != sizeof(resolved)) {
        fprintf(stderr, "missing symbol %s\n", name);
        return 0;
    }
    memcpy(target, &resolved, sizeof(resolved));
    return 1;
}

static int api_version_at_least(const char *version, unsigned required_major,
                                unsigned required_minor, unsigned required_patch) {
    unsigned major;
    unsigned minor;
    unsigned patch;
    char trailing;

    if (version == NULL ||
        sscanf(version, "%u.%u.%u%c", &major, &minor, &patch, &trailing) != 3) {
        return 0;
    }
    if (major != required_major) {
        return major > required_major;
    }
    if (minor != required_minor) {
        return minor > required_minor;
    }
    return patch >= required_patch;
}

int main(int argc, char **argv) {
    api_version_fn api_version = NULL;
    abi_version_fn abi_version = NULL;
    inspect_fn inspect = NULL;
    string_free_fn string_free = NULL;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <library> <absolute-pe-path>\n", argv[0]);
        return 2;
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (library == NULL) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return 1;
    }

    if (!load_function(library, "cf_api_version", &api_version, sizeof(api_version)) ||
        !load_function(library, "cf_abi_version", &abi_version, sizeof(abi_version))) {
        dlclose(library);
        return 1;
    }
    if (!api_version_at_least(api_version(), 0U, 9U, 0U) || abi_version() != 1U) {
        fprintf(stderr, "unexpected CompatForge API/ABI\n");
        return 1;
    }

    if (!load_function(library, "cf_inspect_executable", &inspect, sizeof(inspect)) ||
        !load_function(library, "cf_string_free", &string_free, sizeof(string_free))) {
        dlclose(library);
        return 1;
    }
    char *report = NULL;
    if (inspect(argv[2], &report) != CF_STATUS_OK || report == NULL) {
        fprintf(stderr, "inspection failed\n");
        return 1;
    }
    if (strstr(report, "\"schemaVersion\":\"1\"") == NULL ||
        strstr(report, "\"architecture\":\"x86_64\"") == NULL ||
        strstr(report, "\"subsystem\":\"windowsConsole\"") == NULL ||
        strstr(report, "kernel32.dll") == NULL) {
        fprintf(stderr, "unexpected inspection report: %s\n", report);
        string_free(report);
        return 1;
    }
    string_free(report);
    dlclose(library);
    return 0;
}
