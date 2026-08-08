#include "compatforge.h"

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRED_API_VERSION "0.6.0"

typedef const char *(*api_version_fn)(void);
typedef uint32_t (*abi_version_fn)(void);
typedef cf_status_t (*context_create_fn)(const char *, cf_context_t **);
typedef cf_status_t (*capabilities_get_fn)(const cf_context_t *, char **);
typedef cf_status_t (*last_error_json_fn)(char **);
typedef void (*string_free_fn)(char *);
typedef void (*context_release_fn)(cf_context_t *);

static int load_function(void *library, const char *name, void *target, size_t target_size) {
    const char *error;
    void *resolved;

    (void)dlerror();
    resolved = dlsym(library, name);
    error = dlerror();
    if (resolved == NULL || error != NULL || target_size != sizeof(resolved)) {
        fprintf(stderr, "missing CompatForge symbol: %s\n", name);
        return 0;
    }
    memcpy(target, &resolved, sizeof(resolved));
    return 1;
}

static char *read_file(const char *path) {
    FILE *file = fopen(path, "rb");
    long length;
    char *content;

    if (file == NULL || fseek(file, 0, SEEK_END) != 0) {
        return NULL;
    }
    length = ftell(file);
    if (length < 0 || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return NULL;
    }
    content = (char *)malloc((size_t)length + 1U);
    if (content == NULL || fread(content, 1U, (size_t)length, file) != (size_t)length) {
        free(content);
        fclose(file);
        return NULL;
    }
    content[length] = '\0';
    fclose(file);
    return content;
}

int main(int argc, char **argv) {
    void *library;
    char *config_json;
    char *report_json = NULL;
    char *error_json = NULL;
    cf_context_t *context = NULL;
    cf_status_t status;
    api_version_fn api_version = NULL;
    abi_version_fn abi_version = NULL;
    context_create_fn context_create = NULL;
    capabilities_get_fn capabilities_get = NULL;
    last_error_json_fn last_error_json = NULL;
    string_free_fn string_free = NULL;
    context_release_fn context_release = NULL;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <compatforge-library> <context-config>\n", argv[0]);
        return 2;
    }
    library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (library == NULL) {
        fprintf(stderr, "failed to load CompatForge: %s\n", dlerror());
        return 3;
    }
    if (!load_function(library, "cf_api_version", &api_version, sizeof(api_version)) ||
        !load_function(library, "cf_abi_version", &abi_version, sizeof(abi_version))) {
        dlclose(library);
        return 4;
    }
    if (api_version() == NULL || strcmp(api_version(), REQUIRED_API_VERSION) != 0 || abi_version() != 1U) {
        fprintf(stderr, "unsupported CompatForge API/ABI (need API %s, ABI 1)\n", REQUIRED_API_VERSION);
        dlclose(library);
        return 5;
    }

    /* API 0.6.0 is the first version required to export cf_capabilities_get. */
    if (!load_function(library, "cf_context_create", &context_create, sizeof(context_create)) ||
        !load_function(library, "cf_capabilities_get", &capabilities_get, sizeof(capabilities_get)) ||
        !load_function(library, "cf_last_error_json", &last_error_json, sizeof(last_error_json)) ||
        !load_function(library, "cf_string_free", &string_free, sizeof(string_free)) ||
        !load_function(library, "cf_context_release", &context_release, sizeof(context_release))) {
        dlclose(library);
        return 6;
    }

    config_json = read_file(argv[2]);
    if (config_json == NULL) {
        fprintf(stderr, "failed to read context fixture\n");
        dlclose(library);
        return 7;
    }
    status = context_create(config_json, &context);
    free(config_json);
    if (status != CF_STATUS_OK) {
        (void)last_error_json(&error_json);
        fprintf(stderr, "context creation failed: %s\n", error_json == NULL ? "unknown" : error_json);
        string_free(error_json);
        dlclose(library);
        return 8;
    }

    status = capabilities_get(context, &report_json);
    if (status != CF_STATUS_OK || report_json == NULL || strstr(report_json, "\"schemaVersion\":\"1\"") == NULL ||
        strstr(report_json, "\"runtimeProviders\"") == NULL || strstr(report_json, "\"translators\"") == NULL ||
        strstr(report_json, "\"graphicsBackends\"") == NULL) {
        (void)last_error_json(&error_json);
        fprintf(stderr, "capability negotiation failed: %s\n", error_json == NULL ? "unknown" : error_json);
        string_free(error_json);
        string_free(report_json);
        context_release(context);
        dlclose(library);
        return 9;
    }

    puts("FORGEOS_COMPAT_CAPABILITIES_OK");
    string_free(report_json);
    context_release(context);
    dlclose(library);
    return 0;
}
