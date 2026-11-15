#!/usr/bin/env python3
"""读板子的串口日志。用 ESP-IDF 环境里的 Python 运行（里面带 pyserial）：

    firmware\\idf-env.cmd python firmware\\serial_log.py                 读 COM12，先复位，读 20 秒
    firmware\\idf-env.cmd python firmware\\serial_log.py --port COM11 --seconds 60 --no-reset

立创实战派有两个串口：CH340（一般是 COM12）是固件的日志口；原生 USB（COM11）用来烧录。
"""
import argparse
import re
import sys
import time

import serial

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM12")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--no-reset", action="store_true", help="不复位板子，只读正在输出的日志")
    args = ap.parse_args()

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, args.baud, 0.2
    ser.dtr = False  # 不拉低 IO0，保证正常启动而不是进下载模式
    ser.rts = False
    ser.open()
    if not args.no_reset:
        ser.rts = True  # 拉低 EN，复位
        time.sleep(0.15)
        ser.rts = False
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8", errors="replace")
    deadline = time.time() + args.seconds
    buf = b""
    while time.time() < deadline:
        buf += ser.read(4096)
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            out.write(ANSI.sub("", line.decode("utf-8", errors="replace")).rstrip("\r") + "\n")
            out.flush()
    ser.close()


if __name__ == "__main__":
    main()
