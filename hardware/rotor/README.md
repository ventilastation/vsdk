Requirements
============
To build the ESP32 firmware for the rotor in the physical Ventilastation, you'll need:

- micropython sourcecode
- esp32 idf

In this working directory:

- `git clone https://github.com/micropython/micropython`
- `cd micropython; git submodule update --init --recursive`

Compile the `mpy-cross` tool before compiling the esp32 firmware: 
- `cd mpy-cross; make; cd ..`

Steps to install both:
https://github.com/micropython/micropython/blob/master/ports/esp32/README.md

