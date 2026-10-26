import struct
from spv_eval import Run, UNK

SDF_BINDINGS = (72, 73, 74, 75)
MIN_SDF_READS = 30
OP_LOAD, OP_ACCESS_CHAIN, OP_BRANCH, OP_BRANCH_COND, OP_SWITCH = 61, 65, 249, 250, 251


def _root(m, p):
    while p in m.defs and m.defs[p][0] in (OP_ACCESS_CHAIN, 66, 67):
        p = m.defs[p][1][3]
    return p


def _succ(m, b):
    op, ins = m.blocks[b][-1][1:]
    if op == OP_BRANCH:
        return [ins[1]]
    if op == OP_BRANCH_COND:
        return [ins[2], ins[3]]
    if op == OP_SWITCH:
        return [ins[2]] + [ins[q + 1] for q in range(3, len(ins), 2)]
    return []


def _loads(m, x, seen):
    if x in seen or x not in m.defs:
        return set()
    seen.add(x)
    op, ins, _ = m.defs[x]
    if op == OP_LOAD:
        return {x}
    out = set()
    for y in ins[3:]:
        out |= _loads(m, y, seen)
    return out


def collision_switch(m, si):
    sdf_vars = {m.var_with_binding(b, 1) for b in SDF_BINDINGS} - {None}
    if not sdf_vars or si.ev is None:
        return None
    reads = {b: sum(1 for _, op, ins in m.blocks[b] if op in (OP_LOAD, OP_ACCESS_CHAIN)
                    and _root(m, ins[3]) in sdf_vars) for b in m.order}

    def side(start, merge):
        if start == merge:
            return 0
        seen, todo = {start}, [start]
        while todo:
            for t in _succ(m, todo.pop()):
                if t != merge and t not in seen:
                    seen.add(t)
                    todo.append(t)
        return sum(reads[b] for b in seen)

    pos = {b: n for n, b in enumerate(m.order)}
    in_loop = set()
    for h, (merge, _) in m.loopmerge.items():
        in_loop |= {b for b in m.order if pos[h] <= pos[b] < pos.get(merge, pos[h])}
    best, best_gain = None, MIN_SDF_READS - 1
    for b in m.order:
        op, ins = m.blocks[b][-1][1:]
        if op != OP_BRANCH_COND or b not in m.selmerge or b in in_loop:
            continue
        loads = _loads(m, ins[1], set())
        if len(loads) != 1 or _root(m, m.defs[next(iter(loads))][1][3]) != si.ev:
            continue
        gain = side(ins[2], m.selmerge[b]) - side(ins[3], m.selmerge[b])
        if gain > best_gain:
            best, best_gain = b, gain
    return best


def _run(m, si, buf):
    r = Run(m, si.ev, si.ebase, bytes(buf))
    r.walk(m.order[0], None, ())
    return r


def _words(m, r, x, seen):
    if x in seen or x not in m.defs:
        return set()
    seen.add(x)
    if x in r.reads:
        return {r.reads[x]}
    out = set()
    for y in m.defs[x][1][3:]:
        out |= _words(m, r, y, seen)
    return out


def switch_state(m, si, block, buf, verify=True):
    cond = m.blocks[block][-1][2][1]
    r = _run(m, si, buf)
    if block not in r.executed or r.val(cond) is UNK:
        return 'unknown', None
    if r.val(cond):
        return 'on', None
    words = _words(m, r, cond, set())
    if len(words) != 1:
        return 'unknown', None
    off = next(iter(words))
    if off + 4 > len(buf) or struct.unpack_from('<I', buf, off)[0] != 0:
        return 'unknown', None
    if not verify:
        return 'off', off
    flipped = bytearray(buf)
    struct.pack_into('<I', flipped, off, 1)
    r2 = _run(m, si, flipped)
    if block not in r2.executed or r2.val(cond) is not True or len(r2.unres) > len(r.unres) \
            or len(r2.oob) > len(r.oob):
        return 'unknown', None
    return 'off', off
