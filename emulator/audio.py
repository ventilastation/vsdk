import pyglet
import platform
import os
import threading
from ffmpeg import FFmpeg

SOUNDS_FOLDER = "../apps/sounds"

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

def load_sound(fullname):
    size = os.path.getsize(fullname)
    if size > 200 * 1024:
        # large file, probably music, don't preload fully, load as streaming
        try:
            sound = pyglet.media.load(fullname, streaming=True)
            return sound
        except Exception as e:
            print("WARNING: sound cannot be loaded:", fullname, e)
            return None
        
    # small size, convert to wav if needed and load as non-streaming
    wavname = fullname + ".wav"

    if (not os.path.exists(wavname)
        or os.path.getmtime(fullname) > os.path.getmtime(wavname)):
        print("Converting mp3 to wav:", fullname)
        ffmpeg = (
            FFmpeg()
            .option("y")
            .input(fullname)
            .output(wavname)
        )
        ffmpeg.execute()

    try:
        sound = pyglet.media.load(wavname, streaming=False)
        return sound
    except pyglet.media.codecs.wave.WAVEDecodeException:
        print("WARNING: sound cannot be loaded:", wavname)
        return None


def sound_init():
    def load_sounds():
        for dirpath, dirs, files in os.walk(SOUNDS_FOLDER):
            for fn in files:
                if fn.endswith(".mp3"):
                    fullname = os.path.join(dirpath, fn)
                    sound = load_sound(fullname)
                    if not sound:
                        continue
                    fn = fullname[len(SOUNDS_FOLDER)+1:-4].replace("\\", "/")
                    sounds[bytes(fn, "latin1")] = sound

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
        command, *args = sound_queue.pop()
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
            if name != b"off":
                s = sounds.get(name)
                if s:
                    print("Playing music:", name)
                    try:
                        s.seek(0)
                    except:
                        pass
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

