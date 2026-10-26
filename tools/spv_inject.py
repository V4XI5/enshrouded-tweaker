import struct

from spv_eval import Spv
from vfx_age import ShaderInfo

DEFAULTS = {'pushback': 'off', 'push_radius': 0.9, 'push_strength': 2.5, 'push_lift': 1.0,
            'smoke_push': 'off', 'smoke_push_radius': 1.0, 'smoke_push_strength': 1.5, 'smoke_push_lift': 0.5,
            'smoke_push_own': 'off', 'spark_life': 1.0, 'linger_all': 'on', 'smoke_collide': 'off',
            'smoke_collide_radius': 0.25, 'smoke_collide_slide': 1.0, 'smoke_volume': 0.0, 'smoke_volume_sprites': 1.0}
LIMITS = {'push_radius': (0.3, 3.0), 'push_strength': (0.5, 10.0), 'push_lift': (0.0, 5.0),
          'smoke_push_radius': (0.3, 3.0), 'smoke_push_strength': (0.2, 10.0), 'smoke_push_lift': (0.0, 5.0),
          'spark_life': (1.0, 8.0), 'smoke_collide_radius': (0.05, 2.0), 'smoke_collide_slide': (0.0, 3.0),
          'smoke_volume': (0.0, 3.0),
          'smoke_volume_sprites': (0.0, 1.0)}
SWITCHES = ('pushback', 'smoke_push', 'smoke_push_own', 'linger_all', 'smoke_collide')
CAPSULE_HEIGHT = 1.5
ATTACH_RADIUS = 1.0
STATE_MEMBERS = {'position': (3, 0), 'velocity': (3, 0), 'collisionResting': (1, 3),
                 'collisionRestTimer': (1, 0), 'collisionEnabled': (1, 3), 'collisionHasEverCollided': (1, 3)}
LOOSE_MEMBERS = {'position': (3, 0), 'velocity': (3, 0)}
AGE_MEMBERS = {'age': (1, 0)}
PROCESS_TAG = 'debris player pushback'
LOOSE_TAG = 'particle player pushback'
EFFECT_INDEX_OFFSET = 8
EFFECT_BINDING = 40
EFFECT_PARAMETER_OFFSETS = [0, 12, 16, 32, 44, 48, 52, 56, 60]
TIME_STEP_MEMBER = 1
COLLIDE_TAG = 'particle world collision'
COLLIDE_DEPTH = 1.0
SDF_MEMBER = 3
SDF_QUERY_SAMPLES = 7
SLIDE_UPHILL = 2.0
SLIDE_HASH = (0x9E3779B9, 0x85EBCA6B)
VOLUME_TAG = 'particle fog volume'
UB_INJECT_CAPACITY, UB_INJECT_COUNTER, UB_FRUSTUM_PLANES, UB_SKIP_INJECT_SORT = 596, 600, 736, 848
TRANSPARENT_BINDINGS = (1, 2, 3)
TI_DEPTH_FADE, TI_COLOR, TI_ALPHA = 56, 88, 100
INJECT_BINDING, INJECT_SORT_BINDING, INJECT_STRIDE = 7, 8, 116
INJECT_MEMBERS = [(0, 'vec3'), (12, 'u32'), (16, 'vec4'), (32, 'vec3'), (44, 'f32'), (48, 'u32'), (52, 'u32'),
                  (56, 'f32'), (60, 'vec3'), (72, 'vec3'), (84, 'vec3'), (96, 'f32'), (100, 'vec3'), (112, 'f32')]
INJECT_SHAPE_SPHERE = 1
SORT_KEY_ZERO = 0x80000000
EVAL_BINDING = 41
EVAL_DEPTH_FADE, EVAL_COLLIDE_RADIUS, VOLUME_DENSITY_OFFSET = 48, 52, 60
VOLUME_RADIUS = 0.8
VOLUME_ALBEDO = 0.6
VOLUME_LOD = 0.03
VOLUME_MIN_DEPTH = 0.005
VOLUME_MIN_RADIUS = 0.25
VOLUME_RESERVE_SHIFT = 2
UB_CAMERA_POSITION = 660
STATE_BINDING = 42

MAGIC = 0x07230203
OP_STRING, OP_EXT_INST_IMPORT, OP_EXT_INST, OP_ENTRY_POINT = 7, 11, 12, 15
OP_TYPE_BOOL, OP_TYPE_INT, OP_TYPE_FLOAT, OP_TYPE_VECTOR = 20, 21, 22, 23
OP_TYPE_ARRAY, OP_TYPE_RUNTIME_ARRAY, OP_TYPE_STRUCT, OP_TYPE_POINTER = 28, 29, 30, 32
OP_CONSTANT_FALSE, OP_CONSTANT = 42, 43
OP_FUNCTION, OP_FUNCTION_END, OP_VARIABLE, OP_LOAD, OP_STORE, OP_ACCESS_CHAIN = 54, 56, 59, 61, 62, 65
OP_DECORATE, OP_MEMBER_DECORATE, OP_DECORATION_GROUP, OP_COMPOSITE_EXTRACT, OP_BITCAST = 71, 72, 73, 81, 124
OP_VECTOR_SHUFFLE, OP_COMPOSITE_CONSTRUCT, OP_COPY_OBJECT, OP_COPY_LOGICAL = 79, 80, 83, 400
OP_IMAGE_SAMPLE_EXPLICIT_LOD, OP_VECTOR_TIMES_SCALAR, OP_DOT = 88, 142, 148
OP_IADD, OP_FADD, OP_ISUB, OP_FSUB, OP_IMUL, OP_FMUL, OP_FDIV = 128, 129, 130, 131, 132, 133, 136
OP_CONVERT_U_TO_F = 112
OP_LOGICAL_OR, OP_LOGICAL_AND, OP_LOGICAL_NOT, OP_SELECT, OP_INOT_EQUAL, OP_ULESS_THAN = 166, 167, 168, 169, 171, 176
OP_FORD_GREATER_THAN, OP_SHIFT_RIGHT_LOGICAL, OP_BITWISE_AND, OP_ATOMIC_IADD = 186, 194, 199, 234
OP_PHI, OP_LOOP_MERGE, OP_SELECTION_MERGE, OP_LABEL = 245, 246, 247, 248
OP_BRANCH, OP_BRANCH_CONDITIONAL, OP_SWITCH, OP_UNREACHABLE = 249, 250, 251, 255
OP_MODULE_PROCESSED = 330
PLAIN_OPS = {65, 80, 86, 112, 124, 127, 128, 129, 130, 131, 132, 133, 134, 136, 137, 142, 148, 154, 155, 156,
             166, 167, 168, 169, 170, 171, 172, 174, 176, 178, 184, 186, 188, 190, 194, 196, 197, 199, 400}
TERMINATORS = {249, 250, 251, 252, 253, 254, 255, 4416, 4448, 4449}
ANNOTATIONS = {71, 72, 73, 74, 75, 332, 5632, 5633}
TYPE_DECLS = set(range(19, 39)) | {322, 327, 4472, 5341}
INT_ARITHMETIC = {126, 128, 130, 132, 134, 135, 137, 138, 139}
NO_RESULT = {8, 56, 62, 63, 99, 218, 219, 224, 225, 228, 246, 247, 249, 250, 251, 252, 253, 254, 255, 256, 257,
             317, 331, 4416, 4445, 4448, 4449, 4473, 4474, 4475, 4476, 5294, 5295}
GLSL_FABS, GLSL_SQRT, GLSL_INVERSE_SQRT, GLSL_FMIN, GLSL_UMIN, GLSL_FMAX, GLSL_FCLAMP = 4, 31, 32, 37, 38, 40, 43
OP_FORD_LESS_THAN, OP_UGREATER_THAN_EQUAL = 184, 174
UNIFORM, STORAGE_BUFFER = 2, 12
SCOPE_DEVICE, SEMANTICS_RELAXED = 1, 0
DECO_BLOCK, DECO_ARRAY_STRIDE, DECO_BINDING, DECO_SET, DECO_OFFSET, DECO_NO_CONTRACTION = 2, 6, 33, 34, 35, 42


class InjectError(Exception):
    pass


def normalise(opts):
    out = {**DEFAULTS, **{n: v for n, v in opts.items() if n in DEFAULTS and v is not None}}
    for n in SWITCHES:
        if out[n] not in ('on', 'off'):
            raise ValueError(f'{n} must be on or off')
    for n, (lo, hi) in LIMITS.items():
        out[n] = round(min(hi, max(lo, float(out[n]))), 3)
    return out


def f32_bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def instr(op, *operands):
    return [((len(operands) + 1) << 16) | op, *operands]


def opcode(ins):
    return ins[0] & 0xFFFF


def literal_string(text, words):
    data = text.encode('ascii')
    if len(data) + 1 > 4 * words:
        raise ValueError('string does not fit')
    data = data.ljust(4 * words - 1, b'.') + b'\0'
    return list(struct.unpack(f'<{words}I', data))


def decode_string(words):
    return b''.join(struct.pack('<I', x) for x in words).split(b'\0')[0].decode('ascii', 'replace')


def result_of(ins):
    op = opcode(ins)
    if op in TYPE_DECLS or op in (OP_LABEL, OP_STRING, OP_EXT_INST_IMPORT, OP_DECORATION_GROUP):
        return None, ins[1]
    if op < 19 and op not in (1, 12) or op in NO_RESULT or op in ANNOTATIONS or op == OP_MODULE_PROCESSED:
        return None, None
    return (ins[1], ins[2]) if len(ins) > 2 else (None, None)


def branch_targets(ins):
    op = opcode(ins)
    if op == OP_BRANCH:
        return [ins[1]]
    if op == OP_BRANCH_CONDITIONAL:
        return [ins[2], ins[3]]
    if op == OP_SWITCH:
        return [ins[2], *ins[4::2]]
    return []


class Module:
    def __init__(self, blob):
        if len(blob) < 20 or len(blob) % 4:
            raise InjectError('not a SPIR-V module')
        w = struct.unpack(f'<{len(blob) // 4}I', blob)
        if w[0] != MAGIC:
            raise InjectError('not a SPIR-V module')
        self.header = list(w[:5])
        self.ins = []
        i = 5
        while i < len(w):
            n = w[i] >> 16
            if n == 0 or i + n > len(w):
                raise InjectError('malformed instruction stream')
            self.ins.append(list(w[i:i + n]))
            i += n

    def to_bytes(self):
        words = self.header + [x for ins in self.ins for x in ins]
        return struct.pack(f'<{len(words)}I', *words)

    def function_range(self, label):
        start, found = None, False
        for n, ins in enumerate(self.ins):
            op = opcode(ins)
            if op == OP_FUNCTION:
                start, found = n, False
            elif op == OP_LABEL and ins[1] == label:
                found = True
            elif op == OP_FUNCTION_END and found:
                return start, n
        raise InjectError(f'block {label} is not in a function')


class Cfg:
    def __init__(self, mod, lo, hi):
        self.block, self.succ, self.order = {}, {}, []
        cur = None
        for n in range(lo, hi):
            ins = mod.ins[n]
            if opcode(ins) == OP_LABEL:
                cur = ins[1]
                self.order.append(cur)
                self.succ[cur] = []
            self.block[n] = cur
            if cur is not None and opcode(ins) in TERMINATORS:
                self.succ[cur] = branch_targets(ins)
        self.entry = self.order[0]
        self.pred = {b: [] for b in self.order}
        for b in self.order:
            for s in self.succ[b]:
                self.pred[s].append(b)
        self.reach_without = {}

    def dominates(self, d, x):
        if d == x:
            return True
        if d not in self.reach_without:
            seen = set() if d == self.entry else {self.entry}
            stack = list(seen)
            while stack:
                for s in self.succ[stack.pop()]:
                    if s != d and s not in seen:
                        seen.add(s)
                        stack.append(s)
            self.reach_without[d] = seen
        return x not in self.reach_without[d]


class Shape:
    def __init__(self, mod):
        self.types, self.typ, self.consts, self.deco, self.member_deco = {}, {}, {}, {}, {}
        self.first_function = self.first_annotation = self.glsl = None
        for n, ins in enumerate(mod.ins):
            op = opcode(ins)
            rt, rid = result_of(ins)
            if op in TYPE_DECLS:
                self.types[rid] = ins
            if rt is not None:
                self.typ[rid] = rt
            if op == OP_CONSTANT and len(ins) == 4:
                self.consts[rid] = (rt, ins[3])
            if op == OP_DECORATE:
                self.deco.setdefault(ins[1], []).append(tuple(ins[2:]))
            if op == OP_MEMBER_DECORATE and len(ins) >= 4:
                self.member_deco.setdefault((ins[1], ins[2]), {})[ins[3]] = tuple(ins[4:])
            if op == OP_EXT_INST_IMPORT and decode_string(ins[2:]) == 'GLSL.std.450':
                self.glsl = ins[1]
            if op == OP_FUNCTION and self.first_function is None:
                self.first_function = n
            if op in ANNOTATIONS and self.first_annotation is None:
                self.first_annotation = n
        if self.glsl is None or self.first_function is None or self.first_annotation is None:
            raise InjectError('missing GLSL.std.450 import, function or annotations')
        self.f32 = self.unique(lambda t: opcode(t) == OP_TYPE_FLOAT and t[2] == 32, 'f32 type')
        self.u32 = self.unique(lambda t: opcode(t) == OP_TYPE_INT and t[2:] == [32, 0], 'u32 type')
        self.bool = self.unique(lambda t: opcode(t) == OP_TYPE_BOOL, 'bool type')
        self.vec4 = self.unique(lambda t: opcode(t) == OP_TYPE_VECTOR and t[2:] == [self.f32, 4], 'vec4 type')

    def unique(self, pred, what):
        hits = [i for i, t in self.types.items() if pred(t)]
        if len(hits) != 1:
            raise InjectError(f'expected one {what}, found {len(hits)}')
        return hits[0]

    def vector(self, n):
        return self.unique(lambda t: opcode(t) == OP_TYPE_VECTOR and t[2:] == [self.f32, n], f'float{n} type')

    def member_at(self, struct_id, offset):
        hits = [j for (s, j), d in self.member_deco.items() if s == struct_id and d.get(DECO_OFFSET) == (offset,)]
        if len(hits) != 1:
            raise InjectError(f'no unique member at offset {offset} of struct {struct_id}')
        return hits[0]

    def decorations(self, i):
        return {d[0]: d[1:] for d in self.deco.get(i, [])}

    def pointer(self, storage, pointee):
        hits = sorted(i for i, t in self.types.items() if opcode(t) == OP_TYPE_POINTER and t[2:] == [storage, pointee])
        return hits[0] if hits else None

    def constant(self, type_id, bits):
        hits = sorted(i for i, (t, v) in self.consts.items() if t == type_id and v == bits)
        return hits[0] if hits else None


def descriptor(mod, shape, binding, set_=1):
    return [ins for ins in mod.ins[:shape.first_function] if opcode(ins) == OP_VARIABLE
            and shape.decorations(ins[2]).get(DECO_SET) == (set_,)
            and shape.decorations(ins[2]).get(DECO_BINDING) == (binding,)]


def update_buffer(mod, shape):
    vars_ = descriptor(mod, shape, 0)
    if len(vars_) != 1:
        raise InjectError('no unique uniform buffer at set 1, binding 0')
    ptr = shape.types.get(vars_[0][1])
    if ptr is None or opcode(ptr) != OP_TYPE_POINTER or ptr[2] != UNIFORM \
            or opcode(shape.types.get(ptr[3], [0])) != OP_TYPE_STRUCT:
        raise InjectError('set 1, binding 0 is not a uniform buffer struct')
    return vars_[0][2], ptr[3]


def uint_buffer(mod, shape, set_, binding):
    vars_ = descriptor(mod, shape, binding, set_)
    if len(vars_) != 1:
        raise InjectError(f'no unique buffer at set {set_}, binding {binding}')
    ptr = shape.types.get(vars_[0][1])
    st = shape.types.get(ptr[3]) if ptr is not None and opcode(ptr) == OP_TYPE_POINTER else None
    arr = shape.types.get(st[2]) if st is not None and opcode(st) == OP_TYPE_STRUCT and len(st) == 3 else None
    if ptr[2] != STORAGE_BUFFER or arr is None or opcode(arr) != OP_TYPE_RUNTIME_ARRAY or arr[2] != shape.u32:
        raise InjectError(f'set {set_}, binding {binding} is not a uint storage buffer')
    return vars_[0][2]


def find_player_buffer(mod, shape):
    vars_ = descriptor(mod, shape, 0)
    if len(vars_) != 1:
        raise InjectError('no unique uniform buffer at set 1, binding 0')
    var, ptr = vars_[0][2], shape.types.get(vars_[0][1])
    if ptr is None or opcode(ptr) != OP_TYPE_POINTER or ptr[2] != UNIFORM:
        raise InjectError('set 1, binding 0 is not a uniform buffer')
    st = shape.types.get(ptr[3])
    if st is None or opcode(st) != OP_TYPE_STRUCT:
        raise InjectError('set 1, binding 0 is not a struct')
    members = st[2:]
    hits = []
    for j, t in enumerate(members):
        a = shape.types.get(t)
        if (a is not None and opcode(a) == OP_TYPE_ARRAY and a[2] == shape.vec4
                and shape.consts.get(a[3]) == (shape.u32, 16) and shape.decorations(t).get(DECO_ARRAY_STRIDE) == (16,)):
            hits.append((j, a[3]))
    if len(hits) != 1:
        raise InjectError(f'expected one float4[16] member (playerPositions) in VfxUpdateBuffer, found {len(hits)}')
    pos, length = hits[0]
    if pos == 0 or members[pos - 1] != shape.u32:
        raise InjectError('playerPositions is not preceded by a uint (playerCount)')
    if len(members) <= TIME_STEP_MEMBER or members[TIME_STEP_MEMBER] != shape.f32 \
            or shape.member_deco.get((ptr[3], TIME_STEP_MEMBER), {}).get(DECO_OFFSET) != (4,):
        raise InjectError('VfxUpdateBuffer member 1 is not the float timeStep at offset 4')
    return var, pos - 1, pos, length


def find_effect_position(mod, shape, si):
    vars_ = descriptor(mod, shape, EFFECT_BINDING)
    if len(vars_) != 1:
        raise InjectError(f'no unique buffer at set 1, binding {EFFECT_BINDING}')
    var, ptr = vars_[0][2], shape.types.get(vars_[0][1])
    if ptr is None or opcode(ptr) != OP_TYPE_POINTER or ptr[2] != STORAGE_BUFFER:
        raise InjectError(f'set 1, binding {EFFECT_BINDING} is not a storage buffer')

    def struct_member(t, j):
        d = shape.types.get(t)
        return d[2 + j] if d is not None and opcode(d) == OP_TYPE_STRUCT and len(d) > 2 + j else None

    arr = shape.types.get(struct_member(ptr[3], 0))
    if arr is None or opcode(arr) != OP_TYPE_RUNTIME_ARRAY:
        raise InjectError('the effect buffer does not start with a runtime array')
    params = struct_member(arr[2], 0)
    pd = shape.types.get(params)
    if pd is None or opcode(pd) != OP_TYPE_STRUCT or len(pd) - 2 != len(EFFECT_PARAMETER_OFFSETS) \
            or [shape.member_deco.get((params, j), {}).get(DECO_OFFSET) for j in range(len(pd) - 2)] \
            != [(o,) for o in EFFECT_PARAMETER_OFFSETS] \
            or shape.member_deco.get((arr[2], 0), {}).get(DECO_OFFSET) != (0,):
        raise InjectError('the effect buffer elements do not start with VfxBaseEffectParameters')
    vec3 = pd[2]
    vt = shape.types.get(vec3)
    if vt is None or opcode(vt) != OP_TYPE_VECTOR or vt[2:] != [shape.f32, 3]:
        raise InjectError('VfxBaseEffectParameters.position is not a float3')
    loads = [ins[2] for b in si.m.order for _, op, ins in si.m.blocks[b]
             if op == OP_LOAD and si.state_offset(ins[3]) == EFFECT_INDEX_OFFSET]
    if len(loads) != 1 or shape.typ.get(loads[0]) != shape.u32:
        raise InjectError(f'expected one uint load of particle state byte {EFFECT_INDEX_OFFSET} (effect instance index)')
    return var, ptr[2], vec3, loads[0]


def shader_info(mod):
    m = Spv(mod.to_bytes())
    si = ShaderInfo(m)
    if not si.ok:
        raise InjectError('particle state buffer not recognised')
    return si


def find_store_block(mod, offsets, si=None):
    si = si or shader_info(mod)
    m = si.m
    found = {}
    for b in m.order:
        for _, op, ins in m.blocks[b]:
            if op == OP_STORE:
                off = si.state_offset(ins[1])
                if off in offsets:
                    found.setdefault(off, []).append((b, ins[1], ins[2]))
    missing = sorted(set(offsets) - set(found))
    if missing:
        raise InjectError(f'no store of particle state bytes {missing}')
    if any(len(v) != 1 for v in found.values()):
        raise InjectError('a particle state member is stored more than once')
    blocks = {v[0][0] for v in found.values()}
    if len(blocks) != 1:
        raise InjectError('the particle state is not written back in one block')
    return blocks.pop(), {off: v[0][1:] for off, v in found.items()}


class Emitter:
    def __init__(self, mod, shape):
        self.mod, self.shape = mod, shape
        self.globals, self.deco, self.code = [], [], {}

    def new_id(self):
        i = self.mod.header[3]
        self.mod.header[3] += 1
        return i

    def u32(self, v):
        return self.constant(self.shape.u32, v)

    def f32(self, x):
        return self.constant(self.shape.f32, f32_bits(x))

    def constant(self, type_id, bits):
        c = self.shape.constant(type_id, bits)
        if c is None:
            c = self.new_id()
            self.globals.append(instr(OP_CONSTANT, type_id, c, bits))
            self.shape.consts[c] = (type_id, bits)
            self.shape.typ[c] = type_id
        return c

    def pointer(self, pointee, storage=UNIFORM):
        p = self.shape.pointer(storage, pointee)
        if p is None:
            p = self.new_id()
            self.globals.append(instr(OP_TYPE_POINTER, p, storage, pointee))
            self.shape.types[p] = self.globals[-1]
        return p

    def false(self):
        hits = [ins[2] for ins in self.mod.ins[:self.shape.first_function]
                if opcode(ins) == OP_CONSTANT_FALSE and ins[1] == self.shape.bool]
        if hits:
            return hits[0]
        c = self.new_id()
        self.globals.append(instr(OP_CONSTANT_FALSE, self.shape.bool, c))
        self.shape.typ[c] = self.shape.bool
        return c

    def op(self, block, op, rt, *operands, rid=None):
        rid = self.new_id() if rid is None else rid
        self.code[block].append(instr(op, rt, rid, *operands))
        self.shape.typ[rid] = rt
        return rid

    def ext(self, block, rt, fn, *operands):
        return self.op(block, OP_EXT_INST, rt, self.shape.glsl, fn, *operands)

    def raw(self, block, op, *operands):
        self.code[block].append(instr(op, *operands))


def keep_size(body, src, int_results, tag, extra=0):
    grow = extra + sum(len(ins) for ins, s in zip(body, src) if s is None)
    minimum = 1 + (len(tag) + 4) // 4
    removed, freed = set(), 0
    for n, ins in enumerate(body):
        if freed - grow >= minimum:
            break
        if src[n] is not None and opcode(ins) == OP_DECORATE and ins[2:] == [DECO_NO_CONTRACTION]                 and ins[1] in int_results:
            removed.add(n)
            freed += len(ins)
    if freed - grow < minimum:
        raise InjectError('not enough removable decorations to keep the shader size')
    body = [ins for n, ins in enumerate(body) if n not in removed]
    src = [x for n, x in enumerate(src) if n not in removed]
    at = next(n for n, ins in enumerate(body) if opcode(ins) in ANNOTATIONS)
    body.insert(at, instr(OP_MODULE_PROCESSED, *literal_string(tag, freed - grow - 1)))
    src.insert(at, None)
    return body, src


def int_results_of(ins_list):
    return {ins[2] for ins in ins_list if opcode(ins) in INT_ARITHMETIC}


def add_pushback(blob, offsets, radius, strength, lift, loose=False, own=False):
    mod = Module(blob)
    orig = [list(ins) for ins in mod.ins]
    shape = Shape(mod)
    b0, m_count, m_pos, c_len = find_player_buffer(mod, shape)
    pos, vel = offsets['position'], offsets['velocity']
    words = {'pos': (pos, pos + 4, pos + 8), 'vel': (vel, vel + 4, vel + 8)}
    if not loose:
        words.update(resting=offsets['collisionResting'], timer=offsets['collisionRestTimer'],
                     enabled=offsets['collisionEnabled'], landed=offsets['collisionHasEverCollided'])
    wanted = {*words['pos'], *words['vel'], *(words[n] for n in ('resting', 'timer', 'enabled', 'landed') if n in words)}
    si = shader_info(mod)
    label, stores = find_store_block(mod, wanted, si)
    effect = find_effect_position(mod, shape, si) if loose and not own else None

    start = next(n for n, ins in enumerate(mod.ins) if opcode(ins) == OP_LABEL and ins[1] == label)
    term = next(n for n in range(start, len(mod.ins)) if opcode(mod.ins[n]) in TERMINATORS)
    tail_from = term - 1 if opcode(mod.ins[term - 1]) in (OP_SELECTION_MERGE, OP_LOOP_MERGE) else term
    if opcode(mod.ins[tail_from]) == OP_LOOP_MERGE:
        raise InjectError('the state write-back block is a loop header')
    if any(opcode(ins) == OP_LOOP_MERGE and ins[2] == label for ins in mod.ins):
        raise InjectError('the state write-back block is a loop continue target')
    moved = mod.ins[tail_from:term + 1]
    defs = {}
    for ins in mod.ins[shape.first_function:]:
        rid = result_of(ins)[1]
        if rid is not None:
            defs[rid] = ins

    e = Emitter(mod, shape)
    F, U, B = shape.f32, shape.u32, shape.bool
    u0, u1 = e.u32(0), e.u32(1)
    f0, f1 = e.f32(0.0), e.f32(1.0)
    c_count, c_pos = e.u32(m_count), e.u32(m_pos)
    c_height, c_inv_radius = e.f32(CAPSULE_HEIGHT), e.f32(1.0 / radius)
    c_strength, c_lift, c_eps = e.f32(strength), e.f32(lift), e.f32(1e-6)
    c_false = None if loose else e.false()
    p_uint, p_vec4 = e.pointer(U), e.pointer(shape.vec4)
    L = {n: e.new_id() for n in ('head', 'body', 'cont', 'merge')}
    for n in ('tail', 'head', 'body', 'cont', 'merge'):
        e.code[n] = []
    if loose:
        eff_var, eff_storage, vec3, eff_index = effect or (None,) * 4
        c_step = e.u32(TIME_STEP_MEMBER)
        c_attach = e.f32(ATTACH_RADIUS) if effect else None
        p_float = e.pointer(F)
        p_vec3 = e.pointer(vec3, eff_storage) if effect else None

    def as_float(value):
        d = defs.get(value)
        if d is not None and opcode(d) == OP_BITCAST and shape.typ.get(d[3]) == F:
            return d[3]
        return e.op('tail', OP_BITCAST, F, value)

    t = 'tail'
    count = e.op(t, OP_LOAD, U, e.op(t, OP_ACCESS_CHAIN, p_uint, b0, c_count))
    count = e.ext(t, U, GLSL_UMIN, count, c_len)
    if not loose:
        flags = [e.op(t, OP_INOT_EQUAL, B, e.op(t, OP_BITWISE_AND, U, stores[words[n]][1], u1), u0)
                 for n in ('enabled', 'landed')]
        count = e.op(t, OP_SELECT, U, e.op(t, OP_LOGICAL_AND, B, *flags), count, u0)
    p = [as_float(stores[w][1]) for w in words['pos']]
    v = [as_float(stores[w][1]) for w in words['vel']]
    if loose:
        dt = e.op(t, OP_LOAD, F, e.op(t, OP_ACCESS_CHAIN, p_float, b0, c_step))
    if effect:
        origin = e.op(t, OP_LOAD, vec3, e.op(t, OP_ACCESS_CHAIN, p_vec3, eff_var, u0, eff_index, u0, u0))
        origin = [e.op(t, OP_COMPOSITE_EXTRACT, F, origin, k) for k in range(3)]
    e.raw(t, OP_BRANCH, L['head'])

    h = 'head'
    e.raw(h, OP_LABEL, L['head'])
    if loose:
        i_next, v_next, p_next = e.new_id(), [e.new_id() for _ in range(3)], [e.new_id() for _ in range(3)]
    else:
        i_next, v_next, woke_next = e.new_id(), [e.new_id() for _ in range(3)], e.new_id()
    i = e.op(h, OP_PHI, U, u0, label, i_next, L['cont'])
    a = [e.op(h, OP_PHI, F, v[k], label, v_next[k], L['cont']) for k in range(3)]
    if loose:
        q = [e.op(h, OP_PHI, F, p[k], label, p_next[k], L['cont']) for k in range(3)]
    else:
        woke = e.op(h, OP_PHI, B, c_false, label, woke_next, L['cont'])
    more = e.op(h, OP_ULESS_THAN, B, i, count)
    e.raw(h, OP_LOOP_MERGE, L['merge'], L['cont'], 0)
    e.raw(h, OP_BRANCH_CONDITIONAL, more, L['body'], L['merge'])

    b = 'body'
    e.raw(b, OP_LABEL, L['body'])
    feet = e.op(b, OP_LOAD, shape.vec4, e.op(b, OP_ACCESS_CHAIN, p_vec4, b0, c_pos, i))
    if loose:
        f = [e.op(b, OP_COMPOSITE_EXTRACT, F, feet, k) for k in range(3)]

        def capsule(pt):
            dx, dy, dz = (e.op(b, OP_FSUB, F, pt[k], f[k]) for k in range(3))
            above = e.op(b, OP_FSUB, F, dy, e.ext(b, F, GLSL_FCLAMP, dy, f0, c_height))
            flat = e.op(b, OP_FADD, F, e.op(b, OP_FMUL, F, dx, dx), e.op(b, OP_FMUL, F, dz, dz))
            return dx, dz, flat, e.ext(b, F, GLSL_SQRT, e.op(b, OP_FADD, F, flat, e.op(b, OP_FMUL, F, above, above)))

        dx, dz, flat, dist = capsule(q)
        fall = e.op(b, OP_FSUB, F, f1, e.op(b, OP_FMUL, F, dist, c_inv_radius))
        if effect:
            detached = e.op(b, OP_FORD_GREATER_THAN, B, capsule(origin)[3], c_attach)
            hit = e.op(b, OP_LOGICAL_AND, B, e.op(b, OP_FORD_GREATER_THAN, B, fall, f0), detached)
        else:
            hit = e.op(b, OP_FORD_GREATER_THAN, B, fall, f0)
        inv = e.ext(b, F, GLSL_INVERSE_SQRT, e.op(b, OP_FADD, F, flat, c_eps))
        nx, nz = e.op(b, OP_FMUL, F, dx, inv), e.op(b, OP_FMUL, F, dz, inv)
        out = e.op(b, OP_FADD, F, e.op(b, OP_FMUL, F, a[0], nx), e.op(b, OP_FMUL, F, a[2], nz))
        lack = e.op(b, OP_FSUB, F, e.op(b, OP_FMUL, F, c_strength, fall), out)
        add = e.op(b, OP_SELECT, F, hit, e.ext(b, F, GLSL_FMAX, lack, f0), f0)
        e.op(b, OP_FADD, F, a[0], e.op(b, OP_FMUL, F, nx, add), rid=v_next[0])
        up = e.ext(b, F, GLSL_FMAX, a[1], e.op(b, OP_FMUL, F, c_lift, fall))
        e.op(b, OP_SELECT, F, hit, up, a[1], rid=v_next[1])
        e.op(b, OP_FADD, F, a[2], e.op(b, OP_FMUL, F, nz, add), rid=v_next[2])
        step = e.op(b, OP_FMUL, F, add, dt)
        e.op(b, OP_FADD, F, q[0], e.op(b, OP_FMUL, F, nx, step), rid=p_next[0])
        rise = e.op(b, OP_FMUL, F, e.op(b, OP_FSUB, F, v_next[1], a[1]), dt)
        e.op(b, OP_FADD, F, q[1], rise, rid=p_next[1])
        e.op(b, OP_FADD, F, q[2], e.op(b, OP_FMUL, F, nz, step), rid=p_next[2])
    else:
        dx, dy, dz = (e.op(b, OP_FSUB, F, p[k], e.op(b, OP_COMPOSITE_EXTRACT, F, feet, k)) for k in range(3))
        above = e.op(b, OP_FSUB, F, dy, e.ext(b, F, GLSL_FCLAMP, dy, f0, c_height))
        flat = e.op(b, OP_FADD, F, e.op(b, OP_FMUL, F, dx, dx), e.op(b, OP_FMUL, F, dz, dz))
        dist = e.ext(b, F, GLSL_SQRT, e.op(b, OP_FADD, F, flat, e.op(b, OP_FMUL, F, above, above)))
        fall = e.op(b, OP_FSUB, F, f1, e.op(b, OP_FMUL, F, dist, c_inv_radius))
        hit = e.op(b, OP_FORD_GREATER_THAN, B, fall, f0)
        inv = e.ext(b, F, GLSL_INVERSE_SQRT, e.op(b, OP_FADD, F, flat, c_eps))
        nx, nz = e.op(b, OP_FMUL, F, dx, inv), e.op(b, OP_FMUL, F, dz, inv)
        out = e.op(b, OP_FADD, F, e.op(b, OP_FMUL, F, a[0], nx), e.op(b, OP_FMUL, F, a[2], nz))
        lack = e.op(b, OP_FSUB, F, e.op(b, OP_FMUL, F, c_strength, fall), out)
        add = e.op(b, OP_SELECT, F, hit, e.ext(b, F, GLSL_FMAX, lack, f0), f0)
        e.op(b, OP_FADD, F, a[0], e.op(b, OP_FMUL, F, nx, add), rid=v_next[0])
        up = e.ext(b, F, GLSL_FMAX, a[1], e.op(b, OP_FMUL, F, c_lift, fall))
        e.op(b, OP_SELECT, F, hit, up, a[1], rid=v_next[1])
        e.op(b, OP_FADD, F, a[2], e.op(b, OP_FMUL, F, nz, add), rid=v_next[2])
        e.op(b, OP_LOGICAL_OR, B, woke, hit, rid=woke_next)
    e.raw(b, OP_BRANCH, L['cont'])

    c = 'cont'
    e.raw(c, OP_LABEL, L['cont'])
    e.op(c, OP_IADD, U, i, u1, rid=i_next)
    e.raw(c, OP_BRANCH, L['head'])

    mg = 'merge'
    e.raw(mg, OP_LABEL, L['merge'])
    for w, val in zip(words['vel'], a):
        e.raw(mg, OP_STORE, stores[w][0], e.op(mg, OP_BITCAST, U, val))
    if loose:
        for w, val in zip(words['pos'], q):
            e.raw(mg, OP_STORE, stores[w][0], e.op(mg, OP_BITCAST, U, val))
    else:
        for name in ('resting', 'timer'):
            ptr, val = stores[words[name]]
            e.raw(mg, OP_STORE, ptr, e.op(mg, OP_SELECT, U, woke, u0, val))

    targets = set(branch_targets(moved[-1]))
    for n, ins in enumerate(mod.ins):
        if opcode(ins) == OP_LABEL and ins[1] in targets:
            k = n + 1
            while opcode(mod.ins[k]) == OP_PHI:
                mod.ins[k][4::2] = [L['merge'] if x == label else x for x in mod.ins[k][4::2]]
                k += 1

    new_code = [*e.code['tail'], *e.code['head'], *e.code['body'], *e.code['cont'], *e.code['merge']]
    fn = shape.first_function
    body = mod.ins[:fn] + e.globals + mod.ins[fn:tail_from] + new_code + moved + mod.ins[term + 1:]
    new = ([False] * fn + [True] * len(e.globals) + [False] * (tail_from - fn) + [True] * len(new_code)
           + [False] * (len(moved) + len(mod.ins) - term - 1))
    int_results = int_results_of(orig)
    body, src = keep_size(body, [None if f else n for n, f in enumerate(new)], int_results,
                          LOOSE_TAG if loose else PROCESS_TAG)
    new = [x is None for x in src]
    mod.ins = body

    result = mod.to_bytes()
    if len(result) != len(blob):
        raise InjectError(f'size changed from {len(blob)} to {len(result)}')
    restored = [list(ins) for ins, f in zip(body, new) if not f]
    for ins in restored:
        if opcode(ins) == OP_PHI:
            ins[4::2] = [label if x == L['merge'] else x for x in ins[4::2]]
    if not same_but_dropped(orig, restored, int_results):
        raise InjectError('original instructions were changed')
    injected = {n for n, f in enumerate(new) if f}
    check_loop(mod, label, L)
    check(mod, injected, label, shape.glsl, blocks={label, *L.values()})
    return result


class Patcher:
    def __init__(self, blob):
        self.mod = Module(blob)
        self.orig = [list(ins) for ins in self.mod.ins]
        self.shape = Shape(self.mod)
        self.e = Emitter(self.mod, self.shape)
        self.at = {}
        for n, ins in enumerate(self.mod.ins):
            rid = result_of(ins)[1]
            if rid is not None:
                self.at[rid] = n
        self.edited = {}
        self.extended = {}
        self.cloned = set()
        self.label = None

    def _point(self, n):
        if n < self.shape.first_function or opcode(self.mod.ins[n]) in (OP_PHI, OP_LABEL):
            raise InjectError('cannot insert code there')
        self.e.code.setdefault(n, [])
        if self.label is None:
            self.label = next(ins[1] for ins in reversed(self.mod.ins[:n]) if opcode(ins) == OP_LABEL)
        return n

    def before(self, rid):
        return self._point(self.at[rid])

    def after(self, rid):
        n = self.at[rid] + 1
        while opcode(self.mod.ins[n]) == OP_PHI:
            n += 1
        return self._point(n)

    def redirect(self, rid, old, new):
        n = self.at[rid]
        ins = self.mod.ins[n]
        hits = [k for k in range(3, len(ins)) if ins[k] == old]
        if not hits:
            raise InjectError(f'%{rid} does not use %{old}')
        for k in hits:
            self.edit(n, k, new)

    def edit(self, n, k, value):
        self.edited.setdefault(n, {}).setdefault(k, self.mod.ins[n][k])
        self.mod.ins[n][k] = value

    def extend(self, n, *words):
        ins = self.mod.ins[n]
        self.extended.setdefault(n, len(ins))
        ins += words
        ins[0] = (len(ins) << 16) | opcode(ins)

    def relabel_phis(self, targets, old, new):
        for n, ins in enumerate(self.mod.ins):
            if opcode(ins) == OP_LABEL and ins[1] in targets:
                k = n + 1
                while opcode(self.mod.ins[k]) == OP_PHI:
                    for j in range(4, len(self.mod.ins[k]), 2):
                        if self.mod.ins[k][j] == old:
                            self.edit(k, j, new)
                    k += 1

    def finish(self, tag):
        mod, shape = self.mod, self.shape
        last_annotation = max(n for n in range(shape.first_function) if opcode(mod.ins[n]) in ANNOTATIONS)
        body, src = [], []
        for n, ins in enumerate(mod.ins):
            if n == shape.first_function:
                body += self.e.globals
                src += [None] * len(self.e.globals)
            for x in self.e.code.get(n, []):
                body.append(x)
                src.append(None)
            body.append(ins)
            src.append(n)
            if n == last_annotation:
                body += self.e.deco
                src += [None] * len(self.e.deco)
        int_results = int_results_of(self.orig)
        extra = sum(len(mod.ins[n]) - length for n, length in self.extended.items())
        size = len(mod.to_bytes()) - 4 * extra
        body, src = keep_size(body, src, int_results, tag, extra)
        mod.ins = body
        result = mod.to_bytes()
        if len(result) != size:
            raise InjectError(f'size changed from {size} to {len(result)}')
        restored = []
        for ins, s in zip(body, src):
            if s is not None:
                ins = list(ins)
                for k, old in self.edited.get(s, {}).items():
                    ins[k] = old
                if s in self.extended:
                    del ins[self.extended[s]:]
                    ins[0] = (len(ins) << 16) | opcode(ins)
                restored.append(ins)
        if not same_but_dropped(self.orig, restored, int_results):
            raise InjectError('original instructions were changed')
        checked = {n for n, s in enumerate(src) if s is None or s in self.edited or s in self.extended}
        cloned = {n for n, ins in enumerate(body) if id(ins) in self.cloned}
        check(mod, checked, self.label, shape.glsl, cloned=cloned)
        return result


def age_step_uses(m, value, dt):
    sites, seen, stack = [], set(), [value]
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        d = m.defs.get(x)
        if d is None:
            continue
        op, ins, _ = d
        if op in (OP_BITCAST, OP_COPY_OBJECT, OP_COPY_LOGICAL):
            args = [ins[3]]
        elif op == OP_PHI:
            args = list(ins[3::2])
        elif op == OP_SELECT:
            args = list(ins[4:6])
        elif op in (OP_FADD, OP_FSUB, OP_FMUL, OP_FDIV):
            args = list(ins[3:5])
            if dt in args:
                sites.append(x)
        elif op == OP_EXT_INST and ins[4] in (GLSL_FMIN, GLSL_FMAX, GLSL_FCLAMP):
            args = list(ins[5:])
        else:
            continue
        stack.extend(y for y in args if y != dt)
    return sites


def age_store(si, age_offset):
    if len(si.tsl) != 1:
        raise InjectError(f'expected one load of timeStep, found {len(si.tsl)}')
    stores = [ins for b in si.m.order for _, op, ins in si.m.blocks[b]
              if op == OP_STORE and si.state_offset(ins[1]) == age_offset]
    if len(stores) != 1:
        raise InjectError(f'expected one store of age, found {len(stores)}')
    return next(iter(si.tsl)), stores[0][2]


def scale_age_step(blob, age_offset, factor):
    p = Patcher(blob)
    si = shader_info(p.mod)
    dt, value = age_store(si, age_offset)
    if p.shape.typ.get(dt) != p.shape.f32:
        raise InjectError('timeStep is not a float')
    sites = age_step_uses(si.m, value, dt)
    if not sites:
        raise InjectError('the age update does not use timeStep')
    k = p.e.f32(1.0 / factor)
    slow = p.e.op(p.after(dt), OP_FMUL, p.shape.f32, dt, k)
    for s in sites:
        p.redirect(s, dt, slow)
    return p.finish('particle lifetime')


def linger_landed(blob, age_offset, rate, landed, rate_selects):
    p = Patcher(blob)
    si = shader_info(p.mod)
    dt, value = age_store(si, age_offset)
    m = si.m
    F = p.shape.f32

    def reaches(x):
        seen, stack = set(), [x]
        while stack:
            y = stack.pop()
            if y in rate_selects:
                return True
            if y in seen or y not in m.defs:
                continue
            seen.add(y)
            op, ins, _ = m.defs[y]
            if op in (OP_BITCAST, OP_COPY_OBJECT, OP_COPY_LOGICAL):
                stack.append(ins[3])
            elif op == OP_PHI:
                stack.extend(ins[3::2])
        return False

    hits = []
    for s in age_step_uses(m, value, dt):
        op, ins, _ = m.defs[s]
        if op == OP_FMUL:
            r = ins[4] if ins[3] == dt else ins[3]
            if reaches(r):
                hits.append((s, r))
    if len(hits) != 1:
        raise InjectError(f'expected one landing-dependent age rate, found {len(hits)}')
    s, r = hits[0]
    if p.shape.typ.get(r) != F or p.shape.typ.get(landed) != p.shape.bool:
        raise InjectError('unexpected age rate or landing condition type')
    n = p.before(s)
    capped = p.e.ext(n, F, GLSL_FMIN, r, p.e.f32(rate))
    p.redirect(s, r, p.e.op(n, OP_SELECT, F, landed, capped, r))
    return p.finish('debris linger')


def eval_float(p, si, n, offset):
    sh, e, U = p.shape, p.e, p.shape.u32
    ev = uint_buffer(p.mod, sh, 1, EVAL_BINDING)
    if ev != si.ev or sh.typ.get(si.ebase) != U:
        raise InjectError('renderer parameter slice buffer not recognised')
    index = e.op(n, OP_SHIFT_RIGHT_LOGICAL, U, e.op(n, OP_IADD, U, si.ebase, e.u32(offset)), e.u32(2))
    word = e.op(n, OP_LOAD, U, e.op(n, OP_ACCESS_CHAIN, e.pointer(U, STORAGE_BUFFER), ev, e.u32(0), index))
    return e.op(n, OP_BITCAST, sh.f32, word)


def state_float(p, si, n, offset):
    sh, e, U = p.shape, p.e, p.shape.u32
    sv = uint_buffer(p.mod, sh, 1, STATE_BINDING)
    if sv != si.sv or sh.typ.get(si.sbase) != U:
        raise InjectError('particle state buffer not recognised')
    index = e.op(n, OP_SHIFT_RIGHT_LOGICAL, U, e.op(n, OP_IADD, U, si.sbase, e.u32(offset)), e.u32(2))
    word = e.op(n, OP_LOAD, U, e.op(n, OP_ACCESS_CHAIN, e.pointer(U, STORAGE_BUFFER), sv, e.u32(0), index))
    return e.op(n, OP_BITCAST, sh.f32, word)


EVAL_INDEX_OPS = {OP_IADD, OP_ISUB, 132, OP_SHIFT_RIGHT_LOGICAL, 196, OP_PHI, OP_SELECT, OP_BITCAST, OP_COPY_OBJECT,
                  OP_COPY_LOGICAL}
WIDEN_AFTER = 40


def free_eval_words(blob, words=16):
    mod = Module(blob)
    sh = Shape(mod)
    si = shader_info(mod)
    ev, ebase = si.ev, si.ebase
    inf = float('inf')
    defs, uses = {}, {}
    for ins in mod.ins[sh.first_function:]:
        rt, rid = result_of(ins)
        if rid is None or rt is None:
            continue
        defs[rid] = ins
        for v in (ins[3::2] if opcode(ins) == OP_PHI else ins[3:]):
            uses.setdefault(v, []).append(rid)
    based, stack = {ebase}, [ebase]
    while stack:
        for u in uses.get(stack.pop(), []):
            if u not in based and opcode(defs[u]) != OP_LOAD:
                based.add(u)
                stack.append(u)

    def signed(t):
        d = sh.types.get(t)
        return d is not None and opcode(d) == OP_TYPE_INT and d[3] == 1

    def const(x):
        v = sh.consts[x][1]
        return v - (1 << 32) if v >= 1 << 31 else v

    def mul(a, b):
        return 0 if a == 0 or b == 0 else a * b

    ints = [x for x, d in defs.items() if x != ebase and opcode(sh.types.get(d[1], [0])) == OP_TYPE_INT]
    tracked = set(ints)
    bounds = {}

    def bound(x):
        if x == ebase:
            return 0, 0
        if x in sh.consts:
            return const(x), const(x)
        if x in tracked:
            return bounds.get(x)
        return (-inf, inf) if x not in defs or signed(sh.typ.get(x)) or x in based else (0, inf)

    def step(x):
        d = defs[x]
        op = opcode(d)
        if op not in EVAL_INDEX_OPS:
            return (-inf, inf) if signed(d[1]) or x in based else (0, inf)
        if op == OP_PHI:
            vals = [b for b in map(bound, d[3::2]) if b is not None]
            return (min(b[0] for b in vals), max(b[1] for b in vals)) if vals else None
        if op == OP_SELECT:
            vals = [bound(d[4]), bound(d[5])]
            return None if None in vals else (min(b[0] for b in vals), max(b[1] for b in vals))
        if op in (OP_BITCAST, OP_COPY_OBJECT, OP_COPY_LOGICAL):
            return bound(d[3])
        a, b = bound(d[3]), bound(d[4])
        if a is None or b is None:
            return None
        if op == OP_IADD:
            return a[0] + b[0], a[1] + b[1]
        if op == OP_ISUB:
            return a[0] - b[1], a[1] - b[0]
        if op == 132:
            return (mul(a[0], b[0]), mul(a[1], b[1])) if a[0] >= 0 and b[0] >= 0 else (-inf, inf)
        if d[4] not in sh.consts or not 0 <= const(d[4]) < 32:
            return -inf, inf
        k = 1 << const(d[4])
        if op == OP_SHIFT_RIGHT_LOGICAL:
            return (a[0] // k if a[0] > -inf else -inf), (a[1] // k if a[1] < inf else inf)
        return (a[0] * k, a[1] * k) if a[0] >= 0 else (-inf, inf)

    passes = 0
    while True:
        moved = False
        for x in ints:
            new = step(x)
            if new is None:
                continue
            old = bounds.get(x)
            if old is not None:
                new = (min(new[0], old[0]), max(new[1], old[1]))
                if new == old:
                    continue
                if passes >= WIDEN_AFTER:
                    new = (-inf if new[0] < old[0] else new[0], inf if new[1] > old[1] else new[1])
            bounds[x] = new
            moved = True
        if not moved:
            break
        passes += 1
    free = set(range(words))
    for ins in mod.ins[sh.first_function:]:
        if opcode(ins) != OP_ACCESS_CHAIN or ins[3] != ev:
            continue
        b = bound(ins[5]) if len(ins) == 6 and ins[5] in based else None
        if b is None:
            return set()
        free -= {w for w in range(words) if b[0] <= w <= b[1]}
    return free


def terminator(mod, n, hi):
    return next(k for k in range(n, hi) if opcode(mod.ins[k]) in TERMINATORS)


def find_sdf_query(p, cfg, lo, hi):
    mod, sh = p.mod, p.shape
    b0, ub = update_buffer(mod, sh)
    if sh.member_deco.get((ub, SDF_MEMBER), {}).get(DECO_OFFSET) != (16,):
        raise InjectError(f'VfxUpdateBuffer member {SDF_MEMBER} is not at offset 16')
    vec3 = sh.vector(3)
    at_label = {mod.ins[n][1]: n for n in range(lo, hi) if opcode(mod.ins[n]) == OP_LABEL}
    pos = {b: k for k, b in enumerate(cfg.order)}
    found = []
    for b in cfg.order:
        n = at_label[b] + 1
        while opcode(mod.ins[n]) == OP_PHI:
            n += 1
        first = mod.ins[n]
        if not (opcode(first) == OP_ACCESS_CHAIN and len(first) == 5 and first[3] == b0
                and sh.consts.get(first[4], (None, None))[1] == SDF_MEMBER):
            continue
        term = terminator(mod, n, hi)
        if opcode(mod.ins[term]) != OP_SWITCH or opcode(mod.ins[term - 1]) != OP_SELECTION_MERGE:
            continue
        merge = mod.ins[term - 1][1]
        if pos.get(merge, -1) <= pos[b]:
            continue
        blocks = cfg.order[pos[b]:pos[merge]]
        inside = set(blocks)
        if any(s not in inside and s != merge for x in blocks for s in cfg.succ[x]) \
                or any(q not in inside for x in [*blocks[1:], merge] for q in cfg.pred[x]):
            continue
        start, end = at_label[b], at_label[merge] + 1
        while opcode(mod.ins[end]) == OP_PHI:
            end += 1
        if [ins[1] for ins in mod.ins[at_label[merge] + 1:end]] != [sh.bool, sh.f32, vec3]:
            continue
        region = mod.ins[start:end]
        if sum(opcode(ins) == OP_IMAGE_SAMPLE_EXPLICIT_LOD for ins in region) != SDF_QUERY_SAMPLES \
                or any(id_positions(ins) is None for ins in region):
            continue
        defined = {result_of(ins)[1] for ins in region} - {None}
        local = {ins[k] for ins in region for k in value_positions(ins)} - defined
        local = {x for x in local if lo <= p.at.get(x, -1) < hi}
        points = [x for x in local if sh.typ.get(x) == vec3]
        if len(points) == 1:
            found.append((start, end, b, merge, points[0], local - {points[0]}))
    if len(found) != 1:
        raise InjectError(f'expected one world SDF point query, found {len(found)}')
    return found[0]


def clone_region(p, start, end, subst):
    mod, sh, e = p.mod, p.shape, p.e
    region = mod.ins[start:end]
    remap = {}
    for ins in region:
        rid = result_of(ins)[1]
        if rid is not None:
            remap[rid] = e.new_id()
    copies = []
    for ins in region:
        positions = id_positions(ins)
        if positions is None:
            raise InjectError(f'cannot copy an instruction with opcode {opcode(ins)}')
        c = list(ins)
        rt, rid = result_of(ins)
        if rid is not None:
            c[1 if opcode(ins) == OP_LABEL else 2] = remap[rid]
            if rt is not None:
                sh.typ[remap[rid]] = rt
        for k in positions:
            c[k] = remap.get(c[k], subst.get(c[k], c[k]))
        copies.append(c)
        p.cloned.add(id(c))
    for old, new in remap.items():
        for d in sh.deco.get(old, []):
            e.deco.append(instr(OP_DECORATE, new, *d))
    return copies, remap


def add_collision(blob, offsets, radius_offset=EVAL_COLLIDE_RADIUS, slide=0.0):
    p = Patcher(blob)
    mod, sh, e = p.mod, p.shape, p.e
    F, B, U = sh.f32, sh.bool, sh.u32
    vec3 = sh.vector(3)
    si = shader_info(mod)
    b0, ub = update_buffer(mod, sh)
    if slide > 0.0 and (sh.types[ub][2 + TIME_STEP_MEMBER] != F
                        or sh.member_deco.get((ub, TIME_STEP_MEMBER), {}).get(DECO_OFFSET) != (4,)):
        raise InjectError('VfxUpdateBuffer.timeStep is not a float at offset 4')
    if slide > 0.0 and sh.typ.get(si.sbase) != U:
        raise InjectError('particle state address is not a 32-bit integer')
    pw = [offsets['position'] + 4 * k for k in range(3)]
    vw = [offsets['velocity'] + 4 * k for k in range(3)]
    label, stores = find_store_block(mod, {*pw, *vw}, si)
    lo, hi = mod.function_range(label)
    cfg = Cfg(mod, lo, hi)
    if any(opcode(ins) == OP_LOOP_MERGE and label in (ins[2], cfg.block[n])
           for n, ins in enumerate(mod.ins[lo:hi], lo)):
        raise InjectError('the state write-back block is a loop header or continue target')
    n0 = p.at[label] + 1
    while opcode(mod.ins[n0]) == OP_PHI:
        n0 += 1
    end = terminator(mod, n0, hi)

    def source(w):
        cast = stores[w][1]
        d = mod.ins[p.at.get(cast, 0)]
        if opcode(d) != OP_BITCAST or not n0 <= p.at[cast] < end:
            raise InjectError(f'state word {w} is not stored as a bitcast made in the write-back block')
        x = mod.ins[p.at.get(d[3], 0)]
        if opcode(x) != OP_COMPOSITE_EXTRACT or len(x) != 5 or x[1] != F:
            raise InjectError(f'state word {w} is not a component of a float3')
        return cast, d[3], x[3], x[4]

    src = {w: source(w) for w in (*pw, *vw)}
    composites = []
    for words in (pw, vw):
        c = {src[w][2] for w in words}
        if len(c) != 1 or [src[w][3] for w in words] != [0, 1, 2] or sh.typ.get(min(c)) != vec3:
            raise InjectError('the stored position or velocity is not the components of one float3')
        c = c.pop()
        db = cfg.block.get(p.at.get(c, -1))
        if db is None or db == label or not cfg.dominates(db, label):
            raise InjectError('the stored position or velocity is not available before the write-back block')
        composites.append(c)
    pos3, vel3 = composites
    q_start, q_end, entry, merge, point, uses = find_sdf_query(p, cfg, lo, hi)
    for x in uses:
        db = cfg.block[p.at[x]]
        if db == label or not cfg.dominates(db, label):
            raise InjectError(f'the world SDF query uses %{x}, which is not available in the write-back block')
    phis = [ins[2] for ins in mod.ins[p.at[merge] + 1:q_end]]
    incoming = []
    for q in cfg.pred[merge]:
        t = mod.ins[terminator(mod, p.at[q], hi)]
        if opcode(t) == OP_BRANCH:
            incoming.append(None)
        elif opcode(t) == OP_BRANCH_CONDITIONAL and t[2] == merge != t[3]:
            incoming.append(t[1])
        else:
            raise InjectError('unexpected branch into the world SDF query merge block')
    if sum(x is not None for x in incoming) != 1:
        raise InjectError('expected one conditional branch into the world SDF query merge block')

    n = p._point(n0)
    radius = eval_float(p, si, n, radius_offset)
    P = [e.op(n, OP_COMPOSITE_EXTRACT, F, pos3, k) for k in range(3)]
    V = [e.op(n, OP_COMPOSITE_EXTRACT, F, vel3, k) for k in range(3)]
    f0 = e.f32(0.0)
    want = e.op(n, OP_FORD_GREATER_THAN, B, radius, f0)
    after = e.new_id()
    copies, remap = clone_region(p, q_start, q_end, {point: pos3})
    e.raw(n, OP_SELECTION_MERGE, after, 0)
    e.raw(n, OP_BRANCH_CONDITIONAL, want, remap[entry], after)
    e.code[n].extend(copies)

    args = []
    for q, cond in zip(cfg.pred[merge], incoming):
        args += [e.false() if cond is None else remap.get(cond, cond), remap[q]]
    found = e.op(n, OP_PHI, B, *args)
    flag, dist, normal = (remap[x] for x in phis)
    d = e.op(n, OP_SELECT, F, flag, e.ext(n, F, GLSL_FABS, dist), dist)
    N = [e.op(n, OP_COMPOSITE_EXTRACT, F, normal, k) for k in range(3)]
    near = e.op(n, OP_FORD_GREATER_THAN, B, radius, d)
    shallow = e.op(n, OP_FORD_GREATER_THAN, B, d, e.f32(-COLLIDE_DEPTH))
    hit = e.op(n, OP_LOGICAL_AND, B, found, e.op(n, OP_LOGICAL_AND, B, near, shallow))
    push = e.op(n, OP_FSUB, F, radius, d)
    dot = e.op(n, OP_FADD, F, e.op(n, OP_FADD, F, e.op(n, OP_FMUL, F, V[0], N[0]), e.op(n, OP_FMUL, F, V[1], N[1])),
               e.op(n, OP_FMUL, F, V[2], N[2]))
    into = e.ext(n, F, GLSL_FMIN, dot, f0)
    Pn = [e.op(n, OP_FADD, F, P[k], e.op(n, OP_FMUL, F, N[k], push)) for k in range(3)]
    Vn = [e.op(n, OP_FSUB, F, V[k], e.op(n, OP_FMUL, F, N[k], into)) for k in range(3)]
    if slide > 0.0:
        h = []
        x = si.sbase
        for mult in SLIDE_HASH:
            x = e.op(n, OP_IMUL, U, x, e.u32(mult))
            u = e.op(n, OP_CONVERT_U_TO_F, F, e.op(n, OP_SHIFT_RIGHT_LOGICAL, U, x, e.u32(16)))
            h.append(e.op(n, OP_FSUB, F, e.op(n, OP_FMUL, F, u, e.f32(1.0 / 32768)), e.f32(1.0)))
        H = [h[0], f0, h[1]]
        hn = e.op(n, OP_FADD, F, e.op(n, OP_FMUL, F, H[0], N[0]), e.op(n, OP_FMUL, F, H[2], N[2]))
        up = e.f32(SLIDE_UPHILL)
        ny = e.op(n, OP_FMUL, F, N[1], up)
        D = []
        for k in range(3):
            g = e.op(n, OP_FSUB, F, up if k == 1 else f0, e.op(n, OP_FMUL, F, ny, N[k]))
            t = e.op(n, OP_FSUB, F, H[k], e.op(n, OP_FMUL, F, hn, N[k]))
            D.append(e.op(n, OP_FADD, F, g, t))
        len2 = e.op(n, OP_FADD, F, e.op(n, OP_FADD, F, e.op(n, OP_FMUL, F, D[0], D[0]), e.op(n, OP_FMUL, F, D[1], D[1])),
                    e.op(n, OP_FMUL, F, D[2], D[2]))
        inv = e.ext(n, F, GLSL_INVERSE_SQRT, e.ext(n, F, GLSL_FMAX, len2, e.f32(1e-8)))
        speed = e.op(n, OP_FMUL, F, e.op(n, OP_FSUB, F, f0, into), e.op(n, OP_FMUL, F, inv, e.f32(slide)))
        dt = e.op(n, OP_LOAD, F, e.op(n, OP_ACCESS_CHAIN, e.pointer(F), b0, e.u32(TIME_STEP_MEMBER)))
        step = e.op(n, OP_FMUL, F, speed, dt)
        Vn = [e.op(n, OP_FADD, F, Vn[k], e.op(n, OP_FMUL, F, D[k], speed)) for k in range(3)]
        Pn = [e.op(n, OP_FADD, F, Pn[k], e.op(n, OP_FMUL, F, D[k], step)) for k in range(3)]
    P2 = [e.op(n, OP_SELECT, F, hit, Pn[k], P[k]) for k in range(3)]
    V2 = [e.op(n, OP_SELECT, F, hit, Vn[k], V[k]) for k in range(3)]
    e.raw(n, OP_BRANCH, after)

    e.raw(n, OP_LABEL, after)
    m2 = remap[merge]
    P3 = [e.op(n, OP_PHI, F, P2[k], m2, P[k], label) for k in range(3)]
    V3 = [e.op(n, OP_PHI, F, V2[k], m2, V[k], label) for k in range(3)]
    for words, values in ((pw, P3), (vw, V3)):
        for w, x in zip(words, values):
            p.redirect(src[w][0], src[w][1], x)
    p.relabel_phis(set(cfg.succ[label]), label, after)
    result = p.finish(COLLIDE_TAG)
    inner = {remap[b] for b in cfg.order[cfg.order.index(entry):cfg.order.index(merge) + 1]}
    check_split(p.mod, label, remap[entry], m2, after, inner)
    return result


def transparent_writes(p):
    mod, sh = p.mod, p.shape
    lists = {ins[2] for b in TRANSPARENT_BINDINGS for ins in descriptor(mod, sh, b)}
    out = []
    for ins in mod.ins[sh.first_function:]:
        if opcode(ins) != OP_STORE:
            continue
        ptr = mod.ins[p.at.get(ins[1], 0)]
        if opcode(ptr) != OP_ACCESS_CHAIN or ptr[3] not in lists:
            continue
        val = mod.ins[p.at.get(ins[2], 0)]
        con = mod.ins[p.at.get(val[3], 0)] if opcode(val) == OP_COPY_LOGICAL else val
        if len(ptr) != 6 or sh.consts.get(ptr[4], (None, None))[1] != 0 or opcode(con) != OP_COMPOSITE_CONSTRUCT:
            raise InjectError('a transparent instance is not stored as one constructed element')
        out.append((p.at[con[2]], sh.types[ptr[1]][3], ptr[5]))
    return out


def frustum_sphere(p, ub_var, planes, cfg, label):
    mod, sh = p.mod, p.shape

    def defn(x, op):
        d = mod.ins[p.at.get(x, 0)]
        return d if opcode(d) == op else None

    def dominating(x):
        b = cfg.block.get(p.at.get(x))
        return b is not None and cfg.dominates(b, label)

    hits = set()
    for n in cfg.block:
        ins = mod.ins[n]
        if opcode(ins) != OP_FORD_GREATER_THAN or not dominating(ins[4]) or not (s := defn(ins[3], OP_FADD)):
            continue
        for dot, w in ((s[3], s[4]), (s[4], s[3])):
            d, x = defn(dot, OP_DOT), defn(w, OP_COMPOSITE_EXTRACT)
            if not d or not x or x[4:] != [3]:
                continue
            for centre, xyz in ((d[3], d[4]), (d[4], d[3])):
                v = defn(xyz, OP_VECTOR_SHUFFLE)
                if not v or v[3] != v[4] or v[5:] != [0, 1, 2] or v[3] != x[3]:
                    continue
                load = defn(v[3], OP_LOAD)
                chain = load and defn(load[3], OP_ACCESS_CHAIN)
                if chain and chain[3] == ub_var and sh.consts.get(chain[4], (None, None))[1] == planes \
                        and dominating(centre):
                    hits.add((centre, ins[4]))
    if len(hits) != 1:
        raise InjectError(f'expected one sphere frustum test, found {len(hits)}')
    return hits.pop()


def sort_pointer(p):
    sh, e, U = p.shape, p.e, p.shape.u32
    for pid, t in sorted(sh.types.items()):
        if opcode(t) != OP_TYPE_POINTER or t[2] != STORAGE_BUFFER:
            continue
        blk = sh.types.get(t[3])
        if blk is None or opcode(blk) != OP_TYPE_STRUCT or len(blk) != 3 or (DECO_BLOCK,) not in sh.deco.get(t[3], []):
            continue
        arr = sh.types.get(blk[2])
        if arr is None or opcode(arr) != OP_TYPE_RUNTIME_ARRAY or sh.decorations(blk[2]).get(DECO_ARRAY_STRIDE) != (8,):
            continue
        el = sh.types.get(arr[2])
        if el is not None and opcode(el) == OP_TYPE_STRUCT and el[2:] == [U, U] \
                and [sh.member_deco.get((arr[2], j), {}).get(DECO_OFFSET) for j in (0, 1)] == [(0,), (4,)] \
                and sh.member_deco.get((t[3], 0), {}).get(DECO_OFFSET) == (0,):
            return pid
    return buffer_pointer(p, [U, U], [0, 4], 8)


def buffer_pointer(p, members, offsets, stride):
    e, sh = p.e, p.shape
    el, arr, blk = e.new_id(), e.new_id(), e.new_id()
    for ins in (instr(OP_TYPE_STRUCT, el, *members), instr(OP_TYPE_RUNTIME_ARRAY, arr, el),
                instr(OP_TYPE_STRUCT, blk, arr)):
        e.globals.append(ins)
        sh.types[ins[1]] = ins
    e.deco += [instr(OP_MEMBER_DECORATE, el, j, DECO_OFFSET, o) for j, o in enumerate(offsets)]
    e.deco += [instr(OP_DECORATE, arr, DECO_ARRAY_STRIDE, stride), instr(OP_DECORATE, blk, DECO_BLOCK),
               instr(OP_MEMBER_DECORATE, blk, 0, DECO_OFFSET, 0)]
    for j, o in enumerate(offsets):
        sh.member_deco.setdefault((el, j), {})[DECO_OFFSET] = (o,)
    sh.deco.setdefault(arr, []).append((DECO_ARRAY_STRIDE, stride))
    sh.deco.setdefault(blk, []).append((DECO_BLOCK,))
    return e.pointer(blk, STORAGE_BUFFER)


def new_buffer(p, pointer, binding):
    e = p.e
    v = e.new_id()
    e.globals.append(instr(OP_VARIABLE, pointer, v, STORAGE_BUFFER))
    p.shape.typ[v] = pointer
    e.deco += [instr(OP_DECORATE, v, DECO_SET, 1), instr(OP_DECORATE, v, DECO_BINDING, binding)]
    eps = [n for n in range(p.shape.first_function) if opcode(p.mod.ins[n]) == OP_ENTRY_POINT]
    if len(eps) != 1:
        raise InjectError(f'expected one entry point, found {len(eps)}')
    p.extend(eps[0], v)
    return v


def add_volume(blob, keep=1.0, density_offset=VOLUME_DENSITY_OFFSET, age_offset=None, lod=True):
    p = Patcher(blob)
    mod, sh, e = p.mod, p.shape, p.e
    F, U, B = sh.f32, sh.u32, sh.bool
    vec3, vec4 = sh.vector(3), sh.vec4
    si = shader_info(mod)
    if descriptor(mod, sh, INJECT_BINDING) or descriptor(mod, sh, INJECT_SORT_BINDING):
        raise InjectError('the shader already writes fog inject instances')
    b0, ub = update_buffer(mod, sh)
    members = {off: sh.member_at(ub, off) for off in (UB_INJECT_CAPACITY, UB_INJECT_COUNTER, UB_SKIP_INJECT_SORT)}
    if any(sh.types[ub][2 + j] != U for j in members.values()):
        raise InjectError('the fog inject members of VfxUpdateBuffer are not uints')
    if lod:
        camera = sh.member_at(ub, UB_CAMERA_POSITION)
        if sh.types[ub][2 + camera] != vec3:
            raise InjectError('VfxUpdateBuffer cameraPosition is not a float3')
    counters = uint_buffer(mod, sh, 0, 2)
    writes = transparent_writes(p)
    if not writes:
        raise InjectError('no transparent billboard instance stores')
    atomics = {w[2] for w in writes}
    if len(atomics) != 1 or opcode(mod.ins[p.at[min(atomics)]]) != OP_ATOMIC_IADD:
        raise InjectError('the transparent instances are not indexed by one atomic counter')
    alphas = {mod.ins[n][3 + sh.member_at(struct_id, TI_ALPHA)] for n, struct_id, _ in writes}
    if len(alphas) != 1:
        raise InjectError('the transparent instances are written with different alphas')
    alpha = alphas.pop()
    if sh.typ.get(alpha) != F:
        raise InjectError('unexpected transparent instance alpha type')

    atomic = mod.ins[p.at[min(atomics)]]
    label = next(ins[1] for ins in reversed(mod.ins[:p.at[atomic[2]]]) if opcode(ins) == OP_LABEL)
    lo, hi = mod.function_range(label)
    cfg = Cfg(mod, lo, hi)
    if any(opcode(ins) == OP_LOOP_MERGE and label in (ins[2], cfg.block[n])
           for n, ins in enumerate(mod.ins[lo:hi], lo)):
        raise InjectError('the billboard counter block is a loop header or continue target')
    centre, radius = frustum_sphere(p, b0, sh.member_at(ub, UB_FRUSTUM_PLANES), cfg, label)
    if sh.typ.get(centre) != vec3 or sh.typ.get(radius) != F:
        raise InjectError('unexpected frustum sphere types')
    n0 = p.at[label] + 1
    while opcode(mod.ins[n0]) == OP_PHI:
        n0 += 1

    types = {'vec3': vec3, 'u32': U, 'vec4': vec4, 'f32': F}
    inst_ptr = buffer_pointer(p, [types[t] for _, t in INJECT_MEMBERS], [o for o, _ in INJECT_MEMBERS], INJECT_STRIDE)
    inst_struct = sh.types[sh.types[sh.types[inst_ptr][3]][2]][2]
    v_inst = new_buffer(p, inst_ptr, INJECT_BINDING)
    v_sort = new_buffer(p, sort_pointer(p), INJECT_SORT_BINDING)

    u0, u1, f0, f1 = e.u32(0), e.u32(1), e.f32(0.0), e.f32(1.0)
    p_uint = e.pointer(U)
    L = {name: e.new_id() for name in ('add', 'write', 'sort', 'sorted', 'undo', 'added', 'rest')}

    def ub_uint(n, off):
        return e.op(n, OP_LOAD, U, e.op(n, OP_ACCESS_CHAIN, p_uint, b0, e.u32(members[off])))

    n = p._point(n0)
    tag = eval_float(p, si, n, density_offset)
    has_tag = e.op(n, OP_FORD_GREATER_THAN, B, tag, f0) if keep < 1.0 or not lod else None
    if keep < 1.0:
        faded = e.op(n, OP_SELECT, F, has_tag, e.op(n, OP_FMUL, F, alpha, e.f32(keep)), alpha)
        for k, struct_id, _ in writes:
            p.edit(k, 3 + sh.member_at(struct_id, TI_ALPHA), faded)
    r = e.op(n, OP_FMUL, F, radius, e.f32(VOLUME_RADIUS))
    depth = e.op(n, OP_FMUL, F, tag, e.ext(n, F, GLSL_FCLAMP, alpha, f0, f1))
    if age_offset is not None:
        life = e.op(n, OP_FSUB, F, f1, state_float(p, si, n, age_offset))
        depth = e.op(n, OP_FMUL, F, depth, e.ext(n, F, GLSL_FMAX, life, f0))
    if lod:
        cam = e.op(n, OP_LOAD, vec3, e.op(n, OP_ACCESS_CHAIN, e.pointer(vec3), b0, e.u32(camera)))
        to = e.op(n, OP_FSUB, vec3, centre, cam)
        dist = e.ext(n, F, GLSL_SQRT, e.op(n, OP_DOT, F, to, to))
        r0, r = r, e.ext(n, F, GLSL_FMAX, r, e.op(n, OP_FMUL, F, dist, e.f32(VOLUME_LOD)))
        q = e.op(n, OP_FDIV, F, r0, r)
        depth = e.op(n, OP_FMUL, F, depth, e.op(n, OP_FMUL, F, q, q))
        want = e.op(n, OP_FORD_GREATER_THAN, B, depth, e.f32(VOLUME_MIN_DEPTH))
    else:
        want = e.op(n, OP_LOGICAL_AND, B, has_tag, e.op(n, OP_FORD_GREATER_THAN, B, r, e.f32(VOLUME_MIN_RADIUS)))
    e.raw(n, OP_SELECTION_MERGE, L['rest'], 0)
    e.raw(n, OP_BRANCH_CONDITIONAL, want, L['add'], L['rest'])

    e.raw(n, OP_LABEL, L['add'])
    p_sb_uint = e.pointer(U, STORAGE_BUFFER)
    word = e.op(n, OP_SHIFT_RIGHT_LOGICAL, U, ub_uint(n, UB_INJECT_COUNTER), e.u32(2))
    counter = e.op(n, OP_ACCESS_CHAIN, p_sb_uint, counters, u0, word)
    scope, relaxed = e.u32(SCOPE_DEVICE), e.u32(SEMANTICS_RELAXED)
    idx = e.op(n, OP_ATOMIC_IADD, U, counter, scope, relaxed, u1)
    cap = ub_uint(n, UB_INJECT_CAPACITY)
    limit = e.op(n, OP_ISUB, U, cap, e.op(n, OP_SHIFT_RIGHT_LOGICAL, U, cap, e.u32(VOLUME_RESERVE_SHIFT)))
    fits = e.op(n, OP_ULESS_THAN, B, idx, limit)
    e.raw(n, OP_SELECTION_MERGE, L['added'], 0)
    e.raw(n, OP_BRANCH_CONDITIONAL, fits, L['write'], L['undo'])

    e.raw(n, OP_LABEL, L['write'])
    zero3 = e.op(n, OP_COMPOSITE_CONSTRUCT, vec3, f0, f0, f0)
    one3 = e.op(n, OP_COMPOSITE_CONSTRUCT, vec3, f1, f1, f1)
    albedo = e.f32(VOLUME_ALBEDO)
    scatter = e.op(n, OP_COMPOSITE_CONSTRUCT, vec3, albedo, albedo, albedo)
    values = {0: centre, 12: e.u32(INJECT_SHAPE_SPHERE), 16: e.op(n, OP_COMPOSITE_CONSTRUCT, vec4, f0, f0, f0, f1),
              32: e.op(n, OP_COMPOSITE_CONSTRUCT, vec3, r, r, r), 44: e.op(n, OP_FDIV, F, depth, r), 48: u0, 52: u0,
              56: r, 60: zero3, 72: one3, 84: zero3, 96: f1, 100: scatter, 112: f0}
    inst = e.op(n, OP_COMPOSITE_CONSTRUCT, inst_struct, *(values[o] for o, _ in INJECT_MEMBERS))
    e.raw(n, OP_STORE, e.op(n, OP_ACCESS_CHAIN, e.pointer(inst_struct, STORAGE_BUFFER), v_inst, u0, idx), inst)
    skip = e.op(n, OP_INOT_EQUAL, B, ub_uint(n, UB_SKIP_INJECT_SORT), u0)
    e.raw(n, OP_SELECTION_MERGE, L['sorted'], 0)
    e.raw(n, OP_BRANCH_CONDITIONAL, skip, L['sorted'], L['sort'])

    e.raw(n, OP_LABEL, L['sort'])
    e.raw(n, OP_STORE, e.op(n, OP_ACCESS_CHAIN, p_sb_uint, v_sort, u0, idx, u0), e.u32(SORT_KEY_ZERO))
    e.raw(n, OP_STORE, e.op(n, OP_ACCESS_CHAIN, p_sb_uint, v_sort, u0, idx, u1), idx)
    e.raw(n, OP_BRANCH, L['sorted'])
    e.raw(n, OP_LABEL, L['sorted'])
    e.raw(n, OP_BRANCH, L['added'])

    e.raw(n, OP_LABEL, L['undo'])
    e.op(n, OP_ATOMIC_IADD, U, counter, scope, relaxed, e.u32(0xFFFFFFFF))
    e.raw(n, OP_BRANCH, L['added'])
    e.raw(n, OP_LABEL, L['added'])
    e.raw(n, OP_BRANCH, L['rest'])

    e.raw(n, OP_LABEL, L['rest'])
    p.relabel_phis(set(cfg.succ[label]), label, L['rest'])
    result = p.finish(VOLUME_TAG)
    check_blocks(p.mod, [label, L['add'], L['write'], L['sort'], L['sorted'], L['undo'], L['added'], L['rest']],
                 {label: [L['add'], L['rest']], L['add']: [L['write'], L['undo']], L['write']: [L['sorted'], L['sort']],
                  L['sort']: [L['sorted']], L['sorted']: [L['added']], L['undo']: [L['added']],
                  L['added']: [L['rest']]})
    return result


def check_blocks(mod, layout, succ):
    lo, hi = mod.function_range(layout[0])
    cfg = Cfg(mod, lo, hi)
    k = cfg.order.index(layout[0])
    if cfg.order[k:k + len(layout)] != layout:
        raise InjectError('check failed: new blocks are not laid out in order')
    for b, s in succ.items():
        if cfg.succ[b] != s:
            raise InjectError(f'check failed: successors of block {b}')
    for b in layout[1:]:
        if sorted(cfg.pred[b]) != sorted(x for x, s in succ.items() if b in s):
            raise InjectError(f'check failed: predecessors of block {b}')


def check_split(mod, label, entry, merge, after, inner):
    lo, hi = mod.function_range(label)
    cfg = Cfg(mod, lo, hi)
    if (cfg.succ[label] != [entry, after] or cfg.succ[merge] != [after] or cfg.pred[entry] != [label]
            or sorted(cfg.pred[after]) != sorted([label, merge])
            or any(s not in inner for b in inner - {merge} for s in cfg.succ[b])
            or any(q not in inner for b in inner - {entry} for q in cfg.pred[b])):
        raise InjectError('check failed: collision block shape')
    k = cfg.order.index(label)
    laid = cfg.order[k + 1:k + 1 + len(inner)]
    if set(laid) != inner or laid[0] != entry or laid[-1] != merge or cfg.order[k + 1 + len(inner)] != after:
        raise InjectError('check failed: collision blocks are not laid out after the write-back block')


def same_but_dropped(orig, restored, int_results):
    j = 0
    for ins in orig:
        if j < len(restored) and restored[j] == ins:
            j += 1
        elif not (opcode(ins) == OP_DECORATE and ins[2:] == [DECO_NO_CONTRACTION] and ins[1] in int_results):
            return False
    return j == len(restored)


def check_loop(mod, label, L):
    lo, hi = mod.function_range(label)
    cfg = Cfg(mod, lo, hi)
    if (cfg.succ[label] != [L['head']] or sorted(cfg.pred[L['head']]) != sorted([label, L['cont']])
            or cfg.succ[L['head']] != [L['body'], L['merge']] or cfg.succ[L['body']] != [L['cont']]
            or cfg.succ[L['cont']] != [L['head']] or cfg.pred[L['merge']] != [L['head']]):
        raise InjectError('check failed: loop shape')
    labels = [ins[1] for ins in mod.ins if opcode(ins) == OP_LABEL]
    at = [labels.index(x) for x in (label, L['head'], L['body'], L['cont'], L['merge'])]
    if at != list(range(at[0], at[0] + 5)):
        raise InjectError('check failed: new blocks are not laid out after the write-back block')
    merges = [ins for n, ins in enumerate(mod.ins[lo:hi], lo) if opcode(ins) == OP_LOOP_MERGE and cfg.block[n] == L['head']]
    if merges != [instr(OP_LOOP_MERGE, L['merge'], L['cont'], 0)]:
        raise InjectError('check failed: loop merge')


def entry_interface(ins):
    end = next(k for k in range(3, len(ins)) if ins[k] >> 24 == 0)
    return ins[end + 1:]


def id_positions(ins):
    op, n = opcode(ins), len(ins)
    if op in PLAIN_OPS or op == OP_PHI:
        return list(range(3, n))
    forms = {OP_LOAD: [3] if n == 4 else None, OP_STORE: [1, 2] if n == 3 else None,
             OP_COMPOSITE_EXTRACT: [3], OP_VECTOR_SHUFFLE: [3, 4], OP_EXT_INST: list(range(5, n)),
             OP_IMAGE_SAMPLE_EXPLICIT_LOD: [3, 4, *range(6, n)], OP_LOOP_MERGE: [1, 2] if n == 4 else None,
             OP_SELECTION_MERGE: [1], OP_LABEL: [], OP_BRANCH: [1], OP_BRANCH_CONDITIONAL: [1, 2, 3],
             OP_SWITCH: [1, 2, *range(4, n, 2)] if n % 2 == 1 else None, OP_UNREACHABLE: []}
    return forms.get(op)


def value_positions(ins):
    op = opcode(ins)
    if op == OP_PHI:
        return list(range(3, len(ins), 2))
    if op in (OP_BRANCH_CONDITIONAL, OP_SWITCH):
        return [1]
    if op in (OP_LOOP_MERGE, OP_SELECTION_MERGE, OP_BRANCH):
        return []
    return id_positions(ins)


def check(mod, checked, label, glsl, blocks=None, cloned=frozenset()):
    def fail(what, ins=None):
        raise InjectError(f'check failed: {what}' + (f' at {ins[:6]}' if ins is not None else ''))

    defined, typ, types = {}, {}, {}
    first_fn = next(n for n, ins in enumerate(mod.ins) if opcode(ins) == OP_FUNCTION)
    for n, ins in enumerate(mod.ins):
        rt, rid = result_of(ins)
        if rid is None:
            continue
        if rid in defined or rid >= mod.header[3]:
            fail(f'result id {rid} reused or not below the bound')
        defined[rid] = n
        if rt is not None:
            typ[rid] = rt
        if opcode(ins) in TYPE_DECLS:
            types[rid] = ins
    lo, hi = mod.function_range(label)
    cfg = Cfg(mod, lo, hi)
    consts = {c[2]: c[3] for c in mod.ins[:first_fn] if opcode(c) == OP_CONSTANT and len(c) == 4}

    def visible(x, n, block):
        d = defined.get(x)
        if d is None:
            return False
        if not lo <= d < hi:
            return d < first_fn
        db = cfg.block[d]
        if db is None:
            return True
        if n is not None and db == block:
            return d < n
        return cfg.dominates(db, block)

    for n in range(lo, hi):
        ins = mod.ins[n]
        if opcode(ins) == OP_PHI and sorted(ins[4::2]) != sorted(cfg.pred[cfg.block[n]]):
            fail('phi parents differ from the block predecessors', ins)

    def scalar(t):
        d = types.get(t)
        return d is not None and opcode(d) in (OP_TYPE_FLOAT, OP_TYPE_INT, OP_TYPE_BOOL)

    def is_bool(t):
        return t in types and opcode(types[t]) == OP_TYPE_BOOL

    def is_int(t):
        return t in types and opcode(types[t]) == OP_TYPE_INT

    def float_vector(t):
        d = types.get(t)
        return d is not None and opcode(d) == OP_TYPE_VECTOR and opcode(types[d[2]]) == OP_TYPE_FLOAT

    for n in sorted(checked):
        ins = mod.ins[n]
        op = opcode(ins)
        if n < first_fn:
            if op not in (OP_MODULE_PROCESSED, OP_CONSTANT, OP_CONSTANT_FALSE, OP_TYPE_POINTER, OP_TYPE_STRUCT,
                          OP_TYPE_RUNTIME_ARRAY, OP_VARIABLE, OP_DECORATE, OP_MEMBER_DECORATE, OP_ENTRY_POINT):
                fail('unexpected global instruction', ins)
            if op in (OP_DECORATE, OP_MEMBER_DECORATE) and ins[1] not in defined:
                fail('decoration of an undefined id', ins)
            if op == OP_ENTRY_POINT:
                interface = entry_interface(ins)
                for x in interface:
                    d = defined.get(x)
                    if d is None or d >= first_fn or opcode(mod.ins[d]) != OP_VARIABLE:
                        fail(f'entry point interface id {x} is not a global variable', ins)
                if len(set(interface)) != len(interface):
                    fail('entry point interface lists a variable twice', ins)
            continue
        if not lo <= n < hi:
            fail('injected code outside the patched function', ins)
        blk = cfg.block.get(n)
        if blk is None or (blocks is not None and blk not in blocks):
            fail('injected code outside the new blocks', ins)
        if op == OP_LABEL:
            continue
        rt = result_of(ins)[0]
        if op == OP_PHI:
            for val, parent in zip(ins[3::2], ins[4::2]):
                if not visible(val, None, parent) or typ.get(val) != rt:
                    fail(f'phi value {val} from {parent}', ins)
            continue
        if n in cloned:
            for k in value_positions(ins):
                if not visible(ins[k], n, blk):
                    fail(f'operand {ins[k]} of a copied instruction not visible', ins)
            continue
        operands = {OP_LOOP_MERGE: [], OP_SELECTION_MERGE: [], OP_BRANCH: [], OP_BRANCH_CONDITIONAL: ins[1:2],
                    OP_STORE: ins[1:3], OP_EXT_INST: ins[5:], OP_COMPOSITE_EXTRACT: ins[3:4]}.get(op, ins[3:])
        for x in operands:
            if not visible(x, n, blk):
                fail(f'operand {x} not visible', ins)
        ot = [typ.get(x) for x in operands]
        if op in (OP_FADD, OP_FSUB, OP_FMUL, OP_FDIV):
            ok = (opcode(types[rt]) == OP_TYPE_FLOAT or op == OP_FSUB and float_vector(rt)) and ot == [rt, rt]
        elif op == OP_DOT:
            ok = opcode(types[rt]) == OP_TYPE_FLOAT and float_vector(ot[0]) and ot == [ot[0]] * 2 \
                and types[ot[0]][2] == rt
        elif op == OP_VECTOR_TIMES_SCALAR:
            ok = float_vector(rt) and ot == [rt, types[rt][2]]
        elif op in (OP_IADD, OP_ISUB, OP_IMUL, OP_BITWISE_AND):
            ok = is_int(rt) and ot == [rt, rt]
        elif op == OP_CONVERT_U_TO_F:
            ok = opcode(types[rt]) == OP_TYPE_FLOAT and is_int(ot[0])
        elif op == OP_SHIFT_RIGHT_LOGICAL:
            ok = is_int(rt) and ot[0] == rt and is_int(ot[1])
        elif op in (OP_LOGICAL_AND, OP_LOGICAL_OR):
            ok = is_bool(rt) and ot == [rt, rt]
        elif op == OP_LOGICAL_NOT:
            ok = is_bool(rt) and ot == [rt]
        elif op in (OP_FORD_GREATER_THAN, OP_FORD_LESS_THAN, OP_ULESS_THAN, OP_UGREATER_THAN_EQUAL, OP_INOT_EQUAL):
            ok = is_bool(rt) and ot[0] == ot[1] and scalar(ot[0])
        elif op == OP_SELECT:
            ok = is_bool(ot[0]) and ot[1] == rt == ot[2] and scalar(rt)
        elif op == OP_EXT_INST:
            ok = (ins[3] == glsl and ins[4] in (GLSL_FABS, GLSL_SQRT, GLSL_INVERSE_SQRT, GLSL_FMIN, GLSL_UMIN,
                                                 GLSL_FMAX, GLSL_FCLAMP)
                  and all(x == rt for x in ot) and (scalar(rt) or ins[4] == GLSL_FCLAMP and float_vector(rt)))
        elif op == OP_COMPOSITE_CONSTRUCT:
            vt = types.get(rt)
            ok = vt is not None and (opcode(vt) == OP_TYPE_VECTOR and ot == [vt[2]] * vt[3]
                                     or opcode(vt) == OP_TYPE_STRUCT and ot == vt[2:])
        elif op == OP_ATOMIC_IADD:
            pt = types.get(ot[0])
            ok = (len(ins) == 7 and is_int(rt) and pt is not None and opcode(pt) == OP_TYPE_POINTER
                  and pt[3] == rt and pt[2] == STORAGE_BUFFER and ot[3] == rt
                  and consts.get(ins[4]) == SCOPE_DEVICE and consts.get(ins[5]) == SEMANTICS_RELAXED)
        elif op == OP_SELECTION_MERGE:
            ok = len(ins) == 3 and opcode(mod.ins[n + 1]) in (OP_BRANCH_CONDITIONAL, OP_SWITCH)
        elif op == OP_BITCAST:
            ok = scalar(rt) and scalar(ot[0]) and ot[0] != rt
        elif op == OP_COMPOSITE_EXTRACT:
            vt = types.get(ot[0])
            ok = vt is not None and opcode(vt) == OP_TYPE_VECTOR and vt[2] == rt and len(ins) == 5 and ins[4] < vt[3]
        elif op == OP_ACCESS_CHAIN:
            ptr = types[ot[0]]
            t = ptr[3]
            for x in ins[4:]:
                d = types[t]
                if opcode(d) == OP_TYPE_STRUCT:
                    k = consts.get(x)
                    if k is None or k >= len(d) - 2:
                        fail('struct index is not a constant member index', ins)
                    t = d[2 + k]
                elif opcode(d) in (OP_TYPE_ARRAY, OP_TYPE_RUNTIME_ARRAY):
                    if not scalar(typ.get(x)) or opcode(types[typ[x]]) != OP_TYPE_INT:
                        fail('array index is not an integer', ins)
                    t = d[2]
                else:
                    fail('access chain into a non-composite', ins)
            ok = types[rt][2:] == [ptr[2], t]
        elif op == OP_LOAD:
            ok = len(ins) == 4 and types[ot[0]][3] == rt
        elif op == OP_STORE:
            ok = len(ins) == 3 and types[ot[0]][3] == ot[1]
        elif op == OP_LOOP_MERGE:
            ok = opcode(mod.ins[n + 1]) == OP_BRANCH_CONDITIONAL
        elif op in (OP_BRANCH, OP_BRANCH_CONDITIONAL):
            ok = op == OP_BRANCH or is_bool(ot[0])
        else:
            ok = False
        if not ok:
            fail('operand types', ins)
    if not ShaderInfo(Spv(mod.to_bytes())).ok:
        fail('the patched module no longer parses as a particle update shader')
