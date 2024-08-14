# Copyright 2021, 2023-2024 Ezra Morris
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import asyncio
import argparse
import os
import pty
from selectors import DefaultSelector as Selector, EVENT_READ
from threading import Thread
import sys
import tty


class VirtualSerialPortException(Exception):
    """Exceptions raised from this module."""


class NotOpenedException(VirtualSerialPortException):
    """Raised when trying to use the port before it is opened."""


class VirtualSerialPorts:
    def __init__(self, num_ports: int, loopback: bool=False, debug: bool=False):
        """Class for managing virtual serial ports.

        :param num_ports: number of ports to create
        :param loopback: whether to echo data back to the sender
        :param debug: whether to print debugging info to stdout

        Can be used as a context manager which will create the ports, start the
        processing, and return the ports on entry; and close and remove the
        ports on exit. For example, using PySerial:

        from serial import Serial
        from virtualserialports import VirtualSerialPorts

        with VirtualSerialPorts(2) as ports:
            print(ports[0])
            print(ports[1])
            with Serial(ports[0]) as s1, Serial(ports[1]) as s2:
                s1.write(b'hello')
                print(s2.read())

        """

        if num_ports <= 0:
            raise VirtualSerialPortException('number of ports must be greater '
                                             'than 0')

        self.num_ports = num_ports
        self.loopback = loopback
        self.debug = debug
        self.running = False

        self._thread = None
        self._master_files = None
        self._slave_names = None

    def __enter__(self):
        self.open()
        self.start()
        return self.ports

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.close()

    def open(self):
        """Configure and open the ports."""

        self.close()
        self._master_files = {}  # Dict of master fd to master file object.
        self._slave_names = {}  # Dict of master fd to slave name.
        for _ in range(self.num_ports):
            master_fd, slave_fd = pty.openpty()

            # Set raw (pass through control characters) and blocking mode on the
            # master. Slaves expected to be configured by the client.
            tty.setraw(master_fd)
            os.set_blocking(master_fd, False)

            # Open the master file descriptor, and store the file object in the
            # dict.
            self._master_files[master_fd] = open(master_fd, 'r+b', buffering=0)

            # Get the os-visible name (e.g. /dev/pts/1) and store in dict.
            self._slave_names[master_fd] = os.ttyname(slave_fd)

    def close(self):
        """Close ports."""

        self.stop()
        if self._master_files is not None:
            for f in self._master_files.values():
                f.close()
        self._master_files = None
        self._slave_names = None

    def process(self):
        """Forward data, until self.running is set to False or the process is
        terminated.
        """

        if self._master_files is None or self._slave_names is None:
            raise NotOpenedException("No ports available.")

        self.running = True

        with Selector() as selector:
            # Add all file descriptors to selector.
            for fd in self._master_files.keys():
                selector.register(fd, EVENT_READ)

            while self.running:
                for key, events in selector.select(timeout=0.1):
                    if not events & EVENT_READ:
                        continue

                    data = self._master_files[key.fileobj].read()
                    if self.debug:
                        print(self._slave_names[key.fileobj], data,
                              file=sys.stderr)
                        sys.stderr.flush()

                    # Write to master files. If loopback is False, don't write
                    # to the sending file.
                    for fd, f in self._master_files.items():
                        if self.loopback or fd != key.fileobj:
                            f.write(data)

    def start(self):
        """Start running in background thread. Stop and restarts if already
        running. Returns list of names of opened ports.
        """

        self.stop()
        self._thread = Thread(target=self.process)
        self._thread.start()

    def stop(self):
        """Stop the background thread if running."""

        self.running = False
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    @property
    def ports(self):
        """List of the created ports."""

        if self._slave_names is None:
            raise NotOpenedException("No ports available.")
        return list(self._slave_names.values())



class AsyncVirtualSerialPort:
    def __init__(self, loopback: bool=False, debug: bool=False):
        """Class for managing a virtual serial port.

        Can be used as a context manager which will create the port, start the
        processing, and return the port on entry; and close and remove the
        port on exit. For example, using PySerial:

        from serial import Serial
        from virtualserialports import AsyncVirtualSerialPort

        with VirtualSerialPort() as port:
            print(port)
            with Serial(port) as s:
                s.write(b'hello')
                print(s.read())
        """

        self.loopback = loopback
        self.debug = debug
        self.running = False

        self._thread = None
        self._main_fd = None
        self._main_file = None
        self.ttyname = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        """Configure and open the ports."""

        self.close()
        self._main_fd, node_fd = pty.openpty()

        # Set raw (pass through control characters) and blocking mode on the
        # master. Nodes expected to be configured by the client.
        tty.setraw(self._main_fd)
        os.set_blocking(self._main_fd, False)

        # Open the main file descriptor, and store the file object in the
        # dict.
        self._main_file = open(self._main_fd, 'r+b', buffering=0)

        # Get the os-visible name (e.g. /dev/pts/1) and store in dict.
        self.ttyname = os.ttyname(node_fd)

    def close(self):
        """Close ports."""
        self.running = False

        if self._main_file is not None:
            self._main_file.close()

        self._main_fd = None
        self._main_file = None
        self.ttyname = None

    @classmethod
    async def run(cls, debug: bool=False, loopback: bool=False):
        """Forward data, until self.running is set to False or the process is
        terminated.
        """

        with cls(debug=debug, loopback=loopback) as port, Selector() as selector:

            if port._main_file is None or port._main_fd is None:
                raise NotOpenedException("No port available.")

            # Flush stdout, in case the ports are being read in a pipe. Else
            # Python will buffer it and block.
            sys.stdout.flush()

            selector.register(port._main_fd, EVENT_READ)

            port.running = True
            while port.running:
                await asyncio.sleep(0)

                for key, events in selector.select(timeout=0):

                    if not events & EVENT_READ:
                        continue

                    data = port._main_file.read()

                    if port.debug:
                        print(port.ttyname, data, file=sys.stderr)
                        sys.stderr.flush()

                    # Write to master files. If loopback is False, don't write
                    # to the sending file.
                    if port.loopback:
                        port._main_file.write(data)

    async def stop(self):
        """Stop the background thread if running."""
        self.running = False


def run(num_ports, loopback=False, debug=False):
    """Creates several virtual serial ports and prints the port names. When
    data is received from one port, sends to all the other ports.

    :param num_ports: number of ports to create
    :param loopback: whether to echo data back to the sender
    :param debug: whether to print debugging info to stdout
    """

    with VirtualSerialPorts(num_ports, loopback, debug) as ports:
        print(*ports, sep='\n')

        # Flush stdout, in case the ports are being read in a pipe. Else
        # Python will buffer it and block.
        sys.stdout.flush()

        # Do nothing until killed.
        # Thread cleanup is handled by the context manager.
        with Selector() as selector:
            selector.select()


def main(args_list=None):
    """Main application execution.

    :param args_list: list of argument strings to interpret; None uses command
                      line args
    """

    parser = argparse.ArgumentParser(
        description='Create a hub of virtual serial ports, which will stay '
        'available until the program is terminated. Once set up, the port names '
        'are printed to stdout, one per line.'
    )
    parser.add_argument('num_ports', type=int,
                        help='number of ports to create')
    parser.add_argument('-l', '--loopback', action='store_true',
                        help='echo data back to the sending device too')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='log received data to stderr')
    args = parser.parse_args(args_list)

    # Catch KeyboardInterrupt so it doesn't print traceback.
    try:
        run(args.num_ports, args.loopback, args.debug)
    except KeyboardInterrupt:
        # Clean line for prompt.
        print()


if __name__ == '__main__':
    main()
