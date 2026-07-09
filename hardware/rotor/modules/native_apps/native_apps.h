#ifndef VSDK_NATIVE_APPS_H
#define VSDK_NATIVE_APPS_H

#include <stdbool.h>

typedef bool (*native_app_launch_fn_t)(void);

typedef struct {
    const char *name;
    const char *partition;
    native_app_launch_fn_t launch;
} native_app_entry_t;

bool native_apps_available(const char *name);
bool native_apps_launch(const char *name);
const char *native_apps_last_exit_reason(void);
void native_apps_set_last_exit_reason(const char *reason);

#endif
