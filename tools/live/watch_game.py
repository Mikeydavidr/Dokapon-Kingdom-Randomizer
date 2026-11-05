"""Start the game under a debugger and log which instructions touch an accessory's bytes (hardware read/write watchpoints).

usage: python watch_game.py <seconds> [--exe DkkStm.exe] [--acc ID] [--chance PCT] [--players 0,1] [--out FILE]
Launches the game (working folder = the exe's folder) as a debuggee and waits until a new game's players exist (player 0 has the
starting weapon). Then it puts accessory ID (default 0x13, Crystal Choker) on --players with chance PCT (default 100), arms
watchpoints (all threads, 1 byte each) on player 0's accessory byte (+0xC0) and the accessory's id (+0x140) and chance (+0x139)
bytes (see docs/item-records-and-effects.md section 3) and logs every hit for <seconds>, as the exe-relative address of the
instruction after the access. At the end it clears the watchpoints, checks they are cleared, and detaches; the game keeps running.
Launching (not attaching) keeps all debug events on this one thread. Output per watch: instruction, hit count, first/last time.
"""
import argparse
import collections
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("seconds", type=float, help="how long to log once the watchpoints are armed")
ap.add_argument("--exe", default="G:/Programming/Dokapon-Workspace/ActualGame/DkkStm.exe")
ap.add_argument("--acc", type=lambda s: int(s, 0), default=0x13)
ap.add_argument("--chance", type=int, default=100)
ap.add_argument("--players", default="0,1")
ap.add_argument("--out", default=None)
opts = ap.parse_args()

k = ctypes.WinDLL("kernel32", use_last_error=True)


class SI(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("r", wt.LPWSTR), ("d", wt.LPWSTR), ("t", wt.LPWSTR), ("x", wt.DWORD), ("y", wt.DWORD), ("xs", wt.DWORD),
                ("ys", wt.DWORD), ("xc", wt.DWORD), ("yc", wt.DWORD), ("fill", wt.DWORD), ("flags", wt.DWORD), ("show", wt.WORD),
                ("r2", wt.WORD), ("r3", ctypes.c_void_p), ("in", wt.HANDLE), ("out", wt.HANDLE), ("err", wt.HANDLE)]


class PI(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("pid", wt.DWORD), ("tid", wt.DWORD)]


class DebugEvent(ctypes.Structure):
    _fields_ = [("code", wt.DWORD), ("pid", wt.DWORD), ("tid", wt.DWORD), ("pad", wt.DWORD), ("u", ctypes.c_byte * 160)]   # union at offset 16


k.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR,
                             ctypes.POINTER(SI), ctypes.POINTER(PI)]
exe_path = Path(opts.exe)
si, pi = SI(), PI()
si.cb = ctypes.sizeof(si)
if not k.CreateProcessW(str(exe_path), None, None, None, False, 0x2, None, str(exe_path.parent), ctypes.byref(si), ctypes.byref(pi)):
    raise SystemExit(f"cannot start {exe_path}: error {ctypes.get_last_error()}")
pid = pi.pid
k.DebugSetProcessKillOnExit(False)
print(f"started {exe_path.name} as pid {pid} under the debugger")

sys.argv = [sys.argv[0], str(pid), "equip"]         # write access to the game, for players.py's helpers
src = Path(__file__).with_name("players.py").read_text().split("cal = calendar()")[0]
exec(src)                                          # read(), write(), find_base(), acc_slots(), PLAYERS ...

k.OpenThread.restype = wt.HANDLE
for fn in (k.GetThreadContext, k.SetThreadContext):
    fn.argtypes = [wt.HANDLE, ctypes.c_void_p]
k.SuspendThread.argtypes = [wt.HANDLE]
k.ResumeThread.argtypes = [wt.HANDLE]
k.CreateToolhelp32Snapshot.restype = wt.HANDLE
CTX_SIZE, CTX_DEBUG = 1232, 0x100010                 # CONTEXT_AMD64 | DEBUG_REGISTERS
targets = []


def context():
    raw = ctypes.create_string_buffer(CTX_SIZE + 16)
    addr = (ctypes.addressof(raw) + 15) & ~15
    ctypes.c_uint32.from_address(addr + 0x30).value = CTX_DEBUG
    return raw, addr


def u64(addr, off):
    return ctypes.c_uint64.from_address(addr + off)


def set_debug_regs(tid: int, on: bool) -> bool:
    """Arm (or clear) one thread's watchpoints; True when a second read of its context shows the wanted state (or it is gone)."""
    th = k.OpenThread(0x1FFFFF, False, tid)
    if not th:
        return True
    k.SuspendThread(th)
    ok = False
    raw, addr = context()
    if k.GetThreadContext(th, addr):
        dr7 = 0
        for i, (_, a) in enumerate(targets):
            if on:
                u64(addr, 0x48 + 8 * i).value = a
                dr7 |= (1 << (2 * i)) | (3 << (16 + 4 * i))
        u64(addr, 0x70).value = dr7
        u64(addr, 0x68).value = 0
        if k.SetThreadContext(th, addr):
            raw2, addr2 = context()
            ok = bool(k.GetThreadContext(th, addr2)) and u64(addr2, 0x70).value == dr7
    k.ResumeThread(th)
    k.CloseHandle(th)
    return ok


def thread_ids():
    class TE(ctypes.Structure):
        _fields_ = [("size", wt.DWORD), ("usage", wt.DWORD), ("tid", wt.DWORD), ("owner", wt.DWORD), ("pri", wt.LONG), ("dpri", wt.LONG), ("flags", wt.DWORD)]
    snap = k.CreateToolhelp32Snapshot(4, 0)
    te, out = TE(), []
    te.size = ctypes.sizeof(te)
    ok = k.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.owner == pid:
            out.append(te.tid)
        ok = k.Thread32Next(snap, ctypes.byref(te))
    k.CloseHandle(snap)
    return out


def try_arm():
    """Once a new game's players exist: equip the accessory, then arm. Returns the state base or None."""
    try:
        base = find_base()
    except SystemExit:
        return None
    p0 = read(base + PLAYERS, PLAYER_STRIDE)
    if len(p0) < PLAYER_STRIDE or p0[0xBE] != 1:       # not set up yet (a new game gives player 0 the Knife)
        return None
    accs = acc_slots(base)
    if opts.acc not in accs:
        return None
    for n in (int(x) for x in opts.players.split(",")):
        write(base + PLAYERS + n * PLAYER_STRIDE + 0xC0, bytes([opts.acc]))
    write(accs[opts.acc] + 0x139, bytes([opts.chance]))
    print(f"B = {base:#x}: accessory {opts.acc:#x} on players {opts.players}, chance {opts.chance}")
    targets[:] = [("player accessory", base + PLAYERS + 0xC0), ("accessory id", accs[opts.acc] + 0x140), ("accessory chance", accs[opts.acc] + 0x139)]
    return base


hits = collections.defaultdict(list)
ev = DebugEvent()
exe_base_addr = None
armed_at = None
armed_tids = set()
last_try = 0.0
exited = False
try:
    while True:
        now = time.time()
        if armed_at is None and now - last_try > 3:
            last_try = now
            if try_arm():
                armed_tids = set(thread_ids())
                for t in armed_tids:
                    set_debug_regs(t, True)
                armed_at = time.time()
                print(f"armed {len(armed_tids)} threads; logging for {opts.seconds:.0f}s")
        if armed_at is not None and now - armed_at > opts.seconds:
            break
        if not k.WaitForDebugEvent(ctypes.byref(ev), 250):
            continue
        status = 0x00010002                                    # DBG_CONTINUE
        data = bytes(ev.u)
        if ev.code == 3:                                       # process created: remember the image base
            exe_base_addr = struct.unpack_from("<Q", data, 24)[0]
        elif ev.code == 2 and armed_at is not None:            # thread created after arming
            armed_tids.add(ev.tid)
            set_debug_regs(ev.tid, True)
        elif ev.code == 5:                                     # process exited
            exited = True
            break
        elif ev.code == 1:
            exc = struct.unpack_from("<I", data, 0)[0]
            if exc == 0x80000004 and armed_at is not None:     # single step = a watchpoint hit
                th = k.OpenThread(0x1FFFFF, False, ev.tid)
                raw, addr = context()
                if th and k.GetThreadContext(th, addr):
                    dr6, rip = u64(addr, 0x68).value, u64(addr, 0xF8).value
                    for i, (name, _) in enumerate(targets):
                        if dr6 >> i & 1:
                            hits[(name, rip - exe_base_addr)].append(time.time() - armed_at)
                    u64(addr, 0x68).value = 0
                    k.SetThreadContext(th, addr)
                if th:
                    k.CloseHandle(th)
            elif exc not in (0x80000003, 0x80000004):
                status = 0x80010001                            # DBG_EXCEPTION_NOT_HANDLED
        k.ContinueDebugEvent(ev.pid, ev.tid, status)
finally:
    if not exited:
        # clear every thread's watchpoints (verified, retried), answer anything still queued, then let go of the game
        left = set(thread_ids()) | armed_tids
        for _ in range(10):
            left = {t for t in left if not set_debug_regs(t, False)}
            while k.WaitForDebugEvent(ctypes.byref(ev), 0):
                single = ev.code == 1 and struct.unpack_from("<I", bytes(ev.u), 0)[0] in (0x80000003, 0x80000004)
                k.ContinueDebugEvent(ev.pid, ev.tid, 0x00010002 if ev.code != 1 or single else 0x80010001)
            if not left:
                break
        if left:
            print(f"WARNING: could not clear the watchpoints of threads {sorted(left)}; save and quit the game", file=sys.stderr)
        k.DebugActiveProcessStop(pid)
        print("detached; the game keeps running")
    else:
        print("the game exited")

lines = [f"{name:17s} exe+{rva:#09x} (VA {0x140000000 + rva:#x})  x{len(ts):<5d} first {ts[0]:6.1f}s last {ts[-1]:6.1f}s"
         for (name, rva), ts in sorted(hits.items(), key=lambda kv: (kv[0][0], kv[1][0]))]
text = "\n".join(lines) or "no hits"
print(text)
if opts.out:
    Path(opts.out).write_text(text + "\n")
