from concurrent.futures import ThreadPoolExecutor
import io
import os
from selectors import DefaultSelector, EVENT_READ
import signal
import subprocess
import sys
from threading import Timer
import tty
import unittest

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


class TestTimeout(Exception):
    """Exception raised if a test times out."""


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
            with open_port(vsp.ports[0]) as f0, open_port(vsp.ports[1]) as f1, \
                 open_port(vsp.ports[2]) as f2:
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


class VSPCLI:
    """Class for running and interacting with the virtualserialports CLI."""

    def __init__(self, args, interrupt_after=5):
        """:param args: list of arguments to pass to CLI
        :param interrupt_after: seconds to interrupt the program after; acts
                                as a safety net in case reads block etc.
        """

        self.args = args
        self.interrupt_after = interrupt_after
        self._proc = None  # type: subprocess.Popen
        self._timer = None  # type: Timer

    def __enter__(self):
        """Entering context manager; start process."""

        self.start()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Exiting context manager, ensure process is properly terminated."""

        self.shutdown()

    def _cancel_timer(self):
        """Cancel any pending interrupt timer."""

        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def start(self):
        """Start the virtualserialports process."""

        if self._proc is not None:
            raise Exception('process is already running; call shutdown() first')
        
        self._proc = subprocess.Popen(
            # Need -u to force Python not to buffer output - else can't read
            # the ports in timely manner.
            [sys.executable, virtualserialports.__file__] + self.args,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, universal_newlines=True
        )
        self._timer = Timer(self.interrupt_after, self.interrupt)
        self._timer.start()

    def interrupt(self):
        """Send interrupt signal to the process."""

        self._proc.send_signal(signal.SIGINT)
        self._cancel_timer()

    def wait_and_get_result(self):
        """Waits for program to exit, and returns tuple of 
        (statuscode, stdout, stderr).

        To ensure the program does indeed exit, run interrupt_after() first.
        """

        stdout, stderr = self._proc.communicate()
        return self._proc.returncode, stdout, stderr
    
    def stdout_readline(self):
        """Read a line from stdout. To ensure this doesn't block indefinitely,
        run interrupt_after() first.
        """

        return self._proc.stdout.readline()
    
    def shutdown(self):
        """Terminate process. If not dead within 1 second, force kills it."""

        self._proc.terminate()
        self._cancel_timer()
        try:
            self._proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.communicate()
        self._proc = None

class CLITestCase(unittest.TestCase):
    def test_help(self):
        with VSPCLI(['--help']) as cli:
            code, stdout, stderr = cli.wait_and_get_result()
        self.assertIn('usage:', stdout)

    def test_no_ports_specified(self):
        with VSPCLI([], interrupt_after=0.1) as cli:
            code, stdout, stderr = cli.wait_and_get_result()
        self.assertGreater(code, 0)

    def test_ports_written_to_stdout(self):
        with VSPCLI(['2'], interrupt_after=0.1) as cli:
            port_paths = [cli.stdout_readline().strip() for _ in range(2)]
            cli.interrupt()
        self.assertEqual(len(port_paths), 2)
        for path in port_paths:
            self.assertRegex(path, r'^/dev/pts/[0-9]+$')

    def test_2_port_communication(self):
        with VSPCLI(['2'], interrupt_after=1) as cli:
            port1_path = cli.stdout_readline().strip()
            port2_path = cli.stdout_readline().strip()

            print(port1_path, port2_path)

            reader1 = BackgroundReader()
            reader2 = BackgroundReader()

            with open_port(port1_path) as f1, open_port(port2_path) as f2:
                reader1.start(f1)
                reader2.start(f2)
                f1.write(b'hello1')
                f2.write(b'hello2')
                out1 = reader1.wait_result()
                out2 = reader2.wait_result()

            self.assertEqual(out1, b'hello2')
            self.assertEqual(out2, b'hello1')

            cli.interrupt()


    def test_debug(self):
        with VSPCLI(['-l', '-d', '1'], interrupt_after=1) as cli:
            port_path = cli.stdout_readline().strip()
            with open_port(port_path) as f:
                f.write(b'hello')
            cli.interrupt()
            code, stdout, stderr = cli.wait_and_get_result()
            debug_text = stderr.strip()

        self.assertRegex(debug_text, r"^/dev/pts/[0-9]+ b'hello'$")
