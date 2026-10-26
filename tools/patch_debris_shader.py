import argparse, hashlib, json, os, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_hash
import kfc4
import patch_debris
from patch_debris import EXPECTED_VERSION, VANILLA_SHA1, sha1

VFX_LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shader_vfx_build1273043.json')
SHADER_DAT = 'enshrouded_053.dat'
SHADER_CONTAINER = 53
SHADER_OFFSET = 582619136
SHADER_SIZE = 699304
SHADER_SHA1 = 'e7a17ef9637a38c2acb6cc3bcfc3167d3d59bfae'
SHADER_KEY = (0x000AABA8, 0xEC9580CF, 0x5F8434F4, 0x7DBBD0DE)
SHADER_REFS = 950
REF_TRAILER = struct.pack('<II', 0x9B276059, 1)
SHADER_BACKUP = 'shader_a8ab0a00_original.bin'
SHADER_PATCHED = 'shader_a8ab0a00_patched.bin'
AGE_RATE_SELECTS = {38343: 'ageRate tag 1 (airborne 0.05)', 36696: 'ageRate tag >=4 (airborne 0.5)'}
ONE_ID = 7625
RATE_IDS = {'0.02': 7779, '0.0125': 7810, '0.01': 7500, '0.0039': 7801}


def read_shader(game_dir):
    with open(os.path.join(game_dir, SHADER_DAT), 'rb') as f:
        f.seek(SHADER_OFFSET)
        return f.read(SHADER_SIZE)


def patch_shader(blob, rate_id):
    buf = bytearray(blob)
    for word, label in AGE_RATE_SELECTS.items():
        op, _, _, _, obj1, _ = struct.unpack_from('<6I', buf, 4 * word)
        if op != (6 << 16 | 169) or obj1 != ONE_ID:
            raise SystemExit(f'shader word {word} ({label}) is not the expected OpSelect; game data changed')
        struct.pack_into('<I', buf, 4 * (word + 4), rate_id)
    assert _mask(buf) == _mask(blob)
    return bytes(buf)


def _mask(blob):
    buf = bytearray(blob)
    for word in AGE_RATE_SELECTS:
        buf[4 * (word + 4):4 * (word + 5)] = bytes(4)
    return bytes(buf)


def game_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq enshrouded.exe', '/NH'],
                         capture_output=True, text=True).stdout
    return 'enshrouded.exe' in out.lower()


def write_shader(game_dir, blob):
    if game_running():
        raise SystemExit('Enshrouded is running; close it first')
    path = os.path.join(game_dir, SHADER_DAT)
    with open(path, 'r+b') as f:
        f.seek(SHADER_OFFSET)
        f.write(blob)
    if read_shader(game_dir) != blob:
        raise SystemExit(f'readback of the shader in {path} failed')
    print(f'wrote shader ({len(blob)} bytes, sha1 {hashlib.sha1(blob).hexdigest()}) to {path} @ {SHADER_OFFSET}')


def shader_for(src_dir, game_dir):
    current = read_shader(game_dir)
    backup = os.path.join(os.path.dirname(os.path.abspath(src_dir)), 'backup', SHADER_BACKUP)
    patched = os.path.join(src_dir, SHADER_PATCHED)
    if not os.path.exists(backup):
        if os.path.exists(patched) or hashlib.sha1(current).hexdigest() != SHADER_SHA1:
            raise SystemExit(f'{backup} is missing; run Steam "Verify integrity" and rebuild')
        return None
    with open(backup, 'rb') as f:
        vanilla = f.read()
    if hashlib.sha1(vanilla).hexdigest() != SHADER_SHA1:
        raise SystemExit(f'{backup} is not the vanilla shader')
    if os.path.exists(patched):
        with open(patched, 'rb') as f:
            want = f.read()
    else:
        want = vanilla
    if current == want:
        return None
    if _mask(current) != _mask(vanilla):
        raise SystemExit('the debris shader in the game files is neither vanilla nor a build of this tool; '
                         'run Steam "Verify integrity" first')
    return want


def find_shader_refs(k, resource_indices):
    key = struct.pack('<4I', *SHADER_KEY)
    offs = []
    for ri in sorted(resource_indices, key=lambda ri: k.res_vals[ri][0]):
        base = k.res_vals[ri][0]
        data = k.read_resource(ri)
        pos = data.find(key)
        while pos >= 0:
            if (base + pos) % 4 or data[pos + 16:pos + 24] != REF_TRAILER:
                raise SystemExit(f'unexpected shader key occurrence in resource {ri} at +{pos}; game data changed')
            offs.append(base + pos)
            pos = data.find(key, pos + 16)
    if len(offs) != SHADER_REFS:
        raise SystemExit(f'found {len(offs)} shader references, expected {SHADER_REFS}; game data changed')
    return offs


def merge_edits(edits, more, what):
    for off in more:
        if any(off + d in edits for d in range(-3, 4)):
            raise SystemExit(f'{what} edit at stream offset {off} overlaps another edit')
    edits.update(more)


def check_content_map(k2, expected, containers):
    buckets = k2.buckets('content_buckets')
    n, pos = len(buckets), 0
    for bi, (first, count) in enumerate(buckets):
        assert first == pos, f'content bucket {bi} starts at {first}, expected {pos}'
        assert all(k2.content_keys[j][1] % n == bi for j in range(first, first + count)), f'bucket {bi} misplaced'
        pos += count
    assert pos == len(k2.content_keys) == len(k2.content_vals)
    assert dict(zip(k2.content_keys, k2.content_vals)) == expected
    assert k2.containers == containers and sum(c[1] for c in containers) == len(k2.content_keys)


def build(game_dir, mod_dir, args):
    backup = os.path.join(mod_dir, 'backup')
    for name, digest in VANILLA_SHA1.items():
        if sha1(os.path.join(backup, name)) != digest:
            raise SystemExit(f'{backup}/{name} is not the vanilla file')
    k = kfc4.KFC(backup)
    if k.version != EXPECTED_VERSION:
        raise SystemExit(f'unsupported game version {k.version!r}; expected {EXPECTED_VERSION!r}')

    shader_backup = os.path.join(backup, SHADER_BACKUP)
    if not os.path.exists(shader_backup):
        blob = read_shader(game_dir)
        if hashlib.sha1(blob).hexdigest() != SHADER_SHA1:
            raise SystemExit('the debris shader in the game files is not vanilla and no backup exists; '
                             'run Steam "Verify integrity" first')
        with open(shader_backup, 'wb') as f:
            f.write(blob)
    with open(shader_backup, 'rb') as f:
        original = f.read()
    if hashlib.sha1(original).hexdigest() != SHADER_SHA1:
        raise SystemExit(f'{shader_backup} is not the vanilla shader')

    idx = k.content_keys.index(SHADER_KEY)
    if k.content_vals[idx] != (SHADER_OFFSET, 0, SHADER_CONTAINER, 0):
        raise SystemExit(f'content entry {idx} does not point at {SHADER_DAT} @ {SHADER_OFFSET}')
    if content_hash.content_key(original) != SHADER_KEY:
        raise SystemExit('content hash self-test failed on the vanilla shader')
    patched = patch_shader(original, RATE_IDS[args.rate])
    new_key = content_hash.content_key(patched)
    if new_key[0] != SHADER_KEY[0] or new_key in set(k.content_keys):
        raise SystemExit(f'unusable content key {new_key} for the patched shader')
    new_key_hex = struct.pack('<4I', *new_key).hex()
    print(f'patched shader content key {new_key_hex}')

    rows = json.load(open(VFX_LIST, encoding='utf-8'))
    edits = {}
    for row in rows:
        new = max(row['killTime'], args.kill_time)
        if new != row['killTime']:
            edits[k.res_vals[row['ri']][0] + 8] = (row['killTime'], new, f"{row['guid']} killTimeInSeconds")
    kill_edits = len(edits)
    refs = find_shader_refs(k, {row['ri'] for row in rows})
    ref_edits = {off + 4 * w: (SHADER_KEY[w], new_key[w], f'strippedCode @ {off} word {w}')
                 for off in refs for w in (1, 2, 3)}
    merge_edits(edits, ref_edits, 'shader reference')
    light_edits = {}
    if not args.no_lights:
        import patch_lights
        light_edits = patch_lights.collect_edits()
        merge_edits(edits, light_edits, 'castShadows')

    keys = list(k.content_keys)
    keys[idx] = new_key
    nbuckets = k.loc['content_buckets'][1]
    for name, (blob, count) in kfc4.build_content_tables(k.content_keys, k.content_vals, nbuckets).items():
        o, n, _ = k.loc[name]
        assert (blob, count) == (k.data[o:o + len(blob)], n), f'{name} does not round-trip'
    tables = kfc4.build_content_tables(keys, k.content_vals, nbuckets)

    od = patch_debris.write_patched_pair(k, edits, os.path.join(mod_dir, 'patched_shader'), tables)
    with open(os.path.join(od, SHADER_PATCHED), 'wb') as f:
        f.write(patched)

    k2 = kfc4.KFC(od)
    check_content_map(k2, dict(zip(keys, k.content_vals)), k.containers)
    with open(os.path.join(od, SHADER_PATCHED), 'rb') as f:
        assert content_hash.content_key(f.read()) == new_key
    old = struct.pack('<4I', *SHADER_KEY)
    assert all(old not in k2.read_resource(row['ri']) for row in rows)
    print(f'verify OK: content map re-keyed (entry moved to bucket {new_key[1] % nbuckets}), '
          f'{len(refs)} references point at the new key, shader file rehashes to it')
    print(f'shader: {len(AGE_RATE_SELECTS)} age-rate selects now use {args.rate} after ground contact')

    names = list(VANILLA_SHA1) + [SHADER_PATCHED]
    with open(os.path.join(od, 'patch_info.json'), 'w', encoding='utf-8') as f:
        json.dump({'rate': args.rate, 'kill_time': args.kill_time, 'kill_time_edits': kill_edits,
                   'shader_refs': len(refs), 'light_edits': len(light_edits), 'shader_key': new_key_hex,
                   'sha1': {n: sha1(os.path.join(od, n)) for n in names}}, f, indent=1)
    print(f'patched files written to {od}')


def install(game_dir, mod_dir):
    od = os.path.join(mod_dir, 'patched_shader')
    info = json.load(open(os.path.join(od, 'patch_info.json'), encoding='utf-8'))
    if 'shader_key' not in info:
        raise SystemExit(f'{od} is an old build without a re-keyed shader; rebuild first')
    for name, digest in info['sha1'].items():
        if sha1(os.path.join(od, name)) != digest:
            raise SystemExit(f'{name} in {od} does not match patch_info.json; rebuild first')
    patch_debris.copy_pair(od, game_dir)


def restore(game_dir, mod_dir):
    patch_debris.restore(game_dir, os.path.join(mod_dir, 'backup'))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'install', 'restore'])
    p.add_argument('game_dir')
    p.add_argument('mod_dir')
    p.add_argument('--rate', choices=sorted(RATE_IDS), default='0.01',
                   help='age rate after ground contact (vanilla 1.0); 0.01 keeps debris about 20-95 s')
    p.add_argument('--kill-time', type=int, default=180, help='minimum killTimeInSeconds for effects using the shader')
    p.add_argument('--no-lights', action='store_true', help='leave out the patch_lights.py castShadows edits')
    a = p.parse_args()
    {'build': lambda: build(a.game_dir, a.mod_dir, a),
     'install': lambda: install(a.game_dir, a.mod_dir),
     'restore': lambda: restore(a.game_dir, a.mod_dir)}[a.command]()


if __name__ == '__main__':
    main()
