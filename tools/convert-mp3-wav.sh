# We found the following error in ArchLinux and we weren't able to install/compile AVBin
# so, we converted all the MP# files into WAV
#
#
# Convert all the sounds from MP3 to WAV using ffmpeg
find apps/sounds/ -iname "*.mp3" | xargs -I '{}' ffmpeg -i '{}' -acodec pcm_s16le -ac 1 -ar 16000 '{}'.wav

# Delete all the MP3 files after convert them
find apps/sounds/ -iname "*.mp3" | xargs -I '{}' rm '{}'
