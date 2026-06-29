import pyglet
import platform
import os
import threading
from ffmpeg import FFmpeg

SOUND_ROOTS = (
    ("../games", "games"),
    ("../system", "system"),
)

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

        # startup sound
        sound_queue.append(("sound", bytes("ventilagon/audio/es/superventilagon", "latin1")))
        print("Sound system initialized with", len(sounds), "sounds.")
    threading.Thread(target=load_sounds, daemon=True).start()

def playsound(name):
    sound_queue.append(("sound", name))

def playnotes(folder, notes):
    sound_queue.append(("notes", folder, notes))

def playmusic(name):
    sound_queue.append(("music", name))

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
            if music_player:
                music_player.delete()
                music_player = None
            if name != b"off":
                s = sounds.get(name)
                if s:
                    print("Playing music:", name)
                    try:
                        s.seek(0)
                    except:
                        pass
                    if name.startswith(b"voom/") or name.startswith(b"ventilagon/"):
                        # Game background music loops continuously until stopped/changed.
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
