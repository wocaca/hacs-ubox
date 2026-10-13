"""Handshake builders + wire templates (vendored from 拉流_骨架.py / 拉流_中继.py).

Byte layout is reverse-engineered from libUBICAPIs29.so (Ghidra) and live
relay captures; see D:/code/ubox/文档/实时视频/交接.md for the full chain.
"""
import random
import struct

from .crypto import decrypt_packet, encrypt_packet

SV_TEMPLATE = bytes.fromhex(
    "0718100090000700031421000100000006008400000000000000000006000c00"
    "12000800b2380100000000000200040012000800070028000200000012000120"
    "0000040000000000000000000000000000000000000000000000000000000000"
    "01000c0002000000110001010100000004001000000000001400000001000000"
    "1200000005001800000014000000140002004b00110000040f00000000000000")
SV_SEQ_OFFS = (32, 48, 56, 60, 100, 120)

PUNCH10240 = bytes.fromhex(
    "81a68d0d62bdd8d2254d498d2ccacbda0121b81d26a8ec97643e490ca9cbd89b"
    "04a48c0d62bcd8d2774b0d4fd990de9d492062656c69657665203120")
PUNCH20001 = bytes.fromhex(
    "44868d0d62bdd8d2254d498d2ccacbda0121b81d26a8ec97643e590ca9cbd99b"
    "04a48c0d62bcd8d2774b0d4fd990de9d492062656c69657665203120")
LOGIN124 = bytes.fromhex(
    "44868d4d62bdd8d2254d498d2ccacbde04a48c0d639c78c2242d490ceccacbd82"
    "7f7d94532a8dd9725cd51aceccacbd860f0c92d33c98b2111184a08898e699dd"
    "361896d3abdd8d272becf3fb8b23e8e54c9f6c99a6ace44342d090ceccacad80"
    "4a48c0d62bc48c224cd4f0ceccacad849206265b858657665203120")

_sv_counter = [0]


def mint_startvideo(first=False):
    pkt = bytearray(SV_TEMPLATE)
    pkt[6] = 0x01 if first else 0x07
    base = 0x0001 if first else struct.unpack("<H", SV_TEMPLATE[32:34])[0]
    _sv_counter[0] += 1
    main = base + _sv_counter[0]
    struct.pack_into("<H", pkt, 32, main & 0xFFFF)
    struct.pack_into("<H", pkt, 48, main & 0xFFFF)
    struct.pack_into("<H", pkt, 60, main & 0xFFFF)
    struct.pack_into("<H", pkt, 56, (main - 0x10) & 0xFFFF)
    struct.pack_into("<H", pkt, 100, (main - 0x10) & 0xFFFF)
    struct.pack_into("<H", pkt, 120, (main + 2) & 0xFFFF)
    return encrypt_packet(bytes(pkt))


def build_knock84(uid: bytes, pwd: bytes, nonce: bytes, random_id: int) -> bytes:
    p = bytearray(84)
    p[0:4] = bytes.fromhex("07181000")
    struct.pack_into("<H", p, 4, 0x44)
    p[8] = 0x0b
    p[9] = 0x13
    p[10] = 0x21
    p[16:16 + len(uid)] = uid[:20]
    p[36:36 + len(pwd)] = pwd[:24]
    p[60:64] = nonce
    struct.pack_into("<I", p, 64, random_id & 0xFFFFFFFF)
    p[68:73] = b"admin"
    p[80:84] = bytes.fromhex("2b452b45")
    return bytes(p)


def build_alive36(nonce: bytes, sid: int, use_24=True) -> bytes:
    p = bytearray(36)
    p[0:4] = bytes.fromhex("07181000")
    struct.pack_into("<H", p, 4, 0x14)
    p[6] = sid & 0xFF
    p[7] = 0x14
    p[8] = 0x24 if use_24 else 0x21
    struct.pack_into("<I", p, 20, struct.unpack("<I", nonce)[0])
    p[32:36] = bytes.fromhex("2b452b45")
    return bytes(p)


def build_echo52(pkt_plain: bytes, random_id: int) -> bytes:
    p = bytearray(52)
    p[0:4] = bytes.fromhex("07181000")
    struct.pack_into("<H", p, 4, 0x24)
    p[8] = 0x0d
    p[9] = 0x13
    p[10] = 0x21
    p[36:48] = pkt_plain[36:48]
    struct.pack_into("<I", p, 48, random_id & 0xFFFFFFFF)
    return bytes(p)


def build_avctrl32(sid: int, nonce: bytes, stream_type: int, use_24=True, channel=0) -> bytes:
    p = bytearray(32)
    p[0:4] = bytes.fromhex("07181000")
    struct.pack_into("<H", p, 4, 0x10)
    struct.pack_into("<H", p, 6, sid & 0xFFFF)
    p[8] = 0x07
    p[9] = 0x14
    p[10] = 0x24 if use_24 else 0x21
    p[12:14] = nonce[2:4]
    p[14] = channel
    p[16] = 0x09
    p[17] = 0x00
    p[18] = stream_type & 0xFF
    p[19] = 0x01
    return bytes(p)


def patch_startvideo160(sv_enc: bytes, sid: int, nonce: bytes) -> bytes:
    p = bytearray(decrypt_packet(sv_enc))
    struct.pack_into("<H", p, 6, sid & 0xFFFF)
    p[10] = 0x24
    p[12:14] = nonce[2:4]
    return encrypt_packet(bytes(p))


def build_login124(reqtick: int, random_id=None, disconnect=False) -> bytes:
    p = bytearray(decrypt_packet(LOGIN124))
    struct.pack_into("<I", p, 0x74, reqtick & 0xFFFFFFFF)
    if random_id is not None:
        struct.pack_into("<I", p, 0x58, random_id & 0xFFFFFFFF)
    if disconnect:
        p[0x50] = 1
    return encrypt_packet(bytes(p))


def parse_rlystreamrsp(plain: bytes):
    n = plain[0x10]
    if n > 0x10:
        n = 0x10
    out = []
    for i in range(n):
        e = plain[0x28 + i * 0xD6:0x28 + (i + 1) * 0xD6]
        if len(e) < 0x24:
            continue
        out.append({"sid": e[0x0F],
                    "randomID": struct.unpack("<I", e[0x12:0x16])[0],
                    "nonce": bytes(e[0x20:0x24]),
                    "result": struct.unpack("<h", e[0:2])[0]})
    addrs = []
    try:
        import socket as _sk
        for port_o, ip_o in ((0x14, 0x24), (0x16, 0x18), (0x20, 0x1C)):
            port = struct.unpack("<H", plain[port_o:port_o + 2])[0]
            ip = _sk.inet_ntoa(bytes(plain[ip_o:ip_o + 4]))
            if port and ip != "0.0.0.0":
                addrs.append((ip, port))
    except Exception:
        pass
    return out, addrs


def fresh_req():
    return random.getrandbits(32), 12000 + random.randint(0, 60000)
