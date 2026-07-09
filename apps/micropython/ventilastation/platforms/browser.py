"""Browser platform: the MicroPython side of the WASM web emulator.

Comms and display talk to the JS worker host registered by
web/wasm-worker.js. High-frequency payloads (frames, sprites, commands)
must cross the bridge as pointer + length into WASM memory, NOT as fresh
Python bytes objects -- object bridging leaks on the MicroPython heap.
See ARCHITECTURE.md ("Why Pointer Posting Matters"). The direct-object
calls below are kept only as compatibility fallbacks.
"""

import uctypes

from ventilastation.compat import ticks_diff_us, ticks_us
from ventilastation.platforms.base import Platform
from ventilastation.platforms.headless import NullDisplay
from ventilastation.runtime import MemoryStorage


class BrowserStorage(MemoryStorage):
    def export_state(self):
        exported = {}
        for filename, content in self.files.items():
            exported[filename] = dict(content)
        return exported

    def import_state(self, files):
        self.files = {}
        for filename, content in files.items():
            self.files[filename] = dict(content)


_BUTTON_BYTES = tuple(bytes((value,)) for value in range(256))


def _post_worker_command(worker_host, line, data=b""):
    if isinstance(line, str):
        line = line.encode("utf-8")
    line = bytes(line)
    if isinstance(data, str):
        data = data.encode("utf-8")
    payload = data if data else b""

    post_command_ptr = getattr(worker_host, "post_command_ptr", None)
    if post_command_ptr is not None:
        payload_ptr = uctypes.addressof(payload) if payload else 0
        try:
            post_command_ptr(
                uctypes.addressof(line),
                len(line),
                payload_ptr,
                len(payload),
            )
            return True
        except Exception:
            pass

    try:
        worker_host.post_command(line.decode("utf-8"), bytes(payload) if payload else b"")
        return True
    except Exception:
        return False


class BrowserComms:
    def __init__(self):
        self.buttons = 0
        self.input_updates = []
        self.input_sequence = 0
        self.events = []
        self.worker_host = None

    def receive(self, _bufsize):
        if self.worker_host is not None:
            try:
                self.set_buttons(self.worker_host.get_buttons())
            except Exception:
                pass
        return _BUTTON_BYTES[self.buttons]

    def send(self, line, data=b""):
        if isinstance(line, str):
            line = line.encode("utf-8")
        line = bytes(line)
        parts = line.split()
        command = parts[0].decode("utf-8") if parts else ""
        args = [p.decode("utf-8") for p in parts[1:]]
        payload = bytes(data) if data else b""

        event = {
            "command": command,
            "args": args,
        }
        if payload:
            event["data"] = payload
        if self.worker_host is not None:
            if _post_worker_command(self.worker_host, line, payload):
                return
        self.events.append(event)

    def set_buttons(self, buttons):
        normalized = buttons & 0xFF
        if normalized == self.buttons:
            return
        self.buttons = normalized
        self.input_sequence += 1

    def set_worker_host(self, worker_host):
        self.worker_host = worker_host

    def drain_input_updates(self):
        updates = self.input_updates
        self.input_updates = []
        return updates

    def drain_events(self):
        events = self.events
        self.events = []
        return events


class BrowserDisplay(NullDisplay):
    def __init__(self, comms):
        super().__init__()
        self.comms = comms
        self.worker_host = None
        self.gamma_mode = 1
        self.frame = 0
        self.sprite_data = bytearray(b"\0\0\0\xff\xff" * 100)
        self.palette_version = 0
        self.palette_dirty = False
        self.asset_data = {}
        self.assets = {}
        self.dirty_asset_slots = set()
        self._worker_post_sprites = None
        self._worker_post_frame = None
        self._worker_post_frame_bytes = None
        self._worker_post_present = None
        self._frame_meta = bytearray(16)
        self._profile_totals = {
            "sampleCount": 0,
            "displayExportUs": 0,
            "displayExportUsMax": 0,
            "paletteAttachUs": 0,
            "paletteAttachUsMax": 0,
            "assetsAssembleUs": 0,
            "assetsAssembleUsMax": 0,
            "eventsDrainUs": 0,
            "eventsDrainUsMax": 0,
            "spritesDecodeUs": 0,
            "spritesDecodeUsMax": 0,
        }
        self._frame_export = {
            "frame": 0,
            "buttons": 0,
            "column_offset": 0,
            "gamma_mode": 1,
            "palette_length": 0,
            "palette_version": 0,
            "palette_dirty": False,
            "palette": None,
            "assets": [],
            "events": [],
            "sprites": [],
            "python_profile": None,
        }

    def set_worker_host(self, worker_host):
        self.worker_host = worker_host
        self._worker_post_sprites = getattr(worker_host, "post_sprites", None)
        self._worker_post_sprites_ptr = getattr(worker_host, "post_sprites_ptr", None)
        self._worker_post_frame_bytes = getattr(worker_host, "post_frame_bytes", None)
        self._worker_post_frame_bytes_ptr = getattr(worker_host, "post_frame_bytes_ptr", None)
        self._worker_post_frame = getattr(worker_host, "post_frame", None)
        self._worker_post_present = getattr(worker_host, "post_present", None)
        self._worker_post_present_ptr = getattr(worker_host, "post_present_ptr", None)

    def _post_command(self, line, data=b""):
        if self.worker_host is None:
            return False
        return _post_worker_command(self.worker_host, line, data)

    def _post_sprites(self):
        if self.worker_host is None:
            return False
        post_sprites = self._worker_post_sprites
        post_sprites_ptr = self._worker_post_sprites_ptr
        if post_sprites_ptr is not None:
            try:
                post_sprites_ptr(uctypes.addressof(self.sprite_data), len(self.sprite_data))
                return True
            except Exception:
                pass
        if post_sprites is None:
            return self._post_command("sprites", self.sprite_data)
        try:
            post_sprites(self.sprite_data)
            return True
        except Exception:
            return False

    def _fill_frame_meta(self, full):
        palette_dirty = 1 if (full or self.palette_dirty) else 0
        frame_meta = self._frame_meta
        frame = self.frame
        palette_length = len(self.palette)
        palette_version = self.palette_version
        frame_meta[0] = frame & 0xFF
        frame_meta[1] = (frame >> 8) & 0xFF
        frame_meta[2] = (frame >> 16) & 0xFF
        frame_meta[3] = (frame >> 24) & 0xFF
        frame_meta[4] = self.comms.buttons & 0xFF
        frame_meta[5] = self.gamma_mode & 0xFF
        frame_meta[6] = self.column_offset & 0xFF
        frame_meta[7] = palette_dirty
        frame_meta[8] = palette_length & 0xFF
        frame_meta[9] = (palette_length >> 8) & 0xFF
        frame_meta[10] = (palette_length >> 16) & 0xFF
        frame_meta[11] = (palette_length >> 24) & 0xFF
        frame_meta[12] = palette_version & 0xFF
        frame_meta[13] = (palette_version >> 8) & 0xFF
        frame_meta[14] = (palette_version >> 16) & 0xFF
        frame_meta[15] = (palette_version >> 24) & 0xFF
        return frame_meta

    def _post_present(self, full):
        if self.worker_host is None:
            return False
        post_present = self._worker_post_present
        post_present_ptr = self._worker_post_present_ptr
        if post_present_ptr is None and post_present is None:
            return False
        try:
            frame_meta = self._fill_frame_meta(full)
            if post_present_ptr is not None:
                post_present_ptr(
                    uctypes.addressof(self.sprite_data),
                    len(self.sprite_data),
                    uctypes.addressof(frame_meta),
                    len(frame_meta),
                )
                return True
            if post_present is None:
                return False
            post_present(self.sprite_data, frame_meta)
            return True
        except Exception:
            return False

    def _post_frame(self, full):
        if self.worker_host is None:
            return False
        palette_dirty = 1 if (full or self.palette_dirty) else 0
        post_frame_bytes = self._worker_post_frame_bytes
        post_frame_bytes_ptr = self._worker_post_frame_bytes_ptr
        if post_frame_bytes is not None:
            frame_meta = self._fill_frame_meta(full)
            try:
                if post_frame_bytes_ptr is not None:
                    post_frame_bytes_ptr(uctypes.addressof(frame_meta), len(frame_meta))
                    return True
                post_frame_bytes(frame_meta)
                return True
            except Exception:
                return False
        post_frame = self._worker_post_frame
        if post_frame is None:
            return self._post_command(
                "frame %d %d %d %d %d %d %d" % (
                    self.frame,
                    self.comms.buttons,
                    self.gamma_mode,
                    self.column_offset,
                    len(self.palette),
                    self.palette_version,
                    palette_dirty,
                )
            )
        try:
            post_frame(
                self.frame,
                self.comms.buttons,
                self.gamma_mode,
                self.column_offset,
                len(self.palette),
                self.palette_version,
                palette_dirty,
            )
            return True
        except Exception:
            return False

    def set_gamma_mode(self, mode):
        self.gamma_mode = mode

    def set_palettes(self, palette):
        palette = bytes(palette)
        if palette == self.palette:
            return
        self.palette = palette
        self.palette_version += 1
        self.palette_dirty = True

    def getaddress(self, sprite_num):
        return uctypes.addressof(self.sprite_data) + sprite_num * 5

    def set_imagestrip(self, number, stripmap):
        stripmap = bytes(stripmap)
        if self.asset_data.get(number) == stripmap:
            return
        asset = self._decode_imagestrip(number, stripmap)
        if asset is None:
            return
        self.asset_data[number] = stripmap
        self.assets[number] = asset
        self.dirty_asset_slots.add(number)

    def update(self):
        self.frame += 1
        if self.worker_host is None:
            return
        full = bool(self.worker_host.consume_full_frame_request())
        if (full or self.palette_dirty) and self.palette:
            self._post_command("palette %d %d" % (len(self.palette), self.palette_version), self.palette)
        if full:
            for slot, stripmap in self.asset_data.items():
                self._post_command("imagestrip %d %d" % (slot, len(stripmap)), stripmap)
        else:
            for slot in self.dirty_asset_slots:
                stripmap = self.asset_data.get(slot)
                if stripmap is not None:
                    self._post_command("imagestrip %d %d" % (slot, len(stripmap)), stripmap)
        if (
            self._worker_post_present_ptr is not None or
            self._worker_post_present is not None
        ):
            self._post_present(full)
        else:
            self._post_sprites()
            self._post_frame(full)
        self.palette_dirty = False
        self.dirty_asset_slots.clear()

    def _decode_imagestrip(self, slot, stripmap):
        if len(stripmap) < 4:
            return None
        width = stripmap[0]
        if width == 255:
            width = 256
        return {
            "slot": slot,
            "width": width,
            "height": stripmap[1],
            "frames": stripmap[2] or 1,
            "palette": stripmap[3] or 0,
            "data": stripmap[4:],
        }

    def _decode_sprites(self):
        sprites = []
        sprite_data = self.sprite_data
        for offset in range(0, len(sprite_data), 5):
            frame = sprite_data[offset + 3]
            if frame == 255:
                continue
            perspective = sprite_data[offset + 4]
            if perspective >= 128:
                perspective -= 256
            sprites.append({
                "slot": offset // 5,
                "x": sprite_data[offset],
                "y": sprite_data[offset + 1],
                "image_strip": sprite_data[offset + 2],
                "frame": frame,
                "perspective": perspective,
            })
        return sprites

    def export_frame(self, full=False):
        started_at = ticks_us()
        exported = self._frame_export
        palette_started_at = ticks_us()
        exported["frame"] = self.frame
        exported["buttons"] = self.comms.buttons
        exported["column_offset"] = self.column_offset
        exported["gamma_mode"] = self.gamma_mode
        exported["palette_length"] = len(self.palette)
        exported["palette_version"] = self.palette_version
        exported["palette_dirty"] = full or self.palette_dirty
        exported["palette"] = self.palette if (full or self.palette_dirty) else None
        after_palette_at = ticks_us()
        assets_started_at = after_palette_at
        if full:
            asset_slots = self.assets
        else:
            asset_slots = self.dirty_asset_slots
        exported["assets"] = [self.assets[slot] for slot in asset_slots if slot in self.assets]
        after_assets_at = ticks_us()
        exported["events"] = self.comms.drain_events()
        after_events_at = ticks_us()
        exported["sprites"] = self._decode_sprites()
        finished_at = ticks_us()
        display_export_us = ticks_diff_us(finished_at, started_at)
        palette_attach_us = ticks_diff_us(after_palette_at, palette_started_at)
        assets_assemble_us = ticks_diff_us(after_assets_at, assets_started_at)
        events_drain_us = ticks_diff_us(after_events_at, after_assets_at)
        sprites_decode_us = ticks_diff_us(finished_at, after_events_at)
        profile = self._profile_totals
        profile["sampleCount"] += 1
        profile["displayExportUs"] += display_export_us
        profile["paletteAttachUs"] += palette_attach_us
        profile["assetsAssembleUs"] += assets_assemble_us
        profile["eventsDrainUs"] += events_drain_us
        profile["spritesDecodeUs"] += sprites_decode_us
        if display_export_us > profile["displayExportUsMax"]:
            profile["displayExportUsMax"] = display_export_us
        if palette_attach_us > profile["paletteAttachUsMax"]:
            profile["paletteAttachUsMax"] = palette_attach_us
        if assets_assemble_us > profile["assetsAssembleUsMax"]:
            profile["assetsAssembleUsMax"] = assets_assemble_us
        if events_drain_us > profile["eventsDrainUsMax"]:
            profile["eventsDrainUsMax"] = events_drain_us
        if sprites_decode_us > profile["spritesDecodeUsMax"]:
            profile["spritesDecodeUsMax"] = sprites_decode_us
        sample_count = profile["sampleCount"] or 1
        exported["python_profile"] = {
            "displayExportMs": profile["displayExportUs"] / sample_count / 1000.0,
            "displayExportMsMax": profile["displayExportUsMax"] / 1000.0,
            "paletteAttachMs": profile["paletteAttachUs"] / sample_count / 1000.0,
            "paletteAttachMsMax": profile["paletteAttachUsMax"] / 1000.0,
            "assetsAssembleMs": profile["assetsAssembleUs"] / sample_count / 1000.0,
            "assetsAssembleMsMax": profile["assetsAssembleUsMax"] / 1000.0,
            "eventsDrainMs": profile["eventsDrainUs"] / sample_count / 1000.0,
            "eventsDrainMsMax": profile["eventsDrainUsMax"] / 1000.0,
            "spritesDecodeMs": profile["spritesDecodeUs"] / sample_count / 1000.0,
            "spritesDecodeMsMax": profile["spritesDecodeUsMax"] / 1000.0,
            "sampleCount": sample_count,
            "assetCount": len(exported["assets"]),
            "spriteCount": len(exported["sprites"]),
            "full": bool(full),
        }
        self.palette_dirty = False
        self.dirty_asset_slots.clear()
        return exported


def create_browser_platform():
    from ventilastation.platforms.base import LazyModule

    comms = BrowserComms()
    sprites_backend = LazyModule("ventilastation.emu_sprites")
    display = BrowserDisplay(comms)
    return Platform(
        name="browser",
        comms=comms,
        display=display,
        sprites_backend=sprites_backend,
        storage=BrowserStorage(),
    )
