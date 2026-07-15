cd `dirname "$0"`/../..
cd tools/sounds
make
cd ../..
. .venv/bin/activate
cd emulator
echo > /tmp/remote-out.log 2>/tmp/remote-err.log
while true; do
    python emu.py SERIAL  --no-display --no-ota-server 2>>/tmp/remote-err.log | tee -a /tmp/remote-out.log
done
