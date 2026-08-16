#include "compatforge.h"

#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef const char *(*api_version_fn)(void);
typedef uint32_t (*abi_version_fn)(void);
typedef cf_status_t (*context_create_fn)(const char *, cf_context_t **);
typedef cf_status_t (*service_create_fn)(const cf_context_t *, const char *, cf_service_t **);
typedef cf_status_t (*service_call_fn)(const cf_service_t *, const char *, char **);
typedef cf_status_t (*last_error_json_fn)(char **);
typedef void (*string_free_fn)(char *);
typedef void (*service_release_fn)(cf_service_t *);
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

static int report_failure(const char *label, last_error_json_fn last_error_json, string_free_fn string_free) {
    char *error_json = NULL;

    (void)last_error_json(&error_json);
    fprintf(stderr, "%s: %s\n", label, error_json == NULL ? "unknown" : error_json);
    string_free(error_json);
    return 1;
}

int main(int argc, char **argv) {
    void *library;
    char *context_json;
    char *service_config;
    char *response = NULL;
    size_t service_config_size;
    cf_context_t *context = NULL;
    cf_service_t *service = NULL;
    api_version_fn api_version = NULL;
    abi_version_fn abi_version = NULL;
    context_create_fn context_create = NULL;
    service_create_fn service_create = NULL;
    service_call_fn service_call = NULL;
    last_error_json_fn last_error_json = NULL;
    string_free_fn string_free = NULL;
    service_release_fn service_release = NULL;
    context_release_fn context_release = NULL;

    if (argc != 4) {
        fprintf(stderr, "usage: %s <compatforge-library> <context-config> <service-root>\n", argv[0]);
        return 2;
    }
    library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (library == NULL) {
        fprintf(stderr, "failed to load CompatForge: %s\n", dlerror());
        return 3;
    }
    if (!load_function(library, "cf_api_version", &api_version, sizeof(api_version)) ||
        !load_function(library, "cf_abi_version", &abi_version, sizeof(abi_version)) ||
        !load_function(library, "cf_context_create", &context_create, sizeof(context_create)) ||
        !load_function(library, "cf_service_create", &service_create, sizeof(service_create)) ||
        !load_function(library, "cf_service_call", &service_call, sizeof(service_call)) ||
        !load_function(library, "cf_last_error_json", &last_error_json, sizeof(last_error_json)) ||
        !load_function(library, "cf_string_free", &string_free, sizeof(string_free)) ||
        !load_function(library, "cf_service_release", &service_release, sizeof(service_release)) ||
        !load_function(library, "cf_context_release", &context_release, sizeof(context_release))) {
        dlclose(library);
        return 4;
    }
    if (strcmp(api_version(), "0.12.0") != 0 || abi_version() != 1U) {
        fprintf(stderr, "service consumer requires API 0.12.0 and ABI 1\n");
        dlclose(library);
        return 5;
    }
    context_json = read_file(argv[2]);
    if (context_json == NULL || context_create(context_json, &context) != CF_STATUS_OK) {
        free(context_json);
        (void)report_failure("context creation failed", last_error_json, string_free);
        dlclose(library);
        return 6;
    }
    free(context_json);

    service_config_size = strlen(argv[3]) + 64U;
    service_config = (char *)malloc(service_config_size);
    if (service_config == NULL ||
        snprintf(service_config, service_config_size, "{\"schemaVersion\":\"1\",\"serviceRoot\":\"%s\"}", argv[3]) < 0) {
        free(service_config);
        context_release(context);
        dlclose(library);
        return 7;
    }
    if (service_create(context, service_config, &service) != CF_STATUS_OK) {
        free(service_config);
        (void)report_failure("service creation failed", last_error_json, string_free);
        context_release(context);
        dlclose(library);
        return 8;
    }
    free(service_config);

    if (service_call(service,
                     "{\"schemaVersion\":\"1\",\"requestId\":\"consumer-01\",\"operation\":\"applications.seed-defaults\",\"payload\":{}}",
                     &response) != CF_STATUS_OK) {
        (void)report_failure("application seeding failed", last_error_json, string_free);
        service_release(service);
        context_release(context);
        dlclose(library);
        return 9;
    }
    string_free(response);
    response = NULL;
    if (service_call(service,
                     "{\"schemaVersion\":\"1\",\"requestId\":\"consumer-02\",\"operation\":\"applications.list\",\"payload\":{}}",
                     &response) != CF_STATUS_OK || response == NULL || strstr(response, "\"7zip\"") == NULL ||
        strstr(response, "\"sumatrapdf\"") == NULL || strstr(response, "\"notepad-plus-plus\"") == NULL) {
        (void)report_failure("application listing failed", last_error_json, string_free);
        string_free(response);
        service_release(service);
        context_release(context);
        dlclose(library);
        return 10;
    }

    puts("FORGEOS_COMPAT_SERVICE_OK");
    string_free(response);
    service_release(service);
    context_release(context);
    dlclose(library);
    return 0;
}
