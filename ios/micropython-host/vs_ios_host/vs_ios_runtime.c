#include "vs_ios_runtime.h"

#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>

#include "py/cstack.h"
#include "py/compile.h"
#include "py/gc.h"
#include "py/lexer.h"
#include "py/nlr.h"
#include "py/objlist.h"
#include "py/objstr.h"
#include "py/mpthread.h"
#include "py/mpstate.h"
#include "py/runtime.h"
#include "extmod/vfs.h"
#include "extmod/vfs_posix.h"

static bool runtime_started;
static bool runtime_tick_cached;
static char runtime_error[256];

// Implemented by the Objective-C bridge so that embedded-runtime diagnostics
// appear in the Simulator's unified log (stderr is not reliably captured by
// a UIKit process).
extern void vs_ios_runtime_log(const char *message);
extern void vs_ios_runtime_log_bytes(const char *message, size_t length);

static void ios_log_print_strn(void *env, const char *str, size_t len) {
    (void)env;
    vs_ios_runtime_log_bytes(str, len);
}

static const mp_print_t ios_log_print = {NULL, ios_log_print_strn};

static void ios_stderr_print_strn(void *env, const char *str, size_t len) {
    (void)env;
    (void)write(STDERR_FILENO, str, len);
}

const mp_print_t mp_stderr_print = {NULL, ios_stderr_print_strn};

void nlr_jump_fail(void *value) {
    vs_ios_runtime_log("FATAL: uncaught MicroPython exception");
    fprintf(stderr, "FATAL: uncaught MicroPython exception %p\n", value);
    abort();
}

static bool execute(const char *source) {
    nlr_buf_t nlr;
    if (nlr_push(&nlr) != 0) {
        vs_ios_runtime_log("execute: caught MicroPython exception");
        mp_obj_t exception = MP_OBJ_FROM_PTR(nlr.ret_val);
        const char *exception_name = qstr_str(mp_obj_get_type(exception)->name);
        vs_ios_runtime_log(exception_name);
        if (mp_obj_is_exception_instance(exception)) {
            mp_obj_t value = mp_obj_exception_get_value(exception);
            if (mp_obj_is_str_or_bytes(value)) {
                size_t value_length;
                const char *value_text = mp_obj_str_get_data(value, &value_length);
                vs_ios_runtime_log_bytes(value_text, value_length);
            }
        }
        // Formatting an exception can allocate.  Keep it behind a fresh NLR
        // boundary so diagnostics cannot escape the UIKit host process.
        nlr_buf_t report_nlr;
        if (nlr_push(&report_nlr) == 0) {
            mp_obj_print_exception(&ios_log_print, exception);
            nlr_pop();
        } else {
            vs_ios_runtime_log("execute: unable to format MicroPython exception");
        }
        strncpy(runtime_error, "MicroPython scene exception; see Simulator log", sizeof(runtime_error) - 1);
        runtime_error[sizeof(runtime_error) - 1] = '\0';
        return false;
    }

    mp_lexer_t *lex = mp_lexer_new_from_str_len(
        MP_QSTR__lt_stdin_gt_, source, strlen(source), false);
    mp_parse_tree_t parse_tree = mp_parse(lex, MP_PARSE_FILE_INPUT);
    mp_obj_t module_fun = mp_compile(&parse_tree, MP_QSTR__lt_stdin_gt_, false);
    mp_call_function_0(module_fun);
    mp_handle_pending(MP_HANDLE_PENDING_CALLBACKS_AND_EXCEPTIONS);
    nlr_pop();
    return true;
}

static bool prepare_tick_function(void) {
    // Compile the frame wrapper once.  Re-parsing and compiling this tiny
    // source string at 60 Hz was dominating the embedded VM's frame time.
    return execute(
        "import ventilastation.browser as __vs_ios_browser\n"
        "def __vs_ios_tick():\n"
        "    try:\n"
        "        __vs_ios_browser.tick()\n"
        "    except BaseException as _ios_error:\n"
        "        import __vs_host\n"
        "        __vs_host.log_error(repr(_ios_error))\n"
    );
}

static bool execute_cached_tick(void) {
    nlr_buf_t nlr;
    if (nlr_push(&nlr) != 0) {
        vs_ios_runtime_log("cached MicroPython tick exception");
        strncpy(runtime_error, "MicroPython frame exception", sizeof(runtime_error) - 1);
        runtime_error[sizeof(runtime_error) - 1] = '\0';
        return false;
    }
    qstr tick_name = qstr_from_str("__vs_ios_tick");
    mp_obj_t tick = mp_obj_dict_get(
        MP_OBJ_FROM_PTR(&MP_STATE_VM(dict_main)), MP_OBJ_NEW_QSTR(tick_name));
    mp_call_function_0(tick);
    mp_handle_pending(MP_HANDLE_PENDING_CALLBACKS_AND_EXCEPTIONS);
    nlr_pop();
    return true;
}

bool vs_ios_runtime_start(const char *runtime_root, const vs_ios_host_callbacks_t *callbacks) {
    if (runtime_started || runtime_root == NULL || chdir(runtime_root) != 0) {
        strncpy(runtime_error, "Unable to enter the staged runtime", sizeof(runtime_error) - 1);
        return false;
    }

    fprintf(stderr, "vs-ios: entered runtime root\n");

    // A UIKit process does not have the Unix port's process entrypoint to
    // establish a fresh VM context.  Initialise the single embedded context
    // explicitly before the port's TLS setup.
    memset(&mp_state_ctx, 0, sizeof(mp_state_ctx));

    #if MICROPY_PY_THREAD
    mp_thread_init();
    #endif

    // UIKit enters the VM from framework callbacks rather than a process
    // entrypoint.  Use the pthread's real stack boundary so GC's conservative
    // scan remains valid across later Timer/SwiftUI callbacks (capturing the
    // current SP here would make the scan range point in the wrong direction).
    void *stack_top = pthread_get_stackaddr_np(pthread_self());
    size_t stack_size = pthread_get_stacksize_np(pthread_self());
    mp_cstack_init_with_top(stack_top, stack_size);
    fprintf(stderr, "vs-ios: stack ready\n");

    #if MICROPY_ENABLE_GC
    char *heap = malloc(2 * 1024 * 1024);
    if (heap == NULL) {
        strncpy(runtime_error, "Unable to allocate the MicroPython heap", sizeof(runtime_error) - 1);
        return false;
    }
    gc_init(heap, heap + 2 * 1024 * 1024);
    fprintf(stderr, "vs-ios: gc ready\n");
    #endif

    mp_init();
    fprintf(stderr, "vs-ios: vm ready\n");

    #if MICROPY_VFS_POSIX
    mp_obj_t mount_args[2] = {
        MP_OBJ_TYPE_GET_SLOT(&mp_type_vfs_posix, make_new)(&mp_type_vfs_posix, 0, 0, NULL),
        MP_OBJ_NEW_QSTR(MP_QSTR__slash_),
    };
    mp_vfs_mount(2, mount_args, (mp_map_t *)&mp_const_empty_map);
    MP_STATE_VM(vfs_cur) = MP_STATE_VM(vfs_mount_table);
    #endif
    fprintf(stderr, "vs-ios: vfs ready\n");

    mp_sys_path = mp_obj_new_list(0, NULL);
    mp_obj_list_append(mp_sys_path, MP_OBJ_NEW_QSTR(MP_QSTR_));
    mp_obj_list_init(MP_OBJ_TO_PTR(mp_sys_argv), 0);

    vs_ios_host_set_callbacks(callbacks);
    vs_ios_host_set_running(true);
    fprintf(stderr, "vs-ios: executing boot\n");
    runtime_started = execute(
        "from ventilastation.director import configure_runtime\n"
        "configure_runtime('browser')\n"
        "import ventilastation.browser as _ios_host\n"
        "_ios_host.configure_worker_host('__vs_host')\n"
        "_ios_host.boot_main()\n"
        "from ventilastation.app_loader import load_app\n"
        "load_app('alecu.vyruss_vs2')\n");
    if (runtime_started) {
        runtime_tick_cached = prepare_tick_function();
        runtime_started = runtime_tick_cached;
    }
    fprintf(stderr, "vs-ios: boot returned %d\n", runtime_started);
    return runtime_started;
}

bool vs_ios_runtime_tick(void) {
    if (!runtime_started) {
        return false;
    }
    return runtime_tick_cached ? execute_cached_tick() : false;
}

void vs_ios_runtime_set_input(uint8_t joy1, uint8_t joy2, uint8_t extra, bool exit_requested) {
    vs_ios_host_set_input(joy1, joy2, extra, exit_requested);
}

const char *vs_ios_runtime_last_error(void) {
    return runtime_error;
}
