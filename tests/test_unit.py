from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO
import os
from selectors import DefaultSelector, EVENT_READ
import tty
import unittest
from unittest.mock import Mock, patch

from virtualserialports import VirtualSerialPorts


def mock_open(file, mode='r', *args, **kwargs):
    """Return a BytesIO if binary file requested, else StringIO."""
    if 'b' in mode:
        return BytesIO()
    else:
        return StringIO()


class InstantiateTestCase(unittest.TestCase):
    def test_1_port(self):
        vsp = VirtualSerialPorts(1)
        self.assertEqual(vsp.num_ports, 1)
        self.assertFalse(vsp.loopback)
        self.assertFalse(vsp.debug)

    def test_3_ports(self):
        vsp = VirtualSerialPorts(3)
        self.assertEqual(vsp.num_ports, 3)

    def test_loopback(self):
        vsp = VirtualSerialPorts(1, loopback=True)
        self.assertTrue(vsp.loopback)

    def test_debug(self):
        vsp = VirtualSerialPorts(1, debug=True)
        self.assertTrue(vsp.debug)


@patch('os.ttyname', wraps=lambda fd: f'/fake/{fd}')
@patch('virtualserialports.open', wraps=mock_open)  # Patch `open` builtin.
@patch('os.set_blocking')
@patch('tty.setraw')
@patch('pty.openpty', return_value=(8888, 9999))
class OpenTestCase(unittest.TestCase):
    def test_open_1(self, openpty_mock: Mock, setraw_mock: Mock, 
            set_blocking_mock: Mock, open_mock: Mock, ttyname_mock: Mock):
        vsp = VirtualSerialPorts(1)
        try:
            vsp.open()
            ports = vsp.ports
            self.assertEqual(ports, ['/fake/9999'])
        finally:
            vsp.close()

        openpty_mock.assert_called_once()
        setraw_mock.assert_called_once_with(8888)
        set_blocking_mock.assert_called_once_with(8888, False)
