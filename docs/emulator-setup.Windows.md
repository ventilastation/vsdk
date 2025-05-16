# Setup Ventilastation Emulator under Windows
Tested on Windows 10 - intel 64 bits

## Install system dependencies
* [git](https://git-scm.com/downloads/win)
* [Python > 3.13](https://www.python.org/downloads/) - ⚠️ make sure to check the box "Add python.exe to PATH"

## Clone Ventilastation SDK repository
```
mkdir ventilastation
cd ventilastation
git clone https://github.com/ventilastation/vsdk
cd vsdk
```
## Install Python dependencies
```
pip install -r requirements.txt
pip install pywin32
```

## Start the emulator
```
vs-emu.bat
```
