from concurrent.futures import ThreadPoolExecutor
import io
from multiprocessing import Process
import os
from selectors import DefaultSelector, EVENT_READ
from time import sleep
import tty
import unittest
from unittest.mock import Mock, patch

import virtualserialports
from virtualserialports import VirtualSerialPorts, VirtualSerialPortException


# Most people would use PySerial to communicate with the ports, however this
# module does not depend on any external dependencies, and it would be
# annoying to have to introduce one just for the tests. As such, the following
# functions provide similar functionality as PySerial.

def open_port(filename):
    f = open(filename, 'r+b', buffering=0)
    fd = f.fileno()
    tty.setraw(fd)
    os.set_blocking(fd, False)
    return f


def read_with_timeout(f, timeout=1):
    with DefaultSelector() as selector:
        selector.register(f, EVENT_READ)
        for key, event in selector.select(timeout):
            if key.fileobj == f and event & EVENT_READ:
                return f.read()

    # If we get here, no data was read after the timeout.
    return None


class BackgroundReader:
    """Allows reading of the port in the background, otherwise the write would
    block. Timeout is used so if something goes wrong, the tests don't hang.
    """
    def __init__(self):
        self._ex = ThreadPoolExecutor(max_workers=1)
        self.future = None

    def start(self, f):
        self.future = self._ex.submit(read_with_timeout, f)

    def wait_result(self):
        if self.future is None:
            raise Exception('BackgroundReader: tried to wait for a result '
                            'before started')
        result = self.future.result()
        self.future = None
        return result


class InitTestCase(unittest.TestCase):
    def test_init_0_ports(self):
        with self.assertRaises(VirtualSerialPortException):
            VirtualSerialPorts(0)

    def test_init_1_port(self):
        vsp = VirtualSerialPorts(1)
        self.assertEqual(vsp.num_ports, 1)
        self.assertFalse(vsp.loopback)
        self.assertFalse(vsp.debug)
        self.assertFalse(vsp.running)

    def test_init_1_port_with_loopback(self):
        vsp = VirtualSerialPorts(1, loopback=True)
        self.assertTrue(vsp.loopback)

    def test_init_1_port_with_debug(self):
        vsp = VirtualSerialPorts(1, debug=True)
        self.assertTrue(vsp.debug)


class OpenTestCase(unittest.TestCase):
    def test_open_2_ports(self):
        vsp = VirtualSerialPorts(2)
        try:
            vsp.open()
            self.assertEqual(len(vsp.ports), 2)

            # Check each ports can be opened and is a binary file object.
            for p in vsp.ports:
                with open_port(p) as f:
                    self.assertIsInstance(f, io.RawIOBase)
        finally:
            vsp.close()


class CloseTestCase(unittest.TestCase):
    def test_ports_not_open(self):
        vsp = VirtualSerialPorts(3)
        vsp.close()
        with self.assertRaises(VirtualSerialPortException):
            vsp.ports

    def test_closing_open_ports(self):
        vsp = VirtualSerialPorts(3)
        vsp.open()
        vsp.close()
        with self.assertRaises(VirtualSerialPortException):
            vsp.ports


class BackgroundProcessingTestCase(unittest.TestCase):
    def test_1_port_loopback(self):
        reader = BackgroundReader()
        vsp = VirtualSerialPorts(1, loopback=True)
        try:
            vsp.open()
            vsp.start()
            self.assertEqual(len(vsp.ports), 1)
            with open_port(vsp.ports[0]) as f:
                reader.start(f)
                f.write(b'foo')
                self.assertEqual(reader.wait_result(), b'foo')
        finally:
            vsp.stop()
            vsp.close()

    def test_3_ports(self):
        reader1 = BackgroundReader()
        reader2 = BackgroundReader()
        vsp = VirtualSerialPorts(3)
        try:
            vsp.open()
            vsp.start()
            self.assertEqual(len(vsp.ports), 3)
            with (open_port(vsp.ports[0]) as f0, open_port(vsp.ports[1]) as f1,
                  open_port(vsp.ports[2]) as f2):
                reader1.start(f1)
                reader2.start(f2)
                f0.write(b'foo')
                self.assertEqual(reader1.wait_result(), b'foo')
                self.assertEqual(reader2.wait_result(), b'foo')
        finally:
            vsp.stop()
            vsp.close()


class ContextManagerTestCase(unittest.TestCase):
    def test_context_manager(self):
        vsp = VirtualSerialPorts(1)

        # Check VSP context manager opens ports and starts processing.
        with vsp as ports:
            self.assertEqual(len(ports), 1)
            self.assertTrue(vsp.running)

        # Check ports are closed and stopped running after context manager.
        self.assertFalse(vsp.running)
        with self.assertRaises(VirtualSerialPortException):
            vsp.ports


class MainTestCase(unittest.TestCase):
    def test_no_ports_specified(self):
        with self.assertRaises(SystemExit):
            virtualserialports.main([])

    # TODO: fix tests
    # def test_1_port_loopback(self):
    #     with patch('sys.stdout', new_callable=io.StringIO) as stdout_mock:
    #         p = Process(target=virtualserialports.main, args=(['-l', '1'],))
    #         try:
    #             p.start()
    #             sleep(1)
    #             self.assertEqual(stdout_mock.getvalue(), 'foo')
    #         finally:
    #             p.terminate()
    #             p.join(1)
