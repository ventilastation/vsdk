import uselect
import usocket

def _load_wifi_config():
    # Primary: NVS namespace "voom_wifi" — shared with prboom-go, written by dev-deploy.
    try:
        import esp32
        nvs = esp32.NVS("voom_wifi")
        ssid_buf = bytearray(33)
        pass_buf = bytearray(65)
        ssid_len = nvs.get_blob("ssid", ssid_buf)
        pass_len = nvs.get_blob("password", pass_buf)
        ssid = ssid_buf[:ssid_len].decode()
        password = pass_buf[:pass_len].decode()
        if ssid:
            return {"ssid": ssid, "password": password}
    except Exception:
        pass
    # No credentials in NVS yet — set them with:
    #   make dev-deploy WIFI_SSID=... WIFI_PASS=...
    return {"ssid": "ventilastation", "password": "plagazombie2"}

try:
    import network
    import utime

    _wifi = _load_wifi_config()
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('connecting to network', _wifi["ssid"], end="")
        sta_if.active(True)
        sta_if.connect(_wifi["ssid"], _wifi["password"])
        while not sta_if.isconnected():
            print(".", end="")
            utime.sleep_ms(333)
        print()
    print('network config:', sta_if.ifconfig())

    # If running from factory (first boot after flash_vsdk_image), migrate to the
    # updatable micropython (ota_2) slot so future OTA updates don't touch factory.
    try:
        import esp32
        running = esp32.Partition(esp32.Partition.RUNNING)
        if running.info()[4] == "factory":
            mp = esp32.Partition.find(esp32.Partition.TYPE_APP, label="micropython")
            if mp:
                print("comms: first boot on factory — switching to micropython slot")
                mp[0].set_boot()
                import machine
                machine.reset()
    except Exception as _me:
        print("comms: ota migration check failed:", _me)

    # Confirm the running image is healthy so the bootloader doesn't roll back.
    try:
        import esp32
        esp32.Partition.mark_app_valid_cancel_rollback()
    except Exception:
        pass  # not an OTA image or already confirmed

except ImportError:
    print("no wifi module, skipping")
except Exception as _e:
    print("wifi setup failed:", _e)

UDP_THIS = "0.0.0.0", 5005
this_addr = usocket.getaddrinfo(*UDP_THIS)[0][-1]

sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
sock.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
sock.bind(this_addr)
sock.listen(10)
sock.setblocking(0)
print("listening on 5005")

# Control socket on port 5006 accepts one-line text commands from the emulator
# (e.g. "ota_start http://..."). Separate from the display connection so the
# button-byte protocol on port 5005 is unchanged.
_ctrl_sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
_ctrl_sock.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
_ctrl_sock.bind(usocket.getaddrinfo("0.0.0.0", 5006)[0][-1])
_ctrl_sock.listen(2)
_ctrl_sock.setblocking(0)
print("listening on 5006 (control)")

poller = uselect.poll()
poller.register(sock, uselect.POLLIN)
poller.register(_ctrl_sock, uselect.POLLIN)
conn = None
_new_connection = False
_pending_commands = []   # list of decoded command strings

def was_new_connection():
    global _new_connection
    if _new_connection:
        _new_connection = False
        return True
    return False

def receive(bufsize):
    global conn, _new_connection
    retval = None
    for obj, event, *more in poller.ipoll(0, 0):
        if obj is sock:
            if conn:
                conn.close()
                poller.unregister(conn)
            conn, addr = sock.accept()
            conn.setblocking(0)
            poller.register(conn, uselect.POLLIN)
            _new_connection = True
            print("comms: new connection from", addr)
        elif obj is _ctrl_sock:
            # Accept a short-lived control connection, read one command line.
            try:
                ctrl_conn, ctrl_addr = _ctrl_sock.accept()
                line = ctrl_conn.readline()
                ctrl_conn.close()
                if line:
                    _pending_commands.append(line.strip().decode("utf-8", "replace"))
            except Exception as _e:
                print("comms: ctrl accept error:", _e)
        else:
            try:
                b = obj.read(1)
            except OSError:
                b = None
            if b:
                retval = b
            else:
                obj.close()
                poller.unregister(obj)
                conn = None
    return retval


def next_command():
    """Return the next pending control command string, or None."""
    return _pending_commands.pop(0) if _pending_commands else None

def _drop_conn(reason):
    global conn
    print("comms: drop connection:", reason)
    conn.close()
    poller.unregister(conn)
    conn = None

def send(line, data=b""):
    global conn
    if conn:
        msg = line + b"\n" + data
        view = memoryview(msg)
        sent = 0
        while sent < len(msg):
            try:
                n = conn.write(view[sent:])
                if n is None:
                    n = 0
                sent += n
            except OSError as e:
                if e.args[0] == 11:  # EAGAIN: buffer full, retry
                    continue
                _drop_conn("OSError %d" % e.args[0])
                return
