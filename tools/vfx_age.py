import struct
from spv_eval import Run, UNK, f32, bits

COPY = (124, 83, 400)


class ShaderInfo:
    def __init__(self, m):
        self.m = m
        self.ev = m.var_with_binding(41, 1)
        self.sv = m.var_with_binding(42, 1)
        dv = m.var_with_binding(39, 1)
        b0 = m.var_with_binding(0, 1)
        load = None
        for b in m.order:
            for i, op, ins in m.blocks[b]:
                if op == 61:
                    d = m.defs.get(ins[3])
                    if d and d[0] == 65 and d[1][3] == dv:
                        load = ins[2]
                        break
            if load:
                break
        src = {load}
        ext = {}
        for b in m.order:
            for i, op, ins in m.blocks[b]:
                if op in COPY and ins[3] in src:
                    src.add(ins[2])
                elif op == 81 and ins[3] in src and len(ins) == 5:
                    ext.setdefault(ins[4], ins[2])
        self.ebase, s6 = ext.get(1), ext.get(6)
        self.sbase = None
        for b in m.order:
            for i, op, ins in m.blocks[b]:
                if op == 128 and s6 is not None and s6 in (ins[3], ins[4]):
                    self.sbase = ins[2]
                    break
            if self.sbase:
                break
        ts = set()
        for b in m.order:
            for i, op, ins in m.blocks[b]:
                if op == 65 and ins[3] == b0 and len(ins) == 5 and m.consts.get(ins[4]) == 1:
                    ts.add(ins[2])
        self.tsl = set()
        for b in m.order:
            for i, op, ins in m.blocks[b]:
                if op == 61 and ins[3] in ts:
                    self.tsl.add(ins[2])
        self.ok = None not in (self.ev, self.sv, self.ebase, self.sbase) and bool(self.tsl)

    def state_offset(self, ptr):
        m = self.m
        d = m.defs.get(ptr)
        if not d or d[0] != 65 or d[1][3] != self.sv or len(d[1]) < 6:
            return None
        di = m.defs.get(d[1][5])
        if not di or di[0] != 194:
            return None
        add = di[1][3]
        if add == self.sbase:
            return 0
        da = m.defs.get(add)
        if not da or da[0] != 128:
            return None
        a, c = da[1][3], da[1][4]
        if a == self.sbase:
            return m.consts.get(c)
        if c == self.sbase:
            return m.consts.get(a)
        return None

    def _factors(self, buf, age_off):
        m = self.m
        run = Run(m, self.ev, self.ebase, buf)
        run.walk(m.order[0], None, ())
        env, exe = run.env, run.executed
        found, seen, stores = [], set(), 0

        def walk(x, depth):
            if depth > 60 or x in seen:
                return
            seen.add(x)
            dd = m.defs.get(x)
            if not dd:
                return
            op, ins, b = dd
            a = ins[3:]
            if op == 245:
                for q in range(0, len(a), 2):
                    if a[q + 1] in exe:
                        walk(a[q], depth + 1)
                return
            if op == 133:
                for u, w in ((a[0], a[1]), (a[1], a[0])):
                    if u in self.tsl:
                        while w in m.defs and m.defs[w][0] in COPY:
                            w = m.defs[w][1][3]
                        if w in run.reads:
                            found.append(('param', run.reads[w]))
                        elif w in m.consts:
                            found.append(('const', f32(m.consts[w])))
                        else:
                            v = env.get(w, UNK)
                            found.append(('value', f32(v)) if isinstance(v, int) and not isinstance(v, bool)
                                         else ('unknown', None))
                        return
            if op == 169:
                c = env.get(a[0], UNK)
                if c is not UNK and not isinstance(c, tuple):
                    walk(a[1] if c else a[2], depth + 1)
                    return
            if op == 129 and any(y in self.tsl for y in a):
                found.append(('const', 1.0))
            for y in a:
                walk(y, depth + 1)

        for b in m.order:
            if b not in exe:
                continue
            for i, op, ins in m.blocks[b]:
                if op == 62 and self.state_offset(ins[1]) == age_off:
                    stores += 1
                    walk(ins[2], 0)
        return found, stores, run

    def find_age_rate(self, buf, age_off):
        found, stores, run = self._factors(buf, age_off)
        if not stores:
            return 'nostore', None, None
        kinds = set(found)
        if not kinds:
            return 'nostore', None, None
        if len(kinds) > 1:
            return 'multi', None, sorted(kinds, key=str)
        kind, x = kinds.pop()
        if kind == 'param':
            v = f32(struct.unpack_from('<I', buf, x)[0])
            return ('zero' if v == 0 else 'param'), x, v
        if kind == 'value':
            if x == 0:
                return 'zero', None, 0.0
            target = bits(x)
            for o in sorted(set(run.reads.values())):
                if o + 4 > len(buf) or struct.unpack_from('<I', buf, o)[0] != target:
                    continue
                trial = bytearray(buf)
                struct.pack_into('<I', trial, o, bits(x * 0.5))
                f2, s2, r2 = self._factors(bytes(trial), age_off)
                if set(f2) == {('value', x * 0.5)} or set(f2) == {('param', o)}:
                    return 'param', o, x
            return 'unknown', None, x
        return kind, None, x
