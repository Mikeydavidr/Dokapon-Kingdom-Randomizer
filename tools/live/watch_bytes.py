"""Log which instructions of the RUNNING game touch a few bytes (hardware read/write watchpoints), to find the code behind a feature.

usage: python watch_bytes.py <pid> <seconds> [--acc ID] [--player N] [--out FILE]
Attaches as a debugger, watches (all threads, 1 byte each): the player's equipped accessory byte (+0xC0), the accessory's id byte
(+0x140) and its chance byte (+0x139) in the item structs (see docs/item-records-and-effects.md section 3), and logs every hit as
"seconds since start, watch, address of the next instruction (relative to the exe base)". Detaches cleanly at the end (the game is
not killed). Keep the time short: every hit stops the game for a moment. Prints, per watch, each instruction with its hit count
and the time of its first and last hit.
"""
import argparse
import collections
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("pid", type=int)
ap.add_argument("seconds", type=float)
ap.add_argument("--acc", type=lambda s: int(s, 0), default=0x13)
ap.add_argument("--player", type=int, default=0)
ap.add_argument("--out", default=None)
opts = ap.parse_args()

sys.argv = [sys.argv[0], str(opts.pid), "show"]
src = open(__file__.replace("watch_bytes.py", "players.py")).read().split("cal = calendar()")[0]
exec(src)                                       # read(), find_base(), acc_slots(), exe_base(), PLAYERS ... from players.py
args = opts
base = find_base()
slot = acc_slots(base)[args.acc]
targets = [("player accessory", base + PLAYERS + args.player * PLAYER_STRIDE + 0xC0),
           ("accessory id", slot + 0x140), ("accessory chance", slot + 0x139)]
exe = exe_base()
print(f"B = {base:#x}; watching " + ", ".join(f"{n} @ {a:#x}" for n, a in targets))

k.DebugActiveProcess.argtypes = [wt.DWORD]
k.OpenThread.restype = wt.HANDLE
k.GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
k.SetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
k.SuspendThread.argtypes = [wt.HANDLE]
k.ResumeThread.argtypes = [wt.HANDLE]
k.CreateToolhelp32Snapshot.restype = wt.HANDLE
CTX_SIZE, CTX_DEBUG = 1232, 0x100000 | 0x10 | 0x1       # CONTEXT_AMD64 | DEBUG_REGISTERS | CONTROL


def context():
    raw = ctypes.create_string_buffer(CTX_SIZE + 16)
    addr = (ctypes.addressof(raw) + 15) & ~15
    ctypes.memset(addr, 0, CTX_SIZE)
    struct.pack_into("<I", (ctypes.c_char * 4).from_address(addr + 0x30), 0, CTX_DEBUG)
    return raw, addr


def set_debug_regs(tid: int, on: bool) -> bool:
    """Arm (or clear) the watchpoints of one thread; True when a second read of its context shows the wanted state."""
    th = k.OpenThread(0x1FFFFF, False, tid)
    if not th:
        return True                                  # the thread is gone: nothing to clear
    k.SuspendThread(th)
    ok = False
    raw, addr = context()
    if k.GetThreadContext(th, addr):
        dr7 = 0
        for i, (_, a) in enumerate(targets):
            if on:
                ctypes.c_uint64.from_address(addr + 0x48 + 8 * i).value = a
                dr7 |= (1 << (2 * i)) | (3 << (16 + 4 * i))
        ctypes.c_uint64.from_address(addr + 0x70).value = dr7
        ctypes.c_uint64.from_address(addr + 0x68).value = 0
        if k.SetThreadContext(th, addr):
            raw2, addr2 = context()
            ok = bool(k.GetThreadContext(th, addr2)) and ctypes.c_uint64.from_address(addr2 + 0x70).value == dr7
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
        if te.owner == args.pid:
            out.append(te.tid)
        ok = k.Thread32Next(snap, ctypes.byref(te))
    k.CloseHandle(snap)
    return out


class DebugEvent(ctypes.Structure):
    _fields_ = [("code", wt.DWORD), ("pid", wt.DWORD), ("tid", wt.DWORD), ("u", ctypes.c_byte * 160)]


if not k.DebugActiveProcess(args.pid):
    raise SystemExit("cannot attach")
k.DebugSetProcessKillOnExit(False)
tids = set(thread_ids())
for t in tids:
    set_debug_regs(t, True)
hits = collections.defaultdict(list)
t0 = time.time()
ev = DebugEvent()
try:
    while time.time() - t0 < args.seconds:
        if not k.WaitForDebugEvent(ctypes.byref(ev), 200):
            continue
        status = 0x00010002                                    # DBG_CONTINUE
        if ev.code == 3 or ev.code == 2:                       # a thread was created: give it the watchpoints too
            set_debug_regs(ev.tid, True)
        elif ev.code == 1:
            exc = struct.unpack_from("<I", bytes(ev.u), 0)[0]
            if exc == 0x80000004:                              # single step = a watchpoint hit
                th = k.OpenThread(0x1FFFFF, False, ev.tid)
                raw, addr = context()
                if th and k.GetThreadContext(th, addr):
                    dr6 = ctypes.c_uint64.from_address(addr + 0x68).value
                    rip = ctypes.c_uint64.from_address(addr + 0xF8).value
                    for i, (name, _) in enumerate(targets):
                        if dr6 >> i & 1:
                            hits[(name, rip - exe)].append(time.time() - t0)
                    ctypes.c_uint64.from_address(addr + 0x68).value = 0
                    k.SetThreadContext(th, addr)
                if th:
                    k.CloseHandle(th)
            elif exc != 0x80000003:
                status = 0x80010001                            # DBG_EXCEPTION_NOT_HANDLED
        k.ContinueDebugEvent(ev.pid, ev.tid, status)
finally:
    # disarm every thread (verified, retried), answering any hit that is still queued, and only then let go of the game
    left = set(thread_ids()) | tids
    for _ in range(10):
        left = {t for t in left if not set_debug_regs(t, False)}
        while k.WaitForDebugEvent(ctypes.byref(ev), 0):
            k.ContinueDebugEvent(ev.pid, ev.tid, 0x00010002 if ev.code != 1 or struct.unpack_from("<I", bytes(ev.u), 0)[0] in (0x80000003, 0x80000004) else 0x80010001)
        if not left:
            break
    if left:
        print(f"WARNING: could not clear the watchpoints of threads {sorted(left)}; the game may crash: save and quit it", file=sys.stderr)
    k.DebugActiveProcessStop(args.pid)

lines = []
for (name, rva), ts in sorted(hits.items(), key=lambda kv: (kv[0][0], kv[1][0])):
    lines.append(f"{name:17s} exe+{rva:#09x} (VA {0x140000000 + rva:#x})  x{len(ts):<5d} first {ts[0]:6.1f}s last {ts[-1]:6.1f}s")
text = "\n".join(lines) or "no hits"
print(text)
if args.out:
    open(args.out, "w").write(text + "\n")
