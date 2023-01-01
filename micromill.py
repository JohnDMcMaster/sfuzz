#!/usr/bin/env python3

"""
^C makes a clicking noise
helps validate 9600 baud theory
"""

import argparse
import serial
import random
import string

from main import default_date_dir, mkdir_p, logwt, SFuzz, tobytes


class MyFuzz(SFuzz):
    def __init__(self, *args, **kwargs):
        SFuzz.__init__(self, *args, **kwargs)
        self.rtsctss = [True]
    
    def loop_begin(self):
        # reset state before every test
        # if self.itr % 16 == 0:
        #    self.txrx(b"\x03")
        # self.chunk_size = 3

        self.chunk_size = random.randint(1, 6)


    def get_tx(self, chunk_size):
        def rand_ascii(n):
            return ''.join(
                random.choice(string.ascii_uppercase + string.digits)
                for _ in range(n))

        if self.ascii:
            prefix = ""
            postfix = ""
            # if self.ascii_newlines:
            #    postfix = random.choice(self.ascii_newlines)
            if random.randint(0, 8) == 0:
                prefix = random.choice(["\x03", "\x1B", "\n", "X", "*", ";"])
            if random.randint(0, 8) == 0:
                postfix = random.choice(["\x03", "\x1B", "\n", "X", "*", ";"])
            if 1 or random.randint(0, 2) == 0:
                ret = "VN"
                if random.randint(0, 1):
                    ret = rand_ascii(1) + ret
                if random.randint(0, 1):
                    ret = ret + rand_ascii(1)
            else:
                ret = rand_ascii(chunk_size - len(prefix) - len(postfix))
            return tobytes(prefix + ret + postfix)
        else:
            # FIXME: hack
            while True:
                ret = bytearray(
                    [random.randint(0, 127) for _i in range(chunk_size)])
                # ^C
                if 0x03 in ret or 0x83 in ret:
                    # print("regen")
                    continue
                # ^[
                if 0x1B in ret or 0x9B in ret:
                    continue
                if ord("*") in ret or ord("X") in ret or ord("Y") in ret or ord("Z") in ret:
                    continue
                return ret

            return bytearray(
                [random.randint(0, 255) for _i in range(chunk_size)])

def main():
    parser = argparse.ArgumentParser(description="Try to figure out an undocumented serial protocol")
    parser.add_argument("--port", default=None, help="Serial port")
    parser.add_argument("--dir", default=None, help="Output dir")
    parser.add_argument("--postfix", default="micromill", help="")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("mode", nargs="?", default="fuzz")
    args = parser.parse_args()

    # baudrates = [9600, 19200, 38400, 115200]
    # rx all 0s
    # baudrates = [115200]
    # some suspicous echos back
    # baudrates = [9600]
    # like corrupted values back
    # baudrates = [19200]
    # like corrupted values back
    # baudrates = [38400]

    # ascii = False
    # pretty sure this is right
    # baudrates = [9600]

    # parities = [serial.PARITY_NONE]
    # stopbitss = [serial.STOPBITS_ONE]

    log_dir = args.dir
    if log_dir is None:
        log_dir = default_date_dir("log", "", args.postfix)
    mkdir_p(log_dir)
    _dt = logwt(log_dir, 'log.txt', shift_d=False, stampout=False)

    sf = MyFuzz(port=args.port,
        ascii=True,
        baudrates=[9600],
        parities=[serial.PARITY_NONE],
        stopbitss=[serial.STOPBITS_ONE],
        verbose=args.verbose)
    if args.mode == "fuzz":
        sf.run()
    else:
        """
        2023-01-01T03:48:36.001672: tx 5
        00000000  09 7D 97 1A 48                                    |.}..H           |
        2023-01-01T03:48:36.001717: rx 1
        00000000  09                                                |.               |


        mcmaster@thudpad:~/doc/ext/sfuzz$ ./micromill.py 
        2023-01-01T03:53:12.294229: 
        2023-01-01T03:53:12.294258: baudrate=9600, parity=N, stopbits=1
        2023-01-01T03:53:12.505423: tx 5
        00000000  09 7D 97 1A 48                                    |.}..H           |
        2023-01-01T03:53:12.505668: rx 0

        """
        sf.ser_init()

        # ESC seems to have some special meaning
        if args.mode == "test2":
            print("test2")
            # rx = b"\x5A\x7B\x4A\x18\x4D"
            # sf.txrx(b"\xE9\xBE\x14\xE9\xD7\x54\xA7\x4E\x0D\x40\xB7\xEF\x12\x9B\x5A\x7B"
            #            b"\xCA\x98\xCD", verbose=True)

            # sf.txrx(b"\x03", verbose=True)

            for i in range(5):
                sf.txrx(b"\x1B\x58", verbose=True)
                sf.txrx(b"\x1B\x59", verbose=True)
                sf.txrx(b"\x1B\x5A", verbose=True)

        if args.mode == "test3":
            # rx = b"\x5A\x0D\x44\x61\x07"
            sf.txrx(b"\x77\x0A\x5A\x0D\x44\x61\x07", verbose=True)

        # hmm really interesting returns garbage
        if args.mode == "test4":
            sf.txrx(b"*VN\r", verbose=True)
            sf.txrx(b"*ON\r", verbose=True)
            sf.txrx(b"*OF\r", verbose=True)


        if 0:
            # "^C" => makes click
            sf.txrx(b"\x03", verbose=True)
            # also
            sf.txrx(b"\x83", verbose=True)

        if 0:
            sf.txrx(b"VN", verbose=True)
            sf.txrx(b"VN\r\n", verbose=True)
            sf.txrx(b"VN\r", verbose=True)
            sf.txrx(b"VN\n", verbose=True)
        
        if 0:
            # rx = b"\x54"
            # sf.txrx(b"\x07\xF9\x1C\x12\x47\xE5\xEF\x84\x94\xF9\x5A\x32\x10\x31\x9C", verbose=True)
            # rx = b"\x56"
            # sf.txrx(b"\x83\x61\xA5\x44\x23\x53\x0C\x7D\x25\x5F\x35\xB8\xCF\xE9\xEB", verbose=True)
            sf.txrx(b"\x83", verbose=True)
            pass

        if 0:
            sf.txrx(b"\x09\x7D\x97\x1A\x48", verbose=True)
    
            # # rx = b"\x05"
            sf.txrx(b"\x26\xD7\xE2\xCC\xF6\x66\x34\xDF\xBD\x53\x4F\xDE\x51\xFB\xE0\x3A"
                    b"\xA4\x60\xB0\xBE\xCD\xD8", verbose=True)
    
            # rx = b"\x56"
            sf.txrx(b"\xFA\xEF\x43\x65\xA6\x09\xE6\x2A\xF6\xBD\x12\xCB\xC2\x5C\x75\x80"
                         b"\x39\x9D\xBC\x08\x8F\x50", verbose=True)
    
            # rx = b"\x31"
            sf.txrx(b"\xD1\x43\x4B\x94\x9C\x60\x9F\xE2\xA0\x37\x9C\xA9\xA2\x18\xA4\x17"
                         b"\x68\x85\x11\x62\x0E\xE8", verbose=True)

        if 0:
            print("test 1")
            if 0:
                # rx = b"\x59\x6A"
                sf.txrx(b"\x7E\x54\x53\x6F\x24\x74\xEF\xCF\x5C\xBC\x7D\xB1\x5A\x1B\x59\x6A", verbose=True)

            if 1:
                # rx = b"\x59\x6A"
                sf.txrx(b"\x59", verbose=True)



            if 0:
                # rx = b"\x09\x3F\x42\x31\x02\x79\x6E\x78\x52\x20\x20\x6F\x08\x73\x29\x0B"
                sf.txrx(b"\x89\xBF\x42\x31\x02\x79\xEE\x78\x52\xA0\x20\x6F\x88\x73\x29\x8B", verbose=True)
            
            if 0:
                # rx = b"\x3E\x7D\x0A"
                sf.txrx(b"\x3E\x7D\xC2\xE9\xF9\x39\x1A\xD0\xC5\x49\x2D\x1A\xAD\x6D\x6F\x14", verbose=True)


if __name__ == "__main__":
    main()
