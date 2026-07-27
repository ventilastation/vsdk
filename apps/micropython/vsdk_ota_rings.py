"""OTA progress display: concentric single-LED "rings" on the POV display.

The display renders identically at every rotation column (persistence of
vision paints a full circle), so a *ring* (one row/radius, lit at every
column) can only convey a value through which row lights up, not through
any per-column shape. A short text label is different: unlike a ring, it's
given a strip *narrower* than the full 256-column disc and a fixed x
position, so it only lights up across the angular arc its own width
covers, appearing once as the disc spins past that arc -- the same trick
system/launcher/code/__init__.py uses for the "VENTILASTATION" logo, except
that one is a single pre-drawn bitmap Sprite, not text. There's still no
general string-to-Sprite renderer usable from here -- the real tinyfont
system (system/shared/other/images/tinyfont_*.png, tools/generate_tinyfont_*.py)
is a genuine per-glyph bitmap font, but every runtime call site depends on
director.load_rom() having read a ROM off the VFS filesystem into a
Sprite-per-character-cell, none of which this frozen, pre-vfs module can
use. _TINY_FONT below is instead a small, hand-embedded subset of that same
glyph data -- see its own comment -- covering only the two fixed messages
this module ever shows, rendered as one static strip per message (not one
Sprite per character), following the same precedent already used for
exactly this in emulator/unplugged_video.py.

Each kind of information gets its own ring, at its own single-LED radius,
in its own color, all shown simultaneously:

  - WiFi connecting: only the outermost LED, blue. After a few failed
    connection attempts (see updater.py's _wifi_connect()), that ring turns
    red instead -- still retrying, not given up -- via show_wifi_problem().
  - Throughout both of the above, and the "preparing" stage right after: a
    text label reading "updating", or "wifi problem" during the red state
    -- see _TINY_FONT and _build_label_strip() below.
  - Preparing (WiFi already connected, but before the file/partition
    manifest comparison has produced a real total to show progress
    against -- resolving the base station's address, fetching the
    manifest, scanning for stale .tmp files): an orange ring that bounces
    in and out by one LED per checkpoint reached, same idea as the
    activity pulses below. Without this, this phase used to show nothing
    at all -- not even the (by-then-hidden) WiFi ring -- which reads as a
    stall rather than progress.
  - Partition writes (tier 2/3, counted in 4096-byte blocks across every
    partition that needs writing): a 50%-gray ring whose radius closes in
    from the outermost LED (0%) to the innermost (99%) as blocks are
    written, plus a 10%-yellow ring that bounces in and out by one LED
    every time a block is actually written -- a "yes, it's alive" pulse
    distinct from the calm progress ring.
  - LFS file sync (tier 1, counted in bytes across every file that needs
    downloading): the same idea in white (progress) and green (activity).

Each tier's rings are hidden as soon as that tier finishes (see
hide_file_rings()/hide_partition_rings()) rather than left showing their
last position into the next tier -- a finished operation should look
finished, not still lit.

Where two rings land on the same LED, white always wins; see _Z_ORDER.

Renders through vshw_vs2 (render_vs2(), the same path every game uses) with
the background starfield explicitly turned off for the duration -- gpu.c's
render()/render_vs2() both draw it unconditionally otherwise, which is what
made an earlier attempt at this feature look like it was doing nothing at
all: the progress indicator was rendering correctly underneath, but the
ever-present, visually busy starfield buried it. vshw_vs2 is a native
module with no dependency on the vfs-resident vs2.py package (the layer/
sprite/tilemap primitives it exposes are exactly what vs2.py itself builds
on) -- see vs2_native.c -- so using it here doesn't compromise this module's
own vfs-independence requirement, below.

Frozen at the top level (not nested under ventilastation/) so it works from
vsdk_recovery.py with vfs completely empty, same as updater.py/boot.py/
vsdk_uart_log.py -- see vsdk_recovery.py's docstring for why a frozen
submodule nested under a vfs-resident package isn't reliably reachable.
"""

try:
    import vshw_povdisplay as _display
    import vshw_sprites as _sprites  # only for set_imagestrip() -- image_stripes[] is shared with vshw_vs2
    import vshw_vs2 as _vs2
    _NATIVE = True
except ImportError:
    _NATIVE = False

_VS2_FLAG_VISIBLE = 0x01
_VS2_FLAG_FLIP_Y = 0x04  # 0x02 (FLIP_X) also works -- see _set_label()'s own comment for why this one shipped

PIXELS = 54  # must match gpu.h's PIXELS -- the physical LED count per arm.

_WIDTH_BYTE = 255  # "actually 256" -- see gpu.c's `if (width == 255) width++`.
WIDTH = 256
TRANSPARENT = 0xFF
_LIT = 1

# perspective=2 in render()'s HUD mode maps strip row y directly onto LED
# (PIXELS-1-y) with sprite_y=0 -- row 0 is the outermost LED, row PIXELS-1
# the innermost (confirmed against povdisplay.c's init_buffers(): framebuffer
# index 0 is the hub-shared center LED, so PIXELS-1 is the tip).
_PERSPECTIVE_HUD = 2

# One ring per kind of information, each its own strip slot + palette group
# (palette is a per-strip property, not per-sprite -- see sprites.c). Colors
# are (blue, green, red) bytes, packed as [255, b, g, r] per palette entry --
# see _build_palette()'s wire format below.
_WIFI = "wifi"
_WIFI_PROBLEM = "wifi_problem"
_PREP_ACTIVITY = "prep_activity"
_PARTITION_PROGRESS = "partition_progress"
_PARTITION_ACTIVITY = "partition_activity"
_FILE_PROGRESS = "file_progress"
_FILE_ACTIVITY = "file_activity"
_LABEL = "label"

_RING_COLOR = {
    _WIFI: (200, 60, 0),                # blue
    _WIFI_PROBLEM: (0, 0, 255),            # red
    _PREP_ACTIVITY: (0, 140, 255),         # orange
    _PARTITION_PROGRESS: (128, 128, 128),  # 50% gray
    _PARTITION_ACTIVITY: (0, 90, 90),      # dim (~10%) yellow
    _FILE_PROGRESS: (255, 255, 255),       # white
    _FILE_ACTIVITY: (0, 200, 0),           # green
    _LABEL: (255, 255, 255),               # white
}

# Six rows per glyph, 3 usable columns per row (bit 2 = leftmost); only the
# letters needed for "updating" and "wifi problem" (the only two messages
# this module ever shows). " a b d e g l n o p r u" copied verbatim from
# emulator/unplugged_video.py's own TINY_FONT (same source glyphs, same
# extraction); "f i m t w" copied from apps/retro-go/components/retro-go/
# drivers/display/tinyfont_data.h (generated by tools/generate_tinyfont_c.py
# from the same tinyfont_white.png) -- both ultimately the same font this
# module's own docstring explains it otherwise has no way to use.
_TINY_FONT = {
    " ": (0, 0, 0, 0, 0, 0),
    "a": (0, 3, 5, 5, 3, 0),
    "b": (4, 6, 5, 5, 6, 0),
    "d": (1, 3, 5, 5, 3, 0),
    "e": (0, 2, 5, 6, 3, 0),
    "f": (1, 2, 7, 2, 2, 0),
    "g": (0, 2, 5, 3, 1, 2),
    "i": (0, 2, 0, 2, 2, 0),
    "l": (2, 2, 2, 2, 1, 0),
    "m": (0, 5, 7, 5, 5, 0),
    "n": (0, 6, 5, 5, 5, 0),
    "o": (0, 2, 5, 5, 2, 0),
    "p": (0, 6, 5, 5, 6, 4),
    "r": (0, 2, 5, 4, 4, 0),
    "t": (2, 7, 2, 2, 2, 0),
    "u": (0, 5, 5, 5, 3, 0),
    "w": (0, 5, 5, 7, 5, 0),
}
_GLYPH_WIDTH = 3
_GLYPH_HEIGHT = 6
_CHAR_STEP = _GLYPH_WIDTH + 1  # one blank column of spacing between glyphs

# This module's row convention (0=outermost, PIXELS-1=innermost) generalizes
# to a sprite with a nonzero y position as row+y (see render_vs2()'s
# `px_y = PIXELS - 1 - y` where `y = source_row + sprite_y`) -- so setting
# the label sprite's y to this value places its own row 0 at LED row
# _LABEL_ROW in that same convention. Chosen to clear the WiFi ring (row 0)
# by a few LEDs while still leaving the rest of the radius free for
# _PREP_ACTIVITY's full bounce to pass behind it.
_LABEL_ROW = 10

# Stacking order, most-visible first: when two rings land on the same LED,
# the one drawn *last* wins (render()'s sprite loop runs high id -> low id,
# and lower ids draw on top -- see gpu.c). Sprites are created in this same
# order below, so the first-created (_FILE_PROGRESS, i.e. white) gets the
# lowest sprite id and therefore always wins, per the user's requirement;
# the rest is this module's own judgment call, not separately specified.
# _PREP_ACTIVITY/_WIFI/_WIFI_PROBLEM never overlap in time with anything
# else at the same radius (0, the outermost LED) except each other, and
# show_wifi_connecting()/show_wifi_problem() never show both at once, so
# their relative order doesn't matter in practice. _LABEL is listed first
# (lowest id) so the text always stays legible over _PREP_ACTIVITY passing
# through the same radius on its way past _LABEL_ROW; it's a different
# width/height than every ring (see _build_label_strip()), which is fine --
# _STRIP_SLOT/_PALETTE_GROUP below just need a slot per name, not a
# uniform strip shape.
_Z_ORDER = (_LABEL, _FILE_PROGRESS, _FILE_ACTIVITY, _PARTITION_ACTIVITY, _PARTITION_PROGRESS, _WIFI, _WIFI_PROBLEM, _PREP_ACTIVITY)

_STRIP_SLOT = {name: 20 + i for i, name in enumerate(_Z_ORDER)}  # arbitrary, just needs to not collide with another module's strip slot
_PALETTE_GROUP = {name: i for i, name in enumerate(_Z_ORDER)}

_DISPLAY_NVS_KEYS = (
    "hall_gpio", "irdiode_gpio", "led_spi_host",
    "led_clk", "led_mosi", "led_cs", "led_freq",
)

_started = False
_sprite = {}  # name -> Sprite instance
_row = {}     # name -> currently-shown row, or None if disabled
_palette_buffer = None  # keeps set_palettes()'s buffer GC-rooted -- see _strip_buffer below

# vshw_sprites.set_imagestrip() (native) only stores the raw pointer out of
# whatever buffer it's given -- it never keeps the owning Python object
# alive (see sprites.c, and docs/internals/menu-sprite-corruption.md's Bug
# #1, the identical issue in director.py). Without a live reference here,
# the memoryview built by _set_ring() has zero references the instant
# set_imagestrip() returns and is immediately GC-eligible. This turned out
# not to be the cause of the corruption actually seen on hardware (see
# docs/internals/ota-ring-sprite-corruption.md -- that was Bug #2's type
# confusion, fixed by the memoryview(...) wrap itself), but it's a real
# latent risk independent of that bug, so it's still worth keeping -- see
# director.py's own _stripe_buffers, which keeps both fixes for the same
# reason. Keyed by ring name and never cleared wholesale.
_strip_buffer = {}


def _read_display_args():
    import esp32
    nvs = esp32.NVS("vs_board")
    return tuple(nvs.get_i32(key) for key in _DISPLAY_NVS_KEYS)


def _build_palette():
    # A plain bytearray, not bytes: vshw_povdisplay.set_palettes() (like
    # set_imagestrip() below) reads its argument via memoryview_data(),
    # which casts to mp_obj_array_t* and computes items+free for the data
    # pointer. `free` is a valid element offset only for a real
    # memoryview/bytearray; for a plain bytes/str object that identical
    # struct slot holds the object's eagerly-computed hash instead (see
    # docs/internals/menu-sprite-corruption.md's Bug #2, which hit this
    # exact function pair in director.py). Callers must wrap this in
    # memoryview(...) before handing it to set_palettes() -- see ensure_started().
    palette = bytearray(256 * 4 * len(_Z_ORDER))
    for name in _Z_ORDER:
        b, g, r = _RING_COLOR[name]
        offset = _PALETTE_GROUP[name] * 256 * 4 + _LIT * 4
        palette[offset:offset + 4] = bytes([255, b, g, r])
    return palette


def _build_ring_strip(name, row):
    """One WIDTH x PIXELS x 1-frame strip with `row` lit across every
    column (a full-circle ring at that radius) and everything else
    transparent, or fully blank if row is None. Returns a bytearray, not
    bytes -- see _build_palette()'s comment; the same memoryview_data()
    constraint applies to set_imagestrip(). Callers must wrap this in
    memoryview(...) before handing it to set_imagestrip() -- see _set_ring()."""
    header = bytearray([_WIDTH_BYTE, PIXELS, 1, _PALETTE_GROUP[name]])
    body = bytearray(b"\xff" * (WIDTH * PIXELS))
    if row is not None:
        for col in range(WIDTH):
            body[col * PIXELS + row] = _LIT
    return header + body


def _build_label_strip(text):
    """A (len(text)*_CHAR_STEP) x _GLYPH_HEIGHT x 1-frame strip -- narrower
    than the full WIDTH used by _build_ring_strip(), so (see this module's
    own docstring) it only lights up across its own angular arc instead of
    wrapping all the way around like a ring. Same bytearray-not-bytes and
    memoryview(...)-at-the-call-site requirements as _build_ring_strip().

    Built in plain left-to-right reading order, unmirrored -- confirmed
    backwards on real hardware otherwise (this display's column mapping
    mirrors both character order and each glyph's own x axis, exactly as
    emulator/unplugged_video.py's render_unplugged_frame() already
    documents and manually corrects for). Either FLIP_X or FLIP_Y alone
    reads correctly -- flipping *either* axis undoes that same mirror --
    and the two choices are 180 degrees apart from each other (see gpu.c's
    render_vs2(): FLIP_X reverses only the column mapping, FLIP_Y reverses
    only the row mapping, entirely independently of each other). Setting
    *both* flags at once was tried and confirmed wrong on a real capture --
    it reads just as scrambled as no flip at all, not a valid third option.
    _set_label() below sets FLIP_Y: after shipping FLIP_X and
    seeing it upside-down on the real device, this is the one that reads
    right-side-up for someone viewing the fan from its usual side --
    confirmed against a real capture, not a guess."""
    width = len(text) * _CHAR_STEP
    header = bytearray([width, _GLYPH_HEIGHT, 1, _PALETTE_GROUP[_LABEL]])
    body = bytearray(b"\xff" * (width * _GLYPH_HEIGHT))
    for index, character in enumerate(text):
        bits_per_row = _TINY_FONT.get(character, _TINY_FONT[" "])
        col0 = index * _CHAR_STEP
        for row, bits in enumerate(bits_per_row):
            for glyph_x in range(_GLYPH_WIDTH):
                if bits & (1 << (_GLYPH_WIDTH - 1 - glyph_x)):
                    body[(col0 + glyph_x) * _GLYPH_HEIGHT + row] = _LIT
    return header + body


_label_text = None  # the text currently shown, or None if hidden
_label_buffer = None  # keeps set_imagestrip()'s buffer GC-rooted -- see _strip_buffer


def _set_label(text):
    global _label_text, _label_buffer
    if not _started or _label_text == text:
        return
    _label_text = text
    built = memoryview(_build_label_strip(text))
    _label_buffer = built
    _sprites.set_imagestrip(_STRIP_SLOT[_LABEL], built)
    sprite = _sprite[_LABEL]
    width = len(text) * _CHAR_STEP
    sprite.set_x(-(width // 2))  # centered on column 0, the hall-sensor reference angle
    sprite.set_y(_LABEL_ROW)
    sprite.set_frame(0)
    # FLIP_Y corrects the mirroring described in _build_label_strip()'s
    # own comment -- both FLIP_X and FLIP_Y independently fix it, 180
    # degrees apart from each other; FLIP_X shipped first and read upside-
    # down on the real device, so this switched to FLIP_Y instead (not
    # FLIP_X plus FLIP_Y -- confirmed on hardware that combining both
    # reintroduces the original scrambled look, not a rotated-but-still-
    # correct one).
    sprite.set_flags(_VS2_FLAG_VISIBLE | _VS2_FLAG_FLIP_Y)


def _hide_label():
    global _label_text
    if _label_text is None:
        return
    _label_text = None
    if _started:
        _sprite[_LABEL].disable()


def ensure_started():
    """Idempotent: init the POV display and create the (initially disabled)
    ring sprites. Returns False without doing anything if the native
    display modules aren't linked in (desktop/emulator) or the board's
    wiring isn't provisioned yet -- best-effort, like vsdk_recovery.py's
    old _make_sprite()."""
    global _started
    if _started:
        return True
    if not _NATIVE:
        return False
    try:
        display_args = _read_display_args()
    except Exception:
        return False
    global _palette_buffer
    try:
        _display.init(PIXELS, *display_args)
        _display.set_gamma_mode(1)
        _display.set_starfield_enabled(False)
        # vshw_povdisplay.set_palettes() has the exact same raw-pointer,
        # no-GC-root behavior as set_imagestrip() (see _strip_buffer's
        # comment, and menu-sprite-corruption.md's Bug #1, which covers
        # both calls) -- director.py roots this one in self.palette_data;
        # this module's equivalent is _palette_buffer. memoryview(...) is
        # required, not optional -- see _build_palette()'s comment.
        _palette_buffer = memoryview(_build_palette())
        _display.set_palettes(_palette_buffer)
        _vs2.set_active(True)
        for name in _Z_ORDER:
            sprite = _vs2.Sprite()
            sprite.set_strip(_STRIP_SLOT[name])
            sprite.set_perspective(_PERSPECTIVE_HUD)
            sprite.set_x(0)
            sprite.set_y(0)
            sprite.disable()
            _sprite[name] = sprite
            _row[name] = None
    except Exception as error:
        print("vsdk_ota_rings: display unavailable, continuing without it:", error)
        return False
    _started = True
    return True


def _set_ring(name, row):
    """row=None disables the ring; otherwise clamps into [0, PIXELS) and
    (re)builds+registers that ring's one-frame strip -- set_imagestrip()
    only stores a pointer (see sprites.c), so this is a cheap atomic swap,
    not a copy into shared, concurrently-rendered memory. The built buffer
    is stashed in _strip_buffer to keep it GC-rooted for as long as the
    sprite's pointer references it -- see _strip_buffer's own comment."""
    if not _started:
        return
    if row is not None:
        row = 0 if row < 0 else (PIXELS - 1 if row >= PIXELS else row)
    if _row.get(name) == row:
        return
    _row[name] = row
    sprite = _sprite[name]
    if row is None:
        sprite.disable()
        return
    # memoryview(...) is required, not optional -- see _build_ring_strip()'s
    # comment.
    built = memoryview(_build_ring_strip(name, row))
    _strip_buffer[name] = built
    _sprites.set_imagestrip(_STRIP_SLOT[name], built)
    sprite.set_frame(0)
    sprite.set_flags(_VS2_FLAG_VISIBLE)


def _row_for_fraction(done, total):
    """0% -> row 0 (outermost), 99%+ -> row PIXELS-1 (innermost)."""
    if total <= 0:
        return 0
    fraction = done / total
    if fraction < 0:
        fraction = 0.0
    elif fraction > 1:
        fraction = 1.0
    return int(fraction * (PIXELS - 1))


def show_wifi_connecting():
    if ensure_started():
        _set_ring(_WIFI, 0)
        _set_ring(_WIFI_PROBLEM, None)
        _set_label("updating")


def show_wifi_problem():
    """Called after a few failed connection attempts (see updater.py's
    _wifi_connect()) -- WiFi is still being retried, not given up on, but a
    real outage should look different from the calm "just connecting"
    state instead of looking like a hang."""
    if ensure_started():
        _set_ring(_WIFI, None)
        _set_ring(_WIFI_PROBLEM, 0)
        _set_label("wifi problem")


def hide_wifi():
    _set_ring(_WIFI, None)
    _set_ring(_WIFI_PROBLEM, None)


def hide_prep_activity():
    """Also hides the "updating"/"wifi problem" label -- it's shown
    throughout the WiFi-connecting + preparing stretch (see
    show_wifi_connecting()/show_wifi_problem()) and has nothing further to
    say once real file/partition progress ring take over."""
    _set_ring(_PREP_ACTIVITY, None)
    _hide_label()


def set_file_progress(done_bytes, total_bytes):
    if ensure_started():
        _set_ring(_FILE_PROGRESS, _row_for_fraction(done_bytes, total_bytes))


def hide_file_rings():
    """Call once tier-1 (LFS sync) is done, so white/green don't linger
    at their last position through tier 2/3 -- a finished operation should
    look finished, not still lit."""
    _set_ring(_FILE_PROGRESS, None)
    _set_ring(_FILE_ACTIVITY, None)


def hide_partition_rings():
    """Same idea as hide_file_rings(), for tier 2/3 (gray/yellow)."""
    _set_ring(_PARTITION_PROGRESS, None)
    _set_ring(_PARTITION_ACTIVITY, None)


_activity_pos = {_PARTITION_ACTIVITY: 0, _FILE_ACTIVITY: 0, _PREP_ACTIVITY: 0}
_activity_dir = {_PARTITION_ACTIVITY: 1, _FILE_ACTIVITY: 1, _PREP_ACTIVITY: 1}

# Each activity ring bounces between the center (PIXELS-1) and its own
# progress ring's *current* radius, not all the way out to the outermost
# LED -- the outer end of that range is "already done", so bouncing past it
# read as noise rather than activity. _PREP_ACTIVITY has no progress
# counterpart (see its own comment above) and keeps the full range.
_ACTIVITY_PROGRESS_RING = {
    _PARTITION_ACTIVITY: _PARTITION_PROGRESS,
    _FILE_ACTIVITY: _FILE_PROGRESS,
}


def _pulse_activity(name):
    if not ensure_started():
        return
    progress_name = _ACTIVITY_PROGRESS_RING.get(name)
    lo = _row.get(progress_name) if progress_name else None
    if lo is None:
        lo = 0
    hi = PIXELS - 1
    pos = _activity_pos[name] + _activity_dir[name]
    if pos >= hi:
        pos = hi
        _activity_dir[name] = -1
    elif pos <= lo:
        pos = lo
        _activity_dir[name] = 1
    _activity_pos[name] = pos
    _set_ring(name, pos)


def pulse_file_activity():
    _pulse_activity(_FILE_ACTIVITY)


def pulse_prep_activity():
    _pulse_activity(_PREP_ACTIVITY)


def set_partition_progress(done_blocks, total_blocks):
    if ensure_started():
        _set_ring(_PARTITION_PROGRESS, _row_for_fraction(done_blocks, total_blocks))


def pulse_partition_activity():
    _pulse_activity(_PARTITION_ACTIVITY)


def clear():
    """Hide every ring and restore the starfield for whatever runs next
    (a game, the menu, or another vs2 scene) -- deliberately doesn't touch
    vs2_render_active or the sprite registrations themselves (no
    vshw_vs2.reset_scene()), so this module's own sprites stay valid and
    reusable if another OTA/recovery attempt calls into it again in the
    same boot."""
    for name in _Z_ORDER:
        _set_ring(name, None)
    _hide_label()
    if _started:
        try:
            _display.set_starfield_enabled(True)
        except Exception:
            pass
