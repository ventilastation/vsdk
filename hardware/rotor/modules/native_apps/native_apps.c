#include "native_apps.h"

#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_system.h"

#include <stdio.h>
#include <string.h>

#include "py/runtime.h"

static char last_exit_reason[96] = "idle";

static bool native_partition_launch(const native_app_entry_t *entry) {
    const esp_partition_t *partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP,
        ESP_PARTITION_SUBTYPE_ANY,
        entry->partition
    );
    if (partition == NULL) {
        native_apps_set_last_exit_reason("native app partition missing");
        return false;
    }

    esp_err_t err = esp_ota_set_boot_partition(partition);
    if (err != ESP_OK) {
        native_apps_set_last_exit_reason("esp_ota_set_boot_partition failed");
        return false;
    }

    native_apps_set_last_exit_reason("rebooting into native app");
    esp_restart();
    return true;
}

static const native_app_entry_t native_apps_registry[] = {
    { "voom", "prboom-go", NULL },
};

static size_t native_apps_registry_len(void) {
    return sizeof(native_apps_registry) / sizeof(native_apps_registry[0]);
}

static const native_app_entry_t *native_apps_find(const char *name) {
    for (size_t i = 0; i < native_apps_registry_len(); ++i) {
        const native_app_entry_t *entry = &native_apps_registry[i];
        if (strcmp(entry->name, name) == 0) {
            return entry;
        }
    }
    return NULL;
}

void native_apps_set_last_exit_reason(const char *reason) {
    if (reason == NULL || reason[0] == '\0') {
        reason = "unknown";
    }
    snprintf(last_exit_reason, sizeof(last_exit_reason), "%s", reason);
}

const char *native_apps_last_exit_reason(void) {
    return last_exit_reason;
}

bool native_apps_available(const char *name) {
    const native_app_entry_t *entry = native_apps_find(name);
    if (entry == NULL) {
        return false;
    }
    if (entry->launch != NULL) {
        return true;
    }
    if (entry->partition == NULL || entry->partition[0] == '\0') {
        return false;
    }
    return esp_partition_find_first(
        ESP_PARTITION_TYPE_APP,
        ESP_PARTITION_SUBTYPE_ANY,
        entry->partition
    ) != NULL;
}

bool native_apps_launch(const char *name) {
    const native_app_entry_t *entry = native_apps_find(name);
    if (entry == NULL) {
        native_apps_set_last_exit_reason("unknown native app");
        return false;
    }
    if (entry->launch != NULL) {
        native_apps_set_last_exit_reason("launching");
        bool launched = entry->launch();
        if (!launched) {
            native_apps_set_last_exit_reason("native app launch rejected");
        }
        return launched;
    }

    if (entry->partition != NULL && entry->partition[0] != '\0') {
        return native_partition_launch(entry);
    }

    native_apps_set_last_exit_reason("native app has no launch route");
    return false;
}

static mp_obj_t native_apps_launch_obj(mp_obj_t name_obj) {
    const char *name = mp_obj_str_get_str(name_obj);
    if (native_apps_launch(name)) {
        return mp_const_true;
    }
    return mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_1(native_apps_launch_fun_obj, native_apps_launch_obj);

static mp_obj_t native_apps_available_obj(mp_obj_t name_obj) {
    const char *name = mp_obj_str_get_str(name_obj);
    if (native_apps_available(name)) {
        return mp_const_true;
    }
    return mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_1(native_apps_available_fun_obj, native_apps_available_obj);

static mp_obj_t native_apps_last_exit_reason_obj(void) {
    return mp_obj_new_str(native_apps_last_exit_reason(), strlen(native_apps_last_exit_reason()));
}
static MP_DEFINE_CONST_FUN_OBJ_0(native_apps_last_exit_reason_fun_obj, native_apps_last_exit_reason_obj);

static const mp_map_elem_t native_apps_globals_table[] = {
    { MP_OBJ_NEW_QSTR(MP_QSTR___name__), MP_OBJ_NEW_QSTR(MP_QSTR_vshw_native_apps) },
    { MP_OBJ_NEW_QSTR(MP_QSTR_launch), (mp_obj_t)&native_apps_launch_fun_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_available), (mp_obj_t)&native_apps_available_fun_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_last_exit_reason), (mp_obj_t)&native_apps_last_exit_reason_fun_obj },
};

static MP_DEFINE_CONST_DICT(
    mp_module_native_apps_globals,
    native_apps_globals_table
);

const mp_obj_module_t mp_module_native_apps = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp_module_native_apps_globals,
};

MP_REGISTER_MODULE(MP_QSTR_vshw_native_apps, mp_module_native_apps);
