#define _POSIX_C_SOURCE 200809L

#include "compatforge.h"

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef const char *(*api_version_fn)(void);
typedef uint32_t (*abi_version_fn)(void);
typedef cf_status_t (*context_create_fn)(const char *, cf_context_t **);
typedef cf_status_t (*launch_prepare_fn)(const cf_context_t *, const char *,
                                         const char *, cf_prepared_launch_t **);
typedef cf_status_t (*prepared_get_fn)(const cf_prepared_launch_t *, char **);
typedef void (*string_free_fn)(char *);
typedef void (*context_release_fn)(cf_context_t *);
typedef void (*prepared_release_fn)(cf_prepared_launch_t *);

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

static char *read_file(const char *path) {
    FILE *stream = fopen(path, "rb");
    long length;
    char *buffer;
    if (stream == NULL || fseek(stream, 0L, SEEK_END) != 0 ||
        (length = ftell(stream)) < 0 || fseek(stream, 0L, SEEK_SET) != 0) {
        if (stream != NULL) {
            fclose(stream);
        }
        return NULL;
    }
    buffer = malloc((size_t)length + 1U);
    if (buffer == NULL || fread(buffer, 1U, (size_t)length, stream) != (size_t)length) {
        free(buffer);
        fclose(stream);
        return NULL;
    }
    buffer[length] = '\0';
    fclose(stream);
    return buffer;
}

static int api_version_at_least(const char *version, unsigned required_minor) {
    unsigned major;
    unsigned minor;
    unsigned patch;
    char trailing;
    if (version == NULL || sscanf(version, "%u.%u.%u%c", &major, &minor, &patch, &trailing) != 3) {
        return 0;
    }
    return major > 0U || (major == 0U && minor >= required_minor);
}

int main(int argc, char **argv) {
    api_version_fn api_version = NULL;
    abi_version_fn abi_version = NULL;
    context_create_fn context_create = NULL;
    launch_prepare_fn launch_prepare = NULL;
    prepared_get_fn inspection_get = NULL;
    prepared_get_fn plan_get = NULL;
    string_free_fn string_free = NULL;
    context_release_fn context_release = NULL;
    prepared_release_fn prepared_release = NULL;
    cf_context_t *context = NULL;
    cf_prepared_launch_t *prepared = NULL;
    char *inspection = NULL;
    char *plan = NULL;
    char *config;
    char *request;
    size_t request_size;

    if (argc != 4) {
        fprintf(stderr, "usage: %s <library> <config.json> <absolute-pe-path>\n", argv[0]);
        return 2;
    }
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (library == NULL) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return 1;
    }
    if (!load_function(library, "cf_api_version", &api_version, sizeof(api_version)) ||
        !load_function(library, "cf_abi_version", &abi_version, sizeof(abi_version)) ||
        !load_function(library, "cf_context_create", &context_create, sizeof(context_create)) ||
        !load_function(library, "cf_launch_prepare", &launch_prepare, sizeof(launch_prepare)) ||
        !load_function(library, "cf_prepared_launch_inspection_get", &inspection_get, sizeof(inspection_get)) ||
        !load_function(library, "cf_prepared_launch_plan_get", &plan_get, sizeof(plan_get)) ||
        !load_function(library, "cf_string_free", &string_free, sizeof(string_free)) ||
        !load_function(library, "cf_context_release", &context_release, sizeof(context_release)) ||
        !load_function(library, "cf_prepared_launch_release", &prepared_release, sizeof(prepared_release))) {
        dlclose(library);
        return 1;
    }
    if (!api_version_at_least(api_version(), 10U) || abi_version() != 1U) {
        fprintf(stderr, "unexpected CompatForge API/ABI\n");
        dlclose(library);
        return 1;
    }

    config = read_file(argv[2]);
    request_size = strlen(argv[3]) + 512U;
    request = malloc(request_size);
    if (config == NULL || request == NULL) {
        free(config);
        free(request);
        dlclose(library);
        return 1;
    }
    (void)snprintf(
        request, request_size,
        "{\"schemaVersion\":\"1\",\"requestId\":\"018fe3cb-9d12-7b52-b334-1cce0e857fc9\","
        "\"bottleId\":\"prepared-c-consumer\",\"executable\":{\"path\":\"%s\","
        "\"architecture\":\"x86_64\"},\"arguments\":[],\"environment\":{},"
        "\"constraints\":{\"allowVirtualMachine\":false,\"allowRemote\":false,"
        "\"networkPolicy\":\"deny\"}}",
        argv[3]);

    if (context_create(config, &context) != CF_STATUS_OK || context == NULL ||
        launch_prepare(context, argv[3], request, &prepared) != CF_STATUS_OK || prepared == NULL ||
        inspection_get(prepared, &inspection) != CF_STATUS_OK || inspection == NULL ||
        plan_get(prepared, &plan) != CF_STATUS_OK || plan == NULL) {
        fprintf(stderr, "prepared launch C ABI flow failed\n");
        free(config);
        free(request);
        if (inspection != NULL) string_free(inspection);
        if (plan != NULL) string_free(plan);
        if (prepared != NULL) prepared_release(prepared);
        if (context != NULL) context_release(context);
        dlclose(library);
        return 1;
    }
    if (strstr(inspection, "\"architecture\": \"x86_64\"") == NULL ||
        strstr(inspection, "\"subsystem\": \"windowsConsole\"") == NULL ||
        strstr(plan, "\"guestArtifact\":") == NULL ||
        strstr(plan, "\"imageKind\": \"executable\"") == NULL) {
        fprintf(stderr, "unexpected prepared launch evidence\n%s\n%s\n", inspection, plan);
        return 1;
    }

    free(config);
    free(request);
    string_free(inspection);
    string_free(plan);
    prepared_release(prepared);
    context_release(context);
    dlclose(library);
    return 0;
}
