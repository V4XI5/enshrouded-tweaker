import struct, math, sys

UNK = None
NO_RESULT = {5, 6, 8, 62, 63, 71, 72, 99, 218, 219, 224, 225, 228, 246, 247, 249, 250, 251, 252, 253, 254, 255, 317, 4416}


class Spv:
    def __init__(self, data):
        w = struct.unpack_from('<%dI' % (len(data) // 4), data)
        assert w[0] == 0x07230203
        self.w = w
        self.ins = []
        i = 5
        while i < len(w):
            wc, op = w[i] >> 16, w[i] & 0xffff
            self.ins.append((i, op, w[i:i + wc]))
            i += wc
        self.consts, self.types, self.deco, self.defs, self.ext = {}, {}, {}, {}, {}
        self.blocks, self.order = {}, []
        self.selmerge, self.loopmerge = {}, {}
        cur = None
        TYPED_RESULT = None
        for i, op, ins in self.ins:
            if 19 <= op <= 39 and op != 37:
                self.types[ins[1]] = (op, ins)
            if op == 43: self.consts[ins[2]] = ins[3]
            if op == 41: self.consts[ins[2]] = True
            if op == 42: self.consts[ins[2]] = False
            if op == 71: self.deco.setdefault(ins[1], []).append(tuple(ins[2:]))
            if op == 11: self.ext[ins[1]] = bytes(b for x in ins[2:] for b in struct.pack('<I', x)).split(b'\0')[0].decode()
            if op == 248:
                cur = ins[1]; self.blocks[cur] = []; self.order.append(cur); continue
            if op == 56: cur = None
            if cur is not None:
                self.blocks[cur].append((i, op, ins))
                if op == 247: self.selmerge[cur] = ins[1]
                if op == 246: self.loopmerge[cur] = (ins[1], ins[2])
        for b, lst in self.blocks.items():
            for i, op, ins in lst:
                if op not in NO_RESULT and len(ins) > 2:
                    self.defs[ins[2]] = (op, ins, b)

    def var_with_binding(self, binding, dset):
        for v, ds in self.deco.items():
            d = {x[0]: x[1:] for x in ds}
            if d.get(33) == (binding,) and d.get(34) == (dset,):
                return v
        return None

    def ftype_is_float(self, t):
        x = self.types.get(t)
        return x is not None and x[0] == 22


def f32(u): return struct.unpack('<f', struct.pack('<I', u & 0xffffffff))[0]


def bits(x):
    try:
        return struct.unpack('<I', struct.pack('<f', x))[0]
    except (OverflowError, struct.error):
        return struct.unpack('<I', struct.pack('<f', math.copysign(math.inf, x)))[0]


def s32(u): return u - (1 << 32) if u & 0x80000000 else u


class Run:
    def __init__(self, m, var22, base_id, buf, overrides=None):
        self.m, self.var22, self.base_id, self.buf = m, var22, base_id, buf
        self.env = {}
        self.reads = {}
        self.oob = set()
        self.unres = set()
        self.overrides = overrides or {}
        self.executed = set()

    def val(self, x):
        if x in self.m.consts: return self.m.consts[x]
        return self.env.get(x, UNK)

    def exec_ins(self, op, ins, came):
        m = self.m
        rid = ins[2]
        a = ins[3:]
        if rid in self.overrides:
            return self.overrides[rid]
        if rid == self.base_id:
            return 0
        V = self.val
        M = 0xffffffff
        if op == 245:
            cands = []
            for k in range(0, len(a), 2):
                if came is None or a[k + 1] in came:
                    cands.append(V(a[k]))
            if not cands or any(c is UNK for c in cands): return UNK
            return cands[0] if all(c == cands[0] for c in cands) else UNK
        if op == 65:
            if a[0] == self.var22 and len(a) == 3 and V(a[1]) == 0:
                idx = V(a[2])
                if idx is UNK:
                    return ('p', UNK)
                return ('p', idx)
            return UNK
        if op == 61:
            p = V(a[0])
            if isinstance(p, tuple) and p[0] == 'p':
                if p[1] is UNK:
                    self.unres.add(rid); return UNK
                o = 4 * p[1]
                self.reads[rid] = o
                if o + 4 > len(self.buf) or o < 0:
                    self.oob.add(rid); return UNK
                return struct.unpack_from('<I', self.buf, o)[0]
            return UNK
        if op in (124, 83, 400):
            v = V(a[0]); return v if isinstance(v, (int, bool)) else UNK
        vs = [V(x) for x in a]
        if op == 169:
            c, t, f = vs
            if c is UNK: return t if (t is not UNK and t == f) else UNK
            return t if c else f
        if op == 12:
            return UNK
        if any(v is UNK or isinstance(v, tuple) for v in vs): return UNK
        try:
            if op == 128: return (vs[0] + vs[1]) & M
            if op == 130: return (vs[0] - vs[1]) & M
            if op == 132: return (vs[0] * vs[1]) & M
            if op == 134: return (vs[0] // vs[1]) if vs[1] else UNK
            if op == 137: return (vs[0] % vs[1]) if vs[1] else UNK
            if op == 194: return vs[0] >> (vs[1] & 31)
            if op == 195: return (s32(vs[0]) >> (vs[1] & 31)) & M
            if op == 196: return (vs[0] << (vs[1] & 31)) & M
            if op == 197: return vs[0] | vs[1]
            if op == 198: return vs[0] ^ vs[1]
            if op == 199: return vs[0] & vs[1]
            if op == 200: return (~vs[0]) & M
            if op == 126: return (-s32(vs[0])) & M
            if op == 170: return vs[0] == vs[1]
            if op == 171: return vs[0] != vs[1]
            if op == 172: return vs[0] > vs[1]
            if op == 174: return vs[0] >= vs[1]
            if op == 176: return vs[0] < vs[1]
            if op == 178: return vs[0] <= vs[1]
            if op == 173: return s32(vs[0]) > s32(vs[1])
            if op == 175: return s32(vs[0]) >= s32(vs[1])
            if op == 177: return s32(vs[0]) < s32(vs[1])
            if op == 179: return s32(vs[0]) <= s32(vs[1])
            if op == 164: return bool(vs[0]) == bool(vs[1])
            if op == 165: return bool(vs[0]) != bool(vs[1])
            if op == 166: return bool(vs[0]) or bool(vs[1])
            if op == 167: return bool(vs[0]) and bool(vs[1])
            if op == 168: return not vs[0]
            if op == 129: return bits(f32(vs[0]) + f32(vs[1]))
            if op == 131: return bits(f32(vs[0]) - f32(vs[1]))
            if op == 133: return bits(f32(vs[0]) * f32(vs[1]))
            if op == 136: return bits(f32(vs[0]) / f32(vs[1])) if f32(vs[1]) != 0 else UNK
            if op == 127: return vs[0] ^ 0x80000000
            if op == 112: return bits(float(vs[0]))
            if op == 111: return bits(float(s32(vs[0])))
            if op == 184: return f32(vs[0]) < f32(vs[1])
            if op == 186: return f32(vs[0]) > f32(vs[1])
            if op == 188: return f32(vs[0]) <= f32(vs[1])
            if op == 190: return f32(vs[0]) >= f32(vs[1])
            if op == 180: return f32(vs[0]) == f32(vs[1])
            if op == 182: return f32(vs[0]) != f32(vs[1])
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            return UNK
        return UNK

    def run_block_body(self, b, came):
        self.executed.add(b)
        for i, op, ins in self.m.blocks[b]:
            if op in NO_RESULT:
                continue
            if len(ins) > 2 and ins[2] in self.m.defs and self.m.defs[ins[2]][0] == op:
                self.env[ins[2]] = self.exec_ins(op, ins, came)

    @staticmethod
    def combine(d1, d2):
        out = dict(d1)
        for k, v in d2.items():
            if k in out:
                out[k] = None if (out[k] is None or v is None) else (out[k] | v)
            else:
                out[k] = v
        return out

    def loop_exits(self, h, merge, stack):
        seen, todo, exits = {h}, [h], {}
        while todo:
            b = todo.pop()
            for t in self.succ(b):
                if t == merge: continue
                if t in stack: exits[t] = None; continue
                if t not in seen: seen.add(t); todo.append(t)
        return exits

    def succ(self, b):
        i, op, ins = self.m.blocks[b][-1]
        if op == 249: return [ins[1]]
        if op == 250: return [ins[2], ins[3]]
        if op == 251: return [ins[2]] + [ins[k + 1] for k in range(3, len(ins), 2)]
        return []

    def walk(self, b, came, stack):
        acc = {}
        while True:
            if b in self.m.loopmerge:
                mg, cont = self.m.loopmerge[b]
                acc = self.combine(acc, self.loop_exits(b, mg, stack))
                if mg in stack:
                    return self.combine(acc, {mg: None})
                b, came = mg, None
                continue
            self.run_block_body(b, came)
            i, op, ins = self.m.blocks[b][-1]
            if op in (252, 253, 254, 255, 4416):
                return acc
            if op == 249:
                targets = [ins[1]]
            elif op == 250:
                c = self.val(ins[1])
                targets = [ins[2], ins[3]] if c is UNK else ([ins[2]] if c else [ins[3]])
            elif op == 251:
                sel = self.val(ins[1])
                cases = {ins[k]: ins[k + 1] for k in range(3, len(ins), 2)}
                if sel is UNK:
                    targets = [ins[2]] + list(cases.values())
                else:
                    targets = [cases.get(sel, ins[2])]
            else:
                raise RuntimeError('bad terminator %d in %d' % (op, b))
            targets = list(dict.fromkeys(targets))
            mg = self.m.selmerge.get(b)
            if mg is not None:
                st = stack + (mg,)
                ex = {}
                for t in targets:
                    ex = self.combine(ex, self.goto(t, b, st))
                if mg not in ex:
                    return self.combine(acc, ex)
                preds = ex.pop(mg)
                acc = self.combine(acc, ex)
                if mg in stack:
                    return self.combine(acc, {mg: preds})
                b, came = mg, preds
                continue
            if len(targets) == 1:
                t = targets[0]
                if t in stack:
                    return self.combine(acc, {t: {b}})
                came, b = {b}, t
                continue
            inner = [t for t in targets if t not in stack]
            if len(inner) > 1:
                raise RuntimeError('unstructured split at %d' % b)
            for t in targets:
                acc = self.combine(acc, self.goto(t, b, stack))
            return acc

    def goto(self, t, frm, stack):
        if t in stack:
            return {t: {frm}}
        return self.walk(t, {frm}, stack)
