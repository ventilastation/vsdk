cd `dirname "$0"`/../..
. .venv/bin/activate
cd emulator
echo > /tmp/remote-out.log 2>/tmp/remote-err.log
while true; do
	python emu.py SERIAL  --no-display 2>>/tmp/remote-err.log | tee -a /tmp/remote-out.log
done
