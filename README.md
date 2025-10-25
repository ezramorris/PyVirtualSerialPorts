# PyVirtualSerialPorts

A Python implementation of virtual serial ports. Useful for developing and 
testing programs which need to talk to a serial port.

You can:

* Create a virtual port which echoes back any data sent to it:
  [![Demo showing characters being entered into a terminal emulator being echoed back](https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/images/demo_1_loopback.gif?raw=true)](https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/images/demo_1_loopback.gif?raw=true)

* Create a two or more ports; sending data to one sends data to the others:
  [![Demo showing characters being sent alternately into two terminal emulators, with the characters appearing on the opposite terminal.](https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/images/demo_2.gif?raw=true)](https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/images/demo_2.gif?raw=true)

* Monitor what is being sent between the ports:
  [![Demo showing characters being sent alternately in two terminal emulators, with the characters appearing on both terminals, and debug data showing in the pyvirtualserialports output.](https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/images/demo_2_loopback_debug.gif?raw=true)](https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/images/demo_2_loopback_debug.gif?raw=true)

It should work on Python 3.5+, however is only tested on supported
[Python versions].

Has no dependencies other than the Python standard library.

Currently works on *nix type systems. Tested on Ubuntu and MacOS, but should 
work on others e.g. BSD. Windows support is being worked on.

## Installation

### Install for current user

    $ pip3 install PyVirtualSerialPorts

### Install system-wide

    $ sudo pip3 install PyVirtualSerialPorts

## Running

If the script install folder is in your `PATH` (almost certainly the case if
installed as root), you can simply run:

    $ virtualserialports ...

Otherwise, you can use it as a module:

    $ python3 -m virtualserialports ...

## Usage

    usage: virtualserialports [-h] [-l] [-d] num_ports
    
    positional arguments:
      num_ports       number of ports to create
    
    optional arguments:
      -h, --help      show this help message and exit
      -l, --loopback  echo data back to the sending device too
      -d, --debug     log received data to stderr

## Examples

### Create a single port, and echo back anything sent to it

    $ virtualserialports -l 1

The created port will be printed on the command line e.g. `/dev/pts/0`, and can 
be used with any serial program, e.g. minicom:

    $ minicom -D /dev/pts/0

### Create a pair of ports, sending the data between them

    $ virtualserialports 2

The two created ports will be printed, and again can be used with any serial
program. E.g. in one terminal window:

    $ minicom -D /dev/pts/0

and in a second:

    $ minicom -D /dev/pts/1

Now typing data on one terminal will appear in the other.

### Create three ports, sending data received from any of them to all three

    $ virtualserialports -l 3

## Use as a library

As of version 2.0.0, much improved support has been added for use as a library,
with processing done in the background.

It is recommended to use as a context manager, which will handle setup and
clean up nicely:

```python
with VirtualSerialPorts(2) as ports:
    print(f'Port 1: {ports[0]}')
    print(f'Port 2: {ports[1]}')

    # Open and use ports as required.
    # When the context manager ends, ports will be removed.
```

`ports` is a list of strings, which can be used to open the ports, e.g with
PySerial. A complete example is in [example.py](example.py).

It can also be used without a context manager as follows:

```python
vsp = VirtualSerialPorts(2)
vsp.open()
# `vsp.ports` is a list of strings of the created ports.

vsp.start()
# Use ports as you wish here.
vsp.stop()
vsp.close()
```


[Python versions]: https://devguide.python.org/versions/