# Setup Ventilastation Emulator under macOS
Tested on a Macbook Air M1 - macOS Sonoma 14.5 

## Install system dependencies

1. Install homebrew:
```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
2. Setup shell for homebrew:
```
echo >> $HOME/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> $HOME/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```
3. Install python plus micropython:
```
brew install python3 micropython
```

## Install Ventilastation Emulator
4. Clone Ventilastation sdk repository:
```
git clone https://github.com/ventilastation/vsdk
```
5. Enter cloned repo:
```
cd vsdk
```
6. Install python dependencies in a virtual environment
```
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
``` 
7. Start the emulator.
```
./vs-emu.sh
```
