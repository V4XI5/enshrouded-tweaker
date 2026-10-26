import argparse, bisect, collections, hashlib, json, math, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buildcache
import content_hash
import gfxmods
import kfc4
import patch_debris
import patch_debris_shader
import spv_inject
import watermods

TOOLS = os.path.dirname(os.path.abspath(__file__))
MOD_DIR = os.path.dirname(TOOLS)
STATE = os.path.join(MOD_DIR, 'state.json')
MANIFEST = os.path.join(TOOLS, 'portable_sites_build1273043.json')
PAIR = ('enshrouded.kfc', 'enshrouded.kfc_resources')
VANILLA_1273043 = patch_debris.VANILLA_SHA1
VERSION_1273043 = patch_debris.EXPECTED_VERSION
VFX_TYPE = kfc4.fnv1a32(b'keen::VfxResource')
VFX_LAYOUT = 0xF6128527
KILL_TIME_OFFSET = 8
CODE_CATEGORY = struct.pack('<I', 0x9B276059)
GPC_CODE_CATEGORY = struct.pack('<I', watermods.GPC_CODE_CATEGORY)
AIRBORNE_RATES = {'ageRate tag 1': 0.05, 'ageRate tag >=4': 0.5}
LINGER_RATES = {20: 0.05, 50: 0.02, 80: 0.0125229, 100: 0.01, 255: 0.003924, 319: 0.0031308, 1000: 0.001, 0: 0.0}
DEFAULTS = {'lights': 'on', 'linger': 100, 'kill_time': None, **gfxmods.DEFAULTS, **spv_inject.DEFAULTS,
            **watermods.DEFAULTS}
BUILD_FORMAT = 7
SLICE_HEADER = 64
TAG_DEFAULTS = {'collide': spv_inject.EVAL_COLLIDE_RADIUS, 'volume': spv_inject.VOLUME_DENSITY_OFFSET}
VOLUME_AGE = {'ageNormalized': (1, 0)}
SPARK_SHARE, SPARK_MIN_PARTICLES = 0.9, 20
LOOSE_SHARE, LOOSE_MIN_PARTICLES = 0.5, 3
LEGACY_SHADER = {'container': patch_debris_shader.SHADER_CONTAINER, 'offset': patch_debris_shader.SHADER_OFFSET,
                 'size': patch_debris_shader.SHADER_SIZE, 'vanilla_sha1': patch_debris_shader.SHADER_SHA1,
                 'vanilla_blob': os.path.join('backup', patch_debris_shader.SHADER_BACKUP),
                 'patched_blob': os.path.join('patched_shader', patch_debris_shader.SHADER_PATCHED)}


class Refuse(Exception):
    pass


def say(msg):
    print(msg, flush=True)


def mod_path(rel):
    return os.path.join(MOD_DIR, rel)


def sha1_bytes(b):
    return hashlib.sha1(b).hexdigest()


_FILE_SHA1 = {}


def file_sha1(path):
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if key not in _FILE_SHA1:
        _FILE_SHA1[key] = patch_debris.sha1(path)
    return _FILE_SHA1[key]


def pair_sha1(d):
    return {n: file_sha1(os.path.join(d, n)) if os.path.exists(os.path.join(d, n)) else None for n in PAIR}


def read_file(path):
    with open(path, 'rb') as f:
        return f.read()


def key_hex(key):
    return struct.pack('<4I', *key).hex()


def svn(version):
    return version.split('|')[0]


def ensure_closed():
    if patch_debris_shader.game_running():
        raise Refuse('Enshrouded is running; close it first')


def full_options(opts):
    opts = {n: opts.get(n, v) for n, v in DEFAULTS.items()}
    return {**opts, **gfxmods.normalise(opts), **spv_inject.normalise(opts), **watermods.normalise(opts)}


def kill_time_for(opts):
    return opts['kill_time'] if opts['kill_time'] is not None else max(180, opts['linger'] + 30)


def load_state():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'builds': {}}


def save_state(st):
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def legacy_patched_sha1s():
    out = []
    for sub in ('patched', 'patched_shader', 'patched_lights'):
        try:
            with open(mod_path(os.path.join(sub, 'patch_info.json')), encoding='utf-8') as f:
                out.append({n: d for n, d in json.load(f)['sha1'].items() if n in PAIR})
        except (FileNotFoundError, KeyError):
            pass
    return out


def all_shaders(rec):
    return ([rec['shader']] if rec and rec.get('shader') else []) + (rec.get('extra_shaders', []) if rec else [])


def shader_records(st):
    out = {}
    recs = [sh for b in st['builds'].values() for sh in all_shaders(b)] + st.get('shader_history', [])
    for rec in [LEGACY_SHADER] + recs:
        out.setdefault((rec['container'], rec['offset'], rec['size'], rec['vanilla_sha1']), []).append(rec)
    return list(out.values())


def remember_shader(st, rec):
    history = st.setdefault('shader_history', [])
    for sh in all_shaders(rec):
        if all(h['patched_sha1'] != sh['patched_sha1'] for h in history):
            history.append(sh)


def patched_sha1s(recs):
    return {r['patched_sha1'] for r in recs if r.get('patched_sha1')}


def dat_file(game_dir, container):
    return os.path.join(game_dir, f'enshrouded_{container:03d}.dat')


def read_dat(game_dir, container, offset, size):
    with open(dat_file(game_dir, container), 'rb') as f:
        f.seek(offset)
        return f.read(size)


def write_dat(game_dir, container, offset, blob):
    ensure_closed()
    path = dat_file(game_dir, container)
    with open(path, 'r+b') as f:
        f.seek(offset)
        f.write(blob)
    if read_dat(game_dir, container, offset, len(blob)) != blob:
        raise SystemExit(f'readback of {len(blob)} bytes at {path} @ {offset} failed')
    say(f'wrote {len(blob)} bytes (sha1 {sha1_bytes(blob)}) to {os.path.basename(path)} @ {offset}')


def operand_words(blob):
    sel = parse_shader(blob)
    return sorted(4 * (w + 4) for w in sel[0]) if sel else []


def own_bytes(cur, vanilla, operands):
    if len(cur) != len(vanilla) or not operands:
        return False
    buf = bytearray(cur)
    for o in operands:
        buf[o:o + 4] = vanilla[o:o + 4]
    return bytes(buf) == vanilla


def own_shader(cur, vanilla, operands, known):
    return own_bytes(cur, vanilla, operands) or sha1_bytes(cur) in known


def region_fix(game_dir, k, recs):
    rec = recs[0]
    try:
        vanilla = read_file(mod_path(rec['vanilla_blob']))
    except FileNotFoundError:
        return None
    if sha1_bytes(vanilla) != rec['vanilla_sha1']:
        raise SystemExit(f'{rec["vanilla_blob"]} was modified')
    operands, known = operand_words(vanilla), patched_sha1s(recs)
    cur = read_dat(game_dir, rec['container'], rec['offset'], rec['size'])
    if cur == vanilla or not own_shader(cur, vanilla, operands, known):
        return None
    lo, hi = rec['offset'], rec['offset'] + rec['size']
    covering = [j for j, (off, _, ci, _) in enumerate(k.content_vals)
                if ci == rec['container'] and off < hi and lo < off + k.content_keys[j][0]]

    def satisfies(region):
        for j in covering:
            off, size = k.content_vals[j][0], k.content_keys[j][0]
            data = bytearray(read_dat(game_dir, rec['container'], off, size))
            a, b = max(off, lo), min(off + size, hi)
            data[a - off:b - off] = region[a - lo:b - lo]
            if content_hash.content_key(bytes(data)) != k.content_keys[j]:
                return False
        return True

    if satisfies(cur):
        return None
    candidates = [vanilla] + [read_file(mod_path(r['patched_blob'])) for r in recs
                              if r.get('patched_blob') and os.path.exists(mod_path(r['patched_blob']))]
    for blob in candidates:
        if (blob == vanilla or own_shader(blob, vanilla, operands, known)) and satisfies(blob):
            return blob
    raise SystemExit(f'enshrouded_{rec["container"]:03d}.dat @ {rec["offset"]} does not match the installed index; '
                     'run Steam "Verify integrity of game files"')


def unpoison(game_dir, k, st, skip=()):
    for recs in shader_records(st):
        if (recs[0]['container'], recs[0]['offset']) in skip:
            continue
        blob = region_fix(game_dir, k, recs)
        if blob is not None:
            say(f'putting back the shader bytes the installed index expects at '
                f'enshrouded_{recs[0]["container"]:03d}.dat @ {recs[0]["offset"]}')
            write_dat(game_dir, recs[0]['container'], recs[0]['offset'], blob)


def mods_installed(game_dir):
    try:
        version, cur = kfc4.KFC(game_dir).version, pair_sha1(game_dir)
        return (any(rec['patched'] == cur for v, rec in load_state()['builds'].items() if v == version)
                or (version == VERSION_1273043 and cur in legacy_patched_sha1s()))
    except (Exception, SystemExit):
        return False


def consistent(game_dir):
    try:
        k = kfc4.KFC(game_dir)
        return all(region_fix(game_dir, k, recs) is None for recs in shader_records(load_state()))
    except (Exception, SystemExit):
        return False


def parse_shader(blob):
    if len(blob) < 20 or len(blob) % 4 or blob[:4] != b'\x03\x02\x23\x07':
        return None
    w = struct.unpack(f'<{len(blob) // 4}I', blob)
    floats, consts, selects = set(), {}, []
    i = 5
    while i < len(w):
        n, op = w[i] >> 16, w[i] & 0xFFFF
        if n == 0 or i + n > len(w):
            return None
        a = w[i + 1:i + n]
        if op == 22 and len(a) >= 2 and a[1] == 32:
            floats.add(a[0])
        elif op == 43 and len(a) == 3 and a[0] in floats:
            consts[a[1]] = struct.unpack('<f', struct.pack('<I', a[2]))[0]
        elif op == 169 and len(a) == 5 and a[0] in floats:
            selects.append((i, a))
        i += n
    found, one = {}, None
    for label, airborne in AIRBORNE_RATES.items():
        hits = [(i, a) for i, a in selects if near(consts.get(a[3]), 1.0) and near(consts.get(a[4]), airborne)]
        if len(hits) != 1 or (one is not None and hits[0][1][3] != one):
            return None
        one = hits[0][1][3]
        found[hits[0][0]] = label
    return found, one, consts


def near(x, y):
    if x is None:
        return False
    return abs(x - y) <= 1e-5 * abs(y) if y else x == 0.0


def rate_constant(consts, rate):
    ids = sorted(c for c, v in consts.items() if near(v, rate))
    if not ids:
        raise Refuse(f'the debris shader in this build has no constant {rate}; pick another --linger')
    return ids[0]


def patch_selects(blob, selects, one_id, rate_id):
    buf = bytearray(blob)
    for word in selects:
        assert struct.unpack_from('<I', buf, 4 * (word + 4))[0] == one_id
        struct.pack_into('<I', buf, 4 * (word + 4), rate_id)
    diff = {i for i in range(0, len(buf), 4) if buf[i:i + 4] != blob[i:i + 4]}
    assert diff == {4 * (word + 4) for word in selects}
    return bytes(buf)


def key_of(blob, cache=None):
    if cache is None:
        return content_hash.content_key(blob)
    return tuple(cache.get('content key', sha1_bytes(blob), lambda: content_hash.content_key(blob)))


def content_blob(k, j, game_dir, vanilla_dir, save=False, cache=None):
    key = k.content_keys[j]
    off, _, container, _ = k.content_vals[j]
    saved = [os.path.join(vanilla_dir, f'content_{key_hex(key)}.bin')]
    if (container, off) == (LEGACY_SHADER['container'], LEGACY_SHADER['offset']):
        saved.append(mod_path(LEGACY_SHADER['vanilla_blob']))
    for path in saved:
        if os.path.exists(path):
            blob = read_file(path)
            if key_of(blob, cache) == key:
                return blob, path
    blob = read_dat(game_dir, container, off, key[0])
    if key_of(blob, cache) != key:
        raise SystemExit(f'content {key_hex(key)} in enshrouded_{container:03d}.dat @ {off} does not match its '
                         'key; run Steam "Verify integrity of game files"')
    if not save:
        return blob, None
    with open(saved[0], 'wb') as f:
        f.write(blob)
    return blob, saved[0]


def locate_shader(k, man, game_dir, vanilla_dir, index, cache=None):
    old = tuple(man['shader']['key'])
    if old in index:
        blob, _ = content_blob(k, index[old], game_dir, vanilla_dir, cache=cache)
        if parse_shader(blob) is None:
            raise Refuse('the debris shader has its known key but not the expected age-rate selects')
        return index[old], 'unchanged since build 1273043'
    cands = set()
    for guid, th, part in man['shader']['users']:
        ri = k.res_by_id.get((bytes.fromhex(guid), th, part))
        if ri is None:
            continue
        r = k.read_resource(ri)
        pos = r.find(CODE_CATEGORY, 16)
        while pos >= 0:
            key = struct.unpack_from('<4I', r, pos - 16)
            if (k.res_vals[ri][0] + pos) % 4 == 0 and key in index:
                cands.add(key)
            pos = r.find(CODE_CATEGORY, pos + 4)
    matches = [key for key in sorted(cands)
               if parse_shader(content_blob(k, index[key], game_dir, vanilla_dir, cache=cache)[0])]
    if len(matches) != 1:
        raise Refuse(f'found {len(matches)} candidates for the recompiled debris shader (need exactly 1)')
    return index[matches[0]], 'found by its age-rate selects'


class Owners:
    def __init__(self, k):
        sizes = k.actual_sizes()
        self.spans = {}
        for i, (off, _) in enumerate(k.res_vals):
            if sizes[i] > self.spans.get(off, (0, None))[0]:
                self.spans[off] = (sizes[i], i)
        self.starts = sorted(self.spans)

    def __call__(self, off):
        j = bisect.bisect_right(self.starts, off) - 1
        if j < 0:
            return None
        size, i = self.spans[self.starts[j]]
        return i if off < self.starts[j] + size else None


def code_ref(k, ri, off):
    th = k.res_keys[ri][1]
    if th == VFX_TYPE:
        return k.read_stream(off + 16, 4) == CODE_CATEGORY
    return (th == watermods.GPC_TYPE and off - k.res_vals[ri][0] == watermods.GPC_STRIPPED_CODE
            and k.read_stream(off + 16, 4) == GPC_CODE_CATEGORY)


def find_refs(k, keys, owners):
    patterns = {struct.pack('<4I', *key): tuple(key) for key in keys}
    hits, tail, tail_end = {key: set() for key in patterns.values()}, b'', None
    for ci, c in enumerate(k.chunks):
        if tail_end != c[3]:
            tail = b''
        data = tail + k.chunk(ci)
        base = c[3] - len(tail)
        for kb, key in patterns.items():
            pos = data.find(kb)
            while pos >= 0:
                hits[key].add(base + pos)
                pos = data.find(kb, pos + 1)
        tail, tail_end = data[-15:], c[3] + c[4]
    out = {}
    for key, offs in hits.items():
        refs, users = [], set()
        for off in sorted(offs):
            ri = owners(off)
            if ri is None or off % 4 or not code_ref(k, ri, off):
                out[key] = f'key {key_hex(key)} appears at stream offset {off} outside a known reference field'
                break
            refs.append(off)
            users.add(ri)
        else:
            out[key] = (refs, sorted(users))
    return out


def cached_shader(cache, kind, key, options, patched_rel, compute):
    blobs = {}

    def path(v):
        return mod_path(os.path.join(patched_rel, f'content_{v["key"]}.bin'))

    def run(view):
        lines = []
        try:
            blob, *details = compute(view, lines.append)
        except spv_inject.InjectError as e:
            return {'error': str(e), 'log': lines}
        digest = sha1_bytes(blob)
        blobs[digest] = blob
        return {'sha1': digest, 'key': key_hex(key_of(blob, cache)), 'details': details, 'log': lines}

    def valid(v):
        if 'error' in v or v['sha1'] in blobs:
            return True
        if not os.path.exists(path(v)):
            return False
        blob = read_file(path(v))
        if sha1_bytes(blob) != v['sha1']:
            return False
        blobs[v['sha1']] = blob
        return True

    v = cache.get_variant(kind, sha1_bytes(json.dumps(key).encode()), options, run, valid)
    for line in v['log']:
        say(line)
    if 'error' in v:
        raise spv_inject.InjectError(v['error'])
    return blobs[v['sha1']], v['details']


def find_refs_cached(cache, vanilla, k, keys):
    name = sha1_bytes(f'{vanilla} {" ".join(key_hex(key) for key in keys)}'.encode())
    got = cache.get('refs', name, lambda: [[list(key), v] for key, v in find_refs(k, keys, Owners(k)).items()])
    return {tuple(key): v for key, v in got}


def debris_state_offsets(k, users, key, need=spv_inject.STATE_MEMBERS):
    layouts, particles = set(), 0
    for ri in users:
        d = k.read_resource(ri)
        pa, pn = gfxmods.blob_array(d, gfxmods.VFX_PARTICLES)
        sa, sn = gfxmods.blob_array(d, gfxmods.VFX_STATE_INFOS)
        if sn != pn:
            raise spv_inject.InjectError(f'resource {ri} has {pn} particles but {sn} state infos')
        for pi in range(pn):
            if struct.unpack_from('<4I', d, pa + gfxmods.PARTICLE_SIZE * pi + gfxmods.P_STRIPPED_CODE) != tuple(key):
                continue
            ma, mn = gfxmods.blob_array(d, sa + gfxmods.STATE_INFO_SIZE * pi)
            members = {}
            for m in range(mn):
                q = ma + gfxmods.MEMBER_SIZE * m
                members[gfxmods.blob_string(d, q)] = struct.unpack_from('<III', d, q + 8)
            layout = {}
            for name, want in need.items():
                if members.get(name, (None, None))[:2] != want:
                    raise spv_inject.InjectError(f'resource {ri} particle {pi}: state member {name} missing or '
                                                 f'not {want}')
                layout[name] = members[name][2]
            layouts.add(tuple(sorted(layout.items())))
            particles += 1
    if len(layouts) != 1:
        raise spv_inject.InjectError(f'{particles} particles with {len(layouts)} different state layouts')
    return dict(layouts.pop())


def particle_census(k):
    names, out = gfxmods.TextureNames(k), {}
    for ri, rk in enumerate(k.res_keys):
        if rk[1] != VFX_TYPE:
            continue
        d = k.read_resource(ri)
        pa, pn = gfxmods.blob_array(d, gfxmods.VFX_PARTICLES)
        ia, inn = gfxmods.blob_array(d, gfxmods.VFX_IMAGES)
        ga, gn = gfxmods.blob_array(d, gfxmods.VFX_GPU_DATA)
        images = []
        for q in range(inn):
            at = ia + gfxmods.IMAGE_SIZE * q
            images.append((struct.unpack_from('<H', d, at)[0],
                           names(d[at + gfxmods.IMAGE_REF:at + gfxmods.IMAGE_REF + 16])))
        ranges = [struct.unpack_from('<HHHH', d, pa + gfxmods.PARTICLE_SIZE * pi + gfxmods.P_INIT_RANGE)
                  for pi in range(pn)]
        spans = [(a, a + n, pi) for pi, r in enumerate(ranges) for a, n in (r[:2], r[2:]) if n]
        for pi in range(pn):
            pb = pa + gfxmods.PARTICLE_SIZE * pi
            key = struct.unpack_from('<4I', d, pb + gfxmods.P_STRIPPED_CODE)
            i0, ic, e0, ec = ranges[pi]
            used = [n for q, n in images if e0 <= q < e0 + ec or i0 <= q < i0 + ic]
            kind = gfxmods.particle_kind(used)
            smoke = gfxmods.category(used) == 'smoke'
            c = out.setdefault(key, {'particles': 0, 'loose': 0, 'spark': 0, 'flame': 0, 'smoke': 0, 'sites': [],
                                     'slices': []})
            c['particles'] += 1
            c['flame'] += gfxmods.is_flame(used)
            c['smoke'] += smoke
            c['sites'].append((ri, pb))
            if gn and ec:
                shared = any(a < e0 + ec and e0 < b for a, b, other in spans if other != pi)
                marks = tuple(q - e0 for q, _ in images if e0 <= q < e0 + ec)
                c['slices'].append((ri, ga + e0, ec, smoke, shared, d[ga + e0:ga + e0 + min(ec, SLICE_HEADER)],
                                    marks))
            if kind:
                c[kind] += 1
                if kind == 'spark':
                    c['loose'] += 1
    return out


def tag_words(blob, slices, cache=None):
    if cache is None:
        free = spv_inject.free_eval_words(blob, SLICE_HEADER // 4)
    else:
        free = cache.get('free eval words', f'{sha1_bytes(blob)} {SLICE_HEADER // 4}',
                         lambda: sorted(spv_inject.free_eval_words(blob, SLICE_HEADER // 4)))
    free = (4 * w for w in free)
    return sorted(off for off in free
                  if all(ec >= off + 4 and not any(off <= q < off + 4 for q in marks)
                         and (smoke and not shared or struct.unpack_from('<I', head, off)[0] == 0)
                         for _, _, ec, smoke, shared, head, marks in slices))


def tag_edits(k, slices, off, value, label):
    new, edits = spv_inject.f32_bits(value), {}
    for ri, at, _, smoke, shared, head, _ in slices:
        old = struct.unpack_from('<I', head, off)[0]
        if smoke and not shared and old != new:
            edits[k.res_vals[ri][0] + at + off] = (old, new, f'res {ri} slice @ {at} {label}')
    return edits


def tagged_count(slices):
    return sum(1 for s in slices if s[3] and not s[4])


def pick_shaders(census, index, exclude):
    sparks = sorted((c['particles'], key) for key, c in census.items()
                    if key in index and key not in exclude and c['particles'] >= SPARK_MIN_PARTICLES
                    and c['spark'] >= SPARK_SHARE * c['particles'])
    spark = sparks[-1][1] if sparks else None
    loose = sorted(key for key, c in census.items() if key in index and key not in exclude and key != spark
                   and c['particles'] >= LOOSE_MIN_PARTICLES and c['loose'] >= LOOSE_SHARE * c['particles'])
    return spark, loose


def rebase_sites(k, sites):
    edits, how, skipped, cache = {}, collections.Counter(), [], {}
    for s in sites:
        th = s['type']
        if k.internal_hash.get(th) != s['layout']:
            skipped.append((s['label'], 'resource type layout changed'))
            continue
        ri = k.res_by_id.get((bytes.fromhex(s['guid']), th, s['part']))
        if ri is None:
            skipped.append((s['label'], 'resource no longer exists'))
            continue
        if ri not in cache:
            r = k.read_resource(ri)
            cache[ri] = (r, sha1_bytes(r))
        r, digest = cache[ri]
        before, after = bytes.fromhex(s['before']), bytes.fromhex(s['after'])
        if digest == s['res_sha1']:
            pos, method = s['rel'], 'unchanged resource'
        else:
            ctx = before + struct.pack('<I', s['old']) + after
            at = r.find(ctx)
            if at < 0 or at != r.rfind(ctx):
                skipped.append((s['label'], 'resource changed and the edit context is gone or ambiguous'))
                continue
            pos, method = at + len(before), 'relocated by context'
        if struct.unpack_from('<I', r, pos)[0] != s['old']:
            skipped.append((s['label'], 'unexpected current value'))
            continue
        edits[k.res_vals[ri][0] + pos] = (s['old'], s['new'], s['label'])
        how[method] += 1
    return edits, how, skipped


def vanilla_dir_for(version):
    return 'backup' if version == VERSION_1273043 else os.path.join('builds', svn(version), 'vanilla')


def shader_record(k, j, vanilla_blob, vanilla_path, patched, shader_rel, new_key, role=None):
    off, _, container, _ = k.content_vals[j]
    rec = {'container': container, 'offset': off, 'size': k.content_keys[j][0],
           'vanilla_sha1': sha1_bytes(vanilla_blob), 'vanilla_blob': os.path.relpath(vanilla_path, MOD_DIR),
           'vanilla_key': key_hex(k.content_keys[j]), 'patched_sha1': sha1_bytes(patched),
           'patched_blob': shader_rel, 'patched_key': key_hex(new_key)}
    return {'role': role, **rec} if role else rec


def patch_debris_code(k, vanilla_blob, users, old_key, opts, push, log=None):
    selects, one_id, consts = parse_shader(vanilla_blob)
    rate = LINGER_RATES[opts['linger']]
    patched = patch_selects(vanilla_blob, selects, one_id, rate_constant(consts, rate))
    report = {}
    if push['linger_all'] == 'on':
        words = struct.unpack(f'<{len(vanilla_blob) // 4}I', vanilla_blob)
        conditions = {words[w + 3] for w in selects}
        try:
            if len(conditions) != 1:
                raise spv_inject.InjectError('the airborne age-rate selects have different conditions')
            age = debris_state_offsets(k, users, old_key, spv_inject.AGE_MEMBERS)['age']
            patched = spv_inject.linger_landed(patched, age, rate, conditions.pop(), {words[w + 2] for w in selects})
            report['linger_all'] = 'on'
        except spv_inject.InjectError as e:
            report['linger_all'] = f'skipped: {e}'
        (log or say)(f'fixed-rate debris linger: {report["linger_all"]}')
    report['pushback'] = 'off'
    if push['pushback'] == 'on':
        try:
            offsets = debris_state_offsets(k, users, old_key)
            patched = spv_inject.add_pushback(patched, offsets, push['push_radius'], push['push_strength'],
                                              push['push_lift'])
            report['pushback'] = f'on (radius {push["push_radius"]} m, strength {push["push_strength"]} m/s, ' \
                                 f'lift {push["push_lift"]} m/s)'
        except spv_inject.InjectError as e:
            report['pushback'] = f'skipped: {e}'
        (log or say)(f'player pushback: {report["pushback"]}')
    return patched, rate, report


def add_volume(k, key, blob, users, keep, word, notes):
    try:
        age = debris_state_offsets(k, users, key, VOLUME_AGE)['ageNormalized']
    except spv_inject.InjectError as e:
        age = None
        notes.append(('volume age fade', str(e)))
    if age is not None:
        try:
            return spv_inject.add_volume(blob, keep, word, age)
        except spv_inject.InjectError as e:
            notes.append(('volume age fade', str(e)))
    try:
        return spv_inject.add_volume(blob, keep, word)
    except spv_inject.InjectError as e:
        notes.append(('volume distance LOD', str(e)))
    return spv_inject.add_volume(blob, keep, word, lod=False)


def patch_extra_code(k, key, blob, users, steps, push, own=False, words=()):
    applied, notes, left = {}, [], list(words)
    for step in steps:
        word = None
        if step in TAG_DEFAULTS:
            if not left:
                notes.append((step, 'no free renderer parameter word'))
                continue
            word = TAG_DEFAULTS[step] if TAG_DEFAULTS[step] in left else max(left)
        try:
            if step == 'spark':
                age = debris_state_offsets(k, users, key, spv_inject.AGE_MEMBERS)['age']
                blob = spv_inject.scale_age_step(blob, age, push['spark_life'])
            elif step == 'collide':
                offsets = debris_state_offsets(k, users, key, spv_inject.LOOSE_MEMBERS)
                blob = spv_inject.add_collision(blob, offsets, word, push['smoke_collide_slide'])
            elif step == 'loose':
                offsets = debris_state_offsets(k, users, key, spv_inject.LOOSE_MEMBERS)
                blob = spv_inject.add_pushback(blob, offsets, push['smoke_push_radius'], push['smoke_push_strength'],
                                               push['smoke_push_lift'], loose=True, own=own)
            else:
                blob = add_volume(k, key, blob, users, push['smoke_volume_sprites'], word, notes)
        except spv_inject.InjectError as e:
            notes.append((step, str(e)))
            continue
        applied[step] = word
        if word is not None:
            left.remove(word)
    if not applied:
        raise spv_inject.InjectError('; '.join(f'{step}: {why}' for step, why in notes))
    return blob, applied, notes


def wave_reach(k, game_dir, vanilla_dir, index, vanilla, cache, taken):
    ri = watermods.find_water_gpc(k)
    if ri is None:
        raise watermods.WaveError(f'{watermods.GPC_NAME} not found')
    if k.internal_hash.get(watermods.GPC_TYPE) != watermods.GPC_LAYOUT:
        raise watermods.WaveError('keen::GpcResource changed layout')
    d, base = k.read_resource(ri), k.res_vals[ri][0]
    key = struct.unpack_from('<4I', d, watermods.GPC_STRIPPED_CODE)
    if key not in index:
        raise watermods.WaveError(f'its code {key_hex(key)} is not in the content index')
    found = find_refs_cached(cache, vanilla, k, [key])[key]
    if isinstance(found, str):
        raise watermods.WaveError(found)
    refs, users = found
    if list(refs) != [base + watermods.GPC_STRIPPED_CODE] or list(users) != [ri]:
        raise watermods.WaveError(f'its code {key_hex(key)} is referenced by other resources')
    blob, path = content_blob(k, index[key], game_dir, vanilla_dir, save=True, cache=cache)
    patched, checks = watermods.reach_patch(d, blob)
    new_key = key_of(patched, cache)
    if new_key[0] != key[0] or new_key in index or new_key in taken:
        raise watermods.WaveError(f'unusable content key {key_hex(new_key)}')
    return (({'wave_reach': None}, index[key], new_key, blob, path, patched, list(refs), [ri]),
            {base + off: edit for off, edit in checks.items()})


def build(game_dir, vanilla_rel, version, opts):
    vanilla_dir = mod_path(vanilla_rel)
    k = kfc4.KFC(vanilla_dir)
    if k.version != version:
        raise SystemExit(f'{vanilla_dir} holds version {k.version!r}, expected {version!r}')
    if k.internal_hash.get(VFX_TYPE) != VFX_LAYOUT:
        raise Refuse('keen::VfxResource changed layout in this build; the mod needs a new analysis')
    with open(MANIFEST, encoding='utf-8') as f:
        man = json.load(f)
    index = {key: j for j, key in enumerate(k.content_keys)}
    push = spv_inject.normalise(opts)
    patched_rel = os.path.join('builds', svn(version), 'patched')
    cache = buildcache.Cache(mod_path(os.path.join('builds', svn(version), 'analysis_cache.json')))
    vanilla = sha1_bytes(json.dumps(pair_sha1(vanilla_dir), sort_keys=True).encode())

    j, found_by = locate_shader(k, man, game_dir, vanilla_dir, index, cache)
    old_key = k.content_keys[j]
    vanilla_blob, vanilla_path = content_blob(k, j, game_dir, vanilla_dir, save=True, cache=cache)
    collide, volume = push['smoke_collide'] == 'on', push['smoke_volume'] > 0
    census = particle_census(k) if push['spark_life'] != 1.0 or push['smoke_push'] == 'on' or collide or volume \
        else {}
    spark_key, loose_keys = pick_shaders(census, index, {old_key})
    flame_keys = {key for key in loose_keys if census[key]['flame'] >= LOOSE_SHARE * census[key]['particles']}
    smoke_keys = sorted(key for key, c in census.items() if c['smoke'] and key in index and key != old_key)
    steps = {spark_key: ['spark']} if spark_key and push['spark_life'] != 1.0 else {}
    for key in sorted(set(loose_keys) | set(smoke_keys)):
        smoke = key in smoke_keys
        for step, on in (('collide', collide and smoke), ('loose', push['smoke_push'] == 'on' and key in loose_keys),
                         ('volume', volume and smoke)):
            if on:
                steps.setdefault(key, []).append(step)
    wanted = list(steps.items())
    found = find_refs_cached(cache, vanilla, k, [old_key] + [key for key, _ in wanted])
    if isinstance(found[old_key], str):
        raise Refuse(f'the debris shader {found[old_key]}')
    refs, users = found[old_key]
    patched, (rate, code_report) = cached_shader(
        cache, 'debris code', [vanilla, sha1_bytes(vanilla_blob), key_hex(old_key), users], {**opts, **push},
        patched_rel, lambda view, log: patch_debris_code(k, vanilla_blob, users, old_key, view, view, log))
    new_key = key_of(patched, cache)
    if new_key[0] != old_key[0] or new_key in index:
        raise Refuse(f'unusable content key {key_hex(new_key)} for the patched shader')
    say(f'debris shader {key_hex(old_key)} ({found_by}) -> {key_hex(new_key)}, post-landing age rate {rate}')

    extras, skipped, taken = [], [], {new_key}
    for key, want in wanted:
        try:
            if isinstance(found[key], str):
                raise spv_inject.InjectError(found[key])
            xrefs, xusers = found[key]
            blob, _ = content_blob(k, index[key], game_dir, vanilla_dir, cache=cache)
            own = push['smoke_push_own'] == 'on' and key not in flame_keys
            words = tag_words(blob, census[key]['slices'], cache) if set(want) & set(TAG_DEFAULTS) else []
            xpatched, (applied, notes) = cached_shader(
                cache, 'extra code', [vanilla, sha1_bytes(blob), key_hex(key), xusers, want, own, words], push,
                patched_rel, lambda view, log: patch_extra_code(k, key, blob, xusers, want, view, own, words))
            xkey = key_of(xpatched, cache)
            if xkey[0] != key[0] or xkey in index or xkey in taken:
                raise spv_inject.InjectError(f'unusable content key {key_hex(xkey)}')
        except spv_inject.InjectError as e:
            skipped.append(f'{"+".join(want)} {key_hex(key)}: {e}')
            continue
        skipped += [f'{step} {key_hex(key)}: {why}' for step, why in notes]
        taken.add(xkey)
        blob, path = content_blob(k, index[key], game_dir, vanilla_dir, save=True, cache=cache)
        extras.append((applied, index[key], xkey, blob, path, xpatched, xrefs, xusers))
    spark_users = next((x[7] for x in extras if 'spark' in x[0]), [])
    own_note = (f', own effects too (not on {len(flame_keys)} flame shaders)'
                if push['smoke_push_own'] == 'on' else '')
    loose_done = sum(1 for x in extras if 'loose' in x[0])
    smoke_total = sum(census[key]['smoke'] for key in smoke_keys)
    tagged = {step: [k.content_keys[x[1]] for x in extras if step in x[0]] for step in TAG_DEFAULTS}
    tag_notes = {'collide': f'smoke world collision (radius {push["smoke_collide_radius"]} m, '
                            f'slide x{push["smoke_collide_slide"]})',
                 'volume': f'volumetric smoke (density {push["smoke_volume"]}, billboard opacity '
                           f'x{push["smoke_volume_sprites"]})'}
    for step, on in (('collide', collide), ('volume', volume)):
        if on:
            n = sum(tagged_count(census[key]['slices']) for key in tagged[step])
            tag_notes[step] += f': {len(tagged[step])} of {len(smoke_keys)} smoke shaders, {n} of {smoke_total} ' \
                               f'smoke particles'
    if push['spark_life'] != 1.0:
        say(f'spark lifetime x{push["spark_life"]}: ' + (f'on ({len(spark_users)} effects)' if spark_users else 'skipped'))
    if push['smoke_push'] == 'on':
        say(f'loose-particle pushback: {loose_done} of {len(loose_keys)} shaders' + own_note)
    for step, on in (('collide', collide), ('volume', volume)):
        if on:
            say(tag_notes[step])
    for line in skipped:
        say(f'  skipped {line}')
    water = watermods.normalise(opts)
    water_report, checks = {}, {}
    if water['wave_reach'] == 'on':
        damping, radius = watermods.DAMPING[1], watermods.free_radius()[1]
        try:
            gpc, checks = wave_reach(k, game_dir, vanilla_dir, index, vanilla, cache, taken)
            taken.add(gpc[2])
            extras.append(gpc)
            water_report['wave_reach'] = f'on (damping {damping}, free out to {radius} of the grid)'
        except watermods.WaveError as e:
            water_report['wave_reach'] = f'skipped: {e}'
        say(f'wave reach: {water_report["wave_reach"]}')

    edits = {off + 4 * w: (old_key[w], new_key[w], f'shader reference @ {off} word {w}')
             for off in refs for w in (1, 2, 3)}
    patch_debris_shader.merge_edits(edits, checks, 'wave checksum')
    values = {'collide': push['smoke_collide_radius'], 'volume': push['smoke_volume']}
    for applied, xj, xkey, _, _, _, xrefs, _ in extras:
        okey = k.content_keys[xj]
        role = '+'.join(applied)
        patch_debris_shader.merge_edits(edits, {off + 4 * w: (okey[w], xkey[w], f'{role} shader reference @ {off} '
                                                f'word {w}') for off in xrefs for w in (1, 2, 3)}, 'shader reference')
        for step, word in applied.items():
            if word is not None:
                patch_debris_shader.merge_edits(edits, tag_edits(k, census[okey]['slices'], word, values[step],
                                                                 f'{step} value'), f'{step} value')
    gfx = gfxmods.normalise(opts)
    if gfxmods.active(gfx):
        effects, kill_min, gfx_report = gfxmods.run_deep(
            gfxmods.effect_edits, k, lambda i: content_blob(k, i, game_dir, vanilla_dir, cache=cache)[0], gfx,
            exclude_keys=[old_key], log=say, cache=cache)
    else:
        effects, kill_min, gfx_report = {}, {}, {}
    if spark_users:
        factor = push['spark_life']
        for ri in spark_users:
            cur = struct.unpack('<I', k.read_stream(k.res_vals[ri][0] + KILL_TIME_OFFSET, 4))[0]
            kill_min[ri] = max(kill_min.get(ri, 0), math.ceil(cur * factor))
        if gfx['smoke_caps'] == 'on':
            for ri, pb in census[spark_key]['sites']:
                off = k.res_vals[ri][0] + pb + gfxmods.P_MAX_COUNT
                cur = struct.unpack('<I', k.read_stream(off, 4))[0]
                new = min(gfxmods.MAX_COUNT_LIMIT, max(cur, math.ceil(cur * factor)))
                if off in effects:
                    new = max(new, effects[off][1])
                if new != cur:
                    effects[off] = (cur, new, f'res {ri} spark maxCount')
    kill_time, kill = kill_time_for(opts), 0
    wanted_kill = {ri: kill_time for ri in users}
    for ri, t in kill_min.items():
        wanted_kill[ri] = max(wanted_kill.get(ri, 0), t)
    for ri, want in sorted(wanted_kill.items()):
        off = k.res_vals[ri][0] + KILL_TIME_OFFSET
        cur = struct.unpack('<I', k.read_stream(off, 4))[0]
        if cur < want:
            patch_debris_shader.merge_edits(edits, {off: (cur, want, f'res {ri} killTimeInSeconds')},
                                            'killTimeInSeconds')
            kill += 1
    say(f'{len(refs)} shader references in {len(users)} effects re-pointed, killTimeInSeconds raised on {kill} '
        f'effects (debris effects to at least {kill_time})')
    patch_debris_shader.merge_edits(edits, effects, 'effect')
    fog = gfxmods.fog_edits(k, gfx)
    patch_debris_shader.merge_edits(edits, fog, 'fog')
    if fog:
        say(f'fog: {len(fog)} values scaled ({sum("emissive" in v[2] for v in fog.values())} of them fog glow)')

    report = {'shader': found_by, 'rate': rate, **code_report, 'kill_time': kill_time,
              'shader_refs': len(refs), 'kill_time_edits': kill, 'graphics': dict(gfx_report, fog=len(fog))}
    if push['spark_life'] != 1.0:
        report['spark_life'] = f'x{push["spark_life"]} on {len(spark_users)} effects' if spark_users else 'skipped'
    if push['smoke_push'] == 'on':
        report['smoke_push'] = f'{loose_done} of {len(loose_keys)} loose-particle shaders' + own_note
    for step, on in (('collide', collide), ('volume', volume)):
        if on:
            report[f'smoke_{step}'] = tag_notes[step]
    if skipped:
        report['skipped_shaders'] = skipped
    if opts['lights'] == 'on':
        light_edits, how, lskipped = rebase_sites(k, man['sites'])
        patch_debris_shader.merge_edits(edits, light_edits, 'castShadows')
        report.update(light_edits=len(light_edits), light_skipped=len(lskipped))
        say(f'castShadows: {len(light_edits)} of {len(man["sites"])} edits applied {dict(how)}')
        for label, why in lskipped[:10]:
            say(f'  skipped {label}: {why}')
        if len(lskipped) > 10:
            say(f'  ... and {len(lskipped) - 10} more skipped')
    if watermods.bodies_active(water):
        body, counts, wskipped = watermods.body_edits(k, water)
        clash = [off for off in body if any(off + d in edits for d in range(-3, 4))]
        wskipped += [(body[off][2], 'another option edits the same word') for off in clash]
        patch_debris_shader.merge_edits(edits, {off: e for off, e in body.items() if off not in clash}, 'water body')
        water_report['bodies'] = (f'strength x{water["wave_strength"]}, size x{water["wave_size"]}: '
                                  f'{len(body) - len(clash)} values in {counts["body particles"]} body particles, '
                                  f'{counts["splash sheets"]} splash sheets and {counts["swim strokes"]} swim strokes')
        say(f'water waves: {water_report["bodies"]}')
        for what, why in wskipped:
            say(f'  skipped {what}: {why}')
        if wskipped:
            water_report['skipped'] = [f'{what}: {why}' for what, why in wskipped]
    if water_report:
        report['water'] = water_report

    keys = list(k.content_keys)
    keys[j] = new_key
    for _, xj, xkey, *_ in extras:
        keys[xj] = xkey
    tables = kfc4.build_content_tables(keys, k.content_vals, k.loc['content_buckets'][1])
    out_dir = mod_path(patched_rel)
    patch_debris.write_patched_pair(k, edits, out_dir, tables)
    written = []
    for key, blob in [(new_key, patched)] + [(x[2], x[5]) for x in extras]:
        rel = os.path.join(patched_rel, f'content_{key_hex(key)}.bin')
        with open(mod_path(rel), 'wb') as f:
            f.write(blob)
        written.append(rel)

    k2 = kfc4.KFC(out_dir)
    patch_debris_shader.check_content_map(k2, dict(zip(keys, k.content_vals)), k.containers)
    for okey, ousers in [(old_key, users)] + [(k.content_keys[x[1]], x[7]) for x in extras]:
        kb = struct.pack('<4I', *okey)
        assert all(kb not in k2.read_resource(ri) for ri in ousers)
    for key, rel in zip([new_key] + [x[2] for x in extras], written):
        assert key_of(read_file(mod_path(rel)), cache) == key
    for x, rel in zip(extras, written[1:]):
        if 'wave_reach' in x[0]:
            assert not watermods.bad_checksums(k2.read_resource(x[7][0]), read_file(mod_path(rel)))
    say(f'verify OK: content map re-keyed, references re-pointed, {len(written)} patched shaders rehash to their keys')
    cache.save()

    return {'format': BUILD_FORMAT, 'vanilla_dir': vanilla_rel, 'vanilla': pair_sha1(vanilla_dir),
            'patched_dir': patched_rel, 'patched': pair_sha1(out_dir), 'options': dict(opts), 'report': report,
            'shader': shader_record(k, j, vanilla_blob, vanilla_path, patched, written[0], new_key),
            'extra_shaders': [shader_record(k, xj, blob, path, xpatched, rel, xkey, '+'.join(applied))
                              for (applied, xj, xkey, blob, path, xpatched, _, _), rel in zip(extras, written[1:])]}


def intact(rec):
    return (pair_sha1(mod_path(rec['patched_dir'])) == rec['patched']
            and pair_sha1(mod_path(rec['vanilla_dir'])) == rec['vanilla']
            and all(os.path.exists(mod_path(sh[n])) and sha1_bytes(read_file(mod_path(sh[n]))) == sh[d]
                    for sh in all_shaders(rec)
                    for n, d in (('patched_blob', 'patched_sha1'), ('vanilla_blob', 'vanilla_sha1'))))


def copy_pair(src, game_dir, want):
    for n in PAIR:
        shutil.copyfile(os.path.join(src, n), os.path.join(game_dir, n))
    if pair_sha1(game_dir) != want:
        raise SystemExit('copied kfc pair does not match its build')
    say(f'installed kfc pair from {src}')


def install(game_dir, rec, st):
    ensure_closed()
    if not intact(rec):
        raise SystemExit(f'{rec["patched_dir"]} or its backups were modified; delete {rec["patched_dir"]} and rerun')
    known = patched_sha1s([r for recs in shader_records(st) for r in recs])
    shaders = []
    for sh in all_shaders(rec):
        vanilla, patched = read_file(mod_path(sh['vanilla_blob'])), read_file(mod_path(sh['patched_blob']))
        cur = read_dat(game_dir, sh['container'], sh['offset'], sh['size'])
        if cur != vanilla and not own_shader(cur, vanilla, operand_words(vanilla), known):
            raise SystemExit(f'enshrouded_{sh["container"]:03d}.dat @ {sh["offset"]} is not the '
                             f'{sh.get("role", "debris")} shader; run Steam "Verify integrity of game files"')
        shaders.append((sh, vanilla, patched, cur))
    try:
        if pair_sha1(game_dir) != rec['patched']:
            copy_pair(mod_path(rec['patched_dir']), game_dir, rec['patched'])
        for sh, _, patched, cur in shaders:
            if cur != patched:
                write_dat(game_dir, sh['container'], sh['offset'], patched)
        unpoison(game_dir, kfc4.KFC(game_dir), st, {(sh['container'], sh['offset']) for sh, *_ in shaders})
    except BaseException:
        say('install failed; putting the vanilla files back')
        copy_pair(mod_path(rec['vanilla_dir']), game_dir, rec['vanilla'])
        for sh, vanilla, _, _ in shaders:
            write_dat(game_dir, sh['container'], sh['offset'], vanilla)
        raise


def apply(game_dir, given):
    ensure_closed()
    st = load_state()
    opts = full_options({**st.get('options', {}), **given})
    k = kfc4.KFC(game_dir)
    version = k.version
    cur = pair_sha1(game_dir)
    rec = st['builds'].get(version)
    current = bool(rec) and rec.get('format') == BUILD_FORMAT and full_options(rec['options']) == opts
    if current and cur == rec['patched']:
        if any(sha1_bytes(read_dat(game_dir, sh['container'], sh['offset'], sh['size'])) != sh['patched_sha1']
               for sh in all_shaders(rec)):
            install(game_dir, rec, st)
        say(f'already patched (build {svn(version)})')
        return 0

    vanilla_rel = vanilla_dir_for(version)
    ours = ([rec['patched']] if rec else []) + (legacy_patched_sha1s() if version == VERSION_1273043 else [])
    if cur in ours:
        say('installed files are an earlier build of this mod; rebuilding from the vanilla backup')
        want = rec['vanilla'] if rec else VANILLA_1273043
        if pair_sha1(mod_path(vanilla_rel)) != want:
            raise SystemExit(f'{mod_path(vanilla_rel)} does not hold the vanilla files; run Steam "Verify integrity"')
    else:
        if version == VERSION_1273043 and cur != VANILLA_1273043:
            raise Refuse('the installed kfc pair was modified by something else; run Steam "Verify integrity"')
        say(f'installed files are vanilla build {svn(version)}')
        unpoison(game_dir, k, st)
        if pair_sha1(mod_path(vanilla_rel)) != cur:
            os.makedirs(mod_path(vanilla_rel), exist_ok=True)
            for n in PAIR:
                shutil.copyfile(os.path.join(game_dir, n), os.path.join(mod_path(vanilla_rel), n))
            if pair_sha1(mod_path(vanilla_rel)) != cur:
                raise SystemExit(f'backing up the vanilla kfc pair to {mod_path(vanilla_rel)} failed')
            say(f'backed up the vanilla kfc pair to {mod_path(vanilla_rel)}')

    if current and rec['vanilla'] == pair_sha1(mod_path(vanilla_rel)) and intact(rec):
        say(f'reusing the existing build in {rec["patched_dir"]}')
    else:
        remember_shader(st, rec)
        rec = build(game_dir, vanilla_rel, version, opts)
        st['builds'][version] = rec
        save_state(st)
    install(game_dir, rec, st)
    st['options'] = opts
    save_state(st)
    say(f'mods installed for build {svn(version)}: {rec["report"]}')
    return 0


def set_options(given):
    st = load_state()
    st['options'] = full_options({**st.get('options', {}), **given})
    save_state(st)
    say(f'options saved for the next apply: {st["options"]}')
    return 0


def restore(game_dir):
    ensure_closed()
    st = load_state()
    cur = pair_sha1(game_dir)
    k = kfc4.KFC(game_dir)
    rec = st['builds'].get(k.version)
    if rec and cur == rec['patched']:
        copy_pair(mod_path(rec['vanilla_dir']), game_dir, rec['vanilla'])
    elif k.version == VERSION_1273043 and cur in legacy_patched_sha1s():
        copy_pair(mod_path('backup'), game_dir, VANILLA_1273043)
    else:
        say('the installed kfc pair is not a build of this mod; leaving it alone')
    unpoison(game_dir, kfc4.KFC(game_dir), st)
    say('done; the game files are vanilla as far as this mod is concerned')
    return 0


def status(game_dir):
    st = load_state()
    k = kfc4.KFC(game_dir)
    cur = pair_sha1(game_dir)
    rec = st['builds'].get(k.version)
    say(f'installed build {k.version}')
    if rec and cur == rec['patched']:
        say(f'mods installed, options {rec["options"]}, {rec["report"]}')
    elif k.version == VERSION_1273043 and cur in legacy_patched_sha1s():
        say('mods installed by the older build-1273043 tools')
    elif (rec and cur == rec['vanilla']) or cur == VANILLA_1273043:
        say('vanilla kfc pair (mods not installed)')
    else:
        say('kfc pair not recognised (most likely a game update); run apply')
    say('game files consistent' if consistent(game_dir) else
        'game files INCONSISTENT: run apply or restore, or Steam "Verify integrity of game files"')
    return 0


def make_manifest():
    k = kfc4.KFC(mod_path('backup'))
    assert k.version == VERSION_1273043 and pair_sha1(k.game_dir) == VANILLA_1273043
    owners = Owners(k)
    with open(os.path.join(TOOLS, 'light_shadow_sites_build1273043.json'), encoding='utf-8') as f:
        light = json.load(f)
    sites = []
    for s in light:
        ri = owners(s['stream_off'])
        r = k.read_resource(ri)
        rel = s['stream_off'] - k.res_vals[ri][0]
        assert struct.unpack_from('<I', r, rel)[0] == s['old']
        for width in (8, 16, 32, 64, 128, 256):
            before, after = r[max(0, rel - width):rel], r[rel + 4:rel + 4 + width]
            ctx = before + r[rel:rel + 4] + after
            if r.find(ctx) == r.rfind(ctx):
                break
        else:
            raise SystemExit(f'no unique context for {s["label"]}')
        g, th, part = k.res_keys[ri][:3]
        sites.append({'label': s['label'], 'kind': s['kind'], 'guid': g.hex(), 'type': th, 'part': part,
                      'layout': k.internal_hash[th], 'rel': rel, 'old': s['old'], 'new': s['new'],
                      'res_sha1': sha1_bytes(r), 'before': before.hex(), 'after': after.hex()})
    with open(patch_debris_shader.VFX_LIST, encoding='utf-8') as f:
        users = [k.res_keys[row['ri']][:3] for row in json.load(f)]
    man = {'build': k.version, 'shader': {'key': list(patch_debris_shader.SHADER_KEY),
                                          'users': [[g.hex(), th, part] for g, th, part in users]},
           'sites': sites}
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(man, f, indent=0)
    say(f'wrote {MANIFEST}: {len(sites)} sites, {len(users)} shader users')
    return 0


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['apply', 'set', 'restore', 'status', 'manifest'])
    p.add_argument('game_dir', nargs='?', default=os.path.dirname(MOD_DIR))
    p.add_argument('--lights', choices=['on', 'off'], help='include the castShadows edits (default on)')
    p.add_argument('--linger', type=int, choices=sorted(LINGER_RATES),
                   help='seconds the longest-lived debris stays after landing; 0 = until the effect is killed '
                        '(default 100)')
    p.add_argument('--kill-time', type=int, help='minimum killTimeInSeconds of the effects using the shader '
                                                 '(default max(180, linger + 30))')
    for name in gfxmods.LIMITS:
        lo, hi = gfxmods.LIMITS[name]
        p.add_argument('--' + name.replace('_', '-'), type=float, metavar='M',
                       help=f'graphics multiplier {lo:g}..{hi:g} (default 1 = vanilla)')
    p.add_argument('--smoke-caps', choices=['on', 'off'], help='raise particle caps with --smoke-life/--dust-life')
    p.add_argument('--smoke-collide', choices=['on', 'off'],
                   help='smoke particles collide with the world: walls, ceilings, overhangs (default off)')
    for name, metavar, what in (('smoke_collide_radius', 'R', 'smoke collision radius, metres'),
                                ('smoke_collide_slide', 'S', 'share of the stopped speed turned along the '
                                                             'surface, 0 = smoke rests against it'),
                                ('smoke_volume', 'D', 'volumetric smoke fog density, 0 = off'),
                                ('smoke_volume_sprites', 'K', 'share of the smoke billboard opacity kept with '
                                                              '--smoke-volume')):
        lo, hi = spv_inject.LIMITS[name]
        p.add_argument('--' + name.replace('_', '-'), type=float, metavar=metavar,
                       help=f'{what}, {lo:g}..{hi:g} (default {spv_inject.DEFAULTS[name]:g})')
    p.add_argument('--linger-all', choices=['on', 'off'],
                   help='debris with a fixed age rate also lingers after landing (default on)')
    p.add_argument('--pushback', choices=['on', 'off'], help='players push landed debris away (default off)')
    p.add_argument('--smoke-push', choices=['on', 'off'],
                   help='players push smoke, dust, embers and flames aside (default off)')
    p.add_argument('--smoke-push-own', choices=['on', 'off'],
                   help="also push the player's own effects: held torch smoke and embers, footstep dust "
                        "(default off)")
    for name, unit in (('push_radius', 'm'), ('push_strength', 'm/s'), ('push_lift', 'm/s'),
                       ('smoke_push_radius', 'm'), ('smoke_push_strength', 'm/s'), ('smoke_push_lift', 'm/s')):
        lo, hi = spv_inject.LIMITS[name]
        what = 'loose-particle pushback' if name.startswith('smoke') else 'pushback'
        p.add_argument('--' + name.replace('_', '-'), type=float, metavar='X',
                       help=f'{what} {name.split("_")[-1]} {lo:g}..{hi:g} {unit} '
                            f'(default {spv_inject.DEFAULTS[name]:g})')
    lo, hi = spv_inject.LIMITS['spark_life']
    p.add_argument('--spark-life', type=float, metavar='M',
                   help=f'sparks live M times longer, {lo:g}..{hi:g} (default 1 = vanilla)')
    for name, what in (('wave_strength', 'players push the water surface M times deeper'),
                       ('wave_size', 'players push the water surface over an M times wider area')):
        lo, hi = watermods.LIMITS[name]
        p.add_argument('--' + name.replace('_', '-'), type=float, metavar='M',
                       help=f'{what}, {lo:g}..{hi:g} (default 1 = vanilla)')
    p.add_argument('--wave-reach', choices=['on', 'off'],
                   help='waves on the water fade half as fast and run freely further out (default off)')
    a = p.parse_args()
    game_dir = os.path.abspath(a.game_dir)
    given = {n: getattr(a, n) for n in DEFAULTS if getattr(a, n, None) is not None}
    try:
        return {'apply': lambda: apply(game_dir, given), 'set': lambda: set_options(given),
                'restore': lambda: restore(game_dir),
                'status': lambda: status(game_dir), 'manifest': make_manifest}[a.command]()
    except (Refuse, SystemExit, AssertionError, OSError, ValueError, KeyError) as e:
        say(f'{a.command} failed: {e}')
        if a.command == 'manifest':
            return 2
        if not consistent(game_dir):
            say('the game files are INCONSISTENT: run Steam "Verify integrity of game files" before playing')
            return 2
        if mods_installed(game_dir):
            say('the game files are consistent; the previously installed build of the mods stays active')
            return 0
        say('the game files are consistent; the game runs without the mods')
        return 1


if __name__ == '__main__':
    sys.exit(main())
