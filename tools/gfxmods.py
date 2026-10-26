import hashlib, math, re, struct, sys, threading

import kfc4
from spv_eval import Spv, f32
from vfx_age import ShaderInfo

DEFAULTS = {'smoke_life': 1.0, 'dust_life': 1.0, 'smoke_caps': 'off', 'fog': 1.0, 'weather_fog': 1.0,
            'shroud_fog': 1.0, 'night_glow': 1.0, 'day_glow': 1.0, 'vfx_distance': 1.0}
SWITCHES = ('smoke_caps',)
LIMITS = {'smoke_life': (1.0, 18.0), 'dust_life': (1.0, 8.0), 'fog': (0.0, 4.0), 'weather_fog': (0.0, 4.0),
          'shroud_fog': (0.25, 3.0), 'night_glow': (0.0, 2.0), 'day_glow': (0.0, 2.0),
          'vfx_distance': (1.0, 4.0)}

VFX_TYPE = kfc4.fnv1a32(b'keen::VfxResource')
TEX_TYPE = kfc4.fnv1a32(b'keen::RenderTextureResource')
AMBIENT_TYPE = kfc4.fnv1a32(b'keen::AmbientPostProcessingResource')
FOG3_TYPE = kfc4.fnv1a32(b'keen::VolumetricFog3Resource')
LAYOUTS = {VFX_TYPE: 0xF6128527, TEX_TYPE: 0xEF11EFBC, AMBIENT_TYPE: 0x21C7D974, FOG3_TYPE: 0xB6EC70C8}

VFX_CULL_MIN, VFX_CULL_MAX, VFX_KILL = 0, 4, 8
VFX_PARTICLES, VFX_STATE_INFOS, VFX_GPU_DATA, VFX_IMAGES = 20, 28, 44, 76
PARTICLE_SIZE, P_MAX_COUNT, P_STRIPPED_CODE, P_INIT_RANGE, P_EVAL_RANGE = 104, 20, 56, 96, 100
STATE_INFO_SIZE, MEMBER_SIZE, MEMBER_OFFSET = 12, 20, 16
IMAGE_SIZE, IMAGE_REF = 24, 4
NEVER_CULLED = 9000.0
MAX_COUNT_LIMIT = 4096
TEX_DEBUG_NAME = 60
AMBIENT_SITUATIONS, SITUATION_SIZE, SITUATION_EXTINCTION = 136, 72, 16
SITUATION_FROM, SITUATION_EMISSIVE = 0, 44
FOG3_MATERIALS, FOG3_MATERIAL_SIZE = 48, 16
FOG3_WEATHER = {'rainExtinction': 128, 'snowExtinction': 132, 'blizzardExtinction': 136}
FOG3_HEIGHT_EXTINCTION = 140
FOG3_SHROUD = {'dangerous': FOG3_MATERIALS + FOG3_MATERIAL_SIZE * 1, 'deadly': FOG3_MATERIALS + FOG3_MATERIAL_SIZE * 2}
FOG3_BARRIERS = {'dangerous': 224, 'deadly': 248}
BAKED_EXTINCTION_MAX = 1.0

MAPS = re.compile(r'_(mv|nm)_', re.I)
SMOKE = re.compile(r'smoke|steam|mist|vapou?r|haze|fog', re.I)
DUST = re.compile(r'debris_sand(?!_rock)|dust', re.I)
SKIP = re.compile(r'liquid_splash', re.I)
LOOSE = re.compile(r'smoke|steam|mist|vapou?r|haze|fog|debris_sand(?!_rock)|dust|ember|fire|flame|flake|snow'
                   r'|lea(f|ves)|petal|pollen|spore|(?<![a-z])ash', re.I)
SPARK = re.compile(r'spark', re.I)
FLAME = re.compile(r'fire|flame', re.I)
NOT_FLAME = re.compile(r'ember|spark|smoke', re.I)


def normalise(opts):
    out = {**DEFAULTS, **{n: v for n, v in opts.items() if n in DEFAULTS}}
    for n, (lo, hi) in LIMITS.items():
        out[n] = round(min(hi, max(lo, float(out[n]))), 3)
    for n in SWITCHES:
        if out[n] not in ('on', 'off'):
            raise ValueError(f'{n} must be on or off')
    return out


def active(opts):
    o = normalise(opts)
    return any(o[n] != DEFAULTS[n] for n in DEFAULTS if n != 'smoke_caps')


def u32(f):
    return struct.unpack('<I', struct.pack('<f', f))[0]


def blob_array(d, o):
    rel, cnt = struct.unpack_from('<II', d, o)
    return (o + rel, cnt) if cnt else (0, 0)


def blob_string(d, o):
    a, n = blob_array(d, o)
    return d[a:a + n].split(b'\0')[0].decode('utf-8', 'replace') if n else ''


def layout_ok(k, th):
    return k.internal_hash.get(th) == LAYOUTS[th]


def scaled(value, factor, cap=None):
    v = value * factor
    return v if cap is None else min(v, max(cap, value))


def scale_float(edits, off, old_bits, factor, label, cap=None):
    new = u32(scaled(f32(old_bits), factor, cap))
    if new != old_bits:
        edits[off] = (old_bits, new, label)


FOG_OPTIONS = ('fog', 'weather_fog', 'shroud_fog', 'night_glow', 'day_glow')


def fog_fields(k):
    out = []
    for ri, key in enumerate(k.res_keys):
        if key[1] == AMBIENT_TYPE and layout_ok(k, AMBIENT_TYPE):
            d = k.read_resource(ri)
            a, n = blob_array(d, AMBIENT_SITUATIONS)
            if n:
                fields = [('fog', a + SITUATION_SIZE * j + SITUATION_EXTINCTION, f'ambient situation {j} extinction',
                           None) for j in range(n)]
                at_night = [struct.unpack_from('<q', d, a + SITUATION_SIZE * j + SITUATION_FROM)[0] == 0
                            for j in range(n)]
                fields += [('night_glow' if at_night[j] else 'day_glow', a + SITUATION_SIZE * j + SITUATION_EMISSIVE + 4 * c,
                            f'ambient situation {j} emissive {"rgb"[c]}', None)
                           for j in range(n) for c in range(3)]
                out.append((ri, d, (a, a + SITUATION_SIZE * n), fields))
        elif key[1] == FOG3_TYPE and layout_ok(k, FOG3_TYPE):
            d = k.read_resource(ri)
            fields = [('fog', FOG3_HEIGHT_EXTINCTION, 'height fog extinction', None)]
            fields += [('weather_fog', p, name, None) for name, p in FOG3_WEATHER.items()]
            fields += [('shroud_fog', p, f'{name} shroud extinction', BAKED_EXTINCTION_MAX)
                       for name, p in FOG3_SHROUD.items()]
            fields += [('shroud_fog', p, f'{name} shroud wall extinction', None) for name, p in FOG3_BARRIERS.items()]
            out.append((ri, d, (0, len(d)), fields))
    return out


def fog_edits(k, opts):
    o = normalise(opts)
    edits = {}
    for ri, d, _, fields in fog_fields(k):
        base = k.res_vals[ri][0]
        for name, p, label, cap in fields:
            if o[name] != 1.0:
                scale_float(edits, base + p, struct.unpack_from('<I', d, p)[0], o[name], label, cap)
    return edits


class TextureNames:
    def __init__(self, k):
        self.k, self.cache = k, {}

    def __call__(self, guid):
        if guid not in self.cache:
            ri = self.k.res_by_id.get((guid, TEX_TYPE, 0))
            self.cache[guid] = blob_string(self.k.read_resource(ri), TEX_DEBUG_NAME) if ri is not None else ''
        return self.cache[guid]


def category(names):
    names = [n for n in names if n and not MAPS.search(n)]
    if any(SKIP.search(n) for n in names):
        return None
    if any(SMOKE.search(n) for n in names):
        return 'smoke'
    if any(DUST.search(n) for n in names):
        return 'dust'
    return None


def particle_kind(names):
    names = [n for n in names if n and not MAPS.search(n)]
    if any(SPARK.search(n) for n in names):
        return 'spark'
    if any(LOOSE.search(n) for n in names) and not any(SKIP.search(n) for n in names):
        return 'loose'
    return None


def is_flame(names):
    names = [n for n in names if n and not MAPS.search(n)]
    return any(FLAME.search(n) for n in names) and not any(NOT_FLAME.search(n) for n in names)


class AgeRates:
    def __init__(self, blob, cache=None):
        self.blob, self.cache, self._si = blob, cache, False
        if cache is None:
            self.ok = self._info() is not None
        else:
            self.digest = hashlib.sha1(blob).hexdigest()
            self.ok = cache.get('age shader', self.digest, lambda: self._info() is not None)

    def _info(self):
        if self._si is False:
            try:
                si = ShaderInfo(Spv(self.blob)) if self.blob[:4] == b'\x03\x02\x23\x07' else None
            except (AssertionError, KeyError, IndexError, struct.error):
                si = None
            self._si = si if si is not None and si.ok else None
        return self._si

    def find(self, buf, age_off):
        if self.cache is None:
            return self._info().find_age_rate(buf, age_off)

        def compute():
            kind, off, val = self._info().find_age_rate(buf, age_off)
            return [kind, off, val if kind == 'param' else None]

        return tuple(self.cache.get('age rate', f'{self.digest} {hashlib.sha1(buf).hexdigest()} {age_off}', compute))


def effect_edits(k, read_content, opts, exclude_keys=(), log=print, cache=None):
    o = normalise(opts)
    edits, kill_min = {}, {}
    report = {'smoke': 0, 'dust': 0, 'not_data_driven': 0, 'caps': 0, 'cull': 0}
    if not layout_ok(k, VFX_TYPE) or not layout_ok(k, TEX_TYPE):
        log('effects: VfxResource or RenderTextureResource changed layout in this build; effect options skipped')
        return edits, kill_min, report
    life = {'smoke': o['smoke_life'], 'dust': o['dust_life']}
    want_life = any(v != 1.0 for v in life.values())
    index = {key: j for j, key in enumerate(k.content_keys)} if want_life else {}
    names, shaders = TextureNames(k), {}
    exclude = {tuple(x) for x in exclude_keys}
    for ri, key in enumerate(k.res_keys):
        if key[1] != VFX_TYPE:
            continue
        d, base = k.read_resource(ri), k.res_vals[ri][0]
        if o['vfx_distance'] != 1.0:
            cmin, cmax = struct.unpack_from('<ff', d, VFX_CULL_MIN)
            if cmax < NEVER_CULLED:
                for p, label in ((VFX_CULL_MIN, 'cullingDistanceMin'), (VFX_CULL_MAX, 'cullingDistanceMax')):
                    scale_float(edits, base + p, struct.unpack_from('<I', d, p)[0], o['vfx_distance'],
                                f'res {ri} {label}')
                report['cull'] += 1
        if not want_life:
            continue
        pa, pn = blob_array(d, VFX_PARTICLES)
        sa, sn = blob_array(d, VFX_STATE_INFOS)
        ia, inn = blob_array(d, VFX_IMAGES)
        ga, gn = blob_array(d, VFX_GPU_DATA)
        if not pn or sn != pn or not gn:
            continue
        images = []
        for j in range(inn):
            q = ia + IMAGE_SIZE * j
            images.append((struct.unpack_from('<H', d, q)[0], names(d[q + IMAGE_REF:q + IMAGE_REF + 16])))
        ranges = [struct.unpack_from('<HHHH', d, pa + PARTICLE_SIZE * pi + P_INIT_RANGE) for pi in range(pn)]
        pnames = [[n for s, n in images if e0 <= s < e0 + ec or i0 <= s < i0 + ic] for i0, ic, e0, ec in ranges]
        stretched = 1.0
        for pi in range(pn):
            pb = pa + PARTICLE_SIZE * pi
            i0, ic, e0, ec = ranges[pi]
            cat = category(pnames[pi])
            if cat is None or not ec or life[cat] == 1.0:
                continue
            ckey = struct.unpack_from('<4I', d, pb + P_STRIPPED_CODE)
            if ckey in exclude or ckey not in index:
                continue
            if ckey not in shaders:
                shaders[ckey] = AgeRates(read_content(index[ckey]), cache)
            si = shaders[ckey]
            slice_at = ga + e0
            ma, mn = blob_array(d, sa + STATE_INFO_SIZE * pi)
            age = [struct.unpack_from('<I', d, ma + MEMBER_SIZE * m + MEMBER_OFFSET)[0] for m in range(mn)
                   if blob_string(d, ma + MEMBER_SIZE * m) == 'age']
            if not si.ok or len(age) != 1:
                report['not_data_driven'] += 1
                continue
            kind, off, val = si.find(d[slice_at:slice_at + ec], age[0])
            if kind != 'param' or not val or val < 0:
                report['not_data_driven'] += 1
                continue
            p = slice_at + off
            old = struct.unpack_from('<I', d, p)[0]
            edits[base + p] = (old, u32(f32(old) / life[cat]), f'res {ri} particle {pi} {cat} age rate')
            report[cat] += 1
            stretched = max(stretched, life[cat])
            if o['smoke_caps'] == 'on':
                cur = struct.unpack_from('<I', d, pb + P_MAX_COUNT)[0]
                new = min(MAX_COUNT_LIMIT, max(cur, math.ceil(cur * life[cat])))
                if new != cur:
                    edits[base + pb + P_MAX_COUNT] = (cur, new, f'res {ri} particle {pi} maxCount')
                    report['caps'] += 1
        if stretched > 1.0:
            kill = struct.unpack_from('<I', d, VFX_KILL)[0]
            kill_min[ri] = max(kill, math.ceil(kill * stretched))
    log(f'effects: age rate stretched on {report["smoke"]} smoke and {report["dust"]} dust particles '
        f'({report["not_data_driven"]} left alone: rate not in data), {report["caps"]} caps raised, '
        f'culling distance scaled on {report["cull"]} effects')
    return edits, kill_min, report


def run_deep(fn, *args, **kw):
    out = {}

    def body():
        try:
            out['r'] = fn(*args, **kw)
        except BaseException as e:
            out['e'] = e

    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 100000))
    threading.stack_size(256 * 1024 * 1024 - 4096)
    try:
        t = threading.Thread(target=body)
        t.start()
        t.join()
    finally:
        threading.stack_size(0)
        sys.setrecursionlimit(old)
    if 'e' in out:
        raise out['e']
    return out['r']
