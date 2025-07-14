# Setup Ventilastation Emulator under Linux
Tested on Ubuntu 24.04 x86_64

## Install system dependencies
```
sudo apt install git micropython python3.12-venv ffmpeg
```
## Clone Ventilastation SDK repository
```
mkdir ~/ventilastation; cd ~/ventilastation
git clone https://github.com/ventilastation/vsdk
cd vsdk
```
## Install python dependencies in a virtual environment
```
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Start the emulator
```
./vs-emu.sh
```
