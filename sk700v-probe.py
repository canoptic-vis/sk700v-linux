#!/usr/bin/env python3
# SK700V probe tool: send hand-built frames. Each arg is one frame:
#   on                      -> payload 03 01
#   test0 / test1           -> 01 01 + 12 bytes (segment test off/on)
#   data:P,L,F,T            -> 01 02 | power u16 | 0a 00 (bar 10%, °C) | temp f32 BE | load u8 | freq MHz u16  (13 bytes)
#   raw:<hex>               -> arbitrary payload
import glob, os, struct, sys

def find_dev():
    for d in glob.glob('/sys/class/hidraw/hidraw*'):
        if 'HID_ID=0003:0000381C:00000003' in open(f'{d}/device/uevent').read():
            return '/dev/' + os.path.basename(d)
    sys.exit('SK700V not found')

def frame(payload):
    body = bytes([0x68, 0x01, 0x09, len(payload)]) + payload
    pkt = bytes([0x10]) + body + bytes([sum(body) & 0xff, 0x16])
    return pkt.ljust(64, b'\0')

def payload(arg):
    if arg == 'on':
        return bytes([0x03, 0x01])
    if arg in ('test0', 'test1'):
        return bytes([0x01, 0x01, int(arg[-1])]) + bytes(11)
    if arg.startswith('data:'):
        power, load, freq, temp = (float(x) for x in arg[5:].split(','))
        p = (bytes([0x01, 0x02]) + int(power).to_bytes(2, 'big') + bytes([0x0a, 0x00])
             + struct.pack('>f', temp) + bytes([int(load)]) + int(freq).to_bytes(2, 'big'))
        assert len(p) == 13
        return p
    if arg.startswith('raw:'):
        return bytes.fromhex(arg[4:])
    sys.exit(f'bad frame spec: {arg}')

frames = [frame(payload(a)) for a in sys.argv[1:]]  # validate all before sending any
fd = os.open(find_dev(), os.O_RDWR)
for p in frames:
    os.write(fd, p)
    print('sent', p.rstrip(b'\0').hex(' '))
