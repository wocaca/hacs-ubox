"""P4P block cipher (vendored from 脚本/加解密/加解密_P4P.py).

Per 16B block (decrypt):  P = ROTL(Swap16(ROTL(C)) ^ POEM[0:16])
Tail N<16 bytes:          P = SwapN(C) ^ POEM[0:N]
Key: b"I believe 1 ^ill" (first 16 bytes used per block, tails phase 0).
No third-party deps, stdlib only.
"""
import struct

POEM = bytes.fromhex(
    "492062656c696576652031205e696c6c2077696e2074686520626174746c6521"
    "000a000d0a5b25396c755d5b554c4f475f44454255475d25735b25645d207369")
P16 = [11, 9, 8, 15, 13, 10, 12, 14, 2, 1, 5, 0, 6, 4, 7, 3]
P8 = [7, 4, 3, 2, 1, 6, 5, 0]
SH_A = (3, 7, 11, 15)
SH_B = (1, 5, 9, 13)


def _rol(v, s):
    return ((v << s) | (v >> (32 - s))) & 0xFFFFFFFF


def _ror(v, s):
    return ((v >> s) | (v << (32 - s))) & 0xFFFFFFFF


def _rot(blk, sh, fn):
    return b"".join(struct.pack("<I", fn(struct.unpack("<I", blk[i * 4:(i + 1) * 4])[0], s))
                     for i, s in enumerate(sh))


def _swap(blk, P):
    return bytes(blk[P[i]] for i in range(len(P)))


def _xor(blk, off=0):
    return bytes(a ^ b for a, b in zip(blk, POEM[off:off + len(blk)]))


def decrypt_block(c):
    return _rot(_xor(_swap(_rot(c, SH_A, _rol), P16)), SH_B, _rol)


def encrypt_block(p):
    return _rot(_swap(_xor(_rot(p, SH_B, _ror)), P16), SH_A, _ror)


def decrypt_tail(c):
    n = len(c)
    if n == 0:
        return b""
    if n == 8:
        return _xor(_swap(c, P8))
    return _xor(c)


def encrypt_tail(p):
    n = len(p)
    if n == 0:
        return b""
    if n == 8:
        return _swap(_xor(p), P8)
    return _xor(p)


def decrypt_packet(c):
    n = len(c) // 16 * 16
    return b"".join(decrypt_block(c[i:i + 16]) for i in range(0, n, 16)) + decrypt_tail(c[n:])


def encrypt_packet(p):
    n = len(p) // 16 * 16
    return b"".join(encrypt_block(p[i:i + 16]) for i in range(0, n, 16)) + encrypt_tail(p[n:])
