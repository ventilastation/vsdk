import re
import json

song = "/home/brian/pycamp/vsdk/apps/vance_songs/(3) 505 - Beethoven Virus/505 - Beethoven Virus.ssc"

def read_song():
    with open(song,"r") as file:
        content = file.read()

    bpms = 0.0
    offset = 0.0
    beats = []
    change_beat = False
    current_beat = []
    lines = []

    for i, line in enumerate(content.splitlines()):
        if i+1 == 23:
            # #BPMS:0.000=162.000;
            bpms = line.split("=")[1][:-1]
        elif i+1 == 16:
            # #OFFSET:-0.175500;
            offset = line.split(":")[1][:-1]
        #NOTES:
        lines.append(line)
        if i+1 > 747:
            break

    full_text = "".join(content)

    start = "#NOTES:\n"
    end = """

//---------------pump-single - s2 Hidden----------------"""

    full_text = full_text[full_text.find(start) + len(start) : full_text.find(end)]

    res = re.split(r',? ?// measure \d+\n', full_text)
    final_beats = []
    for beat in res:
        final_beats.append(beat.split("\n")[:-1])

    final_beats = final_beats[1:]

    song_name = song.split("/")[-1].split(".")[0]

    text_to_dump = f"#SONG_NAME={song_name}\n" + f"#BPMS={bpms}\n" + f"#OFFSET={offset}\n"
    for beat in final_beats:
        for note in beat:
            text_to_dump += f"{note}\n"

    with open(f"{song_name}.txt", "w") as file:
        file.write(text_to_dump)

if __name__ == "__main__":
    read_song()