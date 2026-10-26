import collections, math, struct

import gfxmods
import kfc4
import xxh3

DEFAULTS = {'wave_strength': 1.0, 'wave_size': 1.0, 'wave_reach': 'off'}
LIMITS = {'wave_strength': (1.0, 6.0), 'wave_size': (1.0, 4.0)}
FIELD_OPTION = {'strength': 'wave_strength', 'radius': 'wave_size'}

VFX_TYPE = gfxmods.VFX_TYPE
SEQUENCE_TYPE, SEQUENCE_LAYOUT = kfc4.fnv1a32(b'keen::SequenceResource'), 0x5B673669
BODY_SHADER = '9ca8000063907dc6a06d62d69b5332c9'
SHEET_SHADER = '48920200b07b2b07e09d50f8f6b0933f'
PARTICLE_WORDS = [
    ('5829592b-f8e5-4db4-820b-1a9a00bcdbea', 7, BODY_SHADER, {24: ('strength', 0.05), 72: ('radius', 1.0)},
     'wading wake'),
    ('cefe3b4d-26f6-4f01-875e-1fbccdb3d1e7', 9, BODY_SHADER,
     {24: ('strength', 0.15), 28: ('strength', 0.15), 76: ('radius', 1.0)}, 'entry pulse'),
    ('84518ef1-6076-43fe-b2d7-f8ea06871226', 3, BODY_SHADER,
     {24: ('strength', 0.15), 28: ('strength', 0.15), 76: ('radius', 1.0)}, 'exit pulse'),
    ('5829592b-f8e5-4db4-820b-1a9a00bcdbea', 1, SHEET_SHADER, {368: ('strength', 0.5)}, 'wading splash'),
    ('5829592b-f8e5-4db4-820b-1a9a00bcdbea', 3, SHEET_SHADER, {368: ('strength', 0.5)}, 'wading splash'),
    ('5829592b-f8e5-4db4-820b-1a9a00bcdbea', 9, SHEET_SHADER, {368: ('strength', 0.5)}, 'wading splash'),
    ('cefe3b4d-26f6-4f01-875e-1fbccdb3d1e7', 3, SHEET_SHADER, {372: ('strength', 0.5)}, 'entry splash'),
    ('cefe3b4d-26f6-4f01-875e-1fbccdb3d1e7', 5, SHEET_SHADER, {372: ('strength', 0.5)}, 'entry splash'),
    ('cefe3b4d-26f6-4f01-875e-1fbccdb3d1e7', 7, SHEET_SHADER, {372: ('strength', 0.5)}, 'entry splash'),
    ('84518ef1-6076-43fe-b2d7-f8ea06871226', 5, SHEET_SHADER, {372: ('strength', 0.5)}, 'exit splash'),
    ('84518ef1-6076-43fe-b2d7-f8ea06871226', 7, SHEET_SHADER, {372: ('strength', 0.5)}, 'exit splash'),
    ('84518ef1-6076-43fe-b2d7-f8ea06871226', 9, SHEET_SHADER, {372: ('strength', 0.5)}, 'exit splash'),
    ('d066b144-1eb9-4c16-9091-584ec2b35941', 3, SHEET_SHADER, {368: ('strength', 0.5)}, 'diving splash'),
]
SWIM_VFX = '826486f4-2c63-4d34-b0de-8a789d13795c'
SWIM_SEQUENCES = [
    '0e5668c5-aa56-45fa-bb55-cc0e03e4ee2c',
    '449ffe51-48a6-423b-90f3-c6fdfc3e1a75',
    '94e921f2-b34a-4e8a-baaa-5a11e0b049e0',
    '4b121a8c-8a22-4c21-a802-7259ec6e648a',
    '5ed02e2a-922b-4cbf-8d1e-fdaabc99ea04',
    '18eca435-f57d-4d69-afaa-4b03c6c67342',
    '81e4d219-d00b-4ce2-8025-ebabeb1c2cb3',
]
EVENT_PARAMS = 16
SWIM_FIELDS = {4: 'strength', 16: 'radius'}
SWIM_MAX = 4.0

GPC_TYPE, GPC_LAYOUT = kfc4.fnv1a32(b'keen::GpcResource'), 0x3EA062CE
GPC_GUID, GPC_NAME = 'deb6feea-1f30-5147-ab0a-d0690800f41a', 'renderer/water/water.gpc'
GPC_RASTER, RASTER_SIZE, RASTER_STAGES = 56, 136, (48, 64, 80, 96, 112)
GPC_COMPUTE, COMPUTE_SIZE, COMPUTE_VARIANTS = 64, 56, 32
VARIANT_SIZE, VARIANT_CODE, VARIANT_CHECKSUM = 40, 24, 32
GPC_STRIPPED_CODE = 104
GPC_CODE_CATEGORY = 0x80A2B51D
UPDATE_PIPELINE = 'WaterWavesUpdate'
DAMPING = (0.999, 0.9995)
BORDER_SCALE = (2.0, 4.0)

SPV_MAGIC = b'\x03\x02\x23\x07'
OP_EXT_INST_IMPORT, OP_EXT_INST, OP_TYPE_FLOAT, OP_CONSTANT, OP_FMUL = 11, 12, 22, 43, 133
GLSL_SQRT, GLSL_FCLAMP = 31, 43


class WaveError(Exception):
    pass


def normalise(opts):
    out = {**DEFAULTS, **{n: v for n, v in opts.items() if n in DEFAULTS}}
    for n, (lo, hi) in LIMITS.items():
        out[n] = round(min(hi, max(lo, float(out[n]))), 3)
    if out['wave_reach'] not in ('on', 'off'):
        raise ValueError('wave_reach must be on or off')
    return out


def bodies_active(opts):
    o = normalise(opts)
    return any(o[n] != DEFAULTS[n] for n in LIMITS)


def f32_bits(v):
    return struct.unpack('<I', struct.pack('<f', v))[0]


def f32(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def body_edits(k, opts):
    o = normalise(opts)
    factor = {field: o[name] for field, name in FIELD_OPTION.items()}
    edits, counts, skipped, data = {}, collections.Counter(), [], {}
    if not gfxmods.layout_ok(k, VFX_TYPE):
        return edits, counts, [('water bodies', 'keen::VfxResource changed layout')]

    def vfx(guid):
        ri = k.res_by_id.get((kfc4.guid_from_str(guid), VFX_TYPE, 0))
        if ri is not None and ri not in data:
            data[ri] = k.read_resource(ri)
        return ri

    def particle(ri, pi):
        d = data[ri]
        pa, pn = gfxmods.blob_array(d, gfxmods.VFX_PARTICLES)
        ga, gn = gfxmods.blob_array(d, gfxmods.VFX_GPU_DATA)
        if pi >= pn or not gn:
            return None, 0, 0
        pb = pa + gfxmods.PARTICLE_SIZE * pi
        _, _, e0, ec = struct.unpack_from('<HHHH', d, pb + gfxmods.P_INIT_RANGE)
        return d[pb + gfxmods.P_STRIPPED_CODE:pb + gfxmods.P_STRIPPED_CODE + 16].hex(), ga + e0, ec

    for guid, pi, shader, words, what in PARTICLE_WORDS:
        ri = vfx(guid)
        if ri is None:
            skipped.append((what, f'effect {guid} no longer exists'))
            continue
        key, at, size = particle(ri, pi)
        if key != shader:
            skipped.append((what, f'resource {ri} particle {pi} no longer runs shader {shader}'))
            continue
        for w, (field, vanilla) in words.items():
            bits = struct.unpack_from('<I', data[ri], at + w)[0] if w + 4 <= size else None
            if bits != f32_bits(vanilla):
                skipped.append((f'{what} {field}', f'resource {ri} particle {pi} evaluate word +{w} is not {vanilla}'))
                continue
            gfxmods.scale_float(edits, k.res_vals[ri][0] + at + w, bits, factor[field],
                                f'res {ri} p{pi} {what} {field}')
            counts['body words'] += 1
        counts['splash sheets' if shader == SHEET_SHADER else 'body particles'] += 1

    ri = vfx(SWIM_VFX)
    if ri is None or particle(ri, 0)[0] != BODY_SHADER:
        skipped.append(('swim strokes', f'effect {SWIM_VFX} is missing or no longer a body particle'))
    elif k.internal_hash.get(SEQUENCE_TYPE) != SEQUENCE_LAYOUT:
        skipped.append(('swim strokes', 'keen::SequenceResource changed layout'))
    else:
        g = kfc4.guid_from_str(SWIM_VFX)
        for sguid in SWIM_SEQUENCES:
            si = k.res_by_id.get((kfc4.guid_from_str(sguid), SEQUENCE_TYPE, 0))
            if si is None:
                skipped.append(('swim strokes', f'animation {sguid} no longer exists'))
                continue
            s, base = k.read_resource(si), k.res_vals[si][0]
            at = s.find(g)
            while at >= 0:
                p = at + EVENT_PARAMS
                vals = {off: struct.unpack_from('<I', s, p + off)[0] for off in SWIM_FIELDS if p + off + 4 <= len(s)}
                if len(vals) == len(SWIM_FIELDS) and all(0 < f32(b) <= SWIM_MAX for b in vals.values()):
                    for off, bits in vals.items():
                        field = SWIM_FIELDS[off]
                        gfxmods.scale_float(edits, base + p + off, bits, factor[field], f'res {si} swim stroke {field}')
                    counts['swim strokes'] += 1
                else:
                    skipped.append(('swim stroke', f'animation {si} event @ {at} has no stroke parameters'))
                at = s.find(g, at + 16)
    return edits, counts, skipped


def find_water_gpc(k):
    ri = k.res_by_id.get((kfc4.guid_from_str(GPC_GUID), GPC_TYPE, 0))
    if ri is not None and gfxmods.blob_string(k.read_resource(ri), 0) == GPC_NAME:
        return ri
    for ri, key in enumerate(k.res_keys):
        if key[1] == GPC_TYPE and gfxmods.blob_string(k.read_resource(ri), 0) == GPC_NAME:
            return ri
    return None


def gpc_variants(d):
    out = []
    ra, rn = gfxmods.blob_array(d, GPC_RASTER)
    for q in range(rn):
        pb = ra + RASTER_SIZE * q
        for so in RASTER_STAGES:
            va, vn = gfxmods.blob_array(d, pb + so)
            out += [(gfxmods.blob_string(d, pb), va + VARIANT_SIZE * v) for v in range(vn)]
    ca, cn = gfxmods.blob_array(d, GPC_COMPUTE)
    for q in range(cn):
        pb = ca + COMPUTE_SIZE * q
        va, vn = gfxmods.blob_array(d, pb + COMPUTE_VARIANTS)
        out += [(gfxmods.blob_string(d, pb), va + VARIANT_SIZE * v) for v in range(vn)]
    return out


def patch_update(spv):
    if len(spv) % 4 or spv[:4] != SPV_MAGIC:
        raise WaveError(f'{UPDATE_PIPELINE} is not a SPIR-V module')
    w = list(struct.unpack(f'<{len(spv) // 4}I', spv))
    ins, i = [], 5
    while i < len(w):
        n, op = w[i] >> 16, w[i] & 0xFFFF
        if n == 0 or i + n > len(w):
            raise WaveError(f'{UPDATE_PIPELINE} SPIR-V is malformed')
        ins.append((i, op, n))
        i += n
    floats = {w[p + 1] for p, op, n in ins if op == OP_TYPE_FLOAT and n == 3 and w[p + 2] == 32}
    consts = collections.defaultdict(list)
    for p, op, n in ins:
        if op == OP_CONSTANT and n == 4 and w[p + 1] in floats:
            consts[w[p + 3]].append((w[p + 2], p + 3))
    ids = lambda v: {c for c, _ in consts.get(f32_bits(v), [])}
    glsl = {w[p + 1] for p, op, n in ins if op == OP_EXT_INST_IMPORT
            and struct.pack(f'<{n - 2}I', *w[p + 2:p + n]).split(b'\0')[0] == b'GLSL.std.450'}
    ext = {w[p + 2]: (w[p + 4], w[p + 5:p + n]) for p, op, n in ins if op == OP_EXT_INST and n >= 6 and w[p + 3] in glsl}
    fmul = [(p, w[p + 2], w[p + 3], w[p + 4]) for p, op, n in ins if op == OP_FMUL and n == 5]

    old, new = DAMPING
    damp = consts.get(f32_bits(old), [])
    if len(damp) != 1:
        raise WaveError(f'expected one damping constant {old}, found {len(damp)}')
    cid, word = damp[0]
    users = [p for p, _, a, b in fmul if cid in (a, b)]
    if len(users) != 2 or w.count(cid) != 3:
        raise WaveError(f'the damping constant {old} is not used by exactly two multiplies')
    w[word] = f32_bits(new)

    zero, one = ids(0.0), ids(1.0)
    clamp01 = lambda x: x in ext and ext[x][0] == GLSL_FCLAMP and len(ext[x][1]) == 3 and ext[x][1][1] in zero \
        and ext[x][1][2] in one
    sqrt_of = {args[0] for inst, args in ext.values() if inst == GLSL_SQRT and len(args) == 1}
    old, new = BORDER_SCALE
    scale, sites = ids(old), []
    for p, r, a, b in fmul:
        for slot, x, c in ((p + 4, a, b), (p + 3, b, a)):
            outer = [y for y in ext if clamp01(y) and ext[y][1][0] == r and y in sqrt_of]
            if c in scale and clamp01(x) and outer:
                sites.append(slot)
    larger = sorted(ids(new))
    if len(sites) != 1 or not larger:
        raise WaveError(f'expected one absorbing-border multiply by {old} and a constant {new}, found {len(sites)}')
    w[sites[0]] = larger[0]
    return struct.pack(f'<{len(w)}I', *w)


def reach_patch(d, code):
    if not xxh3.check():
        raise WaveError('the XXH3 implementation failed its self-test')
    if struct.unpack_from('<I', d, GPC_STRIPPED_CODE + 16)[0] != GPC_CODE_CATEGORY:
        raise WaveError('the strippedCode reference has another category')
    variants = gpc_variants(d)
    ranges = {vb: struct.unpack_from('<II', d, vb + VARIANT_CODE) for _, vb in variants}
    mine = [vb for name, vb in variants if name == UPDATE_PIPELINE]
    if not mine:
        raise WaveError(f'no {UPDATE_PIPELINE} pipeline')
    buf, edits, done = bytearray(code), {}, {}
    for vb in mine:
        start, count = rng = ranges[vb]
        if start + count > len(code):
            raise WaveError(f'{UPDATE_PIPELINE} variant @ {vb} lies outside the code')
        for name, other in variants:
            s, c = ranges[other]
            if s < start + count and start < s + c and (name != UPDATE_PIPELINE or (s, c) != rng):
                raise WaveError(f'{UPDATE_PIPELINE} code @ {start} is shared with {name}')
        chk = struct.unpack_from('<Q', d, vb + VARIANT_CHECKSUM)[0]
        if chk and xxh3.xxh3_64(code[start:start + count]) != chk:
            raise WaveError(f'{UPDATE_PIPELINE} variant @ {vb} checksum is not the XXH3-64 of its code')
        if rng not in done:
            done[rng] = patch_update(code[start:start + count])
            buf[start:start + count] = done[rng]
        if chk:
            new = xxh3.xxh3_64(done[rng])
            for half in (0, 1):
                a, b = (chk >> 32 * half) & 0xFFFFFFFF, (new >> 32 * half) & 0xFFFFFFFF
                if a != b:
                    edits[vb + VARIANT_CHECKSUM + 4 * half] = (a, b, f'{UPDATE_PIPELINE} variant @ {vb} checksum')
    assert len(buf) == len(code)
    return bytes(buf), edits


def bad_checksums(d, code):
    out = []
    for _, vb in gpc_variants(d):
        start, count = struct.unpack_from('<II', d, vb + VARIANT_CODE)
        chk = struct.unpack_from('<Q', d, vb + VARIANT_CHECKSUM)[0]
        if chk and (start + count > len(code) or xxh3.xxh3_64(code[start:start + count]) != chk):
            out.append(vb)
    return out


def free_radius():
    return tuple(0.5 - 0.5 / s for s in BORDER_SCALE)


def lifetime_steps():
    return tuple(round(-1 / math.log(a)) for a in DAMPING)
