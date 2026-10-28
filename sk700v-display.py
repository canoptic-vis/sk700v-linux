#!/usr/bin/env python3
"""Feed live CPU stats to the Sudokoo SK700V cooler LCD (USB 381c:0003).

Protocol (reverse-engineered from MasterCraft 1.0.5):
  hidraw write, report 0x10:  68 01 09 LEN PAYLOAD SUM 16   (SUM = low byte of sum from 0x68)
  03 01                                  screen on / keep-alive
  01 02 PWR(u16) 0a 00 TEMP(f32) LOAD(u8) FREQ(u16 MHz)   all big-endian
"""
import glob, os, struct, sys, time

INTERVAL = 1.0
HID_ID = 'HID_ID=0003:0000381C:00000003'


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def find_hidraw():
    for d in glob.glob('/sys/class/hidraw/hidraw*'):
        try:
            if HID_ID in open(f'{d}/device/uevent').read():
                return '/dev/' + os.path.basename(d)
        except OSError:
            pass
    return None


def frame(payload):
    body = bytes([0x68, 0x01, 0x09, len(payload)]) + payload
    return (bytes([0x10]) + body + bytes([sum(body) & 0xff, 0x16])).ljust(64, b'\0')


def data_payload(power_w, temp_c, load_pct, freq_mhz):
    return (bytes([0x01, 0x02]) + min(int(round(power_w)), 0xffff).to_bytes(2, 'big')
            + bytes([0x0a, 0x00]) + struct.pack('>f', temp_c)
            + bytes([max(0, min(int(round(load_pct)), 100))])
            + min(int(round(freq_mhz)), 0xffff).to_bytes(2, 'big'))


def read_int(path):
    with open(path) as f:
        return int(f.read())


class Sensors:
    def __init__(self):
        self.temp_path = self._find_tctl()
        self.rapl = '/sys/class/powercap/intel-rapl:0'
        try:
            self.rapl_max = read_int(f'{self.rapl}/max_energy_range_uj')
            self.last_energy = (read_int(f'{self.rapl}/energy_uj'), time.monotonic())
        except OSError as e:
            log(f'RAPL power unavailable ({e}); power will read 0')
            self.rapl = None
        self.last_stat = self._cpu_times()
        self.freq_paths = glob.glob('/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq')

    @staticmethod
    def _find_tctl():
        for h in glob.glob('/sys/class/hwmon/hwmon*'):
            try:
                if open(f'{h}/name').read().strip() == 'k10temp':
                    return f'{h}/temp1_input'  # Tctl
            except OSError:
                pass
        log('k10temp not found; temperature will read 0')
        return None

    @staticmethod
    def _cpu_times():
        with open('/proc/stat') as f:
            v = [int(x) for x in f.readline().split()[1:]]
        idle = v[3] + v[4]  # idle + iowait
        return sum(v), idle

    def temp(self):
        return read_int(self.temp_path) / 1000 if self.temp_path else 0.0

    def load(self):
        total, idle = self._cpu_times()
        dt, di = total - self.last_stat[0], idle - self.last_stat[1]
        self.last_stat = (total, idle)
        return 100 * (dt - di) / dt if dt > 0 else 0.0

    def freq(self):
        khz = [read_int(p) for p in self.freq_paths]
        return max(khz) / 1000 if khz else 0.0

    def power(self):
        if not self.rapl:
            return 0.0
        e, t = read_int(f'{self.rapl}/energy_uj'), time.monotonic()
        e0, t0 = self.last_energy
        self.last_energy = (e, t)
        de = e - e0 if e >= e0 else e + self.rapl_max - e0
        return de / 1e6 / (t - t0) if t > t0 else 0.0


def main():
    sensors = Sensors()
    fd = None
    while True:
        time.sleep(INTERVAL)
        if fd is None:
            dev = find_hidraw()
            if not dev:
                continue
            try:
                fd = os.open(dev, os.O_WRONLY)
                log(f'opened {dev}')
            except OSError as e:
                log(f'cannot open {dev}: {e}')
                continue
        try:
            payload = data_payload(sensors.power(), sensors.temp(), sensors.load(), sensors.freq())
            os.write(fd, frame(bytes([0x03, 0x01])))
            os.write(fd, frame(payload))
        except OSError as e:
            log(f'write failed ({e}); reopening')
            os.close(fd)
            fd = None


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
