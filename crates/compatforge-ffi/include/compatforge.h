#ifndef COMPATFORGE_H
#define COMPATFORGE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

const char *cf_api_version(void);
uint32_t cf_abi_version(void);

#ifdef __cplusplus
}
#endif

#endif
