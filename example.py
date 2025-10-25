#!/bin/env python3

'''Example of using VirtualSerialPorts as a library.

Requires PySerial to be installed:
    pip install pyserial
'''

from virtualserialports import VirtualSerialPorts
from serial import Serial

def main():
    with VirtualSerialPorts(2) as ports:
        print(f'Port 1: {ports[0]}')
        print(f'Port 2: {ports[1]}')

        with Serial(ports[0], timeout=1) as s1, Serial(ports[1], timeout=1) as s2:
            message = b'Hello, Virtual Serial Ports!'
            print(f'Sending from Port 1 to Port 2: {message}')
            s1.write(message)

            response = s2.read(len(message))
            print(f'Received on Port 2: {response}')

if __name__ == '__main__':
    main()