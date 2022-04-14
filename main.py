#!/usr/bin/env python3

import argparse
import serial
import os
import time
import platform
import random
import glob
import sys
import string
import shutil
import datetime
import errno


class Timeout(Exception):
    pass


# Print timestamps in front of all output messages
class IOTimestamp(object):
    def __init__(self, obj=sys, name='stdout'):
        self.obj = obj
        self.name = name

        self.fd = obj.__dict__[name]
        obj.__dict__[name] = self
        self.nl = True

    def __del__(self):
        if self.obj:
            self.obj.__dict__[self.name] = self.fd

    def flush(self):
        self.fd.flush()

    def write(self, data):
        parts = data.split('\n')
        for i, part in enumerate(parts):
            if i != 0:
                self.fd.write('\n')
            # If last bit of text is just an empty line don't append date until text is actually written
            if i == len(parts) - 1 and len(part) == 0:
                break
            if self.nl:
                self.fd.write('%s: ' % datetime.datetime.utcnow().isoformat())
            self.fd.write(part)
            # Newline results in n + 1 list elements
            # The last element has no newline
            self.nl = i != (len(parts) - 1)


# Log file descriptor to file
class IOLog(object):
    def __init__(self,
                 obj=sys,
                 name='stdout',
                 out_fn=None,
                 out_fd=None,
                 mode='a',
                 shift=False,
                 multi=False):
        if not multi:
            if out_fd:
                self.out_fd = out_fd
            else:
                self.out_fd = open(out_fn, 'w')
        else:
            # instead of jamming logs together, shift last to log.txt.1, etc
            if shift and os.path.exists(out_fn):
                i = 0
                while True:
                    dst = out_fn + '.' + str(i)
                    if os.path.exists(dst):
                        i += 1
                        continue
                    shutil.move(out_fn, dst)
                    break

            hdr = mode == 'a' and os.path.exists(out_fn)
            self.out_fd = open(out_fn, mode)
            if hdr:
                self.out_fd.write('*' * 80 + '\n')
                self.out_fd.write('*' * 80 + '\n')
                self.out_fd.write('*' * 80 + '\n')
                self.out_fd.write('Log rolled over\n')

        self.obj = obj
        self.name = name

        self.fd = obj.__dict__[name]
        obj.__dict__[name] = self
        self.nl = True

    def __del__(self):
        if self.obj:
            self.obj.__dict__[self.name] = self.fd

    def flush(self):
        self.fd.flush()

    def write(self, data):
        self.fd.write(data)
        self.out_fd.write(data)


def try_shift_dir(d):
    if not os.path.exists(d):
        return
    i = 0
    while True:
        dst = d + '.' + str(i)
        if os.path.exists(dst):
            i += 1
            continue
        shutil.move(d, dst)
        break


def logwt(d, fn, shift_d=True, shift_f=False, stampout=True):
    '''Log with timestamping'''

    if shift_d:
        try_shift_dir(d)
        os.mkdir(d)

    fn_can = os.path.join(d, fn)
    outlog = IOLog(obj=sys, name='stdout', out_fn=fn_can, shift=shift_f)
    errlog = IOLog(obj=sys, name='stderr', out_fd=outlog.out_fd)

    # Add stamps after so that they appear in output logs
    outdate = None
    errdate = None
    if stampout:
        outdate = IOTimestamp(sys, 'stdout')
        errdate = IOTimestamp(sys, 'stderr')

    return (outlog, errlog, outdate, errdate)


def default_port():
    '''Try to guess the serial port, if we can find a reasonable guess'''
    if platform.system() == "Linux":
        serials = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if len(serials) == 0:
            raise Exception("Could not detect any serial ports")
        elif len(serials) == 1:
            return serials[0]
        else:
            raise Exception("Multiple serial ports, please specify which")
    else:
        return None


def tobytes(buff):
    if type(buff) is str:
        #return bytearray(buff, 'ascii')
        return bytearray([ord(c) for c in buff])
    elif type(buff) is bytearray or type(buff) is bytes:
        return buff
    else:
        assert 0, type(buff)


def tostr(buff):
    if type(buff) is str:
        return buff
    elif type(buff) is bytearray or type(buff) is bytes:
        return ''.join([chr(b) for b in buff])
    else:
        assert 0, type(buff)


def default_date_dir(root, prefix, postfix):
    datestr = datetime.datetime.now().isoformat()[0:10]

    if prefix:
        prefix = prefix + '_'
    else:
        prefix = ''

    n = 1
    while True:
        fn = os.path.join(root, '%s%s_%02u' % (prefix, datestr, n))
        if len(glob.glob(fn + '*')) == 0:
            if postfix:
                return fn + '_' + postfix
            else:
                return fn
        n += 1


def hexdump(data, label=None, indent='', address_width=8, f=sys.stdout):
    def isprint(c):
        return c >= ' ' and c <= '~'

    if label:
        print(label)

    bytes_per_half_row = 8
    bytes_per_row = 16
    data = bytearray(data)
    data_len = len(data)

    def hexdump_half_row(start):
        left = max(data_len - start, 0)

        real_data = min(bytes_per_half_row, left)

        f.write(''.join('%02X ' % c for c in data[start:start + real_data]))
        f.write(''.join('   ' * (bytes_per_half_row - real_data)))
        f.write(' ')

        return start + bytes_per_half_row

    pos = 0
    while pos < data_len:
        row_start = pos
        f.write(indent)
        if address_width:
            f.write(('%%0%dX  ' % address_width) % pos)
        pos = hexdump_half_row(pos)
        pos = hexdump_half_row(pos)
        f.write("|")
        # Char view
        left = data_len - row_start
        real_data = min(bytes_per_row, left)

        f.write(''.join([
            c if isprint(c) else '.'
            for c in tostr(data[row_start:row_start + real_data])
        ]))
        f.write((" " * (bytes_per_row - real_data)) + "|\n")


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


class SFuzz:
    def __init__(self, port=None, verbose=None):
        self.verbose = verbose

        self.port = port
        if self.port is None:
            self.port = default_port()
            if self.port is None:
                raise Exception("Failed to find a serial port")
        if verbose is None:
            verbose = os.getenv("VERBOSE", "N") == "Y"
        self.verbose and print("port: %s" % self.port)
        self.ser = None
        self.ascii = False
        # \r\n
        self.ascii_crnl = False
        self.ascii_newline = True

    def flushInput(self, timeout=0.1, max_size=16):
        # Try to get rid of previous command in progress, if any
        tlast = time.time()
        ret = bytearray()
        while time.time() - tlast < timeout and len(ret) < max_size:
            buf = self.ser.read(max_size)
            if buf:
                ret += buf
                tlast = time.time()
        return ret

    def readline(self, timeout=3.0):
        ret = ""
        tstart = time.time()
        while True:
            if time.time() - tstart > timeout:
                raise Timeout()
            c = self.e.read_nonblocking()
            if not c:
                continue
            if c == '\n':
                return ret
            tstart = time.time()
            ret += c

    def mkser(self, baudrate):
        self.ser = serial.Serial(self.port,
                                 timeout=0.01,
                                 baudrate=baudrate,
                                 writeTimeout=0)
        self.flushInput()

    def get_tx(self, chunk_size):
        def rand_ascii(n):
            return ''.join(
                random.choice(string.ascii_uppercase + string.digits)
                for _ in range(n))

        if self.ascii:
            if self.ascii_newline:
                newline = random.choice(["\r", "\n", "\r\n"])
            elif self.ascii_crnl:
                newline = "\r\n"
            if newline:
                ret = rand_ascii(chunk_size - len(newline)) + newline
            else:
                ret = rand_ascii(chunk_size)
            return tobytes(ret)
        else:
            return bytearray(
                [random.randint(0, 255) for _i in range(chunk_size)])

    def run(self):
        baudrate = 115200
        print("Starting")
        print("baudrate: %s" % baudrate)
        print("ASCII: %s" % self.ascii)
        self.mkser(baudrate)

        itr = 0
        print_interval = 80
        tx_bytes = 0
        rx_bytes = 0
        while True:
            if itr % print_interval == 0:
                print("")
                print("iter %03u tx bytes: %u, rx bytes %u" %
                      (itr, tx_bytes, rx_bytes))
            sys.stdout.write(".")
            sys.stdout.flush()
            itr += 1
            chunk_size = random.randint(1, 16)
            chunk_size = 128
            tx = self.get_tx(chunk_size)
            self.verbose and print("iter %04u, data(%u) = %s" %
                                   (itr, len(tx), tx.hex()))
            self.verbose and print("writing")
            self.ser.write(tx)
            tx_bytes += len(tx)
            # print("flushing")
            # 1) this takes a long time
            # 2) takes a long time after a few passes
            # implies poor implementation not actually flushing :(
            self.verbose and print("flush tx")
            self.ser.flush()
            self.verbose and print("flush rx")
            rx = self.flushInput()
            if not rx:
                continue
            rx_bytes += len(rx)
            print("")
            rx = bytearray()
            hexdump(tx, label="tx")
            hexdump(rx, label="rx")


def run(port=None, verbose=False, log_dir="log"):
    sf = SFuzz(port=port, verbose=verbose)
    sf.run()


def main():
    parser = argparse.ArgumentParser(description='Decode')
    parser.add_argument('--port', default=None, help='Serial port')
    parser.add_argument('--dir', default=None, help='Output dir')
    parser.add_argument('--postfix', default=None, help='')
    parser.add_argument('--verbose', action="store_true")
    args = parser.parse_args()

    log_dir = args.dir
    if log_dir is None:
        log_dir = default_date_dir("log", "", args.postfix)
    mkdir_p(log_dir)
    _dt = logwt(log_dir, 'log.txt', shift_d=False)

    run(port=args.port, verbose=args.verbose)


if __name__ == "__main__":
    main()
