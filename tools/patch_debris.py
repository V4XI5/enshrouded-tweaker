import argparse, hashlib, json, os, shutil, struct, sys
from concurrent.futures import ThreadPoolExecutor
from compression import zstd
from compression.zstd import CompressionParameter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kfc4

EXPECTED_VERSION = '1273043|^/game38/branches/release_1.0|2026-10-20T14:55:29.904125Z'
VANILLA_SHA1 = {
    'enshrouded.kfc': 'ec4ec193bdae1934de836cdb6cef9b843f7515b7',
    'enshrouded.kfc_resources': '7e6a5d0b1fa2c9f4a99d149029a5889d791ba9fc',
}
PATCHMAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debris_patchmap_build1273043.json')
ZSTD_OPTIONS = {
    CompressionParameter.compression_level: 19,
    CompressionParameter.window_log: 22,
    CompressionParameter.content_size_flag: 0,
    CompressionParameter.checksum_flag: 0,
}


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def f32_bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def collect_edits(patchmap, args):
    edits = {}

    def add(loc, old_u32, new_u32, label):
        off = loc['dec_off']
        prev = edits.get(off)
        if prev and prev[:2] != (old_u32, new_u32):
            raise SystemExit(f'conflicting edits at stream offset {off}: {prev} vs {(old_u32, new_u32, label)}')
        edits[off] = (old_u32, new_u32, label)

    for e in patchmap:
        name = f"{e['vfx_guid']} p{e['particle_index']}"
        kt = e['killTimeInSeconds']
        add(kt, kt['u32'], args.kill_time, f"{e['vfx_guid']} killTimeInSeconds")
        tag = e['lifetime_tag']['u32']
        if tag == 1:
            base, scale = e['lifetime_rand_base'], e['lifetime_rand_scale']
            add(base, base['u32'], f32_bits(args.life_min), f'{name} lifetime base')
            add(scale, scale['u32'], f32_bits(args.life_max - args.life_min), f'{name} lifetime scale')
        elif tag == 3 and args.userparam is not None:
            up = e['lifetime_userparam_default']
            add(up, f32_bits(up['f32']), f32_bits(args.userparam), f'{name} lifetime userParam')
    return edits


def build(game_dir, out, args):
    if not 0 < args.life_min <= args.life_max:
        raise SystemExit('need 0 < --life-min <= --life-max')
    if args.kill_time <= args.life_max:
        raise SystemExit('--kill-time must exceed --life-max or the effect is cut off before its debris dies')
    k = kfc4.KFC(game_dir)
    if k.version != EXPECTED_VERSION:
        raise SystemExit(f'unsupported game version {k.version!r}; expected {EXPECTED_VERSION!r}')
    edits = collect_edits(json.load(open(PATCHMAP, encoding='utf-8')), args)
    od = write_patched_pair(k, edits, os.path.join(out, 'patched'))
    with open(os.path.join(od, 'patch_info.json'), 'w', encoding='utf-8') as f:
        json.dump({'life_min': args.life_min, 'life_max': args.life_max, 'kill_time': args.kill_time,
                   'userparam': args.userparam, 'edits': len(edits),
                   'sha1': {n: sha1(os.path.join(od, n)) for n in VANILLA_SHA1}}, f, indent=1)
    print(f'patched files written to {od}')


def write_patched_pair(k, edits, od, tables=None):
    by_chunk = {}
    for off in sorted(edits):
        by_chunk.setdefault(k.chunk_index_for(off), []).append(off)

    replaced, originals, bufs = {}, {}, {}
    for ci, offs in sorted(by_chunk.items()):
        uoff = k.chunks[ci][3]
        orig = k.chunk(ci)
        buf = bytearray(orig)
        for off in offs:
            old, new, label = edits[off]
            cur = struct.unpack_from('<I', buf, off - uoff)[0]
            if cur != old:
                raise SystemExit(f'unexpected value at stream offset {off} ({label}): '
                                 f'{cur:#010x} != {old:#010x}; game data does not match the patch map')
            struct.pack_into('<I', buf, off - uoff, new)
        originals[ci] = orig
        bufs[ci] = bytes(buf)
    with ThreadPoolExecutor(max(1, min(len(bufs), os.cpu_count() or 1))) as ex:
        for ci, data in zip(bufs, ex.map(lambda b: zstd.compress(b, options=ZSTD_OPTIONS), bufs.values())):
            replaced[ci] = data
            print(f'chunk {ci}: {len(by_chunk[ci])} edits, compressed {k.chunks[ci][2]} -> {len(data)} bytes', flush=True)
    del bufs

    os.makedirs(od, exist_ok=True)
    chunks = kfc4.write_resources_file(k, os.path.join(od, 'enshrouded.kfc_resources'), replaced, [])
    total_u = max(c[3] + c[4] for c in chunks)
    locations = [(total_u, sum(c[2] for c in chunks), k.resource_locations[0][2])] + k.resource_locations[1:]
    with open(os.path.join(od, 'enshrouded.kfc'), 'wb') as f:
        f.write(kfc4.build_kfc_bytes(k, chunks, k.res_vals, locations, tables))

    verify(k, kfc4.KFC(od), edits, originals)
    return od


def verify(k, k2, edits, originals):
    assert k2.version == k.version and k2.res_keys == k.res_keys and k2.res_vals == k.res_vals
    assert len(k2.chunks) == len(k.chunks)
    for ci, (a, b) in enumerate(zip(k.chunks, k2.chunks)):
        assert a[3:] == b[3:], f'chunk {ci} uncompressed range changed'
        if ci not in originals:
            assert k.chunk_raw(ci) == k2.chunk_raw(ci), f'untouched chunk {ci} differs'
    allowed = None
    by_chunk = {}
    for off in edits:
        by_chunk.setdefault(k.chunk_index_for(off), []).append(off)
    for ci, orig in originals.items():
        new = k2.chunk(ci)
        uoff = k.chunks[ci][3]
        assert len(new) == len(orig)
        want = bytearray(orig)
        for off in by_chunk.get(ci, ()):
            if off + 4 <= uoff + len(orig):
                struct.pack_into('<I', want, off - uoff, edits[off][1])
        if new == want:
            continue
        if allowed is None:
            allowed = {off + i for off in edits for i in range(4)}
        diff = {uoff + i for i in range(len(orig)) if orig[i] != new[i]}
        assert diff <= allowed, f'chunk {ci} has unexpected changes at {sorted(diff - allowed)[:5]}'
    for off, (old, new, label) in edits.items():
        got = struct.unpack('<I', k2.read_stream(off, 4))[0]
        assert got == new, f'readback failed at {off} ({label})'
    print(f'verify OK: {len(edits)} edits read back, {len(k.chunks) - len(originals)} untouched chunks identical, '
          f'no other bytes changed', flush=True)


def copy_pair(src_dir, game_dir):
    import patch_debris_shader
    if patch_debris_shader.game_running():
        raise SystemExit('Enshrouded is running; close it first')
    version = kfc4.KFC(game_dir).version
    if version != EXPECTED_VERSION:
        raise SystemExit(f'the installed game is {version!r}; this tool only supports {EXPECTED_VERSION!r} '
                         '(use autopatch.py)')
    shader = patch_debris_shader.shader_for(src_dir, game_dir)
    for name in VANILLA_SHA1:
        dst = os.path.join(game_dir, name)
        try:
            shutil.copyfile(os.path.join(src_dir, name), dst)
        except PermissionError:
            raise SystemExit(f'cannot overwrite {dst}: close Enshrouded first')
        print(f'copied {name} -> {dst}')
    if shader is not None:
        patch_debris_shader.write_shader(game_dir, shader)


def install(game_dir, out, subdir='patched'):
    od = os.path.join(out, subdir)
    info = json.load(open(os.path.join(od, 'patch_info.json'), encoding='utf-8'))
    for name, digest in info['sha1'].items():
        if sha1(os.path.join(od, name)) != digest:
            raise SystemExit(f'{name} in {od} does not match patch_info.json; rebuild first')
    copy_pair(od, game_dir)


def restore(game_dir, backup_dir):
    for name, digest in VANILLA_SHA1.items():
        if sha1(os.path.join(backup_dir, name)) != digest:
            raise SystemExit(f'backup {name} is not the vanilla file; use Steam "Verify integrity" instead')
    copy_pair(backup_dir, game_dir)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'install', 'restore'])
    p.add_argument('game_dir')
    p.add_argument('dir', help='out_dir for build/install, backup_dir for restore')
    p.add_argument('--life-min', type=float, default=80.0, help='minimum debris lifetime after landing, seconds')
    p.add_argument('--life-max', type=float, default=100.0, help='maximum debris lifetime after landing, seconds')
    p.add_argument('--kill-time', type=int, default=120, help='killTimeInSeconds for the patched effects')
    p.add_argument('--userparam', type=float, default=None,
                   help='also set the lifetime user parameter of userParam-driven debris (bones, pottery, ...); '
                        'off by default because the parameter may drive other effect properties')
    a = p.parse_args()
    if a.command == 'build':
        build(a.game_dir, a.dir, a)
    elif a.command == 'install':
        install(a.game_dir, a.dir)
    else:
        restore(a.game_dir, a.dir)


if __name__ == '__main__':
    main()
