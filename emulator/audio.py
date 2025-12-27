import pyglet
import platform
import os
import threading

SOUNDS_FOLDER = "../apps/sounds"

if platform.system() != "Windows":
    # Force using OpenAL since pulse crashes
    pyglet.options['audio'] = ('openal', 'silent')

# preload all sounds
sounds = {}
sound_queue = []
music_player = None

def init_sound():
    def load_sounds():
        for dirpath, dirs, files in os.walk(SOUNDS_FOLDER):
            for fn in files:
                if fn.endswith(".mp3"):
                    fullname = os.path.join(dirpath, fn)
                    fn = fullname[len(SOUNDS_FOLDER)+1:-4].replace("\\", "/")
                    try:
                        sound = pyglet.media.load(fullname + ".wav", streaming=False)
                        print(fullname + ".wav")
                    except:
                        try:
                            sound = pyglet.media.load(fullname, streaming=False)
                            print(fullname)
                        except pyglet.media.codecs.wave.WAVEDecodeException:
                            print("WARNING: sound not found:", fullname)

                    sounds[bytes(fn, "latin1")] = sound

        # startup sound
        sound_queue.append(("sound", bytes("ventilagon/audio/es/superventilagon", "latin1")))
    threading.Thread(target=load_sounds, daemon=True).start()

def playsound(name):
    sound_queue.append(("sound", name))

def playnotes(folder, notes):
    sound_queue.append(("notes", folder, notes))

def playmusic(name):
    sound_queue.append(("music", name))

def process_sound_queue():
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
                music_player.pause()
            if name != b"off":
                s = sounds.get(name)
                if s:
                    print("Playing music:", name)
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

