#ifndef COMPATFORGE_H
#define COMPATFORGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct cf_context cf_context_t;
typedef struct cf_launch cf_launch_t;
typedef struct cf_prepared_launch cf_prepared_launch_t;
typedef struct cf_service cf_service_t;
typedef uint32_t cf_status_t;

#define CF_STATUS_OK ((cf_status_t)0)
#define CF_STATUS_NULL_POINTER ((cf_status_t)1)
#define CF_STATUS_INVALID_UTF8 ((cf_status_t)2)
#define CF_STATUS_INVALID_JSON ((cf_status_t)3)
#define CF_STATUS_INVALID_ARGUMENT ((cf_status_t)4)
#define CF_STATUS_PLANNING_FAILED ((cf_status_t)5)
#define CF_STATUS_AUTHORIZATION_FAILED ((cf_status_t)6)
#define CF_STATUS_PROCESS_FAILED ((cf_status_t)7)
#define CF_STATUS_TIMEOUT ((cf_status_t)8)
#define CF_STATUS_END_OF_STREAM ((cf_status_t)9)
#define CF_STATUS_PROBE_FAILED ((cf_status_t)10)
#define CF_STATUS_INSPECTION_FAILED ((cf_status_t)11)
#define CF_STATUS_PREPARATION_FAILED ((cf_status_t)12)
#define CF_STATUS_BOOTSTRAP_FAILED ((cf_status_t)13)
#define CF_STATUS_SERVICE_FAILED ((cf_status_t)14)
#define CF_STATUS_NOT_FOUND ((cf_status_t)15)
#define CF_STATUS_CONFLICT ((cf_status_t)16)
#define CF_STATUS_PANIC ((cf_status_t)255)

const char *cf_api_version(void);
uint32_t cf_abi_version(void);
cf_status_t cf_probe_capabilities(char **out_capabilities_json);
cf_status_t cf_inspect_executable(
    const char *absolute_path,
    char **out_report_json
);

cf_status_t cf_context_create(const char *config_json, cf_context_t **out_context);
cf_status_t cf_macos_local_context_create(
    const char *request_json,
    cf_context_t **out_context,
    char **out_receipt_json
);
cf_status_t cf_capabilities_get(
    const cf_context_t *context,
    char **out_report_json
);
cf_status_t cf_service_create(
    const cf_context_t *context,
    const char *service_config_json,
    cf_service_t **out_service
);
cf_status_t cf_service_call(
    const cf_service_t *service,
    const char *request_json,
    char **out_response_json
);
cf_status_t cf_compile_launch(
    const cf_context_t *context,
    const char *request_json,
    char **out_plan_json
);
cf_status_t cf_launch_prepare(
    const cf_context_t *context,
    const char *absolute_executable_path,
    const char *request_json,
    cf_prepared_launch_t **out_prepared
);
cf_status_t cf_prepared_launch_inspection_get(
    const cf_prepared_launch_t *prepared,
    char **out_report_json
);
cf_status_t cf_prepared_launch_plan_get(
    const cf_prepared_launch_t *prepared,
    char **out_plan_json
);
cf_status_t cf_prepared_launch_start(
    const cf_context_t *context,
    const cf_prepared_launch_t *prepared,
    cf_launch_t **out_launch
);
cf_status_t cf_launch_start(
    const cf_context_t *context,
    const char *plan_json,
    cf_launch_t **out_launch
);
cf_status_t cf_launch_next_event(
    const cf_launch_t *launch,
    uint32_t timeout_ms,
    char **out_event_json
);
cf_status_t cf_launch_terminate(const cf_launch_t *launch);
cf_status_t cf_last_error_json(char **out_error_json);

void cf_string_free(char *value);
void cf_context_release(cf_context_t *context);
void cf_service_release(cf_service_t *service);
void cf_prepared_launch_release(cf_prepared_launch_t *prepared);
void cf_launch_release(cf_launch_t *launch);

#ifdef __cplusplus
}
#endif

#endif
