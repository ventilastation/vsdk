The Ventilastation base is comprised of a Raspberry Pi, plus a joystick and some dedicated hardware.
The code running on the base gathers joystick movement and button presses, and sends that to the game logic in the rotating cpu.
The cpu sends back requests for music and sounds to be played by the base.

Suspect the serial link between the base and the rotor (lost sounds, phantom
button presses, garbage in the log)? Measure it with the Serial Stress app and
`tools/serial_stress.py`: see docs/internals/serial-stress-test.md.
