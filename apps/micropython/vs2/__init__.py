"""The sealed, scene-owned Ventilastation display API (revision 2).

V1 lives in :mod:`ventilastation.sprites` and deliberately remains separate.
This module is the complete V2 surface: a scene builds a fixed display graph
once, then mutates it without allocating renderer records while it runs.
"""

import struct
import utime
from math import atan2, pi, sqrt

from ventilastation import api_guard
from ventilastation.director import director, stripes
from ventilastation.display_geometry import DISPLAY_HEIGHT, DISPLAY_WIDTH
from ventilastation.scene import Scene as _Scene
from ventilastation.runtime import get_platform

from . import params
from . import projection as _curves
from .store import store


def _claim():
    api_guard.claim("vs2", "vs2")


_claim()


# Projection values are the native renderer's wire values.
FULLSCREEN = 0
TUNNEL = 1
HUD = 2

TRANSPARENT = 255
EMPTY_TILE = 255
NO_LAYER = 255
RECYCLE = object()

#: Sentinel an Action's or Behavior's per-sprite dispatch returns when a
#: durative operation finished this tick (``MoveTo`` arrived, ``Animate``
#: completed a ``once`` cycle, ``Wait`` elapsed). Distinct from ``None``,
#: which means "nothing notable happened".
DONE = object()

#: Curve-family surface re-exported at the package's top level so a curve
#: reads as ``vs2.VS1_TUNNEL`` / ``vs2.tunnel(...)``, matching
#: :data:`vs2.TUNNEL` and friends. ``vs2.TUNNEL``/``vs2.HUD``/
#: ``vs2.FULLSCREEN`` above stay the revision-2 wire-format mode ints,
#: unchanged; these are the 256-byte depth<->row tables a layer's
#: :attr:`Layer.projection` can also be set to. See "How the int-mode
#: projection and curve-accepting projection reconcile" in this module's
#: notes for why the two namespaces don't collide.
VS1_TUNNEL = _curves.VS1_TUNNEL
tunnel = _curves.tunnel

#: Names the framework reserves on any sprite, pool, scene or project --
#: for the movement accumulator (``dx``, ``dy``), the state-machine fields
#: (``fsm_state``, ``fsm_hold``, ``fsm_then``), and a Behavior's own
#: ``enabled`` switch. :meth:`SpritePool.var`, :meth:`Scene.var` and
#: :meth:`_Project.var` all reject these.
_RESERVED_VAR_NAMES = frozenset((
    "dx", "dy", "fsm_state", "fsm_hold", "fsm_then", "enabled",
))

FLAG_VISIBLE = 0x01
FLAG_FLIP_X = 0x02
FLAG_FLIP_Y = 0x04

PAYLOAD_MAGIC = b"VS2\0"
PAYLOAD_VERSION = 3
PAYLOAD_HEADER_SIZE = 16
PAYLOAD_LAYER_SIZE = 8
PAYLOAD_SPRITE_SIZE = 24
PAYLOAD_TILEMAP_SIZE = 32
PAYLOAD_DRAW_REF_SIZE = 2
DRAW_SPRITE = 0
DRAW_TILEMAP = 1


class SceneSealedError(RuntimeError):
    """A structural call was made outside :meth:`Scene.build`.

    Creating layers and drawables is only legal while ``build()`` runs. Once it
    returns the scene is sealed, and calling :meth:`Layer.sprite` or any other
    factory from ``update()``, a timer, or ``teardown()`` raises this instead of
    quietly growing the display graph mid-game.

    It is also raised when a drawable that outlived its scene is written to,
    which is how a stale handle kept across scene entries surfaces.
    """


class ResourceLimitError(RuntimeError):
    """A scene asked for more sprites, tilemaps or layers than the target has.

    The message carries a per-layer census so the offending budget is obvious::

        sprite 101/100 in Vixeous (world: 62, hud: 39); reduce the sprite budget

    Because every structural call happens during :meth:`Scene.build`, this is
    always raised the first time the scene is entered rather than mid-game.
    """


class AssetLimitError(ResourceLimitError):
    """The loaded asset pack holds more image strips than the target supports."""


class AssetNotFoundError(LookupError):
    """An image name is not present in the scene's asset pack.

    Usually a typo, or a PNG that is not in the game's ``images/`` folder.
    """


class FrameError(ValueError):
    """A frame index falls outside its image's frame count.

    Raised at the assignment, so an out-of-range frame is reported at the line
    that set it instead of rendering garbage pixels.
    """


class StateConflictError(RuntimeError):
    """A Behavior's ``state = (...)`` declaration collides with something
    else already living on the same subject.

    Priming state -- writing every declared name to ``0`` on every sprite of
    a Behavior's subject at attach time -- is what makes ``sprite.name +=
    ...`` allocation-free in a Step (see :meth:`SpritePool.var`'s identical
    priming loop). That only holds if the name is unique across everything
    else already on the sprite, so this is raised, naming both sides, when:
    a second Behavior on the same subject declares the same state name; a
    state name shadows a pool's own :meth:`SpritePool.var`-declared
    variable, a scene's own :meth:`Scene.var`-declared variable, or a
    built-in :class:`Sprite` property; or a state name is one of the
    framework's reserved names (``dx``, ``dy``, ``fsm_state``, ``fsm_hold``,
    ``fsm_then``, ``enabled``).
    """


class _Limits:
    """Per-target resource budgets, exposed as ``vs2.limits``."""

    layers = 8
    sprites = 100
    tilemaps = 16
    image_strips = 100
    #: Behaviors attached anywhere in one scene, enforced by
    #: :func:`_attach_behavior` -- see its per-kind census in the
    #: :class:`ResourceLimitError` it raises when this is exceeded.
    behaviors = 32


limits = _Limits()


class _Display:
    """Display geometry and palette animation, exposed as ``vs2.display``."""

    #: Circumference of the display in columns, and the period of every X
    #: coordinate. Use it instead of writing ``% 256`` in game code.
    width = DISPLAY_WIDTH

    #: Number of LEDs on the bar, from the outer rim inward. This is the Y
    #: range of a :data:`~vs2.HUD` layer; :data:`~vs2.TUNNEL` and
    #: :data:`~vs2.FULLSCREEN` use depth from 0 through 255.
    height = DISPLAY_HEIGHT

    @property
    def palettes(self):
        """The loaded palette block, as a mutable buffer, or ``None``.

        This is the same buffer the asset bank loaded, so recolouring in place
        allocates nothing. Call :meth:`vs2.display.apply_palettes` to publish the change.
        The buffer is replaced whenever a new asset pack loads, so resolve it in
        :meth:`Scene.build` like any other asset handle.
        """
        return getattr(director, "palette_data", None)

    def apply_palettes(self):
        """Publish the current contents of :attr:`vs2.display.palettes` to the renderer.

        Cheap enough to call every tick, which is what a colour-cycling effect
        wants::

            def build(self):
                self.palettes = vs2.display.palettes

            def update(self):
                cycle(self.palettes)
                vs2.display.apply_palettes()
        """
        palettes = self.palettes
        if palettes is not None:
            get_platform().display.set_palettes(palettes)


display = _Display()


class _BaseLeds:
    """The console base's RGB strip, reached as ``vs2.base.leds``."""

    def __init__(self, owner):
        self.owner = owner

    def set_all(self, red, green, blue):
        """Set every base LED to one colour. Each channel is ``0..255``."""
        self.owner._set_leds(red, green, blue)

    def off(self):
        """Turn the base LEDs off."""
        self.set_all(0, 0, 0)


class _BaseServo:
    """The console base's servo, reached as ``vs2.base.servo``."""

    def __init__(self, owner):
        self.owner = owner

    def set(self, position):
        """Move the servo. ``position`` is ``0..255``."""
        self.owner._set_servo(position)


class _BaseButtons:
    """The console base's lit buttons, reached as ``vs2.base.buttons``."""

    def __init__(self, owner):
        self.owner = owner

    def set(self, mask, blink_ms=0):
        """Light the buttons named by ``mask``, optionally blinking.

        ``mask`` combines ``vs2.base.BUTTON_LED_1`` and
        ``vs2.base.BUTTON_LED_2``; ``blink_ms`` is ``0..10000``, where 0
        means steady.
        """
        self.owner._set_buttons(mask, blink_ms)

    def off(self):
        """Turn the button lights off."""
        self.set(0)


class _BaseControl:
    """Console base hardware, exposed as ``vs2.base``.

    Values are range-checked and de-duplicated, so writing the same colour every
    tick costs one comparison and sends nothing. All of it is safe to call on a
    console with no physical base attached — the commands simply go nowhere.

    Base output follows the app, not the scene: LED, servo and button-light
    state persists across scene transitions within a game and resets to safe
    defaults when the game returns to the launcher.
    """

    #: Left button light.
    BUTTON_LED_1 = 0x01
    #: Right button light.
    BUTTON_LED_2 = 0x02
    #: Both button lights.
    BUTTON_LED_ALL = 0x03

    def __init__(self):
        self.leds = _BaseLeds(self)
        self.servo = _BaseServo(self)
        self.buttons = _BaseButtons(self)
        self._led_state = None
        self._servo_state = None
        self._button_state = None

    @staticmethod
    def _integer(value, minimum, maximum, name):
        if not isinstance(value, int) or value < minimum or value > maximum:
            raise ValueError("%s must be in %d..%d" % (name, minimum, maximum))
        return value

    @staticmethod
    def _send(line):
        get_platform().comms.send(line.encode("ascii"))

    def _set_leds(self, red, green, blue):
        state = (self._integer(red, 0, 255, "red"),
                 self._integer(green, 0, 255, "green"),
                 self._integer(blue, 0, 255, "blue"))
        if state != self._led_state:
            self._send("base leds %d %d %d" % state)
            self._led_state = state

    def _set_servo(self, position):
        state = self._integer(position, 0, 255, "position")
        if state != self._servo_state:
            self._send("base servo %d" % state)
            self._servo_state = state

    def _set_buttons(self, mask, blink_ms):
        state = (self._integer(mask, 0, self.BUTTON_LED_ALL, "mask"),
                 self._integer(blink_ms, 0, 10000, "blink_ms"))
        if state != self._button_state:
            self._send("base buttons %d %d" % state)
            self._button_state = state


base = _BaseControl()


#: Sentinel distinct from any real app slug (including the legitimate "no
#: app is current" state, which is ``None``), so a freshly constructed
#: :class:`_Project` always rebinds on its first access. Mirrors
#: :mod:`vs2.store`'s identical ``_UNBOUND`` sentinel and the reason for it.
_PROJECT_UNBOUND = object()


class _Project:
    """Project-scoped variables that outlive a scene transition, exposed as
    ``vs2.project``.

    Unlike :meth:`Scene.var`, which resets every :meth:`Scene.build`, a
    project variable is declared once -- the first :meth:`var` call for a
    name wins, and a later call with the same name is a no-op that just
    returns the current value -- and lives above the scene stack for the
    life of the app, so it survives :meth:`Scene.push`, :meth:`Scene.pop`
    and :meth:`Scene.switch`::

        vs2.project.var("high_score", 0, persist=True)

    ``persist=True`` additionally reads the variable's initial value from
    :data:`vs2.store` and writes it back on :meth:`save`.

    **Rebinds when the current app changes**, the same way :data:`vs2.store`
    does: :func:`~ventilastation.api_guard.current_app` is checked on every
    call, and a different slug than last seen means a different game is
    running in this same process (a launcher-hosted session switching
    between games, the emulator, or a test), so every declared variable --
    and the plain instance attribute each one was ``setattr()`` onto this
    singleton -- is dropped before the new app's own declarations apply.
    Without this, a second game declaring a name the first game already
    declared would silently read the first game's value instead of its own.
    """

    def __init__(self):
        self._app_slug = _PROJECT_UNBOUND
        self._vars = {}
        self._persisted = set()

    def _ensure_current_app(self):
        slug = api_guard.current_app()
        if slug != self._app_slug:
            for name in self._vars:
                try:
                    delattr(self, name)
                except AttributeError:
                    pass
            self._vars = {}
            self._persisted = set()
            self._app_slug = slug

    def var(self, name, default=0, persist=False, min=None, max=None,
            step=None, label=None, unit=None, options=None):
        """Declare a project variable, returning its current value.

        Raises:
            ValueError: If ``name`` is one of the framework's reserved
                names (``dx``, ``dy``, ``fsm_state``, ``fsm_hold``,
                ``fsm_then``, ``enabled``).
        """
        self._ensure_current_app()
        if name in self._vars:
            return getattr(self, name)
        if name in _RESERVED_VAR_NAMES:
            raise ValueError("%r is a reserved name; choose another" % (name,))
        parameter = _var_parameter(default, min=min, max=max, step=step,
                                    label=label, unit=unit, options=options)
        self._vars[name] = parameter
        value = parameter.default
        if persist:
            self._persisted.add(name)
            value = store.get(name, value)
        setattr(self, name, value)
        return value

    def save(self):
        """Write every ``persist=True`` project variable to
        :data:`vs2.store` and save it. No-ops when nothing is persisted."""
        self._ensure_current_app()
        if not self._persisted:
            return
        for name in self._persisted:
            store[name] = getattr(self, name)
        store.save()


#: The project-variable singleton. See :class:`_Project`.
project = _Project()


from . import controls


def _app_slug():
    return api_guard.current_app() or "the current app"


def _qualified_asset(name):
    if "/" in name:
        return name
    slug = api_guard.current_app()
    return (slug + "/" + name) if slug else name


class _Audio:
    """Sound and music playback, exposed as ``vs2.audio``.

    Names resolve against the current app's ``sounds/`` folder. A name
    containing ``/`` is already qualified and is used as-is, which is how a game
    borrows another app's audio::

        vs2.audio.sound("shoot")                    # this game's shoot.mp3
        vs2.audio.sound("alecu.vyruss/shoot1")      # another game's

    Nothing is decoded on the board: these send compact commands to the host.
    """

    def sound(self, name):
        """Play a one-shot sound effect."""
        director.sound_play(_qualified_asset(name))

    def music(self, name, loop=False):
        """Start a music track, optionally looping.

        Music follows the app, not the scene: a track started here keeps playing
        across :meth:`Scene.push`, :meth:`Scene.pop` and :meth:`Scene.switch`
        within the same game, and stops on its own when the game returns to the
        launcher. Call :meth:`vs2.audio.stop_music` to stop it sooner.
        """
        director.music_play(_qualified_asset(name), loop=bool(loop))

    def stop_music(self):
        """Stop the current music track."""
        director.music_off()

    def notes(self, notes):
        """Play a sequence of synthesised notes."""
        director.notes_play(api_guard.current_app() or "", notes)


audio = _Audio()


def _vs2_backend():
    return getattr(get_platform(), "vs2", None)


def _fixed_8_8(value):
    try:
        fixed = int(value * 256)
    except TypeError:
        fixed = 0
    if fixed < -0x80000000:
        return -0x80000000
    if fixed > 0x7fffffff:
        return 0x7fffffff
    return fixed


def _floor_coord(value):
    try:
        value_int = int(value)
    except TypeError:
        return 0
    return value_int - 1 if value < value_int else value_int


def _render_coord(value, minimum=0, maximum=255):
    try:
        value = int(value)
    except TypeError:
        value = 0
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _sprite_flags(sprite):
    flags = FLAG_VISIBLE if sprite.visible else 0
    if sprite.flip_x:
        flags |= FLAG_FLIP_X
    if sprite.flip_y:
        flags |= FLAG_FLIP_Y
    return flags


def _tilemap_flags(tilemap):
    flags = FLAG_VISIBLE if tilemap.visible else 0
    if tilemap.flip_x:
        flags |= FLAG_FLIP_X
    if tilemap.flip_y:
        flags |= FLAG_FLIP_Y
    return flags


def _strip_metadata(number):
    metadata = getattr(director, "image_metadata", {}).get(number)
    if metadata is not None:
        return metadata
    # Tests and tiny apps can install a strip directly into the backend.  The
    # fallback preserves that useful workflow while ROM-loaded games get the
    # authoritative metadata parsed by the director.
    table = getattr(get_platform().sprites, "stripes", {})
    strip = table.get(number)
    if isinstance(strip, dict):
        return strip
    if strip is not None and len(strip) >= 4:
        width = strip[0]
        return {"width": 256 if width == 255 else width, "height": strip[1],
                "frames": strip[2], "palette": strip[3]}
    return None


class Image:
    """A resolved image from the scene's asset pack.

    Returned by :meth:`Scene.image` and carried by every drawable as its
    ``image`` attribute. Resolving a name once and reusing the handle avoids
    repeating the lookup, and lets one image back several drawables::

        def build(self):
            enemy = self.image("enemy.png")
            self.small = self.world.sprite_pool(enemy, count=12)
            self.boss = self.world.sprite(enemy, frame=4)

    Attributes are read-only and come from the ROM's metadata, so reading
    :attr:`width` or :attr:`frames` costs nothing at runtime.
    """

    def __init__(self, name, strip, metadata):
        #: The image's name in the asset pack, e.g. ``"ship.png"``.
        self.name = name
        self._strip = strip
        #: Width of a single frame, in display columns.
        self.width = int(metadata["width"])
        #: Height of a single frame, in LEDs.
        self.height = int(metadata["height"])
        #: Number of animation frames. Valid frame indices are ``0..frames-1``.
        self.frames = int(metadata["frames"])
        #: Glyph table declared in ``__images__.yaml``, or ``None``. Used by
        #: :meth:`Layer.label` to map characters to frames.
        # ROM V2 records carry a zero-length glyph trailer when the manifest
        # does not declare a custom map. Treat that decoded empty string as
        # absent so labels retain their documented CP437/ASCII fallback.
        self.glyphs = metadata.get("glyphs") or None


def _resolve_image(value):
    if isinstance(value, Image):
        return value
    if not isinstance(value, str):
        raise TypeError("image must be an image name or vs2.Image")
    try:
        strip = stripes[value]
    except KeyError:
        raise AssetNotFoundError("image '%s' is not in %s" % (value, _app_slug()))
    metadata = _strip_metadata(strip)
    if metadata is None:
        raise AssetNotFoundError("image '%s' has no loaded metadata in %s" % (value, _app_slug()))
    return Image(value, strip, metadata)


def _intersects_circular(x1, width1, x2, width2):
    delta = min(x1, x2)
    x1 = (x1 - delta + display.width // 2) % display.width
    x2 = (x2 - delta + display.width // 2) % display.width
    return x1 < x2 + width2 and x1 + width1 > x2


def _var_parameter(default, min=None, max=None, step=None, label=None,
                    unit=None, options=None):
    """Pick a :mod:`vs2.params` type for a declared instance variable, the
    same way :meth:`SpritePool.var`, :meth:`Scene.var` and
    :attr:`vs2.project`'s ``var`` all declare one: ``options=`` makes it a
    :class:`~vs2.params.Choice`, a boolean default makes it a
    :class:`~vs2.params.Flag`, anything else a :class:`~vs2.params.Number`.
    The returned :class:`~vs2.params.Parameter` is used only for its
    ``default``/metadata bookkeeping here -- it is never installed as a
    class-level descriptor, since these are per-instance declarations made
    at build time, not class-level Action/Behavior parameters.
    """
    if options is not None:
        return params.Choice(default, options=options, label=label, unit=unit)
    if isinstance(default, bool):
        return params.Flag(default, label=label)
    return params.Number(default, min=min, max=max, step=step, label=label, unit=unit)


def _behavior_snake_name(behavior):
    """The default name a Behavior gets on a subject when ``behave()`` is
    not given an explicit ``name=``: its class name in snake_case."""
    cls_name = type(behavior).__name__
    chars = []
    for index, char in enumerate(cls_name):
        if char.isupper():
            if index > 0:
                chars.append("_")
            chars.append(char.lower())
        else:
            chars.append(char)
    return "".join(chars)


#: The three step-dispatch method names :meth:`Scene._run_behaviors` looks
#: for, and the one each subject kind actually calls. ``"family"`` accepts
#: either, since a family dispatches each member to whichever fits its own
#: kind (see :meth:`Scene._run_behaviors`).
_STEP_METHODS = ("step", "step_one", "step_scene")

_KIND_REQUIRED_METHOD = {
    "pool": "step",
    "sprite": "step_one",
    "scene": "step_scene",
}

_KIND_NEEDS_TEXT = {
    "pool": "step()",
    "sprite": "step_one()",
    "family": "step() or step_one()",
    "scene": "step_scene()",
}


def _behavior_kind_mismatch(behavior, kind):
    """Whether ``behavior`` is shaped for a *different* subject kind than
    ``kind`` -- the mistake this catches is attaching a Behavior written for
    one subject (say, one that defines only ``step_one``) to another kind
    (a pool, which dispatches through ``step``).

    A ``behavior`` defining **none** of ``step``/``step_one``/``step_scene``
    is not flagged: that is either a Behavior doing all of its work in
    :meth:`Behavior.attached` with no per-tick logic of its own (legitimate
    -- see the proposal's *Cross-behavior wiring* on a passive
    ``Damageable``), or, pre-:class:`Behavior`, a bare duck-typed stand-in
    like the ones :mod:`tests.test_vs2_api` attaches -- both cases
    :meth:`Scene._run_behaviors` already tolerates by no-oping on whichever
    of the three a subject's dispatch does not find, so attaching one is
    legal on any subject.
    """
    if kind == "family":
        if (getattr(behavior, "step", None) is not None
                or getattr(behavior, "step_one", None) is not None):
            return False
        return getattr(behavior, "step_scene", None) is not None
    required = _KIND_REQUIRED_METHOD[kind]
    if getattr(behavior, required, None) is not None:
        return False
    for method in _STEP_METHODS:
        if method != required and getattr(behavior, method, None) is not None:
            return True
    return False


_SPRITE_PUBLIC_ATTRS = None


def _sprite_public_attrs():
    """Every non-private name :class:`Sprite` exposes (``x``, ``frame``,
    ``despawn``, ``behavior``, ...), computed once and cached: what a
    Behavior's ``state`` declaration must not shadow on a sprite subject.
    Deferred (rather than computed at import time) because :class:`Sprite`
    is defined later in this module than :func:`_attach_behavior` is.
    """
    global _SPRITE_PUBLIC_ATTRS
    if _SPRITE_PUBLIC_ATTRS is None:
        _SPRITE_PUBLIC_ATTRS = frozenset(
            attr for attr in dir(Sprite) if not attr.startswith("_"))
    return _SPRITE_PUBLIC_ATTRS


def _check_state_owner(owners, name, behavior, label):
    existing = owners.get(name)
    if existing is not None:
        raise StateConflictError(
            "state name %r is already declared on this %s by %r; %r cannot "
            "declare it again" % (name, label, existing, behavior))


def _prime_pool_state(pool, names, behavior):
    """Validate then prime ``names`` (a Behavior's ``state`` tuple) to ``0``
    on every sprite of ``pool``, free ones included -- the same priming
    idiom :meth:`SpritePool.var` uses, walking ``_free`` then ``_live``.
    Ownership (for cross-Behavior collision detection) is recorded directly
    on the pool object, so a family member primed this way and a pool
    attached to directly are checked against the same registry.
    """
    owners = getattr(pool, "_behavior_state_owners", None)
    if owners is None:
        owners = {}
        pool._behavior_state_owners = owners
    for name in names:
        if name in _RESERVED_VAR_NAMES:
            raise StateConflictError(
                "%r is a reserved name; %r cannot declare it as state"
                % (name, behavior))
        if name in pool._var_defaults:
            raise StateConflictError(
                "state name %r on %r collides with this pool's own "
                "declared variable %r" % (name, behavior, name))
        _check_state_owner(owners, name, behavior, "pool")
    for name in names:
        owners[name] = behavior
        for sprite in pool._free:
            setattr(sprite, name, 0)
        for sprite in pool._live:
            setattr(sprite, name, 0)


def _prime_sprite_state(sprite, names, behavior):
    """Validate then prime ``names`` to ``0`` on one standalone sprite."""
    owners = getattr(sprite, "_behavior_state_owners", None)
    if owners is None:
        owners = {}
        sprite._behavior_state_owners = owners
    reserved_props = _sprite_public_attrs()
    for name in names:
        if name in _RESERVED_VAR_NAMES:
            raise StateConflictError(
                "%r is a reserved name; %r cannot declare it as state"
                % (name, behavior))
        if name in reserved_props:
            raise StateConflictError(
                "state name %r on %r collides with Sprite's own %r property"
                % (name, behavior, name))
        _check_state_owner(owners, name, behavior, "sprite")
    for name in names:
        owners[name] = behavior
        setattr(sprite, name, 0)


def _prime_scene_state(scene, names, behavior):
    """Validate then prime ``names`` to ``0`` on the scene itself -- a
    scene is its own single subject instance, so this primes ``scene``
    directly rather than walking a collection of sprites."""
    owners = getattr(scene, "_behavior_state_owners", None)
    if owners is None:
        owners = {}
        scene._behavior_state_owners = owners
    for name in names:
        if name in _RESERVED_VAR_NAMES:
            raise StateConflictError(
                "%r is a reserved name; %r cannot declare it as state"
                % (name, behavior))
        if name in scene._vars:
            raise StateConflictError(
                "state name %r on %r collides with this scene's own "
                "declared variable %r" % (name, behavior, name))
        _check_state_owner(owners, name, behavior, "scene")
    for name in names:
        owners[name] = behavior
        setattr(scene, name, 0)


def _prime_behavior_state(subject, kind, behavior):
    """Prime ``behavior.state`` (a plain tuple of field names, defaulting
    to ``()`` and costing nothing when absent) across every sprite of
    ``subject`` -- one sprite for a ``sprite`` subject, every sprite (free
    included) of a ``pool`` subject, every member's sprites for a
    ``family`` subject, or the scene object itself for a ``scene`` subject.
    """
    names = getattr(behavior, "state", ())
    if not names:
        return
    if kind == "pool":
        _prime_pool_state(subject, names, behavior)
    elif kind == "sprite":
        _prime_sprite_state(subject, names, behavior)
    elif kind == "family":
        for member_kind, member in subject._members:
            if member_kind == "pool":
                _prime_pool_state(member, names, behavior)
            else:
                _prime_sprite_state(member, names, behavior)
    else:  # "scene"
        _prime_scene_state(subject, names, behavior)


def _attach_behavior(scene, subject, kind, by_name, order, behavior, name):
    """Shared body of ``behave()`` on every subject kind (:class:`Sprite`,
    :class:`SpritePool`, :class:`Family`, :class:`Scene`).

    Structural: legal only while ``scene`` is building. Validates that
    ``behavior`` is shaped for ``kind`` (:func:`_behavior_kind_mismatch`),
    that its name does not collide with another Behavior already on this
    subject, that attaching it would not exceed ``vs2.limits.behaviors``,
    and primes any ``state`` it declares (:func:`_prime_behavior_state`) --
    then registers it under ``name`` (defaulting to its class's snake_case
    name) into the subject's own ``by_name``/``order`` bookkeeping, appends
    it to the scene-wide attachment log that :meth:`Scene._seal_drawables`
    freezes into the subject-kind-tagged Step run list, and finally calls
    ``behavior.attached(subject)`` if it defines one -- once, here, with
    every other Behavior attached earlier on this subject already fully
    registered (call order in :meth:`Scene.build` is what lets one
    Behavior's ``attached()`` look an earlier sibling up via
    ``subject.behavior(OtherClass)`` and cache a direct reference, per the
    proposal's *Cross-behavior wiring*).

    Dispatch itself stays duck-typed (:meth:`Scene._run_behaviors` still
    reads through ``getattr(..., None)``, not an ``isinstance`` check
    against :class:`~vs2.behaviors.Behavior`) -- this function only
    validates the *shape* ``behavior`` needs for ``kind`` to make sense,
    which is why a bare stand-in defining none of the three step methods
    (see :func:`_behavior_kind_mismatch`) still attaches without error,
    and calling ``attached()`` through ``getattr(..., None)`` the same way
    means a stand-in with no ``attached()`` of its own costs nothing extra.
    """
    scene._require_build("behave")
    if _behavior_kind_mismatch(behavior, kind):
        defined = "/".join(
            method for method in _STEP_METHODS
            if getattr(behavior, method, None) is not None)
        raise TypeError(
            "%s cannot attach to a %s: it defines %s, but a %s subject "
            "dispatches through %s"
            % (type(behavior).__name__, kind, defined, kind,
               _KIND_NEEDS_TEXT[kind]))
    if name is None:
        name = _behavior_snake_name(behavior)
    if name in by_name:
        raise ValueError(
            "behavior name %r is already attached to this %s (%r and %r)"
            % (name, kind, by_name[name], behavior))
    requested = len(scene._behavior_attachments) + 1
    if requested > limits.behaviors:
        counts = {}
        for existing_kind, _existing_subject, _existing_behavior in scene._behavior_attachments:
            counts[existing_kind] = counts.get(existing_kind, 0) + 1
        counts[kind] = counts.get(kind, 0) + 1
        census = ", ".join("%s: %d" % (k, counts[k]) for k in sorted(counts))
        raise ResourceLimitError(
            "behavior %d/%d in %s (%s); reduce the behavior budget"
            % (requested, limits.behaviors, scene.__class__.__name__, census))
    _prime_behavior_state(subject, kind, behavior)
    by_name[name] = behavior
    order.append(behavior)
    scene._behavior_attachments.append((kind, subject, behavior))
    attached = getattr(behavior, "attached", None)
    if attached is not None:
        attached(subject)
    return behavior


def _lookup_behavior(by_name, order, key):
    """Shared body of ``behavior()`` on every subject kind: look up by name
    (a string) or by class, returning ``None`` when nothing matches."""
    if isinstance(key, str):
        return by_name.get(key)
    for behavior in order:
        if isinstance(behavior, key):
            return behavior
    return None


class Scene(_Scene):
    """One screen of a game: a display graph plus the logic that drives it.

    Subclass it, build the graph in :meth:`build`, and move it in
    :meth:`update`::

        class MyGame(vs2.Scene):
            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.ship = self.world.sprite("ship.png", x=128, y=0)

            def update(self):
                self.ship.x += 0.5

    The scene has three phases. During ``build()`` it is *building* and layers
    and drawables may be created. When ``build()`` returns it is *sealed*:
    ``update()`` and timers may move, re-frame and hide what exists, but any
    structural call raises :class:`SceneSealedError`. When the scene stops
    showing it is *closed*, its drawables are released, and pending timers are
    discarded.

    ``build()`` runs on every entry, so a scene shown a second time starts from
    a fresh graph. Persistent state — scores, progress, unlocked levels — can
    live in ``__init__``, which runs once; drawable handles must be rebuilt.
    """

    #: Seconds without input from any controller before :meth:`on_idle` fires.
    #: ``None`` disables the timeout. Defaults to 30 so an unattended console
    #: always drifts back to the launcher's attract loop.
    idle_timeout = 30

    #: When true, ``Y`` or ``BACK`` pops the scene. Set it to ``False`` to claim
    #: those buttons for gameplay; the scene stays exitable through the idle
    #: timeout and the console's home command.
    back_button = True

    #: When true, the drifting starfield is drawn behind this scene. Applied on
    #: entry and restored on exit.
    starfield = False

    #: Name of the asset pack to load, defaulting to the current app's own.
    #: Shared and system scenes set this to borrow another pack.
    asset_pack = None

    def __init__(self):
        _claim()
        _Scene.__init__(self)
        self.layers = []
        self._phase = "new"
        self._vs2_payload = None
        self._pending_transition = None
        self._sprite_count = 0
        self._tilemap_count = 0
        self._image_cache = {}
        self._payload_sprites = ()
        self._payload_tilemaps = ()
        self._payload_drawables = ()
        self._payload_frames_size = 0
        #: This scene's own declared variables (:meth:`var`), reset fresh on
        #: every :meth:`build`.
        self._vars = {}
        #: This scene's own attached Behaviors (subject == the scene
        #: itself), as ``{name: behavior}`` plus attachment order.
        self._behaviors = {}
        self._behavior_order = []
        #: Every ``behave()`` call anywhere in the scene, in call order --
        #: what :attr:`behaviors` reads back and what
        #: :meth:`_seal_drawables` freezes into the Step run list.
        self._behavior_attachments = []
        self._behavior_run_list = ()
        #: Every :class:`SpritePool` created on any layer, in creation
        #: order -- what the per-tick ``dx``/``dy`` commit pass walks.
        self._pools = []
        self._payload_pools = ()
        #: Distinct non-default projection curves seen on this scene's
        #: layers, assigned small indices on first sight for
        #: ``export_scene_payload()``'s reserved curve-index byte. Index 0
        #: is never stored here -- it always means "this layer's mode
        #: default curve".
        self._curve_registry = {}

    def build(self):
        """Create this scene's layers and drawables. Override this.

        Runs on every entry to the scene. When it returns the scene is sealed,
        so this is the only place :meth:`layer` and the
        :class:`Layer` factories may be called.
        """

    def update(self):
        """Advance the game by one tick. Override this.

        Called once per rotation of the display. It may move, re-frame, show and
        hide the drawables built in :meth:`build`, but may not create more.
        """

    def teardown(self):
        """Clean up when the scene stops showing. Optional.

        Saving a score or cancelling external work belongs here. Timers and
        drawables are released for you, so most scenes never need it.
        """

    def _require_build(self, method):
        if self._phase != "building":
            raise SceneSealedError("%s() is only allowed while %s.build() runs" %
                                   (method, self.__class__.__name__))

    def _reserve(self, kind, count, layer):
        if kind == "sprite":
            current = self._sprite_count
            limit = limits.sprites
        elif kind == "tilemap":
            current = self._tilemap_count
            limit = limits.tilemaps
        else:
            current = len(self.layers)
            limit = limits.layers
        requested = current + count
        layer_count = getattr(layer, "_" + kind + "_count", 0) + count
        if requested > limit:
            census = []
            if kind in ("sprite", "tilemap"):
                for candidate in self.layers:
                    candidate_count = getattr(candidate, "_" + kind + "_count", 0)
                    if candidate is layer:
                        candidate_count += count
                    if candidate_count:
                        census.append("%s: %d" %
                                      (candidate.name or "unnamed", candidate_count))
            raise ResourceLimitError(
                "%s %d/%d in %s%s; reduce the %s budget"
                % (kind, requested, limit, self.__class__.__name__,
                   " (" + ", ".join(census) + ")" if census else "",
                   kind)
            )
        if kind == "sprite":
            self._sprite_count = requested
        elif kind == "tilemap":
            self._tilemap_count = requested
        if kind in ("sprite", "tilemap"):
            setattr(layer, "_" + kind + "_count", layer_count)

    def image(self, value):
        """Resolve an image name to an :class:`Image` handle.

        Handles are cached for the life of the scene, so resolving the same name
        twice returns the same object. Passing an :class:`Image` returns it
        unchanged, which lets factories accept either form.

        Args:
            value: An image name such as ``"ship.png"``, or an :class:`Image`.

        Returns:
            Image: The resolved handle.

        Raises:
            AssetNotFoundError: If the name is not in the scene's asset pack.
        """
        if isinstance(value, Image):
            return value
        cached = self._image_cache.get(value)
        if cached is None:
            cached = _resolve_image(value)
            self._image_cache[value] = cached
        return cached

    def layer(self, name=None, projection=TUNNEL, visible=True):
        """Create a layer. Only callable from :meth:`build`.

        Layers paint bottom to top in the order they are created, so create the
        background first and the HUD last.

        Args:
            name: A label used in resource-limit messages. Worth setting.
            projection: :data:`~vs2.TUNNEL`, :data:`~vs2.HUD` or
                :data:`~vs2.FULLSCREEN`. Decides how the layer maps Y to LEDs.
            visible: Whether the layer draws at all.

        Returns:
            Layer: The new layer, ready to create drawables on.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ResourceLimitError: If the scene already has ``vs2.limits.layers``.
        """
        self._require_build("layer")
        if name == "scene":
            raise ValueError("a layer cannot be named 'scene'; that name is "
                             "reserved for the scene itself as a Behavior subject")
        self._reserve("layer", 1, self)
        layer = Layer(self, name, projection, visible)
        self.layers.append(layer)
        return layer

    def var(self, name, default=0, min=None, max=None, step=None,
            label=None, unit=None, options=None):
        """Declare a scene-level variable, primed now and reset again on
        every :meth:`build` (a scene rebuilds its whole graph on every
        entry, and its variables reset the same way). For state that must
        survive a :meth:`push`/:meth:`pop` or a :meth:`switch`, declare it
        on :data:`vs2.project` instead.

        Readable and writable afterwards as a plain attribute::

            self.var("score", 0, min=0, max=999999)
            self.score += 10

        Only callable from :meth:`build`.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ValueError: If ``name`` is already declared on this scene, or
                is one of the framework's reserved names (``dx``, ``dy``,
                ``fsm_state``, ``fsm_hold``, ``fsm_then``, ``enabled``).
        """
        self._require_build("var")
        if name in _RESERVED_VAR_NAMES:
            raise ValueError("%r is a reserved name; choose another" % (name,))
        if name in self._vars:
            raise ValueError("scene variable %r is already declared" % (name,))
        parameter = _var_parameter(default, min=min, max=max, step=step,
                                    label=label, unit=unit, options=options)
        self._vars[name] = parameter
        setattr(self, name, parameter.default)
        return parameter.default

    def family(self, *members):
        """Group ``members`` -- :class:`SpritePool` and/or :class:`Sprite`
        objects, all on the same layer -- into a :class:`Family`: a legal
        :class:`~vs2.actions.Action` target and a legal Behavior subject in
        its own right, addressed as one unit without ever being iterated in
        a Step. Only callable from :meth:`build`.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ValueError: If ``members`` is empty, or its members do not all
                share one layer.
            TypeError: If a member is neither a :class:`SpritePool` nor a
                :class:`Sprite`.
        """
        self._require_build("family")
        if not members:
            raise ValueError("family() needs at least one pool or sprite")
        tagged = []
        layer = None
        for member in members:
            if isinstance(member, SpritePool):
                kind = "pool"
            elif isinstance(member, Sprite):
                kind = "sprite"
            else:
                raise TypeError(
                    "family() members must be a SpritePool or Sprite; got %r"
                    % (member,))
            member_layer = member.layer
            if layer is None:
                layer = member_layer
            elif member_layer is not layer:
                raise ValueError(
                    "family() members must share one layer; got %s and %s"
                    % (layer.name or "unnamed", member_layer.name or "unnamed"))
            tagged.append((kind, member))
        return Family(self, layer, tagged)

    def behave(self, behavior, name=None):
        """Attach ``behavior`` to the scene itself -- for conduct with no
        sprite behind it, like wave spawning, which decides *when*
        something is born rather than what an existing sprite does.
        Structural: only callable from :meth:`build`. Returns ``behavior``.
        """
        return _attach_behavior(self, self, "scene",
                                self._behaviors, self._behavior_order,
                                behavior, name)

    @property
    def behaviors(self):
        """Every Behavior attached anywhere in this scene -- on any layer's
        pools, sprites and families, and on the scene itself -- in the
        order ``behave()`` was called. This is the Step's run order, and
        what the panel lists. For only the Behaviors attached to the scene
        itself (as opposed to one of its pools, sprites or families), use
        :meth:`behavior`.
        """
        return tuple(behavior for _kind, _subject, behavior in self._behavior_attachments)

    def behavior(self, key):
        """Look up a Behavior attached directly to the scene itself (not
        one of its pools, sprites or families) by name (a string) or by
        class. Returns ``None`` if nothing matches.
        """
        return _lookup_behavior(self._behaviors, self._behavior_order, key)

    def on_enter(self):
        backend = _vs2_backend()
        self._clear_drawables()
        self._phase = "building"
        self._pending_transition = None
        self._sprite_count = 0
        self._tilemap_count = 0
        self._image_cache.clear()
        self._payload_sprites = ()
        self._payload_tilemaps = ()
        self._payload_drawables = ()
        self._payload_frames_size = 0
        self._vars = {}
        self._behaviors = {}
        self._behavior_order = []
        self._behavior_attachments = []
        self._behavior_run_list = ()
        self._pools = []
        self._payload_pools = ()
        self._curve_registry = {}
        if backend is not None:
            backend.reset_scene()
            backend.set_active(True)
        try:
            # V2 owns its asset pack.  Existing unit tests and embedded tools
            # may construct an anonymous scene with preinstalled strips, in
            # which case there is intentionally nothing to load.
            pack = self.asset_pack or getattr(self, "_vs_api_slug", None)
            if pack:
                director.load_rom("roms/" + pack + ".rom")
            image_count = len(stripes)
            if image_count > limits.image_strips:
                raise AssetLimitError(
                    "%s defines %d images; this target supports %d"
                    % (_app_slug(), image_count, limits.image_strips)
                )
            self.build()
            self._phase = "sealed"
            self._seal_drawables()
        except Exception:
            self._phase = "closed"
            if backend is not None:
                backend.set_active(False)
                backend.reset_scene()
            raise
        setter = getattr(get_platform().display, "set_starfield", None)
        if setter is not None:
            setter(bool(self.starfield))

    def on_exit(self):
        backend = _vs2_backend()
        self._phase = "closing"
        try:
            self.teardown()
        finally:
            self.pending_calls.clear()
            self._clear_drawables()
            self._vs2_payload = None
            self._image_cache.clear()
            self._payload_sprites = ()
            self._payload_tilemaps = ()
            self._payload_drawables = ()
            self._payload_frames_size = 0
            self._vars = {}
            self._behaviors = {}
            self._behavior_order = []
            self._behavior_attachments = []
            self._behavior_run_list = ()
            self._pools = []
            self._payload_pools = ()
            self._curve_registry = {}
            self._phase = "closed"
            setter = getattr(get_platform().display, "set_starfield", None)
            if setter is not None:
                setter(False)
            if backend is not None:
                backend.set_active(False)
                backend.reset_scene()
            _Scene.on_exit(self)

    def _clear_drawables(self):
        for layer in self.layers:
            layer._close()
        del self.layers[:]

    def _seal_drawables(self):
        """Freeze render topology once; export and native rendering reuse it."""
        sprites = []
        tilemaps = []
        drawables = []
        native_order = []
        frames_size = 0
        for layer_index, layer in enumerate(self.layers):
            for drawable in layer._drawables:
                if isinstance(drawable, Sprite):
                    sprites.append((drawable, layer_index))
                    drawables.append((DRAW_SPRITE, len(sprites) - 1))
                    native_order.append(drawable._sprite)
                else:
                    tilemaps.append((drawable, layer_index))
                    drawables.append((DRAW_TILEMAP, len(tilemaps) - 1))
                    native_order.append(drawable._tilemap)
                    frames_size += len(drawable.cells)
        self._payload_sprites = tuple(sprites)
        self._payload_tilemaps = tuple(tilemaps)
        self._payload_drawables = tuple(drawables)
        self._payload_frames_size = frames_size
        # Freeze the pools (for the per-tick dx/dy commit pass) and the
        # subject-kind-tagged Behavior attachments (for the Step's run
        # list) the same way drawables are frozen above: once, here, so
        # neither the Step nor the commit pass ever walks a live Python
        # list or builds an iterator.
        self._payload_pools = tuple(self._pools)
        self._behavior_run_list = tuple(self._behavior_attachments)
        backend = _vs2_backend()
        if backend is not None:
            setter = getattr(backend, "set_draw_order", None)
            if setter is None:
                raise RuntimeError("this firmware is too old for VS2 revision 2")
            setter(tuple(native_order))

    def call_later(self, delay, callback, *args, **kwargs):
        """Schedule a one-shot callback ``delay`` milliseconds from now.

        Extra positional and keyword arguments are stored with the timer and
        passed to the callback when it fires::

            self.call_later(1500, self.respawn)
            self.call_later(500, self.spawn_wave, wave, boss=True)

        Timers live only as long as the scene is showing. Pending callbacks are
        discarded the moment it stops showing — popped, or suspended under a
        :meth:`push` — and a scene shown again starts from a fresh
        :meth:`build` with no timers.

        Scheduling is meant to be infrequent: menus, respawn delays, wave
        timers. Do not call this every tick.

        Raises:
            SceneSealedError: If the scene is not building or running.
        """
        if self._phase not in ("building", "sealed"):
            raise SceneSealedError("call_later() requires a building or running V2 scene")
        when = utime.ticks_add(utime.ticks_ms(), int(delay))
        entry = (when, callback, args, kwargs)
        for index, queued in enumerate(self.pending_calls):
            if utime.ticks_diff(when, queued[0]) < 0:
                self.pending_calls.insert(index, entry)
                break
        else:
            self.pending_calls.append(entry)

    def _queue_transition(self, kind, target=None):
        if self._pending_transition is not None:
            raise RuntimeError("%s already queued a scene transition" % self.__class__.__name__)
        self._pending_transition = (kind, target)

    def push(self, scene):
        """Suspend this scene and run ``scene`` on top of it.

        This scene's timers are discarded and its drawables released; when the
        pushed scene pops, this one is entered again from a fresh
        :meth:`build`.
        """
        self._queue_transition("push", scene)

    def pop(self):
        """Leave this scene, resuming the one below, or exit to the launcher.

        Returns ``None``, so ``return self.pop()`` reads as "handle this input,
        then stop". No V2 scene raises ``StopIteration``.
        """
        self._queue_transition("pop")

    def switch(self, scene):
        """Replace this scene with ``scene``, without growing the stack.

        Music and base-hardware state carry over, since both follow the app
        rather than the scene.
        """
        self._queue_transition("switch", scene)

    def on_idle(self):
        """Called after :attr:`idle_timeout` seconds without input.

        The default pops the scene, so an unattended console walks back out to
        the launcher one screen at a time. Override it for an attract loop::

            def on_idle(self):
                self.push(AttractSlideshow())
        """
        self.pop()

    def _run_defaults(self):
        if self._pending_transition is not None:
            return
        if self.back_button and (controls.joy1.just_pressed(controls.Y)
                                 or controls.joy1.just_pressed(controls.BACK)):
            self.pop()
            return
        if (self.idle_timeout is not None
                and int(controls.idle_ms) >= int(self.idle_timeout) * 1000):
            self.on_idle()

    def _drain_timers(self):
        now = utime.ticks_ms()
        while self.pending_calls:
            when, callback, args, kwargs = self.pending_calls[0]
            if utime.ticks_diff(when, now) > 0:
                break
            self.pending_calls.pop(0)
            callback(*args, **kwargs)
            if self._pending_transition is not None:
                break

    def _commit_transition(self):
        transition = self._pending_transition
        self._pending_transition = None
        if transition is None:
            return
        kind, target = transition
        if kind == "push":
            director.push(target)
        elif kind == "switch":
            director.switch(target)
        else:
            director.pop()

    def scene_step(self):
        self.update()
        if self._pending_transition is None:
            self._run_behaviors()
        if self._pending_transition is None:
            self._run_defaults()
        if self._pending_transition is None:
            self._drain_timers()
        # Director re-reads the stack after scene_step(), so callbacks that
        # queued a transition cannot run against a scene that has just left.
        self._commit_transition()

    def _run_behaviors(self):
        """The Behavior pass: attach-order dispatch across the whole scene,
        followed by the per-pool ``dx``/``dy`` commit.

        Runs after :meth:`update` and before :meth:`_run_defaults`, exactly
        once per Step, guarded the same way as the rest of the pass by
        ``scene_step()`` -- a transition queued in ``update()`` skips this
        entirely. A transition queued *by* a Behavior stops the dispatch
        loop immediately, after the entry that queued it, without visiting
        any Behavior attached later; the motion commit still runs
        regardless, so whatever a sprite accumulated before the stop is not
        silently dropped.

        Dispatch is duck-typed against ``getattr(behavior, "step*", None)``
        rather than a ``Behavior`` base class, because that base class does
        not exist in this module -- it is a later task's
        ``vs2/behaviors.py``. A stand-in object attached today (as this
        module's own tests do) simply runs whichever of ``step``/
        ``step_one``/``step_scene`` it defines for the subject kind it was
        attached to.
        """
        run_list = self._behavior_run_list
        index = 0
        count = len(run_list)
        while index < count:
            kind, subject, behavior = run_list[index]
            if kind == "pool":
                step = getattr(behavior, "step", None)
                if step is not None:
                    step(subject)
            elif kind == "sprite":
                step_one = getattr(behavior, "step_one", None)
                if step_one is not None:
                    step_one(subject)
            elif kind == "family":
                step = getattr(behavior, "step", None)
                step_one = getattr(behavior, "step_one", None)
                members = subject._members
                member_index = 0
                member_count = len(members)
                while member_index < member_count:
                    member_kind, member = members[member_index]
                    if member_kind == "pool":
                        if step is not None:
                            step(member)
                    elif step_one is not None:
                        step_one(member)
                    member_index += 1
            else:  # "scene"
                step_scene = getattr(behavior, "step_scene", None)
                if step_scene is not None:
                    step_scene(self)
            if self._pending_transition is not None:
                break
            index += 1
        self._commit_pool_motion()

    def _commit_pool_motion(self):
        """Apply every live sprite's accumulated ``dx``/``dy`` to its
        ``x``/``y`` and zero the accumulator, once per pool per tick.

        Indexed and downward per pool -- the same zero-allocation,
        despawn-safe shape every Behavior/Action loop in this framework
        uses -- over the pools :meth:`_seal_drawables` froze, not a
        ``for sprite in pool`` iterator. A sprite nobody wrote ``dx``/
        ``dy`` on (every sprite in a scene using none of this API) costs
        one ``or`` comparison and nothing else: no property write, no
        native call.
        """
        pools = self._payload_pools
        pool_index = 0
        pool_count = len(pools)
        while pool_index < pool_count:
            live = pools[pool_index]._live
            slot = len(live) - 1
            while slot >= 0:
                sprite = live[slot]
                dx = sprite.dx
                dy = sprite.dy
                if dx or dy:
                    sprite.x = sprite._x + dx
                    sprite.y = sprite._y + dy
                    sprite.dx = 0
                    sprite.dy = 0
                slot -= 1
            pool_index += 1


class Layer:
    """An ordered group of drawables sharing one projection.

    Created by :meth:`Scene.layer`, never directly. A layer owns its drawables:
    they are created through :meth:`sprite`, :meth:`sprite_pool`,
    :meth:`tilemap` and :meth:`label`, which allocate and attach in one step, so
    a drawable that nothing draws cannot exist.

    Within a layer, drawables paint in creation order — each one over those
    created before it — and layers themselves paint in the order the scene
    created them. Sprites, tilemaps and labels interleave freely::

        ground = world.tilemap("ground.png", columns=8, rows=17)
        player = world.sprite("ship.png")
        clouds = world.tilemap("clouds.png", columns=8, rows=4)

    That paints ground, then the player, then clouds over both.
    """

    def __init__(self, scene, name, projection, visible):
        self.scene = scene
        self.name = name
        self._projection, self._curve = _resolve_projection(projection)
        self._visible = bool(visible)
        self._drawables = []
        self._closed = False
        self._sprite_count = 0
        self._tilemap_count = 0
        #: Render-time translation applied to everything this layer draws.
        #: See :attr:`camera_x`/:attr:`camera_y`.
        self._camera_x = 0
        self._camera_y = 0
        backend = _vs2_backend()
        self._layer = backend.Layer(mode=self._projection, visible=self._visible) if backend else None
        if self._layer is not None:
            # Without this, a native-backed layer never hears about camera_x/
            # camera_y or a non-default curve until something else happens to
            # call set_camera()/set_curve() -- see the camera_x/camera_y and
            # projection setters below, which keep this in sync afterward.
            self._layer.set_camera(0, 0)
            self._layer.set_curve(self._curve)

    def _require_build(self, method):
        if self._closed:
            raise SceneSealedError("%s belongs to a closed V2 scene" % (method,))
        self.scene._require_build(method)

    def _close(self):
        for drawable in self._drawables:
            drawable._closed = True
            drawable._layer = None
        del self._drawables[:]
        self.scene = None
        self._layer = None
        self._closed = True

    @property
    def projection(self):
        """How this layer maps Y to LEDs -- always reads back as one of the
        revision-2 wire values :data:`~vs2.FULLSCREEN`, :data:`~vs2.TUNNEL`
        or :data:`~vs2.HUD`, even after assigning a curve (a curve refines
        *which* depth-to-row table TUNNEL/FULLSCREEN paint through; it does
        not add a fourth mode, and every existing native call, payload byte
        and ``== vs2.HUD``-style check keeps working unchanged). Writable at
        runtime, e.g. a radar layer that flips between tunnel and HUD."""
        return self._projection

    @projection.setter
    def projection(self, value):
        """Set this layer's rendering mode, or its projection curve.

        Passing one of :data:`vs2.FULLSCREEN`/:data:`vs2.TUNNEL`/
        :data:`vs2.HUD` behaves exactly as revision 2: it selects that mode
        and resets this layer's curve to the mode's own default
        (:data:`vs2.VS1_TUNNEL` for TUNNEL and FULLSCREEN, the identity
        curve for HUD).

        Passing a 256-byte curve -- :data:`vs2.VS1_TUNNEL`, one from
        :mod:`vs2.projection`, or the result of :func:`vs2.tunnel` --
        replaces only the curve :meth:`to_depth`/:meth:`to_row`/
        :meth:`polar` read, leaving :attr:`projection`'s mode untouched.
        """
        self._require_open("projection")
        self._projection, self._curve = _resolve_projection(value, self._projection)
        if self._layer is not None:
            self._layer.set_mode(self._projection)
            self._layer.set_curve(self._curve)

    @property
    def camera_x(self):
        """Render-time X translation applied to everything this layer
        draws, in the same angular units as sprite ``x`` -- wraps at
        :data:`vs2.display.width`, at no extra cost, because the renderer's
        column arithmetic is already modular. Defaults to 0."""
        return self._camera_x

    @camera_x.setter
    def camera_x(self, value):
        self._require_open("camera_x")
        self._camera_x = value
        if self._layer is not None:
            self._layer.set_camera(self._camera_x, self._camera_y)

    @property
    def camera_y(self):
        """Render-time Y translation, interpreted like sprite ``y`` under
        this layer's projection: LEDs on HUD, depth on a tunnel. Defaults
        to 0."""
        return self._camera_y

    @camera_y.setter
    def camera_y(self, value):
        self._require_open("camera_y")
        self._camera_y = value
        if self._layer is not None:
            self._layer.set_camera(self._camera_x, self._camera_y)

    def to_row(self, depth):
        """World depth (``0..255``) -> LED row, through this layer's
        curve. The inverse of :meth:`to_depth`."""
        index = int(depth)
        if index < 0:
            index = 0
        elif index > 255:
            index = 255
        return self._curve[index]

    def to_depth(self, led_row):
        """LED row -> world depth (``0..255``), through this layer's
        curve. The inverse of :meth:`to_row`."""
        return _curves.to_depth(int(led_row), self._curve)

    def polar(self, x, y):
        """Convert a cartesian offset ``(x, y)`` to this layer's polar
        terms: ``(angle, depth)``.

        ``angle`` follows the disc's own convention -- 0 at the bottom, 64
        left, 128 top, 192 right, wrapping at :data:`vs2.display.width` --
        matching the ``atan2``-based aiming maths already hand-written in
        the VS jam games (``2bam_sencom``), generalised to any display
        width. ``depth`` is the plain Euclidean distance from the origin,
        in the same world-space units as sprite ``y`` -- *not* run through
        this layer's curve (see :meth:`to_row` for that), since a Behavior
        computing "how far away is this" wants world-space depth, the same
        space :class:`~vs2.actions.Collide` tests in.
        """
        angle = (0.75 * display.width - atan2(y, x) * display.width / (2 * pi)) % display.width
        depth = sqrt(x * x + y * y)
        return angle, depth

    def _curve_index(self):
        """This layer's curve, resolved to the small integer
        ``export_scene_payload()`` packs into the layer record's reserved
        curve-index byte. 0 always means "this layer's mode default
        curve" -- the case that keeps the payload byte-identical to
        revision 2 for every scene that never assigns a custom curve.
        A distinct custom curve is assigned the next free index in the
        scene's registry the first time it is seen; the same curve object
        (or an equal one, e.g. two separately-built ``vs2.tunnel(...)``
        calls with the same arguments) always resolves to the same index.
        """
        default = _DEFAULT_CURVE_BY_MODE[self._projection]
        curve = self._curve
        if curve is default or bytes(curve) == bytes(default):
            return 0
        registry = self.scene._curve_registry
        key = bytes(curve)
        index = registry.get(key)
        if index is None:
            index = len(registry) + 1
            registry[key] = index
        return index

    @property
    def visible(self):
        """Whether the whole layer draws. Toggling it touches no drawable."""
        return self._visible

    @visible.setter
    def visible(self, value):
        self._require_open("visible")
        self._visible = bool(value)
        if self._layer is not None:
            self._layer.set_visible(self._visible)

    @property
    def sprites(self):
        """The layer's :class:`Sprite` drawables, in creation order."""
        return [drawable for drawable in self._drawables if isinstance(drawable, Sprite)]

    @property
    def tilemaps(self):
        """The layer's :class:`Tilemap` drawables, in creation order."""
        return [drawable for drawable in self._drawables if isinstance(drawable, Tilemap)]

    def _require_open(self, field):
        if self._closed:
            raise SceneSealedError("cannot change %s on a closed V2 layer" % field)

    def sprite(self, image, x=0, y=0, frame=0, visible=True, flip_x=False, flip_y=False):
        """Create one sprite on this layer. Only callable from ``build()``.

        Args:
            image: An image name or an :class:`Image` handle.
            x: Angle. 0 is the bottom of the disc, 64 left, 128 top,
                192 right; wraps at :data:`vs2.display.width`.
            y: Distance inward from the rim, where 0 is the outermost LED.
                Its range follows the layer's projection: ``0..53`` on HUD,
                ``0..255`` (depth) on TUNNEL and FULLSCREEN.
            frame: Initial frame, validated against the image's frame count.
            visible: Whether it draws. Independent of ``frame``.
            flip_x: Mirror horizontally.
            flip_y: Mirror vertically.

        Returns:
            Sprite: The new sprite.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ResourceLimitError: If the scene is out of sprite slots.
            FrameError: If ``frame`` is out of range for the image.
        """
        self._require_build("sprite")
        self.scene._reserve("sprite", 1, self)
        sprite = Sprite(self, self.scene.image(image), x, y, frame, visible, flip_x, flip_y)
        self._drawables.append(sprite)
        return sprite

    def sprite_pool(self, image, count, frame=0, on_empty=None):
        """Create a fixed group of interchangeable sprites.

        All ``count`` sprites are allocated here, hidden, so the budget is spent
        visibly and up front in one reviewable number. Nothing is allocated when
        they later spawn and despawn.

        Args:
            image: An image name or an :class:`Image` handle.
            count: How many sprites to reserve. Must be at least 1.
            frame: Initial frame for every sprite in the pool.
            on_empty: What :meth:`SpritePool.spawn` does when the pool is
                exhausted. ``None`` returns ``None`` — "no free bullet this
                frame" is a game rule, not an error. :data:`vs2.RECYCLE` reuses
                the oldest live sprite instead, which is what explosions and
                particles usually want.

        Returns:
            SpritePool: The new pool, with every sprite hidden.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ResourceLimitError: If the scene cannot fit ``count`` more sprites.
        """
        self._require_build("sprite_pool")
        count = int(count)
        if count < 1:
            raise ValueError("sprite_pool count must be positive")
        self.scene._reserve("sprite", count, self)
        image = self.scene.image(image)
        sprites = []
        for _ in range(count):
            sprite = Sprite(self, image, 0, 0, frame, False, False, False)
            self._drawables.append(sprite)
            sprites.append(sprite)
        pool = SpritePool(self, sprites, on_empty)
        self.scene._pools.append(pool)
        return pool

    def tilemap(self, image, columns, rows, cells=None, x=0, y=0,
                view_width=None, view_height=None, view_x=0, view_y=0,
                visible=True, flip_x=False, flip_y=False):
        """Create a grid of tiles drawn from one tileset image.

        Tile size comes from the image, so it can never disagree with it.

        Args:
            image: The tileset. One frame per distinct tile.
            columns: Grid width in tiles.
            rows: Grid height in tiles.
            cells: An existing ``bytearray`` of ``columns * rows`` tile indices
                to draw from. Omit it and one is allocated, filled with
                :data:`vs2.EMPTY_TILE`. Pass your own to keep object identity
                with a buffer the game already owns.
            x: Angle of the map's origin; 0 is the bottom of the disc.
            y: Distance of the origin inward from the rim, 0 being the
                outermost LED.
            view_width: Width of the on-screen window onto the map. Defaults to
                the whole map.
            view_height: Height of that window. Defaults to the whole map.
            view_x: Horizontal scroll offset into the map.
            view_y: Vertical scroll offset into the map.
            visible: Whether it draws.
            flip_x: Mirror the complete visible viewport horizontally.
            flip_y: Mirror the complete visible viewport vertically.

        Returns:
            Tilemap: The new tilemap.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ResourceLimitError: If the scene is out of tilemap slots.
            ValueError: On a :data:`~vs2.FULLSCREEN` layer, which cannot draw
                tilemaps, or if ``cells`` is the wrong length.
        """
        self._require_build("tilemap")
        if self.projection == FULLSCREEN:
            raise ValueError("tilemap() is not supported on a FULLSCREEN layer")
        self.scene._reserve("tilemap", 1, self)
        tilemap = Tilemap(self, self.scene.image(image), columns, rows, cells,
                          x, y, view_width, view_height, view_x, view_y, visible,
                          flip_x, flip_y)
        self._drawables.append(tilemap)
        return tilemap

    def label(self, image, columns, rows=1, x=0, y=0, text=None, glyphs=None,
              visible=True, flip_x=False, flip_y=False):
        """Create a text label: a tilemap you write strings into.

        A label costs one tilemap record and ``columns * rows`` bytes no matter
        how often the text changes, where the same text as individual sprites
        would cost one sprite per character.

        Characters map to frames through a glyph table, resolved once here in
        this order: an explicit ``glyphs`` argument, then a ``glyphs:`` entry
        declared beside the strip in ``__images__.yaml``, then CP437
        (``frame = ord(ch)``). Unmappable characters and spaces become
        :data:`vs2.EMPTY_TILE`, which the renderer skips.

        Args:
            image: The font strip. One frame per glyph.
            columns: Width in characters.
            rows: Height in lines. One-line labels get the :attr:`Label.text`
                property.
            x: Angle; 0 is the bottom of the disc.
            y: Distance inward from the rim, 0 being the outermost LED.
                Text is most legible at low Y, near the rim.
            text: Initial text for a one-line label.
            glyphs: A charmap such as ``"0123456789/-"``, where
                ``frame = glyphs.index(ch)``. Include ``" "`` to get a real
                space glyph on fonts with opaque backgrounds.
            visible: Whether it draws.
            flip_x: Mirror the complete label horizontally.
            flip_y: Mirror the complete label vertically. Set both flips to
                rotate a label 180 degrees without changing its font strip.

        Returns:
            Label: The new label.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ResourceLimitError: If the scene is out of tilemap slots. Labels
                count against the tilemap budget.
            ValueError: On a :data:`~vs2.FULLSCREEN` layer.
        """
        self._require_build("label")
        if self.projection == FULLSCREEN:
            raise ValueError("label() is not supported on a FULLSCREEN layer")
        self.scene._reserve("tilemap", 1, self)
        label = Label(
            self, self.scene.image(image), columns, rows, x, y, glyphs,
            visible, flip_x, flip_y,
        )
        self._drawables.append(label)
        if text is not None:
            label.text = text
        return label


#: The curve each classic mode implies when nothing custom is assigned.
#: FULLSCREEN "stays a mode rather than a curve... but reads the layer's
#: curve" for its radial extent (see the projection-curves spec section),
#: so it gets the same historical shape TUNNEL always had rather than no
#: curve at all.
_DEFAULT_CURVE_BY_MODE = {
    FULLSCREEN: _curves.VS1_TUNNEL,
    TUNNEL: _curves.VS1_TUNNEL,
    HUD: _curves.HUD,
}


def _resolve_projection(value, current_mode=None):
    """Split a :attr:`Layer.projection` argument into ``(mode, curve)``.

    ``value`` is either one of the revision-2 wire ints
    (:data:`FULLSCREEN`/:data:`TUNNEL`/:data:`HUD`) or a 256-byte curve
    (:data:`VS1_TUNNEL`, one from :mod:`vs2.projection`, or the result of
    :func:`tunnel`). A mode selects that mode's default curve and is
    always returned as ``mode`` unchanged -- this is the whole reason
    every existing native call, payload byte and ``layer.projection ==
    vs2.HUD``-style comparison keeps working untouched. A curve keeps
    whichever mode was already active (``current_mode``, or
    :data:`TUNNEL` on a brand new layer with no prior mode, since a curve
    describes exactly the depth-to-row mapping TUNNEL already means) and
    replaces only the curve.
    """
    if isinstance(value, (bytes, bytearray)):
        if len(value) != 256:
            raise ValueError("a projection curve must be exactly 256 bytes")
        mode = current_mode if current_mode is not None else TUNNEL
        return mode, bytes(value)
    mode = int(value)
    if mode not in (FULLSCREEN, TUNNEL, HUD):
        raise ValueError(
            "projection must be vs2.FULLSCREEN, vs2.TUNNEL, vs2.HUD, "
            "or a 256-byte curve from vs2.projection")
    return mode, _DEFAULT_CURVE_BY_MODE[mode]


class Sprite:
    """One movable image on a layer.

    Created by :meth:`Layer.sprite` or handed out by a :class:`SpritePool`,
    never directly. Writing to ``x``, ``y``, ``frame``, ``visible``, ``flip_x``,
    ``flip_y`` or ``image`` goes straight into the renderer's record and
    allocates nothing, so moving sprites every tick is free.

    ``frame`` and ``visible`` are independent, which is what makes priming a
    pooled sprite two plain statements::

        shot.frame = BULLET_FRAME    # still hidden
        shot.show()                  # now visible, same frame
    """

    def __init__(self, layer, image, x, y, frame, visible, flip_x, flip_y):
        self._layer = layer
        self._closed = False
        backend = _vs2_backend()
        if backend is None:
            backend = get_platform().sprites
        self._sprite = backend.Sprite()
        self._uses_fixed_coords = hasattr(self._sprite, "set_x_fixed")
        self._has_flags = hasattr(self._sprite, "set_flags")
        self._has_layer = hasattr(self._sprite, "set_layer")
        self._image = image
        self._x = x
        self._y = y
        self._frame = 0
        self._visible = bool(visible)
        self._flip_x = bool(flip_x)
        self._flip_y = bool(flip_y)
        self._pool = None
        self._pool_live_index = -1
        #: Per-tick movement accumulator, in the same units as :attr:`x`.
        #: An Action or Behavior writes here (never straight to :attr:`x`),
        #: and the scene's one commit pass per pool per tick adds it into
        #: :attr:`x` and resets it to 0. Plain instance attributes, not
        #: descriptors, so a Step that never touches them costs nothing
        #: beyond the ``if dx or dy`` check in the commit pass.
        self.dx = 0
        #: Per-tick movement accumulator for :attr:`y`. See :attr:`dx`.
        self.dy = 0
        self._behaviors = {}
        self._behavior_order = []
        self._set_frame(frame)
        self._sync_all()

    def _require_open(self, field):
        if self._closed:
            raise SceneSealedError("cannot change %s on a sprite from a closed V2 scene" % field)

    def _sync_all(self):
        self._sprite.set_strip(self._image._strip)
        if self._uses_fixed_coords:
            self._sprite.set_x_fixed(_fixed_8_8(self._x))
            self._sprite.set_y_fixed(_fixed_8_8(self._y))
        else:
            self._sprite.set_x(_floor_coord(self._x) % display.width)
            self._sprite.set_y(_render_coord(_floor_coord(self._y), 0, display.height - 1))
        self._sprite.set_perspective(self._layer.projection)
        if self._has_layer:
            self._sprite.set_layer(self._layer._layer)
        self._sync_flags()
        self._sync_frame()

    def _sync_flags(self):
        if self._has_flags:
            self._sprite.set_flags(_sprite_flags(self))

    def _sync_frame(self):
        if self._has_flags or self._visible:
            self._sprite.set_frame(self._frame)
        else:
            self._sprite.set_frame(EMPTY_TILE)

    def _set_frame(self, value):
        value = int(value)
        if value < 0 or value >= self._image.frames:
            raise FrameError("%s has %d frames; frame must be 0..%d" %
                             (self._image.name, self._image.frames, self._image.frames - 1))
        self._frame = value

    @property
    def layer(self):
        """The :class:`Layer` that draws this sprite. Read-only for its whole life,
        so draw order is never ambiguous."""
        return self._layer

    @property
    def image(self):
        """The sprite's :class:`Image`. Assigning a name or handle swaps the
        artwork, keeping :attr:`frame` if it is still in range and resetting it
        to 0 otherwise."""
        return self._image

    @image.setter
    def image(self, value):
        self._require_open("image")
        image = self._layer.scene.image(value)
        self._image = image
        if self._frame >= image.frames:
            self._frame = 0
        self._sprite.set_strip(image._strip)
        self._sync_frame()

    @property
    def x(self):
        """Angle around the disc -- 0 at the bottom, 64 left, 128 top, 192
        right -- wrapping at :data:`vs2.display.width`. Fractional values are
        kept: the renderer stores signed 8.8 fixed point."""
        return self._x

    @x.setter
    def x(self, value):
        self._require_open("x")
        self._x = value
        if self._uses_fixed_coords:
            self._sprite.set_x_fixed(_fixed_8_8(value))
        else:
            self._sprite.set_x(_floor_coord(value) % display.width)

    @property
    def y(self):
        """Distance inward from the rim, where 0 is the outermost LED.

        What it means follows the layer's projection. On a
        :data:`~vs2.HUD` layer it is a direct LED index, ``0..53``. On a
        :data:`~vs2.TUNNEL` layer it is depth, ``0..255``: 0 is the outer
        rim and 255 is the centre. :data:`~vs2.FULLSCREEN` uses that same
        curve as radial extent: 0 fills the disc and increasing values
        contract toward the centre. Out-of-range values clip. Fractional
        values are kept."""
        return self._y

    @y.setter
    def y(self, value):
        self._require_open("y")
        self._y = value
        if self._uses_fixed_coords:
            self._sprite.set_y_fixed(_fixed_8_8(value))
        else:
            self._sprite.set_y(_render_coord(_floor_coord(value), 0, display.height - 1))

    @property
    def frame(self):
        """Which animation frame to draw. Never changes :attr:`visible`.

        Raises:
            FrameError: If the frame is out of range for the image."""
        return self._frame

    @frame.setter
    def frame(self, value):
        self._require_open("frame")
        self._set_frame(value)
        self._sync_frame()

    @property
    def visible(self):
        """Whether the sprite draws. Never changes :attr:`frame`."""
        return self._visible

    @visible.setter
    def visible(self, value):
        self._require_open("visible")
        self._visible = bool(value)
        self._sync_flags()
        self._sync_frame()

    @property
    def flip_x(self):
        """Mirror the sprite horizontally."""
        return self._flip_x

    @flip_x.setter
    def flip_x(self, value):
        self._require_open("flip_x")
        self._flip_x = bool(value)
        self._sync_flags()

    @property
    def flip_y(self):
        """Mirror the sprite vertically."""
        return self._flip_y

    @flip_y.setter
    def flip_y(self, value):
        self._require_open("flip_y")
        self._flip_y = bool(value)
        self._sync_flags()

    @property
    def width(self):
        """Frame width from the image metadata. Read-only, no renderer call."""
        return self._image.width

    @property
    def height(self):
        """Frame height from the image metadata. Read-only, no renderer call."""
        return self._image.height

    def show(self):
        """Make the sprite visible without touching its frame."""
        self.visible = True

    def hide(self):
        """Hide the sprite without touching its frame."""
        self.visible = False

    def overlaps(self, other):
        """Whether this sprite's box overlaps ``other``'s.

        An axis-aligned test that allocates nothing. X wraps around the display,
        so a sprite straddling column 0 still collides correctly; Y does not
        wrap, because the disc has an inside and an outside.
        """
        return (_intersects_circular(self.x, self.width, other.x, other.width)
                and self.y < other.y + other.height
                and self.y + self.height > other.y)

    def first_overlap(self, sprites):
        """Return the first sprite in ``sprites`` that overlaps this one.

        Accepts any iterable, including a :class:`SpritePool`, which is the
        common case::

            baddie = shot.first_overlap(self.baddies)
            if baddie:
                self.baddies.despawn(baddie)

        Returns:
            Sprite or None: The first overlapping sprite, or ``None``.
        """
        for other in sprites:
            if self.overlaps(other):
                return other
        return None

    def despawn(self):
        """Return this sprite to its pool. A convenience over
        ``pool.despawn(sprite)`` -- a sprite already knows its own pool.

        Raises:
            ValueError: If this sprite was not created by a
                :class:`SpritePool` (a standalone :meth:`Layer.sprite`),
                or is not currently live in one.
        """
        if self._pool is None:
            raise ValueError("despawn() is only for sprites from a SpritePool")
        self._pool.despawn(self)

    def behave(self, behavior, name=None):
        """Attach ``behavior`` to this sprite. Structural: only callable
        from :meth:`build`. Returns ``behavior``, so attaching and keeping
        a handle is one line::

            self.turret = boss.behave(Aiming(target=self.ship))
        """
        # Check closedness before touching self._layer -- Layer._close()
        # nulls a closed drawable's own _layer, so a bare
        # self._layer.scene here would crash with a raw AttributeError
        # instead of the clean SceneSealedError a stale handle should
        # raise (see _require_open, the pattern every other mutator uses).
        self._require_open("behave")
        return _attach_behavior(self._layer.scene, self, "sprite",
                                self._behaviors, self._behavior_order,
                                behavior, name)

    @property
    def behaviors(self):
        """This sprite's attached Behaviors, in attachment order."""
        return tuple(self._behavior_order)

    def behavior(self, key):
        """Look up a Behavior attached to this sprite by name (a string)
        or by class. Returns ``None`` if nothing matches."""
        return _lookup_behavior(self._behaviors, self._behavior_order, key)


class _PoolIterator:
    def __init__(self, pool):
        self.pool = pool
        self.index = 0
        self.previous = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.previous is not None and self.previous._pool_live_index == -1:
            self.previous = None
        else:
            self.index += 1 if self.previous is not None else 0
            self.previous = None
        if self.index >= len(self.pool._live):
            raise StopIteration
        self.previous = self.pool._live[self.index]
        return self.previous


class SpritePool:
    """A fixed group of interchangeable sprites, cycled without allocating.

    Created by :meth:`Layer.sprite_pool`. Every operation is O(1) index
    bookkeeping — nothing allocates a Python object or a renderer record.

    Iterating yields only the live sprites, and despawning the current sprite
    mid-loop is supported, which is the pattern most games need. Y is depth on a
    ``TUNNEL`` layer, so a shot fired away from the player counts up toward the
    centre and is retired at a depth the game picks::

        for shot in self.shots:
            shot.y += SHOT_SPEED
            if shot.y > SHOT_RANGE:
                self.shots.despawn(shot)
                continue
            baddie = shot.first_overlap(self.baddies)
            if baddie:
                self.baddies.despawn(baddie)
                self.booms.spawn(x=baddie.x, y=baddie.y)
                self.shots.despawn(shot)

    ``len(pool)`` is the live count and :attr:`free` is the remainder.
    """

    def __init__(self, layer, sprites, on_empty):
        self._layer = layer
        self._free = sprites
        self._live = []
        self._on_empty = on_empty
        #: ``{name: Parameter}`` declared by :meth:`var`.
        self._var_defaults = {}
        #: Declaration order of :attr:`_var_defaults`'s names, tracked
        #: explicitly rather than read back from the dict: MicroPython's
        #: dict does not preserve insertion order the way CPython's does
        #: (confirmed on the unix port -- ``{"hp": 1, "score": 10}.keys()``
        #: comes back ``["score", "hp"]``), so deriving :meth:`kinds`'
        #: field order from ``self._var_defaults.keys()`` silently swapped
        #: values between variables on real MicroPython. This list is what
        #: :meth:`kinds` reads instead.
        self._var_order = []
        #: Field order (from :attr:`_var_order`) a :meth:`kinds` row's
        #: positional values line up against.
        self._kind_fields = ()
        #: ``{kind_name: row}`` declared by :meth:`kinds`.
        self._kind_rows = {}
        self._behaviors = {}
        self._behavior_order = []
        for sprite in sprites:
            sprite._pool = self

    @property
    def layer(self):
        """The :class:`Layer` this pool's sprites belong to."""
        return self._layer

    @property
    def free(self):
        """How many sprites are still available to :meth:`spawn`."""
        return len(self._free)

    @property
    def capacity(self):
        """This pool's total sprite budget -- ``len(pool) + pool.free`` --
        fixed for the life of the scene once :meth:`Layer.sprite_pool`
        reserved it. Live count is :func:`len`; :attr:`free` is the
        remainder."""
        return len(self._free) + len(self._live)

    def __len__(self):
        """The number of live sprites."""
        return len(self._live)

    def __iter__(self):
        """Iterate the live sprites, tolerating despawns during the loop."""
        return _PoolIterator(self)

    def var(self, name, default=0, min=None, max=None, step=None,
            label=None, unit=None, options=None):
        """Declare a per-sprite instance variable on every sprite in this
        pool, with the same parameter types an Action or Behavior
        parameter uses (``options=`` for a :class:`~vs2.params.Choice`, a
        boolean default for a :class:`~vs2.params.Flag`, otherwise a
        :class:`~vs2.params.Number`).

        Primed to ``default`` on every sprite now -- free ones included --
        and reset to it by :meth:`spawn`, so a recycled sprite never
        inherits the previous occupant's value::

            self.enemies.var("hp", 1, min=0, max=99)
            self.enemies.var("angry", False)

        Only callable from :meth:`build`.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ValueError: If ``name`` is already declared on this pool, or
                is one of the framework's reserved names.
        """
        self._layer._require_build("var")
        if name in _RESERVED_VAR_NAMES:
            raise ValueError("%r is a reserved name; choose another" % (name,))
        if name in self._var_defaults:
            raise ValueError("variable %r is already declared on this pool" % (name,))
        parameter = _var_parameter(default, min=min, max=max, step=step,
                                    label=label, unit=unit, options=options)
        self._var_defaults[name] = parameter
        self._var_order.append(name)
        for sprite in self._free:
            setattr(sprite, name, parameter.default)
        for sprite in self._live:
            setattr(sprite, name, parameter.default)
        return parameter.default

    def kinds(self, **rows):
        """Declare named per-type default rows over this pool's own
        instance variables, one positional value per variable in
        declaration order. ``spawn(kind=...)`` applies a row, resolved to
        an index here at build time so spawning costs the same reset loop
        that already applies the plain declared defaults::

            self.enemies.var("hp", 1)
            self.enemies.var("score", 40)
            self.enemies.kinds(driller=(3, 75), chiller=(1, 40))
            self.enemies.spawn(x, y, kind="chiller")

        Only callable from :meth:`build`, and only once per pool.

        Raises:
            SceneSealedError: If called outside ``build()``.
            ValueError: If called twice, or a row's length does not match
                the number of variables :meth:`var` declared.
        """
        self._layer._require_build("kinds")
        if self._kind_rows:
            raise ValueError("kinds() has already been called on this pool")
        fields = tuple(self._var_order)
        for kind_name, row in rows.items():
            if len(row) != len(fields):
                raise ValueError(
                    "kind %r has %d value(s); this pool declared %d "
                    "variable(s) (%s)" % (
                        kind_name, len(row), len(fields), ", ".join(fields)))
        self._kind_fields = fields
        self._kind_rows = dict(rows)

    def behave(self, behavior, name=None):
        """Attach ``behavior`` to this pool. Structural: only callable
        from :meth:`build`. Returns ``behavior``.
        """
        # Layer._require_build checks the layer's own closed flag before
        # touching .scene (which Layer._close() sets to None), the same
        # safe order var()/kinds() above already use.
        self._layer._require_build("behave")
        return _attach_behavior(self._layer.scene, self, "pool",
                                self._behaviors, self._behavior_order,
                                behavior, name)

    @property
    def behaviors(self):
        """This pool's attached Behaviors, in attachment order."""
        return tuple(self._behavior_order)

    def behavior(self, key):
        """Look up a Behavior attached to this pool by name (a string) or
        by class. Returns ``None`` if nothing matches."""
        return _lookup_behavior(self._behaviors, self._behavior_order, key)

    def spawn(self, x, y, frame=0, flip_x=False, flip_y=False, kind=None):
        """Take a free sprite, position it, show it, and return it.

        Every declared :meth:`var` is reset to its default first, so a
        recycled sprite never inherits the previous occupant's values;
        ``kind=``, if given, then overrides those defaults with the named
        :meth:`kinds` row.

        Args:
            x: Angular position.
            y: Radial position.
            frame: Frame to show.
            flip_x: Mirror horizontally.
            flip_y: Mirror vertically.
            kind: A name declared by :meth:`kinds`, applying that row's
                values over the plain declared defaults.

        Returns:
            Sprite or None: The spawned sprite. ``None`` when the pool is
            exhausted and it was not created with
            ``on_empty=vs2.RECYCLE``.

        Raises:
            ValueError: If ``kind`` does not name a declared row.
        """
        if not self._free:
            if self._on_empty is not RECYCLE:
                return None
            self.despawn(self._live[0])
        sprite = self._free.pop()
        sprite.x = x
        sprite.y = y
        sprite.frame = frame
        sprite.flip_x = flip_x
        sprite.flip_y = flip_y
        sprite.visible = True
        sprite.dx = 0
        sprite.dy = 0
        if self._var_defaults:
            for var_name, parameter in self._var_defaults.items():
                setattr(sprite, var_name, parameter.default)
        # A recycled sprite must not carry a previous occupant's Behavior
        # state -- declared `state=` fields (`_behavior_state_owners`,
        # primed to 0 at attach time the same way `_var_defaults` is here)
        # and, separately, a StateMachine's `fsm_state`/`fsm_hold`/
        # `fsm_then` (not part of `_behavior_state_owners` at all -- see
        # `StateMachine.recycle`'s own docstring for why it needs its own
        # reset instead of reusing this loop).
        owners = getattr(self, "_behavior_state_owners", None)
        if owners:
            for state_name in owners:
                setattr(sprite, state_name, 0)
        fsm_owner = getattr(self, "_fsm_owner", None)
        if fsm_owner is not None:
            fsm_owner.recycle(sprite)
        if kind is not None:
            try:
                row = self._kind_rows[kind]
            except KeyError:
                valid = ", ".join(sorted(self._kind_rows.keys()))
                raise ValueError("unknown kind %r; valid: %s" % (kind, valid))
            fields = self._kind_fields
            for field_index in range(len(fields)):
                setattr(sprite, fields[field_index], row[field_index])
        sprite._pool_live_index = len(self._live)
        self._live.append(sprite)
        return sprite

    def despawn(self, sprite):
        """Hide ``sprite`` and return it to the pool.

        Raises:
            ValueError: If the sprite belongs to another pool, or is already
                despawned. Both mean a bookkeeping bug in the game.
        """
        if getattr(sprite, "_pool", None) is not self or sprite._pool_live_index < 0:
            raise ValueError("sprite is not live in this pool")
        index = sprite._pool_live_index
        tail = self._live.pop()
        if tail is not sprite:
            self._live[index] = tail
            tail._pool_live_index = index
        sprite._pool_live_index = -1
        sprite.hide()
        self._free.append(sprite)

    def despawn_all(self):
        """Despawn every live sprite. The usual way to reset a level."""
        while self._live:
            self.despawn(self._live[-1])


class Family:
    """A build-time, sealed group of pools and sprites on one layer,
    addressed as a single :class:`~vs2.actions.Action` target (e.g. a
    ``Collide`` hit list) or Behavior subject.

    Created by :meth:`Scene.family`, never directly. **Not iterable.** Its
    main job is being the target of ``Collide``, which runs inside a
    per-sprite loop; one iterator per sprite per tick would be exactly the
    allocation a zero-allocation Behavior pass exists to avoid. Its
    members are a sealed tuple instead, walked by index -- see
    :attr:`members` -- which is also what a native ``Collide`` kernel
    wants handed to it.
    """

    def __init__(self, scene, layer, members):
        self.scene = scene
        self._layer = layer
        #: Sealed ``((kind, member), ...)`` tuple, ``kind`` being
        #: ``"pool"`` or ``"sprite"``. Internal: :attr:`members` and the
        #: Behavior dispatcher are what consume this.
        self._members = tuple(members)
        self._behaviors = {}
        self._behavior_order = []

    @property
    def layer(self):
        """The single :class:`Layer` every member of this family shares."""
        return self._layer

    @property
    def members(self):
        """This family's pools and sprites, in declared order, as a plain
        tuple. Read freely -- the family object itself is still not
        iterable."""
        return tuple(member for _kind, member in self._members)

    def __iter__(self):
        raise TypeError("a Family is not iterable; use .members, or attach "
                        "a Behavior/Collide instead of looping")

    def __len__(self):
        return len(self._members)

    def behave(self, behavior, name=None):
        """Attach ``behavior`` to the family as a whole -- one Behavior
        instance with one parameter set covering every member, its state
        primed across all of them. Structural: only callable from
        :meth:`Scene.build`. Returns ``behavior``.
        """
        return _attach_behavior(self.scene, self, "family",
                                self._behaviors, self._behavior_order,
                                behavior, name)

    @property
    def behaviors(self):
        """This family's attached Behaviors, in attachment order."""
        return tuple(self._behavior_order)

    def behavior(self, key):
        """Look up a Behavior attached to this family by name (a string)
        or by class. Returns ``None`` if nothing matches."""
        return _lookup_behavior(self._behaviors, self._behavior_order, key)


class Tilemap:
    """A grid of tiles drawn from one tileset image.

    Created by :meth:`Layer.tilemap`. The grid itself is a flat ``bytearray`` of
    tile indices in :attr:`cells`, one byte per cell, addressed in
    ``(column, row)`` order — the same axis order as ``(x, y)`` everywhere
    else::

        self.ground[col, row] = ROCK
        tile = self.ground[col, row]
        self.ground.fill(GRASS)
        self.ground.cells[row * self.ground.columns + col] = ROCK  # fastest

    :data:`vs2.EMPTY_TILE` leaves a cell blank and the renderer skips it.

    Scrolling moves the view over the grid rather than rewriting it, so it costs
    two scalar writes and allocates nothing::

        self.ground.view_y = self.depth % self.ground.tile_height
    """

    def __init__(self, layer, image, columns, rows, cells, x, y,
                 view_width, view_height, view_x, view_y, visible,
                 flip_x=False, flip_y=False):
        columns = int(columns)
        rows = int(rows)
        if columns < 1 or rows < 1:
            raise ValueError("tilemap columns and rows must be positive")
        if cells is None:
            cells = bytearray([EMPTY_TILE] * (columns * rows))
        if len(cells) != columns * rows:
            raise ValueError("cells length must equal columns * rows")
        self._layer = layer
        self._closed = False
        self._image = image
        self._columns = columns
        self._rows = rows
        self._tile_width = image.width
        self._tile_height = image.height
        self._cells = cells if isinstance(cells, bytearray) else bytearray(cells)
        self._cells_view = memoryview(self._cells)
        self._x = x
        self._y = y
        self._view_x = int(view_x)
        self._view_y = int(view_y)
        self._view_width = int(view_width if view_width is not None else columns * image.width)
        self._view_height = int(view_height if view_height is not None else rows * image.height)
        if self._view_x < 0 or self._view_y < 0 or self._view_width < 1 or self._view_height < 1:
            raise ValueError("invalid tilemap view")
        self._visible = bool(visible)
        self._flip_x = bool(flip_x)
        self._flip_y = bool(flip_y)
        backend = _vs2_backend()
        self._tilemap = None
        if backend is not None and hasattr(backend, "Tilemap"):
            self._tilemap = backend.Tilemap(
                strip=image._strip, frames=self._cells_view, columns=columns, rows=rows,
                tile_width=image.width, tile_height=image.height)
        self._sync_all()

    def _require_open(self, field):
        if self._closed:
            raise SceneSealedError("cannot change %s on a tilemap from a closed V2 scene" % field)

    @property
    def layer(self):
        """The :class:`Layer` that draws this tilemap."""
        return self._layer

    @property
    def image(self):
        """The tileset :class:`Image` this map draws from."""
        return self._image

    @property
    def columns(self):
        """Grid width in tiles. Read-only."""
        return self._columns

    @property
    def rows(self):
        """Grid height in tiles. Read-only."""
        return self._rows

    @property
    def tile_width(self):
        """Width of one tile, taken from the image. Read-only."""
        return self._tile_width

    @property
    def tile_height(self):
        """Height of one tile, taken from the image. Read-only."""
        return self._tile_height

    @property
    def cells(self):
        """The flat ``bytearray`` of tile indices, row-major.

        Writable in place; the buffer itself cannot be replaced or resized while
        the map is active, because the renderer reads these bytes directly."""
        # Keeping an exported memoryview alive makes CPython and MicroPython
        # reject bytearray resizing, while callers that supplied a bytearray
        # retain its exact identity for zero-copy bulk updates.
        return self._cells

    @property
    def x(self):
        """Angle of the map's origin, 0 at the bottom of the disc, wrapping at
        :data:`vs2.display.width`."""
        return self._x

    @x.setter
    def x(self, value):
        self._require_open("x")
        self._x = value
        if self._tilemap is not None:
            self._tilemap.set_x_fixed(_fixed_8_8(value))

    @property
    def y(self):
        """Distance of the map's origin inward from the rim, 0 being the
        outermost LED. Interpreted per the layer's projection, like
        :attr:`vs2.Sprite.y`."""
        return self._y

    @y.setter
    def y(self, value):
        self._require_open("y")
        self._y = value
        if self._tilemap is not None:
            self._tilemap.set_y_fixed(_fixed_8_8(value))

    @property
    def view_x(self):
        """Horizontal scroll offset into the grid. Writing it pans the view
        without touching :attr:`cells`."""
        return self._view_x

    @view_x.setter
    def view_x(self, value):
        self._require_open("view_x")
        self._view_x = int(value)
        self._sync_view()

    @property
    def view_y(self):
        """Vertical scroll offset into the grid. Writing it pans the view
        without touching :attr:`cells`."""
        return self._view_y

    @view_y.setter
    def view_y(self, value):
        self._require_open("view_y")
        self._view_y = int(value)
        self._sync_view()

    @property
    def view_width(self):
        """Width of the on-screen window onto the map. Read-only."""
        return self._view_width

    @property
    def view_height(self):
        """Height of the on-screen window onto the map. Read-only."""
        return self._view_height

    @property
    def visible(self):
        """Whether the tilemap draws."""
        return self._visible

    @visible.setter
    def visible(self, value):
        self._require_open("visible")
        self._visible = bool(value)
        self._sync_flags()

    @property
    def flip_x(self):
        """Whether the complete visible viewport is mirrored horizontally."""
        return self._flip_x

    @flip_x.setter
    def flip_x(self, value):
        self._require_open("flip_x")
        self._flip_x = bool(value)
        self._sync_flags()

    @property
    def flip_y(self):
        """Whether the complete visible viewport is mirrored vertically."""
        return self._flip_y

    @flip_y.setter
    def flip_y(self, value):
        self._require_open("flip_y")
        self._flip_y = bool(value)
        self._sync_flags()

    def _sync_all(self):
        if self._tilemap is None:
            return
        self._tilemap.set_x_fixed(_fixed_8_8(self._x))
        self._tilemap.set_y_fixed(_fixed_8_8(self._y))
        self._tilemap.set_perspective(self._layer.projection)
        self._tilemap.set_layer(self._layer._layer)
        self._sync_flags()
        self._sync_view()

    def _sync_flags(self):
        if self._tilemap is not None:
            self._tilemap.set_flags(_tilemap_flags(self))

    def _sync_view(self):
        if self._tilemap is not None:
            self._tilemap.set_viewport(self._view_x, self._view_y,
                                       self._view_width, self._view_height)

    def __getitem__(self, position):
        """Read one cell: ``tile = tilemap[column, row]``.

        Raises:
            IndexError: If the cell is outside the grid.
        """
        column, row = position
        return self.cells[self._cell_index(column, row)]

    def __setitem__(self, position, value):
        """Write one cell: ``tilemap[column, row] = tile``.

        Raises:
            IndexError: If the cell is outside the grid.
        """
        self._require_open("cells")
        self.cells[self._cell_index(*position)] = int(value)

    def _cell_index(self, column, row):
        column = int(column)
        row = int(row)
        if column < 0 or column >= self.columns or row < 0 or row >= self.rows:
            raise IndexError("tilemap cell out of range")
        return row * self.columns + column

    def cell_at(self, x, y):
        """The ``(column, row)`` of the cell under world point ``(x, y)``,
        or ``None`` if it falls outside the grid.

        Accounts for the map's own :attr:`x`/:attr:`y` origin, its
        :attr:`view_x`/:attr:`view_y` scroll offset, the tile size taken
        from its image, and the circular wrap of X -- the same geometry
        the ``TileUnder`` Action (a later task) drives its divide from::

            tile = self.ground.cell_at(sprite.x, sprite.y)
            if tile is not None:
                column, row = tile

        Returns:
            tuple or None: ``(column, row)``, or ``None`` if the point
            falls outside the grid (its Y is above the rim or below the
            floor of the map).
        """
        relative_x = (x - self._x) % display.width
        grid_x = relative_x + self._view_x
        grid_y = (y - self._y) + self._view_y
        if grid_y < 0:
            return None
        column = int(grid_x) // self._tile_width
        row = int(grid_y) // self._tile_height
        if column < 0 or column >= self._columns or row < 0 or row >= self._rows:
            return None
        return (column, row)

    def fill(self, value):
        """Set every cell to ``value``, in place."""
        self._require_open("cells")
        value = int(value)
        for index in range(len(self.cells)):
            self.cells[index] = value

    def show(self):
        """Make the tilemap visible."""
        self.visible = True

    def hide(self):
        """Hide the tilemap."""
        self.visible = False


class Label(Tilemap):
    """A tilemap you write text into.

    Created by :meth:`Layer.label`. Because it is a tilemap, a label counts
    against the tilemap budget rather than the sprite budget, and costs the same
    whether it shows two characters or twenty.

    The display stores tiles counter-clockwise, but a label handles that
    inversion internally: you write ordinary left-to-right strings and never see
    the reversed indices.

    Only fixed-cell ASCII and CP437 are supported. There is no variable-width
    text, wrapping, or Unicode shaping.
    """

    def __init__(self, layer, image, columns, rows, x, y, glyphs, visible,
                 flip_x=False, flip_y=False):
        self._glyphs = glyphs if glyphs is not None else image.glyphs
        Tilemap.__init__(self, layer, image, columns, rows, None, x, y,
                         image.width * int(columns), image.height * int(rows),
                         0, 0, visible, flip_x, flip_y)

    def _glyph(self, char, frame_offset):
        if char == " " and self._glyphs is None:
            return EMPTY_TILE
        if self._glyphs is None:
            value = ord(char)
        else:
            try:
                value = self._glyphs.index(char)
            except ValueError:
                return EMPTY_TILE
        value += frame_offset
        return value if 0 <= value < self.image.frames else EMPTY_TILE

    def write(self, column, row, text, frame_offset=0, pad=True):
        """Write ``text`` starting at ``(column, row)``.

        Touches only the bytes it changes and allocates nothing, so it is safe
        to call every tick. Text longer than the remaining columns is clipped.

        ``frame_offset`` shifts every glyph by a constant, which is how font
        strips that pack a second colour at a fixed offset are reached::

            self.status.write(3, 1, "ABXY", frame_offset=0x80)

        Args:
            column: Starting column.
            row: Row to write into.
            text: The string. Non-strings are converted.
            frame_offset: Added to each glyph's frame index.
            pad: When true, clear the rest of the row after the text. Set it
                false to overwrite in place without disturbing neighbours.

        Raises:
            IndexError: If ``column`` or ``row`` is outside the grid.
        """
        self._require_open("cells")
        column = int(column)
        row = int(row)
        if row < 0 or row >= self.rows:
            raise IndexError("label row out of range")
        if column < 0 or column >= self.columns:
            raise IndexError("label column out of range")
        text = str(text)
        remaining = self.columns - column if pad else min(len(text), self.columns - column)
        for index in range(remaining):
            char = text[index] if index < len(text) else None
            value = EMPTY_TILE if char is None else self._glyph(char, int(frame_offset))
            # Tile storage runs counter-clockwise; this is the one place the
            # direction inversion belongs, never in game code.
            self.cells[row * self.columns + self.columns - 1 - (column + index)] = value

    @property
    def text(self):
        """The label's contents, for one-line labels only.

        Reading maps the cells back through the glyph table and strips trailing
        blanks; writing truncates at :attr:`~Tilemap.columns` and pads the rest
        with :data:`vs2.EMPTY_TILE`::

            title = hud.label("rainbow437.png", columns=18, text="VS2 SPRITES")
            title.text = "GAME OVER"

        Raises:
            AttributeError: On a label with more than one row. Use
                :meth:`write` there.
        """
        if self.rows != 1:
            raise AttributeError("multi-line labels have no text property")
        chars = []
        for column in range(self.columns):
            frame = self.cells[self.columns - 1 - column]
            if frame == EMPTY_TILE:
                chars.append(" ")
            elif self._glyphs is None:
                chars.append(chr(frame))
            elif frame < len(self._glyphs):
                chars.append(self._glyphs[frame])
            else:
                chars.append(" ")
        return "".join(chars).rstrip()

    @text.setter
    def text(self, value):
        if self.rows != 1:
            raise AttributeError("multi-line labels have no text property")
        self.write(0, 0, value)

    def set_number(self, value, width=1, pad="0"):
        """Write a right-aligned integer without building a string.

        A score updated every tick this way costs no allocation at all, where
        ``"%05d" % value`` would allocate a string per frame::

            self.score.set_number(value, width=5, pad="0")

        Negative values clamp to zero, and values too large for ``width`` fill
        with nines rather than overflowing the label.

        Args:
            value: The number to display.
            width: How many digit cells to use, starting at column 0.
            pad: Character for leading blanks. ``"0"`` zero-pads; ``" "``
                leaves them blank.

        Raises:
            ValueError: If ``width`` does not fit the label.
        """
        width = int(width)
        if width < 1 or width > self.columns:
            raise ValueError("number width must fit the label")
        value = int(value)
        if value < 0:
            value = 0
        divisor = 1
        for _ in range(width - 1):
            divisor *= 10
        for index in range(width):
            digit = value // divisor if divisor else value
            if digit > 9:
                digit = 9
            if value < divisor and pad != "0" and index < width - 1:
                char = pad[0] if pad else " "
            else:
                char = chr(ord("0") + digit)
            self.cells[self.columns - 1 - index] = self._glyph(char, 0)
            value %= divisor if divisor else 1
            divisor //= 10 if divisor > 1 else 1


def _payload_buffer(scene, size):
    payload = scene._vs2_payload
    if payload is None or len(payload) != size:
        payload = bytearray(size)
        scene._vs2_payload = payload
    return payload


def export_scene_payload(scene=None):
    """Export the sealed display graph for desktop and browser renderers."""
    _claim()
    if scene is None:
        return bytearray()
    if scene._phase != "sealed":
        raise SceneSealedError("cannot export a scene before build() seals it")
    layers = scene.layers
    sprites = scene._payload_sprites
    tilemaps = scene._payload_tilemaps
    drawables = scene._payload_drawables
    size = (PAYLOAD_HEADER_SIZE + len(layers) * PAYLOAD_LAYER_SIZE
            + len(sprites) * PAYLOAD_SPRITE_SIZE + len(tilemaps) * PAYLOAD_TILEMAP_SIZE
            + scene._payload_frames_size + len(drawables) * PAYLOAD_DRAW_REF_SIZE)
    payload = _payload_buffer(scene, size)
    struct.pack_into("<4sBBBBHHHH", payload, 0, PAYLOAD_MAGIC, PAYLOAD_VERSION,
                     len(layers), len(sprites), len(tilemaps), PAYLOAD_HEADER_SIZE,
                     PAYLOAD_LAYER_SIZE, PAYLOAD_SPRITE_SIZE, PAYLOAD_TILEMAP_SIZE)
    offset = PAYLOAD_HEADER_SIZE
    for index, layer in enumerate(layers):
        # Of the five reserved bytes: camera X (wraps at display.width,
        # same as any other X), camera Y (clamped 0..255, same range as a
        # tunnel depth), then the curve index -- 0 meaning "this layer's
        # mode default curve", which is exactly the no-camera/default-curve
        # case every existing (pre-camera, pre-curve) scene is in, so its
        # payload stays byte-identical. The last two bytes stay reserved.
        camera_x_byte = _floor_coord(layer.camera_x) % display.width
        camera_y_byte = _render_coord(_floor_coord(layer.camera_y), 0, 255)
        curve_index = layer._curve_index()
        struct.pack_into("<BBBBBBBB", payload, offset, index, layer.projection,
                         FLAG_VISIBLE if layer.visible else 0, camera_x_byte,
                         camera_y_byte, curve_index, 0, 0)
        offset += PAYLOAD_LAYER_SIZE
    for sprite, layer_index in sprites:
        struct.pack_into("<BBBBBBhhii", payload, offset, layer_index,
                         sprite.image._strip, sprite.frame, sprite.layer.projection,
                         _sprite_flags(sprite), 0, 0, 0, _fixed_8_8(sprite.x),
                         _fixed_8_8(sprite.y))
        offset += PAYLOAD_SPRITE_SIZE
    cells_offset = offset + len(tilemaps) * PAYLOAD_TILEMAP_SIZE
    for tilemap, layer_index in tilemaps:
        struct.pack_into("<BBBBHHHHHHHHiiI", payload, offset, layer_index,
                         tilemap.image._strip, _tilemap_flags(tilemap),
                         tilemap.layer.projection, tilemap.columns, tilemap.rows,
                         tilemap.tile_width, tilemap.tile_height, tilemap.view_x,
                         tilemap.view_y, tilemap.view_width, tilemap.view_height,
                         _fixed_8_8(tilemap.x), _fixed_8_8(tilemap.y), cells_offset)
        offset += PAYLOAD_TILEMAP_SIZE
        payload[cells_offset:cells_offset + len(tilemap.cells)] = tilemap.cells
        cells_offset += len(tilemap.cells)
    for kind, index in drawables:
        payload[cells_offset] = kind
        payload[cells_offset + 1] = index
        cells_offset += PAYLOAD_DRAW_REF_SIZE
    return payload


def reset_runtime_state():
    base._led_state = None
    base._servo_state = None
    base._button_state = None
