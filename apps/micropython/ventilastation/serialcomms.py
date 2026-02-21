import machine
from ventilastation.hw_config import serial_rx, serial_tx

uart = machine.UART(2, tx=serial_tx, rx=serial_rx) #, bits=8, parity=1, stop=2)

def receive(bufsize):
    return uart.read(bufsize)

def send(line, data=b""):
    uart.write(line)
    uart.write("\n")
    if data:
        uart.write(data) 
