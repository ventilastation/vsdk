# Native MicroPython host

`vs_ios_host` is a MicroPython user C module for the native iOS port. It is
deliberately compatible with the browser worker's `__vs_host` proxy:

- `get_joy1`, `get_joy2`, `get_extra`, and `consume_exit` supply native input;
- `post_command_ptr` carries palette and image-strip updates;
- `post_present_ptr` carries the sprite table and frame metadata in one call.

The iOS runtime will call the existing Python setup without modification:

```python
from ventilastation.director import configure_runtime
configure_runtime("browser")
import ventilastation.browser as browser
browser.configure_worker_host("__vs_host")
browser.boot_main()
```

That reuses the existing browser platform and allows the launcher, Vyruss VS2,
and Vixeous to run from their original files. The next implementation step is
to compile this module together with the local MicroPython source tree and add
the Objective-C VM lifecycle bridge.
