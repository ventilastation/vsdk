// Compatibility shims for the Unix-port sources when built against the iOS
// SDK.  Ventilastation does not expose os.system(), but its Unix port source
// still compiles its implementation.  Keep it safely unsupported on iOS.

#include <errno.h>
#include <pthread.h>
#include <stdlib.h>

static inline int vs_ios_system(const char *command) {
    (void)command;
    errno = ENOSYS;
    return -1;
}

#define system vs_ios_system

// The Unix command-line parser references this helper even when the Python
// thread module is disabled.  It is supplied by mpthreadport.c on Apple.
void mp_thread_set_realtime(void);
