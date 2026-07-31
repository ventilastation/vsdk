#include <stdint.h>

#include "py/obj.h"
#include "py/runtime.h"
#include "vs_ios_host.h"

extern void vs_ios_runtime_log_bytes(const char *message, size_t length);

// __vs_host intentionally mirrors the JS proxy registered by wasm-worker.js.
// BrowserDisplay prefers the *_ptr APIs, allowing the native renderer to copy
// data directly from the MicroPython heap without allocating Python objects.

static mp_obj_t host_get_joy1(void) {
    return MP_OBJ_NEW_SMALL_INT(vs_ios_host_get_joy1());
}
static MP_DEFINE_CONST_FUN_OBJ_0(host_get_joy1_obj, host_get_joy1);

static mp_obj_t host_get_joy2(void) {
    return MP_OBJ_NEW_SMALL_INT(vs_ios_host_get_joy2());
}
static MP_DEFINE_CONST_FUN_OBJ_0(host_get_joy2_obj, host_get_joy2);

static mp_obj_t host_get_extra(void) {
    return MP_OBJ_NEW_SMALL_INT(vs_ios_host_get_extra());
}
static MP_DEFINE_CONST_FUN_OBJ_0(host_get_extra_obj, host_get_extra);

static mp_obj_t host_consume_exit(void) {
    return mp_obj_new_bool(vs_ios_host_consume_exit());
}
static MP_DEFINE_CONST_FUN_OBJ_0(host_consume_exit_obj, host_consume_exit);

static mp_obj_t host_consume_full_frame_request(void) {
    return mp_obj_new_bool(vs_ios_host_consume_full_frame_request());
}
static MP_DEFINE_CONST_FUN_OBJ_0(host_consume_full_frame_request_obj, host_consume_full_frame_request);

static mp_obj_t host_is_running(void) {
    return mp_obj_new_bool(vs_ios_host_is_running());
}
static MP_DEFINE_CONST_FUN_OBJ_0(host_is_running_obj, host_is_running);

static mp_obj_t host_log_error(mp_obj_t message) {
    size_t length;
    const char *text = mp_obj_str_get_data(message, &length);
    vs_ios_runtime_log_bytes(text, length);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(host_log_error_obj, host_log_error);

static const uint8_t *host_pointer(mp_obj_t value) {
    return (const uint8_t *)(uintptr_t)mp_obj_get_int_truncated(value);
}

static size_t host_length(mp_obj_t value) {
    mp_int_t length = mp_obj_get_int(value);
    if (length < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("negative buffer length"));
    }
    return (size_t)length;
}

static mp_obj_t host_post_command_ptr(size_t n_args, const mp_obj_t *args) {
    vs_ios_host_post_command(
        host_pointer(args[0]), host_length(args[1]),
        host_pointer(args[2]), host_length(args[3])
    );
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(host_post_command_ptr_obj, 4, 4, host_post_command_ptr);

static mp_obj_t host_post_present_ptr(size_t n_args, const mp_obj_t *args) {
    vs_ios_host_post_present(
        host_pointer(args[0]), host_length(args[1]),
        host_pointer(args[2]), host_length(args[3])
    );
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(host_post_present_ptr_obj, 4, 4, host_post_present_ptr);

static const mp_rom_map_elem_t host_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR___vs_host) },
    { MP_ROM_QSTR(MP_QSTR_get_buttons), MP_ROM_PTR(&host_get_joy1_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_joy1), MP_ROM_PTR(&host_get_joy1_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_joy2), MP_ROM_PTR(&host_get_joy2_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_extra), MP_ROM_PTR(&host_get_extra_obj) },
    { MP_ROM_QSTR(MP_QSTR_consume_exit), MP_ROM_PTR(&host_consume_exit_obj) },
    { MP_ROM_QSTR(MP_QSTR_consume_full_frame_request), MP_ROM_PTR(&host_consume_full_frame_request_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_running), MP_ROM_PTR(&host_is_running_obj) },
    { MP_ROM_QSTR(MP_QSTR_log_error), MP_ROM_PTR(&host_log_error_obj) },
    { MP_ROM_QSTR(MP_QSTR_post_command_ptr), MP_ROM_PTR(&host_post_command_ptr_obj) },
    { MP_ROM_QSTR(MP_QSTR_post_present_ptr), MP_ROM_PTR(&host_post_present_ptr_obj) },
};
static MP_DEFINE_CONST_DICT(host_module_globals, host_module_globals_table);

const mp_obj_module_t vs_ios_host_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&host_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR___vs_host, vs_ios_host_module);
