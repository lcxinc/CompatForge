#ifndef COMPATFORGE_H
#define COMPATFORGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct cf_context cf_context_t;
typedef uint32_t cf_status_t;

#define CF_STATUS_OK ((cf_status_t)0)
#define CF_STATUS_NULL_POINTER ((cf_status_t)1)
#define CF_STATUS_INVALID_UTF8 ((cf_status_t)2)
#define CF_STATUS_INVALID_JSON ((cf_status_t)3)
#define CF_STATUS_INVALID_ARGUMENT ((cf_status_t)4)
#define CF_STATUS_PLANNING_FAILED ((cf_status_t)5)
#define CF_STATUS_PANIC ((cf_status_t)255)

const char *cf_api_version(void);
uint32_t cf_abi_version(void);

cf_status_t cf_context_create(const char *config_json, cf_context_t **out_context);
cf_status_t cf_compile_launch(
    const cf_context_t *context,
    const char *request_json,
    char **out_plan_json
);
cf_status_t cf_last_error_json(char **out_error_json);

void cf_string_free(char *value);
void cf_context_release(cf_context_t *context);

#ifdef __cplusplus
}
#endif

#endif
