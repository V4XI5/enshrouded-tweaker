import ctypes, ctypes.wintypes as wt, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autopatch
import gfxmods
import kfc4

EXE = 'enshrouded.exe'
RESOURCE_ARENA = 0x20000000000
GI_ROW, GI_ROWS = 140, 5
GI_GRAFT = {'globalRayBudget': 16, 'frustumSpatialCacheStartDiameter': 64,
            'minimumFilledRaysToAmbientProbes': 92, 'prefilterEnergyAngleScale[1]': 100}
GI_PUSH = {'globalRayBudget': (16, 4_000_000), 'frustumRayCacheFrameCount': (24, 0),
           'frustumMinRaysPerProbe': (28, 128), 'frustumIncreasedMinRaysPerProbe': (32, 256),
           'worldCacheMinRaysPerProbe': (48, 32)}
GI_FIXED = (0, 4, 8, 12, 36, 40, 44, 52, 56, 60)
GI_MODES = ('ultra', 'ultraplus', 'ultraplusplus')
PAGE = 0x1000
CHUNK = 64 << 20

PROCESS_QUERY_INFORMATION, PROCESS_VM_READ, PROCESS_VM_WRITE, PROCESS_VM_OPERATION = 0x400, 0x10, 0x20, 0x8
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
PAGE_NOACCESS, PAGE_READWRITE, PAGE_EXECUTE_READWRITE, PAGE_GUARD = 0x01, 0x04, 0x40, 0x100
WRITABLE = 0x04 | 0x08 | 0x40 | 0x80
EXECUTABLE = 0x10 | 0x20 | 0x40 | 0x80
TH32CS_SNAPPROCESS, TH32CS_SNAPMODULE = 0x2, 0x8
INVALID_HANDLE = wt.HANDLE(-1).value

k32 = ctypes.WinDLL('kernel32', use_last_error=True)


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('PartitionId', wt.WORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wt.DWORD), ('cntThreads', wt.DWORD),
                ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', ctypes.c_long), ('dwFlags', wt.DWORD),
                ('szExeFile', ctypes.c_wchar * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('th32ModuleID', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('GlblcntUsage', wt.DWORD), ('ProccntUsage', wt.DWORD), ('modBaseAddr', ctypes.c_void_p),
                ('modBaseSize', wt.DWORD), ('hModule', wt.HMODULE), ('szModule', ctypes.c_wchar * 256),
                ('szExePath', ctypes.c_wchar * 260)]


k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(wt.DWORD)]
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
for _f, _s in (('Process32FirstW', PROCESSENTRY32W), ('Process32NextW', PROCESSENTRY32W),
               ('Module32FirstW', MODULEENTRY32W), ('Module32NextW', MODULEENTRY32W)):
    getattr(k32, _f).argtypes = [wt.HANDLE, ctypes.POINTER(_s)]


def _snapshot(flags, pid, entry, first, nxt):
    snap = k32.CreateToolhelp32Snapshot(flags, pid)
    if not snap or snap == INVALID_HANDLE:
        return
    try:
        e = entry()
        e.dwSize = ctypes.sizeof(e)
        ok = first(snap, ctypes.byref(e))
        while ok:
            yield e
            ok = nxt(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)


def find_pid(name=EXE):
    for e in _snapshot(TH32CS_SNAPPROCESS, 0, PROCESSENTRY32W, k32.Process32FirstW, k32.Process32NextW):
        if e.szExeFile.lower() == name:
            return e.th32ProcessID
    return None


class Process:
    def __init__(self, pid):
        self.pid = pid
        self.h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE |
                                 PROCESS_VM_OPERATION, False, pid)
        if not self.h:
            raise OSError(f'cannot open process {pid} (error {ctypes.get_last_error()})')

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def query(self, addr):
        mbi = MBI()
        return mbi if k32.VirtualQueryEx(self.h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)) else None

    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, addr, buf, size, ctypes.byref(n)):
            return b''
        return buf.raw[:n.value]

    def regions(self):
        addr = 0
        while addr < 0x7FFFFFFFFFFF:
            mbi = self.query(addr)
            if mbi is None:
                break
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            if mbi.State == MEM_COMMIT and not mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS):
                yield base, size, mbi.Protect, mbi.Type
            addr = base + size

    def module(self, name=EXE):
        for e in _snapshot(TH32CS_SNAPMODULE, self.pid, MODULEENTRY32W, k32.Module32FirstW, k32.Module32NextW):
            if e.szModule.lower() == name:
                return e.modBaseAddr, e.modBaseSize
        raise OSError(f'{name} is not loaded in process {self.pid}')

    def write(self, addr, data):
        pos = 0
        while pos < len(data):
            n = min(len(data) - pos, PAGE - (addr + pos) % PAGE)
            self._write_page(addr + pos, data[pos:pos + n])
            pos += n
        if self.read(addr, len(data)) != data:
            raise OSError(f'readback at {addr:#x} failed')

    def _write_page(self, addr, data):
        mbi = self.query(addr)
        if mbi is None or mbi.State != MEM_COMMIT:
            raise OSError(f'{addr:#x} is not committed memory')
        old, changed = wt.DWORD(), False
        if not mbi.Protect & WRITABLE:
            prot = PAGE_EXECUTE_READWRITE if mbi.Protect & EXECUTABLE else PAGE_READWRITE
            if not k32.VirtualProtectEx(self.h, addr, len(data), prot, ctypes.byref(old)):
                raise OSError(f'cannot unprotect {addr:#x} (error {ctypes.get_last_error()})')
            changed = True
        try:
            n = ctypes.c_size_t()
            if not k32.WriteProcessMemory(self.h, addr, data, len(data), ctypes.byref(n)) or n.value != len(data):
                raise OSError(f'write at {addr:#x} failed (error {ctypes.get_last_error()})')
        finally:
            if changed:
                k32.VirtualProtectEx(self.h, addr, len(data), old.value, ctypes.byref(wt.DWORD()))


class FogBlock:
    def __init__(self, ri, base, data, span, fields, vanilla):
        self.ri, self.lo = ri, span[0]
        self.pattern = data[span[0]:span[1]]
        self.fields = [(name, p - span[0], label, cap) for name, p, label, cap in fields]
        self.vanilla = {p - span[0]: v for p, v in vanilla.items()}
        self.arena = RESOURCE_ARENA + base + span[0]
        masked = sorted(p for _, p, _, _ in self.fields)
        self.pieces, at = [], 0
        for p in masked + [len(self.pattern)]:
            if p > at:
                self.pieces.append((at, p))
            at = p + 4
        s, e = max(self.pieces, key=lambda r: (len(set(self.pattern[r[0]:r[1]])), r[1] - r[0]))
        self.anchor_at, self.anchor = s, self.pattern[s:min(e, s + 64)]
        self.copies = []

    def matches(self, mem, at=0):
        return at >= 0 and at + len(self.pattern) <= len(mem) and all(
            mem[at + s:at + e] == self.pattern[s:e] for s, e in self.pieces)


class Fog:
    def __init__(self, game_dir):
        k = kfc4.KFC(game_dir)
        st = autopatch.load_state()
        rec = st.get('builds', {}).get(k.version)
        vk = k
        if rec and autopatch.pair_sha1(game_dir) == rec['patched']:
            vk = kfc4.KFC(autopatch.mod_path(rec['vanilla_dir']))
        self.blocks = []
        for ri, d, span, fields in gfxmods.fog_fields(k):
            vd = vk.read_resource(vk.res_by_id[k.res_keys[ri][:3]])
            vanilla = {p: struct.unpack_from('<f', vd, p)[0] for _, p, _, _ in fields}
            self.blocks.append(FogBlock(ri, k.res_vals[ri][0], d, span, fields, vanilla))
        self.pid = None

    def locate(self, proc, progress=None):
        for b in self.blocks:
            b.copies = [b.arena] if b.matches(proc.read(b.arena, len(b.pattern))) else []
        regions = [(base, size) for base, size, prot, typ in proc.regions()
                   if typ == MEM_PRIVATE and prot & WRITABLE]
        total, done = sum(s for _, s in regions) or 1, 0
        longest = max(len(b.pattern) for b in self.blocks)
        for base, size in regions:
            for o in range(0, size, CHUNK):
                mem = proc.read(base + o, min(CHUNK + longest, size - o))
                for b in self.blocks:
                    pos = mem.find(b.anchor)
                    while pos >= 0:
                        at = pos - b.anchor_at
                        if 0 <= at < CHUNK and b.matches(mem, at):
                            b.copies.append(base + o + at)
                        pos = mem.find(b.anchor, pos + 1)
                done += min(CHUNK, size - o)
                if progress:
                    progress(done / total)
        self.pid = proc.pid
        return sum(len(b.copies) for b in self.blocks)

    def located(self, proc):
        return self.pid == proc.pid and any(b.copies for b in self.blocks)

    def current(self, proc):
        ratios = {}
        for b in self.blocks:
            for addr in b.copies:
                mem = proc.read(addr, len(b.pattern))
                if b.matches(mem):
                    for name, p, _, cap in b.fields:
                        if b.vanilla[p] and cap is None:
                            ratios.setdefault(name, []).append(struct.unpack_from('<f', mem, p)[0] / b.vanilla[p])
                    break
        return {n: round(sum(v) / len(v), 3) for n, v in ratios.items()}

    def apply(self, proc, mults):
        mults = gfxmods.normalise(mults)
        values = copies = 0
        for b in self.blocks:
            for addr in b.copies:
                if not b.matches(proc.read(addr, len(b.pattern))):
                    continue
                for name, p, _, cap in b.fields:
                    proc.write(addr + p, struct.pack('<f', gfxmods.scaled(b.vanilla[p], mults[name], cap)))
                    values += 1
                copies += 1
        return values, copies


def pe_sections(header):
    e = struct.unpack_from('<I', header, 0x3C)[0]
    if header[e:e + 4] != b'PE\0\0':
        raise ValueError('not a PE image')
    count, opt = struct.unpack_from('<H', header, e + 6)[0], struct.unpack_from('<H', header, e + 20)[0]
    out = {}
    for i in range(count):
        name, vsize, va, rsize, rptr = struct.unpack_from('<8sIIII', header, e + 24 + opt + 40 * i)
        out[name.rstrip(b'\0').decode('ascii', 'replace')] = (va, vsize, rptr, rsize)
    return out


def find_gi_table(data):
    hits = []
    pos = data.find(struct.pack('<II', 3, 2))
    while pos >= 0:
        first = pos - (GI_ROWS - 1) * GI_ROW
        if pos % 4 == 0 and first >= 0 and pos + GI_ROW <= len(data):
            rows = [struct.unpack_from('<5I', data, first + GI_ROW * r) for r in range(GI_ROWS)]
            rad, irr, budget = [r[0] for r in rows], [r[1] for r in rows], [r[4] for r in rows]
            if (rad == sorted(rad) and irr == sorted(irr) and rows[3][:2] == (2, 1)
                    and all(budget[i] < budget[i + 1] for i in range(GI_ROWS - 1))
                    and all(8 <= r[2] <= 16384 and 8 <= r[3] <= 16384 for r in rows)):
                hits.append(pos - GI_ROW)
        pos = data.find(struct.pack('<II', 3, 2), pos + 1)
    return hits[0] if len(hits) == 1 else None


class GI:
    def __init__(self, game_dir):
        with open(os.path.join(game_dir, EXE), 'rb') as f:
            exe = f.read()
        va, vsize, rptr, rsize = pe_sections(exe[:0x1000])['.rdata']
        rdata = exe[rptr:rptr + rsize]
        off = find_gi_table(rdata)
        if off is None:
            raise LookupError('the GI quality table was not found in this build of the game')
        self.rva = va + off
        self.ultra, self.groundtruth = rdata[off:off + GI_ROW], rdata[off + GI_ROW:off + 2 * GI_ROW]
        plus = bytearray(self.ultra)
        for o in GI_GRAFT.values():
            plus[o:o + 4] = self.groundtruth[o:o + 4]
        push = bytearray(plus)
        for o, v in GI_PUSH.values():
            struct.pack_into('<I', push, o, v)
        for row in (plus, push):
            assert all(row[o:o + 4] == self.ultra[o:o + 4] for o in GI_FIXED)
        assert struct.unpack_from('<I', push, 16)[0] + 768 < 1 << 22
        self.rows = {'ultra': self.ultra, 'ultraplus': bytes(plus), 'ultraplusplus': bytes(push)}

    def state(self, proc):
        base, _ = proc.module()
        mem = proc.read(base + self.rva, 2 * GI_ROW)
        if mem[GI_ROW:] != self.groundtruth:
            return 'unknown'
        rows = dict(self.rows, groundtruth=self.groundtruth)
        return next((name for name, row in rows.items() if mem[:GI_ROW] == row), 'unknown')

    def set(self, proc, mode):
        if mode not in self.rows:
            raise ValueError(f'unknown GI mode {mode!r}')
        if self.state(proc) == 'unknown':
            raise OSError('the GI table in memory is not the one in the exe; not touching it')
        base, _ = proc.module()
        proc.write(base + self.rva, self.rows[mode])


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    game_dir = os.path.dirname(autopatch.MOD_DIR)
    args = sys.argv[1:]
    if not args or args[0] not in ('status', 'fog', 'gi'):
        print('usage: live.py status | fog FOG [WEATHER SHROUD GLOW DAYGLOW] | gi ultraplusplus|ultraplus|ultra')
        return 2
    pid = find_pid()
    if pid is None:
        print('Enshrouded is not running')
        return 1
    with Process(pid) as proc:
        if args[0] in ('status', 'fog'):
            fog = Fog(game_dir)
            n = fog.locate(proc)
            print(f'pid {pid}: {n} copies of {len(fog.blocks)} fog blocks found')
            if args[0] == 'fog':
                n = len(gfxmods.FOG_OPTIONS)
                vals = [float(x) for x in args[1:1 + n]]
                mults = dict(zip(gfxmods.FOG_OPTIONS, vals + [1.0] * (n - len(vals))))
                print('wrote %d values in %d copies' % fog.apply(proc, mults))
            print('fog multipliers in memory:', fog.current(proc))
        gi = GI(game_dir)
        if args[0] == 'gi':
            if len(args) < 2 or args[1] not in GI_MODES:
                print('gi takes ' + ' or '.join(GI_MODES))
                return 2
            gi.set(proc, args[1])
            print('GI preset written; switch Global Illumination quality away from Ultra and back in the game')
        print('Ultra GI preset in memory:', gi.state(proc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
