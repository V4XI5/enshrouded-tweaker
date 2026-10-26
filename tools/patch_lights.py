import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kfc4
import patch_debris
from patch_debris import EXPECTED_VERSION, VANILLA_SHA1, sha1

SITES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'light_shadow_sites_build1273043.json')


def collect_edits():
    return {s['stream_off']: (s['old'], s['new'], s['label']) for s in json.load(open(SITES, encoding='utf-8'))}


def build(mod_dir):
    backup = os.path.join(mod_dir, 'backup')
    for name, digest in VANILLA_SHA1.items():
        if sha1(os.path.join(backup, name)) != digest:
            raise SystemExit(f'{backup}/{name} is not the vanilla file')
    k = kfc4.KFC(backup)
    if k.version != EXPECTED_VERSION:
        raise SystemExit(f'unsupported game version {k.version!r}; expected {EXPECTED_VERSION!r}')
    edits = collect_edits()
    od = patch_debris.write_patched_pair(k, edits, os.path.join(mod_dir, 'patched_lights'))
    with open(os.path.join(od, 'patch_info.json'), 'w', encoding='utf-8') as f:
        json.dump({'edits': len(edits), 'sha1': {n: sha1(os.path.join(od, n)) for n in VANILLA_SHA1}}, f, indent=1)
    print(f'patched files written to {od}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['build', 'install', 'restore'])
    p.add_argument('game_dir')
    p.add_argument('mod_dir')
    a = p.parse_args()
    if a.command == 'build':
        build(a.mod_dir)
    elif a.command == 'install':
        patch_debris.install(a.game_dir, a.mod_dir, 'patched_lights')
    else:
        patch_debris.restore(a.game_dir, os.path.join(a.mod_dir, 'backup'))


if __name__ == '__main__':
    main()
