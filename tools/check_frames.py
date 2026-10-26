import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kfc4
for d in sys.argv[1:]:
    k = kfc4.KFC(d)
    hdrs = {}
    for i in range(len(k.chunks)):
        raw = k.chunk_raw(i)
        hdrs.setdefault((raw[:4].hex(), raw[4], raw[5]), []).append(i)
    print(d, 'chunks', len(k.chunks), 'res_total', k.resource_locations[0], 'file', os.path.getsize(k.res_path))
    for h, idx in hdrs.items():
        print('  magic', h[0], 'FHD 0x%02x' % h[1], 'window 0x%02x' % h[2], 'chunks', idx[:6], '...' if len(idx) > 6 else '')
