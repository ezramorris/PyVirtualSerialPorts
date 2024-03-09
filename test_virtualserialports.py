from concurrent.futures import ThreadPoolExecutor
import io
import os
from selectors import DefaultSelector, EVENT_READ
import signal
import subprocess
import sys
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


class CLITestCase(unittest.TestCase):
    def _create_vsp_proc(self, args):
        """Create Popen object for running virtualserialports CLI.
        
        :param args: list of arguments to pass to CLI
        :return: Popen object
        """

        proc = subprocess.Popen(
            [sys.executable, virtualserialports.__file__] + args,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, text=True
        )
        return proc

    def _run_vsp(self, args, timeout=0.1):
        """Run virutalserialports CLI.
        
        :param args: list of arguments to pass to CLI
        :param timeout: how long to let it run

        :return: tuple of (statuscode, stdout, stderr); statuscode is None if
                 timeout occurred
        """

        proc = self._create_vsp_proc(args)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            stdout, stderr = self._terminate_proc(proc)
        return proc.returncode, stdout, stderr
    
    def _terminate_proc(self, proc: subprocess.Popen, timeout=1):
        """Terminate a process, and return output. If timeout exceeded, will
        forcefully kill it.
        
        :param proc: Popen object
        :param timeout: time to wait after terminating before killing

        :return: tuple of (stdout, stderr)
        """

        proc.terminate()
        try:
            res = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            res = proc.communicate()

        return res
    
    def setUp(self):
        # There is a risk some of these tests can hang if the process hangs.
        # So this provides a 5s timeout for all tests.

        def _alarm_handler(signum, frame):
            raise TestTimeout('test took over 5s to run so was aborted')
        
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(5)

    def tearDown(self):
        # Clear down alarm signal handling.
        signal.alarm(0)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)

        
    def test_help(self):
        code, stdout, stderr = self._run_vsp(['--help'])
        self.assertIn('usage:', stdout)

    def test_no_ports_specified(self):
        code, stdout, stderr = self._run_vsp([])
        self.assertGreater(code, 0)

    def test_ports_written_to_stdout(self):
        code, stdout, stderr = self._run_vsp(['2'])
        port_paths = stdout.strip().splitlines()
        self.assertEquals(len(port_paths), 2)
        for path in port_paths:
            self.assertRegex(path, r'^/dev/pts/[0-9]+$')

    def test_2_port_communication(self):
        proc = self._create_vsp_proc(['2'])

        try:
            port1_path = proc.stdout.readline().strip()
            port2_path = proc.stdout.readline().strip()
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
        finally:
            self._terminate_proc(proc)


    def test_debug(self):
        proc = self._create_vsp_proc(['-l', '-d', '1'])
        try:
            port_path = proc.stdout.readline().strip()
            with open_port(port_path) as f:
                f.write(b'hello')
            debug_text = proc.stderr.readline().strip()
        finally:
            self._terminate_proc(proc)

        self.assertRegex(debug_text, r"^/dev/pts/[0-9]+ b'hello'$")
