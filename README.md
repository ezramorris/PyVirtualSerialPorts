# PyVirtualSerialPorts

A Python implementation of virtual serial ports. Useful for developing and 
testing programs which need to talk to a serial port.

[![Demo](demo.gif)][demo]

Example uses:

* Create a virtual port which echoes back any data sent to it.
* Create a two or more ports; sending data to one sends data to the others.

Has no dependencies other than the Python standard library.

Only works on *nix type systems. Tested on Debian Linux, but should work on
others (macOS, BSD, etc.). For Windows, look at [com0com] or 
[Virtual Serial Port Driver].

## Installation

### Current user

    $ pip3 install PyVirtualSerialPorts

### System-wide

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

`virtualserialports.run(num_ports, loopback=False, debug=False)`

* *num_ports*: number of ports to create.
* *loopback*: whether to echo data back to the sender.
* *debug*: whether to print debugging info to stdout.

### Example

    import virtualserialports
    virtualserialports.run(2, loopback=True, debug=False)

### Usage within the same process

    import json
    import time
    import serial
    from multiprocessing import Process
    from virtualserialports import VirtualSerial
    
    virtual_serial = VirtualSerial(num_ports=2, loopback=False, debug=False)
    
    ports_dict = virtual_serial.slave_names
    keys = list(ports_dict.keys())
    
    port1 = virtual_serial.slave_names[keys[0]]
    port2 = virtual_serial.slave_names[keys[1]]
    
    cli1 = serial.Serial(port1)
    cli2 = serial.Serial(port2)
    
    virtual_serial = Process(target=virtual_serial.run)
    virtual_serial.start()
    
    cli1.write(data=bytes(json.dumps(dict(hello="world")), "ascii"))
    time.sleep(1)
    print(f"received: {cli2.read_all()}")
    
    virtual_serial.terminate()


[demo]: https://github.com/ezramorris/PyVirtualSerialPorts/blob/main/demo.gif
[com0com]: https://sourceforge.net/projects/com0com/
[Virtual Serial Port Driver]: https://www.virtual-serial-port.org/
