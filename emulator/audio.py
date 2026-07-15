import pyglet
import platform
import os
import threading
from ffmpeg import FFmpeg

SOUND_ROOTS = (
    ("../games", "games"),
    ("../system", "system"),
)

# Installed game packages (.vs2 zips, see emulator/package_manager.py) keep
# their mp3s inside the zip; they're extracted into a cache only when needed
# and loaded after the tree walk so a package wins over an in-tree game with
# the same slug.
_EMULATOR_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGES_DIR = os.path.join(_EMULATOR_DIR, "..", "installed_packages")
SOUND_CACHE_DIR = os.path.join(_EMULATOR_DIR, "..", "build", "base", "sound_cache")

pyglet.options['debug_media'] = False

if platform.system() == "Windows":
    # default sound is glitchy on my Windows 10
    pyglet.options['audio'] = ('directsound', 'silent')
else:
    # Force using OpenAL since pulse crashes
    pyglet.options['audio'] = ('openal', 'silent')

# preload all sounds
sounds = {}
sound_queue = []
music_player = None

if platform.system() == "Windows":
    FFMPEG_PATH = "ffmpeg-win/ffmpeg.exe"
else:
    FFMPEG_PATH = "ffmpeg"

def short_name(path):
    for root, _kind in SOUND_ROOTS:
        if path.startswith(root):
            path = path[len(root)+1:]
            break
    return path


def sound_name_from_path(root_kind, root_path, fullname):
    relative = os.path.relpath(fullname, root_path)
    if relative.endswith(".mp3"):
        relative = relative[:-4]
    relative = relative.replace("\\", "/")

    parts = relative.split("/")
    if "sounds" not in parts:
        return None

    sounds_index = parts.index("sounds")
    prefix_parts = parts[:sounds_index]
    asset_parts = parts[sounds_index + 1:]
    if not prefix_parts or not asset_parts:
        return None

    if root_kind == "games":
        return ".".join(prefix_parts) + "/" + "/".join(asset_parts)

    return prefix_parts[-1] + "/" + "/".join(asset_parts)

def convert_mp3_to_wav(input_filename, output_filename):
    print("Converting mp3 to wav:", short_name(input_filename))
    try:
        ffmpeg = (
            FFmpeg(FFMPEG_PATH)
            .option("y")
            .input(input_filename)
            .output(output_filename)
        )
        ffmpeg.execute()
    except Exception as e:
        print("ERROR: cannot convert mp3 to wav:", e)
        raise e

def load_sound(filename_mp3, force_static=False):
    filename_wav = filename_mp3 + ".wav"

    if os.path.getsize(filename_mp3) > 200 * 1024 and not force_static:
        # larger file, probably music, don't preload fully, load as streaming
        if os.path.exists(filename_wav):
            if is_newer(filename_mp3, filename_wav):
                convert_mp3_to_wav(filename_mp3, filename_wav)
            return pyglet.media.load(filename_wav, streaming=True)
        else:
            try:
                return pyglet.media.load(filename_mp3, streaming=True)
            except Exception:
                # cannot load the mp3, try converting to wav
                convert_mp3_to_wav(filename_mp3, filename_wav)
                return pyglet.media.load(filename_wav, streaming=True)
    else:
        # small size (or forced static): convert to wav if needed and load as
        # non-streaming, so it can be replayed and looped cleanly (Voom music).

        if (not os.path.exists(filename_wav) or is_newer(filename_mp3, filename_wav)):
            convert_mp3_to_wav(filename_mp3, filename_wav)

        return pyglet.media.load(filename_wav, streaming=False)
   
def is_newer(filename_1, filename_2):
    return os.path.getmtime(filename_1) > os.path.getmtime(filename_2)


def register_package_sounds(package_path):
    """Extract one package's sounds/*.mp3 into the cache (skipped while the
    cached copy is newer than the package) and (re)load them under
    "<slug>/<asset>" keys -- the same shape tree games get."""
    import zipfile

    slug = os.path.basename(package_path)[:-len(".vs2")]
    cache_dir = os.path.join(SOUND_CACHE_DIR, slug)
    loaded = 0
    with zipfile.ZipFile(package_path) as archive:
        for member in archive.namelist():
            if not (member.startswith("sounds/") and member.endswith(".mp3")):
                continue
            asset = member[len("sounds/"):-len(".mp3")]
            if not asset or "/" in asset:
                continue
            target = os.path.join(cache_dir, asset + ".mp3")
            if (not os.path.exists(target)
                    or os.path.getmtime(package_path) > os.path.getmtime(target)):
                os.makedirs(cache_dir, exist_ok=True)
                with open(target, "wb") as out:
                    out.write(archive.read(member))
            sound = load_sound(target)
            if sound:
                sounds[bytes(slug + "/" + asset, "latin1")] = sound
                loaded += 1
    return loaded


def scan_package_sounds():
    if not os.path.isdir(PACKAGES_DIR):
        return
    for filename in sorted(os.listdir(PACKAGES_DIR)):
        if not filename.endswith(".vs2") or filename.endswith(".no-sound.vs2"):
            continue
        try:
            register_package_sounds(os.path.join(PACKAGES_DIR, filename))
        except Exception as e:
            print("WARNING: cannot load package sounds:", filename, e)


def rescan_package_sounds(slug=None):
    """Pick up a freshly uploaded package without restarting the base; runs
    on its own thread like sound_init's initial load."""
    def _rescan():
        if slug is None:
            scan_package_sounds()
            return
        try:
            count = register_package_sounds(
                os.path.join(PACKAGES_DIR, slug + ".vs2"))
            print("Loaded", count, "sounds from package", slug)
        except Exception as e:
            print("WARNING: cannot load package sounds:", slug, e)
    threading.Thread(target=_rescan, daemon=True).start()


def sound_init():
    def load_sounds():
        for root_path, root_kind in SOUND_ROOTS:
            if not os.path.exists(root_path):
                continue
            for dirpath, dirs, files in os.walk(root_path):
                for fn in files:
                    if fn.endswith(".mp3"):
                        fullname = os.path.join(dirpath, fn)
                        # Voom (Doom) sounds load static so music can loop/replay.
                        force_static = "/voom/" in fullname.replace("\\", "/")
                        sound = load_sound(fullname, force_static=force_static)
                        if not sound:
                            continue
                        sound_name = sound_name_from_path(root_kind, root_path, fullname)
                        if sound_name:
                            sounds[bytes(sound_name, "latin1")] = sound

        # After the tree so a package overrides an in-tree game's sounds.
        scan_package_sounds()

        # startup sound
        sound_queue.append(("sound", bytes("ventilagon/audio/es/superventilagon", "latin1")))
        print("Sound system initialized with", len(sounds), "sounds.")
    threading.Thread(target=load_sounds, daemon=True).start()

def playsound(name):
    sound_queue.append(("sound", name))

def playnotes(folder, notes):
    sound_queue.append(("notes", folder, notes))

def playmusic(name, loop=False):
    sound_queue.append(("music", name, loop))

def sound_process_queue():
    global music_player
    while sound_queue:
        # FIFO: process triggers in the order they arrived. Doom changes music by
        # emitting "musicstop" then "music ..." back-to-back; popping from the end
        # would reverse them and stop the track right after starting it.
        command, *args = sound_queue.pop(0)
        if command == "sound":
            name = args[0]
            s = sounds.get(name)
            if s:
                s.play()
            else:
                print("WARNING: sound not found:", name)
        elif command == "music":
            name = args[0]
            loop = args[1] if len(args) > 1 else False
            if music_player:
                music_player.delete()
                music_player = None
            if name != b"off":
                s = sounds.get(name)
                if s:
                    print("Playing music:", name, "(loop)" if loop else "")
                    try:
                        s.seek(0)
                    except:
                        pass
                    if loop:
                        # Looping requested by the "music <track> loop" wire command.
                        music_player = pyglet.media.Player()
                        music_player.queue(s)
                        music_player.loop = True
                        music_player.play()
                    else:
                        music_player = s.play()
                else:
                    print("WARNING: music not found:", name)
        elif command == "notes":
            folder, notes = args
            to_play = []
            for note in notes.split(b";"):
                sound = sounds.get(folder + b"/" + note)
                if sound:
                    to_play.append(sound)
                else:
                    print("WARNING: note not found:", folder, note)

            for s in to_play:
                s.play()
