"""Blocking relay snapshot client (simplified from 拉流_中继.py).

Known ceiling (see ubox 交接.md #106): pure-Python relay path only yields
the 360p SUB IDR *first fragment* (~1264B payload with VPS/SPS/PPS); full
continuous GOP needs the 0x1403 video ACK which is not implemented here.
Callers must surface this honestly: snapshot/slideshow grade, not live HD.
For 1080p live use proxy mode (hass-ubox Add-on MJPEG).
"""
import socket
import struct
import time

from .crypto import decrypt_packet, encrypt_packet
from .handshake import (
    PUNCH10240, PUNCH20001, build_alive36, build_avctrl32, build_echo52,
    build_knock84, build_login124, fresh_req, mint_startvideo,
    parse_rlystreamrsp, patch_startvideo160,
)

CAMERA_FALLBACKS = (("10.1.150.30", 32762), ("10.1.150.30", 54561), ("10.1.150.30", 54182))


def _send_all(sock, data, targets):
    for t in targets:
        try:
            sock.sendto(data, t)
        except OSError:
            pass


def fetch_snapshot(uid: bytes, pwd: bytes, relay, stream=0, timeout=25.0, port=0):
    """One-shot: punch -> login -> knock/alive/avctrl/startvideo -> collect.

    Returns dict(ok, h265, frags, total1320, fid_count, relay, sid, note).
    Never raises on network timeouts; ok=False with note instead.
    """
    rip, rport = relay
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError:
        sock.bind(("0.0.0.0", 0))
    sock.settimeout(0.5)
    t_end_listen = None

    def recv_until(deadline, want_468=False):
        nonlocal t_end_listen
        while time.time() < deadline:
            try:
                d, a = sock.recvfrom(4096)
            except socket.timeout:
                yield None, None
                continue
            yield d, a
            if want_468 and len(d) == 468:
                return

    try:
        sock.sendto(PUNCH20001 if rport == 20001 else PUNCH10240, (rip, rport))
        time.sleep(0.3)
        sock.sendto(PUNCH20001 if rport == 20001 else PUNCH10240, (rip, rport))
        time.sleep(0.4)
        # drain punch replies
        t0 = time.time()
        while time.time() - t0 < 2.0:
            try:
                sock.recvfrom(4096)
            except socket.timeout:
                break

        my_rid, tick = fresh_req()
        sock.sendto(build_login124(tick, my_rid), (rip, rport))
        entry = None
        p468 = None
        extra = []
        deadline = time.time() + 12.0
        for d, a in recv_until(deadline):
            if d is None:
                continue
            try:
                p = decrypt_packet(d)
            except Exception:
                continue
            if len(d) == 468 and len(p) >= 76:
                es, addrs = parse_rlystreamrsp(p)
                for ad in addrs:
                    if ad not in extra:
                        extra.append(ad)
                ok = [e for e in es if e["result"] == 0 and any(e["nonce"])]
                if ok:
                    entry = ok[0]
                    p468 = p
                    break
        if entry is None:
            return {"ok": False, "note": "no 468B entry (relay busy/offline)", "relay": relay}
        nonce, random_id, sid = entry["nonce"], entry["randomID"], entry["sid"]
        targets = [(rip, rport)] + list(CAMERA_FALLBACKS) + extra

        knock = encrypt_packet(build_knock84(uid, pwd, nonce, random_id))
        al24 = encrypt_packet(build_alive36(nonce, sid, True))
        al21 = encrypt_packet(build_alive36(nonce, sid, False))
        _send_all(sock, knock, targets)
        time.sleep(0.06)
        _send_all(sock, al24, targets)
        _send_all(sock, al21, targets)
        _send_all(sock, encrypt_packet(build_echo52(p468, random_id)), targets)
        time.sleep(0.06)
        av_r = encrypt_packet(build_avctrl32(sid, nonce, stream, True))
        av_c = encrypt_packet(build_avctrl32(sid, nonce, stream, False))
        _send_all(sock, av_r, targets)
        _send_all(sock, av_c, targets)
        try:
            sv0 = mint_startvideo(first=True)
            _send_all(sock, patch_startvideo160(sv0, sid, nonce), targets)
            time.sleep(0.05)
            _send_all(sock, patch_startvideo160(mint_startvideo(), sid, nonce), targets)
            _send_all(sock, sv0, targets)
        except Exception:
            pass

        # collect video frags: 1320B outer is 40B, payload p[56:] 1264B,
        # inner marker f/c at p[40:42], fid=p[48:52], seq=p[42:44]
        frags = {}  # (fid, seq) -> payload
        fids = {}
        total1320 = 0
        last_alive = time.time()
        t_end_listen = time.time() + timeout
        while time.time() < t_end_listen:
            if time.time() - last_alive > 1.0:
                _send_all(sock, al24, targets)
                last_alive = time.time()
            try:
                d, a = sock.recvfrom(4096)
            except socket.timeout:
                continue
            if len(d) != 1320:
                # reactive 0x130c -> echo 52B+alive (keeps camera side warm)
                try:
                    p = decrypt_packet(d)
                    if len(p) >= 10 and p[8] == 0x0C and p[9] == 0x13:
                        sock.sendto(encrypt_packet(build_echo52(p, random_id)), a)
                        sock.sendto(al24, a)
                except Exception:
                    pass
                continue
            total1320 += 1
            try:
                p = decrypt_packet(d)
            except Exception:
                continue
            if len(p) < 56 or p[40:42] != b"fc":
                continue
            seq = struct.unpack("<H", p[42:44])[0]
            fid = struct.unpack("<I", p[48:52])[0]
            payload = p[56:]
            key = (fid, seq)
            if key not in frags:
                frags[key] = payload
                fids[fid] = fids.get(fid, 0) + 1
        if not frags:
            return {"ok": False, "note": "session up but no video frags (need ACK / camera busy)",
                    "relay": relay, "sid": sid, "total1320": total1320}
        # best fid = most frags; concat seq order -> Annex-B guess
        best_fid = max(fids, key=lambda k: fids[k])
        seqs = sorted(s for (f, s) in frags if f == best_fid)
        blob = b"".join(frags[(best_fid, s)] for s in seqs)
        return {"ok": True, "h265": blob, "frags": len(seqs), "fid": best_fid,
                "fid_count": len(fids), "total1320": total1320,
                "relay": relay, "sid": sid,
                "note": "experimental SUB IDR fragment; continuous GOP needs video ACK"}
    finally:
        try:
            sock.close()
        except Exception:
            pass
