"""Frozen fallback entry point invoked directly by main.c when vfs has no
main.py. Kept as its own tiny, distinctly-named module rather than folded
into vsdk_recovery: pyexec_file_if_exists() runs a frozen module of the
exact requested name unconditionally, before ever checking the filesystem,
so this name must never collide with "main.py" or anything else that should
come from vfs.
"""

import vsdk_recovery

vsdk_recovery.run()
