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


def add_bool_arg(parser, yes_arg, default=False, **kwargs):
    dashed = yes_arg.replace('--', '')
    dest = dashed.replace('-', '_')
    parser.add_argument(
        yes_arg, dest=dest, action='store_true', default=default, **kwargs)
    parser.add_argument(
        '--no-' + dashed, dest=dest, action='store_false', **kwargs)

def bytes2AnonArray(bytes_data):
    byte_str = "b\""

    for i in range(len(bytes_data)):
        if i and i % 16 == 0:
            byte_str += "\"\n            b\""
        byte_str += "\\x%02X" % (bytes_data[i], )
    return byte_str + "\""

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
    def __init__(self, port=None, baudrates=None, ascii=False, parities=None, stopbitss=None, verbose=None):
        self.verbose = verbose
        self.ser = None

        self.port = port
        if self.port is None:
            self.port = default_port()
            if self.port is None:
                raise Exception("Failed to find a serial port")
        if verbose is None:
            verbose = os.getenv("VERBOSE", "N") == "Y"
        self.verbose and print("port: %s" % self.port)
        self.ser = None
        self.rtsctss = [False]
        self.dsrdtrs = [False]
        self.xonxoffs = [False]
        self.ascii = ascii
        self.ascii_newlines = ["\r", "\n", "\r\n"]

        self.baudrates = [9600, 19200, 38400, 115200]
        self.parities = [
                    serial.PARITY_NONE, serial.PARITY_EVEN, serial.PARITY_ODD,
                    serial.PARITY_MARK, serial.PARITY_SPACE
                ]
        self.stopbitss = [
                    serial.STOPBITS_ONE, serial.STOPBITS_ONE_POINT_FIVE,
                    serial.STOPBITS_TWO
                ]

        if baudrates is not None:
            self.baudrates = baudrates
        if ascii is not None:
            self.ascii = ascii
        if parities is not None:
            self.parities = parities
        if stopbitss is not None:
            self.stopbitss = stopbitss

    def flushInput(self, timeout=0.1, max_size=1024):
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

    def mkser(self,
              baudrate=None,
              bytesize=serial.EIGHTBITS,
              parity=serial.PARITY_NONE,
              stopbits=serial.STOPBITS_ONE,
              rtscts=False,
              dsrdtr=False,
              xonxoff=False):
        if self.ser:
            self.ser.close()
            self.ser = None
        self.ser = serial.Serial(self.port,
                                 baudrate=baudrate,
                                 bytesize=bytesize,
                                 parity=parity,
                                 stopbits=stopbits,
                                 rtscts=rtscts,
                                 dsrdtr=dsrdtr,
                                 xonxoff=xonxoff,
                                 timeout=0.01,
                                 writeTimeout=0)

        self.flushInput()


    def get_tx(self, chunk_size):
        def rand_ascii(n):
            return ''.join(
                random.choice(string.ascii_uppercase + string.digits)
                for _ in range(n))

        if self.ascii:
            if self.ascii_newlines:
                newline = random.choice(self.ascii_newlines)
                ret = rand_ascii(chunk_size - len(newline)) + newline
            else:
                ret = rand_ascii(chunk_size)
            return tobytes(ret)
        else:
            return bytearray(
                [random.randint(0, 255) for _i in range(chunk_size)])

    def txrx(self, tx, verbose=False):
        self.ser.write(tx)
        # print("flushing")
        # 1) this takes a long time
        # 2) takes a long time after a few passes
        # implies poor implementation not actually flushing :(
        self.verbose and print("flush tx")
        self.ser.flush()
        self.verbose and print("flush rx")
        rx = self.flushInput()
        if verbose:
            hexdump(tx, label="tx %u" % len(tx))
            hexdump(rx, label="rx %u" % len(rx))
            # print("# rx = %s" % bytes2AnonArray(rx))
            # print("sf.txrx(%s)" % bytes2AnonArray(tx))
        return rx

    def ser_init(self):
        baudrate = random.choice(self.baudrates)
        parity = random.choice(self.parities)
        stopbits = random.choice(self.stopbitss)
        print("")
        print("baudrate=%s, parity=%s, stopbits=%s" %
              (baudrate, parity, stopbits))
        self.mkser(baudrate=baudrate, parity=parity, stopbits=stopbits,
             rtscts=random.choice(self.rtsctss),
             dsrdtr=random.choice(self.dsrdtrs),
             xonxoff=random.choice(self.xonxoffs))

    def loop_begin(self):
        pass

    def run(self):
        print("Starting")
        print("ASCII: %s" % self.ascii)
        print("Baudrates: %u" % len(self.baudrates))
        print("Parities: %u" % len(self.parities))
        print("Stopbits: %u" % len(self.stopbitss))

        self.itr = 0
        open_interval = 10
        print_interval = 80
        tx_bytes = 0
        rx_bytes = 0
        baudrate = None
        parity = None
        stopbits = None
        while True:
            if self.itr % open_interval == 0:
                self.ser_init()

            if self.itr % print_interval == 0:
                print("")
                print("iter %03u tx bytes: %u, rx bytes %u" %
                      (self.itr, tx_bytes, rx_bytes))
            sys.stdout.write(".")
            sys.stdout.flush()
            self.itr += 1
            self.chunk_size = random.randint(1, 32)
            self.loop_begin()
            tx = self.get_tx(self.chunk_size)
            self.verbose and print("iter %04u, data(%u) = %s" %
                                   (self.itr, len(tx), tx.hex()))
            self.verbose and print("writing")
            rx = self.txrx(tx)
            tx_bytes += len(tx)
            if not len(rx):
                continue
            rx_bytes += len(rx)
            print("")
            print("baudrate=%s, parity=%s, stopbits=%s" %
                  (baudrate, parity, stopbits))
            hexdump(tx, label="tx %u" % len(tx))
            hexdump(rx, label="rx %u" % len(rx))
            print("# rx = %s" % bytes2AnonArray(rx))
            print("sf.txrx(%s)" % bytes2AnonArray(tx))


def main():
    parser = argparse.ArgumentParser(description="Try to figure out an undocumented serial protocol")
    parser.add_argument("--port", default=None, help="Serial port")
    parser.add_argument("--dir", default=None, help="Output dir")
    parser.add_argument("--postfix", default=None, help="")
    parser.add_argument("--baudrate", default=None, type=int, help="Set baudrate")
    parser.add_argument("--aggressive", action="store_true", help="Use less common serial modes")
    add_bool_arg(parser, "--ascii", help="Only send ASCII chars")
    add_bool_arg(parser, "--timedate", default=False, help="Display prefix")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    baudrates = None
    parities = None
    stopbitss = None

    if args.baudrate:
        baudrates = [int(args.baudrate)]

    if args.aggressive:
        parities = [
                    serial.PARITY_NONE, serial.PARITY_EVEN, serial.PARITY_ODD,
                    serial.PARITY_MARK, serial.PARITY_SPACE
                ]
        stopbitss = [
                    serial.STOPBITS_ONE, serial.STOPBITS_ONE_POINT_FIVE,
                    serial.STOPBITS_TWO
                ]

    log_dir = args.dir
    if log_dir is None:
        log_dir = default_date_dir("log", "", args.postfix)
    mkdir_p(log_dir)
    _dt = logwt(log_dir, 'log.txt', shift_d=False, stampout=args.timedate)

    sf = SFuzz(port=args.port,
        ascii=args.ascii,
        baudrates=baudrates,
        parities=parities,
        stopbitss=stopbitss,
        verbose=args.verbose)
    sf.run()


if __name__ == "__main__":
    main()
