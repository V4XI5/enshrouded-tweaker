import sys, os, struct, csv, json, mmap, collections, hashlib, re, bisect
from compression import zstd

FNV_OFF, FNV_PRIME = 0x811c9dc5, 0x1000193
def fnv1a32(b, seed=FNV_OFF):
    h = seed
    for x in b:
        h = ((h ^ x) * FNV_PRIME) & 0xffffffff
    return h

def guid_str(g):
    a, b, c = struct.unpack_from('<IHH', g, 0)
    return f'{a:08x}-{b:04x}-{c:04x}-{g[8:10].hex()}-{g[10:16].hex()}'

def guid_from_str(s):
    s = s.strip().lower()
    p = s.split('-')
    return struct.pack('<IHH', int(p[0], 16), int(p[1], 16), int(p[2], 16)) + bytes.fromhex(p[3] + p[4])

LOC_NAMES = ['version', 'containers', 'unused0', 'unused1', 'resource_locations', 'resource_indices',
             'content_buckets', 'content_keys', 'content_values', 'resource_buckets', 'resource_keys',
             'resource_values', 'bundle_buckets', 'bundle_keys', 'bundle_values', 'resource_chunks']
RESOURCE_SIZE_MODULUS = 0x1000000
RESOURCE_ALIGNMENT = 16


def _table(d, fmt, o, n):
    size = struct.calcsize(fmt)
    if o + size * n > len(d):
        raise struct.error(f'table at {o} with {n} records of {size} bytes runs past the end of the file')
    return list(struct.iter_unpack(fmt, memoryview(d)[o:o + size * n]))


class KFC:
    def __init__(self, game_dir, base='enshrouded'):
        self.game_dir = game_dir
        self.kfc_path = os.path.join(game_dir, base + '.kfc')
        self.res_path = os.path.join(game_dir, base + '.kfc_resources')
        self.base = base
        d = self.data = open(self.kfc_path, 'rb').read()
        self.magic, self.data_size, self.unk, self.pad = struct.unpack_from('<4sIII', d, 0)
        if self.magic != b'KFC4':
            raise ValueError(f'bad magic {self.magic!r}')
        self.loc = {}
        for i, n in enumerate(LOC_NAMES):
            fo = 0x10 + 8 * i
            rel, cnt = struct.unpack_from('<II', d, fo)
            self.loc[n] = (fo + rel if rel else 0, cnt, fo)
        o, n, _ = self.loc['version']; self.version = d[o:o + n].decode()
        o, n, _ = self.loc['containers']
        self.containers = _table(d, '<QQ', o, n)
        o, n, _ = self.loc['resource_locations']
        self.resource_locations = _table(d, '<III', o, n)
        o, n, _ = self.loc['resource_chunks']
        self.chunks = _table(d, '<5I', o, n)
        o, n, _ = self.loc['resource_indices']
        self.resource_indices = list(struct.unpack_from(f'<{n}I', d, o))
        o, n, _ = self.loc['resource_keys']
        self.res_keys = _table(d, '<16sIIII', o, n)
        o2, n2, _ = self.loc['resource_values']
        self.res_vals = _table(d, '<II', o2, n2)
        self.res_by_id = {(k[0], k[1], k[2]): i for i, k in enumerate(self.res_keys)}
        self.res_by_guid = collections.defaultdict(list)
        for i, k in enumerate(self.res_keys):
            self.res_by_guid[k[0]].append(i)
        o, n, _ = self.loc['content_keys']
        self.content_keys = _table(d, '<IIII', o, n)
        o, n, _ = self.loc['content_values']
        self.content_vals = _table(d, '<IHHQ', o, n)
        o, n, _ = self.loc['bundle_keys']
        self.bundle_keys = list(struct.unpack_from(f'<{n}I', d, o))
        o, n, _ = self.loc['bundle_values']
        self.bundle_vals = _table(d, '<III', o, n)
        self.internal_hash = {k: v[0] for k, v in zip(self.bundle_keys, self.bundle_vals)}
        self._actual_sizes = None
        self._chunk_cache = collections.OrderedDict()
        self._chunk_starts = None
        self._resf = None

    def buckets(self, name):
        o, n, _ = self.loc[name]
        return [struct.unpack_from('<II', self.data, o + 8 * i) for i in range(n)]

    @staticmethod
    def res_static_hash(key):
        g, th, part = key[0], key[1], key[2]
        return fnv1a32(struct.pack('<II', th, part), struct.unpack_from('<I', g)[0])

    def lookup_resource(self, guid, type_hash, part=0):
        b = self.buckets('resource_buckets')
        h = self.res_static_hash((guid, type_hash, part))
        first, cnt = b[h % len(b)]
        for j in range(first, first + cnt):
            k = self.res_keys[j]
            if k[0] == guid and k[1] == type_hash and k[2] == part:
                return j
        return None

    def stream_end(self):
        return max(c[3] + c[4] for c in self.chunks)

    def actual_sizes(self):
        if self._actual_sizes is None:
            offs = sorted(set(v[0] for v in self.res_vals)) + [self.stream_end()]
            nxt = {offs[i]: offs[i + 1] for i in range(len(offs) - 1)}
            out = []
            for off, size in self.res_vals:
                gap = nxt[off] - (off + size)
                missing = gap - gap % RESOURCE_SIZE_MODULUS
                out.append(size + missing if (missing > 0 and gap - missing < RESOURCE_ALIGNMENT) else size)
            self._actual_sizes = out
        return self._actual_sizes

    def chunk_index_for(self, off):
        if self._chunk_starts is None:
            c = self.chunks
            ordered = all(c[i][3] + c[i][4] <= c[i + 1][3] for i in range(len(c) - 1))
            self._chunk_starts = [x[3] for x in c] if ordered else False
        if self._chunk_starts:
            i = bisect.bisect_right(self._chunk_starts, off) - 1
            if i >= 0 and off < self.chunks[i][3] + self.chunks[i][4]:
                return i
            raise ValueError(off)
        for i, c in enumerate(self.chunks):
            if c[3] <= off < c[3] + c[4]:
                return i
        raise ValueError(off)

    def chunk_raw(self, i):
        if self._resf is None:
            self._resf = open(self.res_path, 'rb')
        c = self.chunks[i]
        self._resf.seek(c[0])
        return self._resf.read(c[2])

    def chunk(self, i):
        if i in self._chunk_cache:
            self._chunk_cache.move_to_end(i)
            return self._chunk_cache[i]
        raw = self.chunk_raw(i)
        dec = zstd.decompress(raw)
        if len(dec) != self.chunks[i][4]:
            raise ValueError(f'chunk {i} decompressed {len(dec)} != {self.chunks[i][4]}')
        self._chunk_cache[i] = dec
        while len(self._chunk_cache) > 4:
            self._chunk_cache.popitem(last=False)
        return dec

    def read_stream(self, off, size):
        out = bytearray()
        while size > 0:
            ci = self.chunk_index_for(off)
            c = self.chunks[ci]
            dec = self.chunk(ci)
            rel = off - c[3]
            take = min(size, c[4] - rel)
            out += dec[rel:rel + take]
            off += take; size -= take
        return bytes(out)

    def read_resource(self, i):
        return self.read_stream(self.res_vals[i][0], self.actual_sizes()[i])

    def dat_path(self, ci):
        return os.path.join(self.game_dir, f'{self.base}_{ci:03d}.dat')

    def read_content(self, j, maxbytes=None):
        size = self.content_keys[j][0]
        off, flags, ci, _ = self.content_vals[j]
        with open(self.dat_path(ci), 'rb') as f:
            f.seek(off)
            return f.read(size if maxbytes is None else min(size, maxbytes))

    def content_guid(self, j):
        return guid_str(struct.pack('<IIII', *self.content_keys[j]))

    def res_qualified(self, i):
        k = self.res_keys[i]
        return f'{guid_str(k[0])}_{k[1]:08x}_{k[2]}'


PRIM = ['None', 'Bool', 'UInt8', 'SInt8', 'UInt16', 'SInt16', 'UInt32', 'SInt32', 'UInt64', 'SInt64',
        'Float32', 'Float64', 'Enum', 'Bitmask8', 'Bitmask16', 'Bitmask32', 'Bitmask64', 'Typedef', 'Struct',
        'StaticArray', 'DsArray', 'DsString', 'DsOptional', 'DsVariant', 'BlobArray', 'BlobString',
        'BlobOptional', 'BlobVariant', 'ObjectReference', 'Guid']


class Reflection:
    def __init__(self, exe_path):
        f = open(exe_path, 'rb')
        self.exe = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        e = self.exe
        pe = struct.unpack_from('<I', e, 0x3c)[0]
        nsec = struct.unpack_from('<H', e, pe + 6)[0]
        opt = struct.unpack_from('<H', e, pe + 20)[0]
        self.base = struct.unpack_from('<Q', e, pe + 24 + 24)[0]
        self.secs = []
        for i in range(nsec):
            o = pe + 24 + opt + 40 * i
            name = e[o:o + 8].rstrip(b'\0').decode()
            vsize, va, rsize, raw = struct.unpack_from('<IIII', e, o + 8)
            self.secs.append((name, va, vsize, raw, rsize))
        self.types = {}
        self.by_qhash = {}
        self._scan()

    def va2fo(self, v):
        r = v - self.base
        for name, va, vs, raw, rs in self.secs:
            if va <= r < va + rs:
                return raw + r - va
        return None

    def fo2va(self, fo):
        for name, va, vs, raw, rs in self.secs:
            if raw <= fo < raw + rs:
                return self.base + va + fo - raw
        return None

    def rdstr(self, va, ln):
        if ln == 0:
            return ''
        if va == 0 or ln > 4096:
            return None
        fo = self.va2fo(va)
        if fo is None:
            return None
        s = self.exe[fo:fo + ln]
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError:
            return None

    def _scan(self):
        e = self.exe
        lo, hi = self.base, self.base + max(va + vs for _, va, vs, _, _ in self.secs)
        for sname in ('.rdata', '.data'):
            sec = [s for s in self.secs if s[0] == sname][0]
            raw, rs = sec[3], sec[4]
            mv = memoryview(e)[raw:raw + rs - (rs % 8)].cast('Q')
            n = len(mv)
            for i in range(n - 18):
                ql = mv[i + 5]
                if ql == 0 or ql > 300:
                    continue
                qp = mv[i + 4]
                if not (lo <= qp < hi):
                    continue
                q = self.rdstr(qp, ql)
                if q is None or not q.isprintable():
                    continue
                fo = raw + 8 * i
                qh, ih = struct.unpack_from('<II', e, fo + 0x50)
                if fnv1a32(q.encode()) != qh:
                    continue
                t = self._read_type(fo)
                if t:
                    self.types[self.fo2va(fo)] = t
            mv.release()
        for va, t in self.types.items():
            self.by_qhash.setdefault(t['qualified_hash'], t)
        for t in self.types.values():
            t['inner'] = self._resolve(t['inner_va'])
            for fl in t['fields']:
                fl['type'] = self._resolve(fl['type_va'])

    def _resolve(self, va):
        if not va:
            return None
        t = self.types.get(va)
        if t:
            return t['qualified_name']
        fo = self.va2fo(va)
        if fo is not None:
            p = struct.unpack_from('<Q', self.exe, fo)[0]
            t = self.types.get(p)
            if t:
                return t['qualified_name']
        return f'?{va:#x}'

    def _read_type(self, fo):
        e = self.exe
        (np_, nl, ip, il, qp, ql, ns, inner) = struct.unpack_from('<8Q', e, fo)
        size, align, ealign, fcount, prim, flags = struct.unpack_from('<IHHIBB', e, fo + 0x40)
        qh, ih, sfp, efp, vtp, dvp, dvl, atp, atc = struct.unpack_from('<II7Q', e, fo + 0x50)
        if prim >= len(PRIM):
            return None
        t = dict(name=self.rdstr(np_, nl), impact_name=self.rdstr(ip, il), qualified_name=self.rdstr(qp, ql),
                 qualified_hash=qh, internal_hash=ih, size=size, alignment=align, element_alignment=ealign,
                 field_count=fcount, primitive=PRIM[prim], flags=flags, inner_va=inner, file_offset=fo,
                 fields=[], enum_values=[])
        if PRIM[prim] == 'Struct' and sfp and fcount < 4096:
            ffo = self.va2fo(sfp)
            for k in range(fcount if ffo is not None else 0):
                a = ffo + 0x30 * k
                fnp, fnl, ftype, doff, fat, fatc = struct.unpack_from('<6Q', e, a)
                t['fields'].append(dict(name=self.rdstr(fnp, fnl), type_va=ftype, offset=doff))
        if PRIM[prim] in ('Enum', 'Bitmask8', 'Bitmask16', 'Bitmask32', 'Bitmask64') and efp and fcount < 65536:
            ffo = self.va2fo(efp)
            for k in range(fcount if ffo is not None else 0):
                a = ffo + 0x28 * k
                fnp, fnl, val = struct.unpack_from('<3Q', e, a)
                t['enum_values'].append((self.rdstr(fnp, fnl), val))
        return t

    def get(self, qname):
        h = fnv1a32(qname.encode())
        return self.by_qhash.get(h)


class Decoder:
    INT = {'Bool': '<?', 'UInt8': '<B', 'SInt8': '<b', 'UInt16': '<H', 'SInt16': '<h', 'UInt32': '<I',
           'SInt32': '<i', 'UInt64': '<Q', 'SInt64': '<q', 'Float32': '<f', 'Float64': '<d',
           'Bitmask8': '<B', 'Bitmask16': '<H', 'Bitmask32': '<I', 'Bitmask64': '<Q'}

    def __init__(self, refl, max_array=256):
        self.r = refl
        self.max_array = max_array

    def t(self, qname):
        return self.r.get(qname) if qname else None

    def decode(self, qname, data, off=0, depth=0):
        t = self.t(qname)
        if t is None:
            return f'<unknown type {qname}>'
        p = t['primitive']
        if depth > 64:
            return '<depth>'
        if p in self.INT:
            v = struct.unpack_from(self.INT[p], data, off)[0]
            if p.startswith('Bitmask') and t['inner']:
                it = self.t(t['inner'])
                names = [n for n, b in (it['enum_values'] if it else []) if v & (1 << b)]
                return {'value': v, 'bits': names}
            return v
        if p == 'Enum':
            it = self.t(t['inner'])
            v = struct.unpack_from(self.INT.get(it['primitive'] if it else 'UInt32', '<I'), data, off)[0]
            for n, ev in t['enum_values']:
                if ev == v:
                    return f'{n}({v})'
            return v
        if p == 'Typedef':
            return self.decode(t['inner'], data, off, depth + 1)
        if p == 'Struct':
            out = {}
            chain = []
            cur = t
            while cur is not None:
                chain.append(cur)
                cur = self.t(cur['inner']) if cur['inner'] else None
            for st in reversed(chain):
                for fl in st['fields']:
                    try:
                        out[fl['name']] = self.decode(fl['type'], data, off + fl['offset'], depth + 1)
                    except Exception as ex:
                        out[fl['name']] = f'<err {ex}>'
            return out
        if p == 'StaticArray':
            it = self.t(t['inner'])
            return [self.decode(t['inner'], data, off + k * it['size'], depth + 1) for k in range(min(t['field_count'], self.max_array))]
        if p == 'BlobArray':
            rel, cnt = struct.unpack_from('<II', data, off)
            it = self.t(t['inner'])
            if cnt == 0:
                return []
            base = off + rel
            res = [self.decode(t['inner'], data, base + k * it['size'], depth + 1) for k in range(min(cnt, self.max_array))]
            if cnt > self.max_array:
                res.append(f'... {cnt - self.max_array} more')
            return res
        if p == 'BlobString':
            rel, ln = struct.unpack_from('<II', data, off)
            if rel == 0:
                return ''
            return data[off + rel:off + rel + ln].decode('utf-8', 'replace')
        if p == 'BlobOptional':
            rel = struct.unpack_from('<I', data, off)[0]
            if rel == 0 or not t['inner']:
                return None
            return self.decode(t['inner'], data, off + rel, depth + 1)
        if p == 'BlobVariant':
            h, rel, sz = struct.unpack_from('<III', data, off)
            if h == 0 and rel == 0:
                return None
            vt = self.r.by_qhash.get(h)
            name = vt['qualified_name'] if vt else f'{h:#010x}'
            return {'$variant': name, 'value': self.decode(name, data, off + 4 + rel, depth + 1) if vt else None}
        if p in ('ObjectReference', 'Guid'):
            g = data[off:off + 16]
            return guid_str(g) if any(g) else None
        return f'<{p} unsupported>'


VFX_RE = re.compile(r'vfx|particle|effect|destruct|debris|fragment|materialfeedback', re.I)


def type_names(kfc, game_dir, refl=None):
    names = {}
    if refl is None:
        refl = Reflection(os.path.join(game_dir, 'enshrouded.exe'))
    for th in kfc.bundle_keys:
        t = refl.by_qhash.get(th)
        names[th] = t['qualified_name'] if t else ''
    return names, refl


def cmd_index(game_dir, out):
    k = KFC(game_dir)
    names, refl = type_names(k, game_dir)
    sizes = k.actual_sizes()
    rows = []
    for i, (key, val) in enumerate(zip(k.res_keys, k.res_vals)):
        off = val[0]
        c0 = k.chunk_index_for(off)
        c1 = k.chunk_index_for(off + max(sizes[i], 1) - 1)
        ch = k.chunks[c0]
        rows.append([i, guid_str(key[0]), f'{key[1]:08x}', names.get(key[1], ''), key[2], off, val[1], sizes[i],
                     c0, c1, ch[0], off - ch[3]])
    with open(os.path.join(out, 'resources.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['index', 'guid', 'type_hash', 'type_name', 'part_index', 'stream_offset', 'stored_size',
                    'actual_size', 'chunk_first', 'chunk_last', 'chunk_file_offset_in_kfc_resources',
                    'offset_in_chunk'])
        w.writerows(rows)
    cnt = collections.Counter(); tot = collections.Counter()
    for r in rows:
        cnt[r[2]] += 1; tot[r[2]] += r[7]
    with open(os.path.join(out, 'types_summary.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['type_hash', 'type_name', 'internal_hash', 'exe_internal_hash', 'count', 'total_bytes'])
        for th, c in cnt.most_common():
            h = int(th, 16)
            t = refl.by_qhash.get(h)
            w.writerow([th, names.get(h, ''), f'{k.internal_hash[h]:08x}', f"{t['internal_hash']:08x}" if t else '',
                        c, tot[th]])
    with open(os.path.join(out, 'vfx_resources.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['index', 'guid', 'type_hash', 'type_name', 'part_index', 'stream_offset', 'actual_size'])
        for r in rows:
            if VFX_RE.search(r[3]):
                w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[7]])
    with open(os.path.join(out, 'content.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['index', 'content_hash', 'size', 'container', 'dat_file', 'offset', 'flags'])
        for j, (ck, cv) in enumerate(zip(k.content_keys, k.content_vals)):
            w.writerow([j, k.content_guid(j), ck[0], cv[2], f'enshrouded_{cv[2]:03d}.dat', cv[0], cv[1]])
    print(f'wrote {len(rows)} resources, {len(cnt)} types, {len(k.content_keys)} content entries to {out}')


def cmd_verify(game_dir, out):
    k = KFC(game_dir)
    L = []
    p = L.append
    p(f'magic={k.magic!r} data_size={k.data_size:#x} unk={k.unk} pad={k.pad} file_size={len(k.data):#x}')
    p(f'version={k.version!r}')
    for n in LOC_NAMES:
        o, c, fo = k.loc[n]
        p(f'  loc@{fo:#06x} {n:20s} abs={o:#09x} count={c}')
    p(f'bytes after data_size are zero padding: {not any(k.data[k.data_size:])} (pad to {len(k.data):#x})')
    p(f'u32 at 0x458 (chunk count written before chunk table) = {struct.unpack_from("<I", k.data, 0x458)[0]}')
    p(f'containers={len(k.containers)} sum(content_count)={sum(c[1] for c in k.containers)} content entries={len(k.content_keys)}')
    for i, (sz, cnt) in enumerate(k.containers):
        real = os.path.getsize(k.dat_path(i)) if os.path.exists(k.dat_path(i)) else None
        if real != sz:
            p(f'  container {i} size mismatch kfc={sz} disk={real}')
    if os.path.exists(k.dat_path(0)):
        p(f'all dat sizes match containers table: {all(os.path.getsize(k.dat_path(i)) == c[0] for i, c in enumerate(k.containers))}')
    rl = k.resource_locations[0]
    p(f'resource_locations[0]: uncompressed={rl[0]} compressed={rl[1]} count={rl[2]} (resources={len(k.res_keys)})')
    rsize = os.path.getsize(k.res_path)
    p(f'kfc_resources size={rsize}; last chunk end={k.chunks[-1][0] + k.chunks[-1][1]}; sum(compressed)={sum(c[2] for c in k.chunks)}; sum(uncompressed)={sum(c[4] for c in k.chunks)}')
    prev_end = 0; uprev = 0; bad = []
    frames = 0
    with open(k.res_path, 'rb') as f:
        for i, c in enumerate(k.chunks):
            if c[0] != prev_end or c[0] % 4096 or c[1] % 4096 or c[3] != uprev or c[2] > c[1]:
                bad.append(i)
            prev_end = c[0] + c[1]; uprev = c[3] + c[4]
            f.seek(c[0]); raw = f.read(c[1])
            if raw[:4] == b'\x28\xb5\x2f\xfd':
                frames += 1
            d = zstd.ZstdDecompressor()
            dec = d.decompress(raw[:c[2]])
            pad_zero = not any(raw[c[2]:])
            if not d.eof or d.unused_data or len(dec) != c[4] or not pad_zero:
                bad.append(('frame', i, d.eof, len(d.unused_data), len(dec), pad_zero))
    p(f'chunks={len(k.chunks)} zstd frames at chunk offsets={frames}; layout/frame problems: {bad or "none"}')
    mag = 0
    with open(k.res_path, 'rb') as f:
        for off in range(0, rsize, 4096):
            f.seek(off)
            if f.read(4) == b'\x28\xb5\x2f\xfd':
                mag += 1
    p(f'zstd magic at 4K-aligned offsets in kfc_resources: {mag}')
    def chk(bname, keyhash, n):
        b = k.buckets(bname); badc = 0; tot = 0
        for bi, (first, cnt) in enumerate(b):
            tot += cnt
            for j in range(first, first + cnt):
                if keyhash(j) % len(b) != bi:
                    badc += 1
        return tot, badc
    p(f'resource static map (total, misplaced) = {chk("resource_buckets", lambda j: k.res_static_hash(k.res_keys[j]), len(k.res_keys))}')
    p(f'content static map (total, misplaced) = {chk("content_buckets", lambda j: k.content_keys[j][1], len(k.content_keys))}')
    p(f'bundle static map (total, misplaced) = {chk("bundle_buckets", lambda j: k.bundle_keys[j], len(k.bundle_keys))}')
    ok = 0
    for bk, (ih, first, cnt) in zip(k.bundle_keys, k.bundle_vals):
        if all(k.res_keys[k.resource_indices[x]][1] == bk for x in range(first, first + cnt)):
            ok += 1
    p(f'bundles whose indices all point at resources of that type: {ok}/{len(k.bundle_keys)}; indices permutation: {sorted(k.resource_indices) == list(range(len(k.res_keys)))}')
    sizes = k.actual_sizes()
    iv = sorted((v[0], sizes[i], i) for i, v in enumerate(k.res_vals))
    overlaps = 0; gaps = collections.Counter(); big = []
    end = 0
    for off, sz, i in iv:
        if off < end:
            overlaps += 1
        else:
            gaps[off - end] += 1
        end = max(end, off + sz)
    p(f'stream end={k.stream_end()} last resource end={end}; overlaps={overlaps}; gap histogram (top)={gaps.most_common(6)}; max gap={max(gaps)}')
    shared = len(k.res_vals) - len(set(v[0] for v in k.res_vals))
    p(f'resources sharing an offset with another resource: {shared}')
    fixed = [(k.res_qualified(i), k.res_vals[i][1], sizes[i]) for i in range(len(sizes)) if sizes[i] != k.res_vals[i][1]]
    p(f'resources with 24-bit size truncation fixed: {len(fixed)} {fixed[:10]}')
    p(f'max stored size={max(v[1] for v in k.res_vals)} (< 2^24={1 << 24})')
    exe_dir = game_dir if os.path.exists(os.path.join(game_dir, 'enshrouded.exe')) else os.environ.get('ENSHROUDED_DIR', game_dir)
    names, refl = type_names(k, exe_dir)
    unresolved = [f'{h:08x}' for h, n in names.items() if not n]
    ihm = [f'{h:08x}' for h in k.bundle_keys if refl.by_qhash.get(h) and refl.by_qhash[h]['internal_hash'] != k.internal_hash[h]]
    p(f'reflection types found in exe: {len(refl.types)}; resource type hashes resolved: {len(names) - len(unresolved)}/{len(names)}; unresolved={unresolved}')
    p(f'bundle internal_hash != exe TypeMetadata.internal_hash for: {ihm or "none"}')
    for pth in (k.kfc_path, k.res_path):
        h = hashlib.sha1()
        with open(pth, 'rb') as f:
            for blk in iter(lambda: f.read(1 << 20), b''):
                h.update(blk)
        p(f'sha1 {os.path.basename(pth)} = {h.hexdigest()}')
    txt = '\n'.join(L)
    open(os.path.join(out, 'verify.txt'), 'w').write(txt + '\n')
    print(txt)


def cmd_types(game_dir, out):
    refl = Reflection(os.path.join(game_dir, 'enshrouded.exe'))
    types = sorted(refl.types.values(), key=lambda t: t['qualified_name'] or '')
    js = []
    with open(os.path.join(out, 'reflection_types.txt'), 'w', encoding='utf-8') as f:
        for t in types:
            f.write(f"{t['qualified_name']}  prim={t['primitive']} size={t['size']} align={t['alignment']} "
                    f"qhash={t['qualified_hash']:08x} ihash={t['internal_hash']:08x} flags={t['flags']:#x} "
                    f"inner={t['inner']} fields={t['field_count']} @exe+{t['file_offset']:#x}\n")
            for fl in t['fields']:
                f.write(f"    +{fl['offset']:#06x} {fl['name']}: {fl['type']}\n")
            for n, v in t['enum_values']:
                f.write(f"    = {v} {n}\n")
            js.append({kk: vv for kk, vv in t.items() if kk not in ('inner_va',)} | {
                'fields': [{'name': fl['name'], 'type': fl['type'], 'offset': fl['offset']} for fl in t['fields']]})
    json.dump(js, open(os.path.join(out, 'reflection_types.json'), 'w'), indent=0)
    print(f'{len(types)} types')


def select(k, names, sels):
    by_name = collections.defaultdict(list)
    for i, key in enumerate(k.res_keys):
        by_name[names.get(key[1], '')].append(i)
    out = []
    limit = None
    for s in sels:
        if s.startswith('limit='):
            limit = int(s[6:]); continue
        if s.startswith('type:'):
            tn = s[5:]
            if '::' not in tn:
                tn = 'keen::' + tn
            idx = by_name.get(tn, [])
            out += idx[:limit] if limit else idx
        elif '_' in s:
            g, th, part = s.split('_')
            out.append(k.res_by_id[(guid_from_str(g), int(th, 16), int(part))])
        else:
            out += k.res_by_guid[guid_from_str(s)]
    return out


def cmd_extract(game_dir, out, sels, decode=False):
    k = KFC(game_dir)
    names, refl = type_names(k, game_dir)
    dec = Decoder(refl) if decode else None
    idx = select(k, names, sels)
    for i in idx:
        key = k.res_keys[i]
        tn = names.get(key[1], f'{key[1]:08x}')
        d = os.path.join(out, 'extract', tn.replace('keen::', '').replace('::', '.'))
        os.makedirs(d, exist_ok=True)
        data = k.read_resource(i)
        base = os.path.join(d, k.res_qualified(i))
        open(base + '.bin', 'wb').write(data)
        msg = f'{k.res_qualified(i)} {tn} {len(data)} bytes -> {base}.bin'
        if dec:
            try:
                obj = dec.decode(tn, data, 0)
            except Exception as ex:
                obj = f'<decode error {ex!r}>'
            json.dump(obj, open(base + '.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            msg += ' (+json)'
        print(msg)


def cmd_vfxscan(game_dir, out, extract_guids=()):
    k = KFC(game_dir)
    names, refl = type_names(k, game_dir)
    dec = Decoder(refl, max_array=1 << 20)
    cmap = {ck: j for j, ck in enumerate(k.content_keys)}
    th_vfx = fnv1a32(b'keen::VfxResource')
    th_mf = fnv1a32(b'keen::MaterialFeedback')
    vfx_guids = {}
    rows_v, rows_p = [], []

    def content_loc(h):
        if not h:
            return None
        key = (h['size'], h['hash0'], h['hash1'], h['hash2'])
        if key == (0, 0, 0, 0):
            return None
        j = cmap.get(key)
        if j is None:
            return ('missing', 'NOT_IN_KFC:' + guid_str(struct.pack('<IIII', *key)))
        off, flags, ci, _ = k.content_vals[j]
        return (j, k.content_guid(j), h['size'], ci, off)

    for i, key in enumerate(k.res_keys):
        if key[1] != th_vfx:
            continue
        data = k.read_resource(i)
        o = dec.decode('keen::VfxResource', data)
        g = guid_str(key[0])
        vfx_guids[g] = i
        parts = o['particles']
        state_members = []
        for si in o['stateInfos']:
            state_members.append('|'.join(m['name'] for m in si['members']))
        rows_v.append([g, len(data), o['killTimeInSeconds'], o['emitterCount'], o['useNewVm'], len(parts),
                       len(o['springs']), len(o['gpuResourceData']), len(o['meshes']), len(o['models']),
                       len(o['decals']), len(o['sounds']), len(o['curves']), len(o['parameters']),
                       ';'.join(p['debugName'] for p in parts)])
        for pi, p in enumerate(parts):
            cl = content_loc(p['code']['hash'])
            sl = content_loc(p['strippedCode']['hash'])
            rows_p.append([g, pi, p['debugName'], p['depth'], p['stateSizeInBytes'], p['parent'], p['child'],
                           p['maxCount'], len(p['initialState']),
                           cl[1] if cl else '', cl[2] if cl and cl[0] != 'missing' else '',
                           f'enshrouded_{cl[3]:03d}.dat@{cl[4]}' if cl and cl[0] != 'missing' else '',
                           sl[1] if sl else '', sl[2] if sl and sl[0] != 'missing' else '',
                           f'enshrouded_{sl[3]:03d}.dat@{sl[4]}' if sl and sl[0] != 'missing' else '',
                           state_members[pi] if pi < len(state_members) else ''])
        if g in extract_guids:
            d = os.path.join(out, 'extract', 'VfxResource')
            os.makedirs(d, exist_ok=True)
            base = os.path.join(d, k.res_qualified(i))
            open(base + '.bin', 'wb').write(data)
            json.dump(o | {'gpuResourceData': f'<{len(o["gpuResourceData"])} bytes>'},
                      open(base + '.json', 'w', encoding='utf-8'), indent=1)
            for pi, p in enumerate(parts):
                for fld in ('code', 'strippedCode'):
                    cl = content_loc(p[fld]['hash'])
                    if cl and cl[0] != 'missing':
                        blob = k.read_content(cl[0])
                        open(f'{base}.p{pi}.{fld}.{cl[1]}.bin', 'wb').write(blob)
            print('extracted', base)
    with open(os.path.join(out, 'vfx_resources_detail.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['guid', 'bytes', 'killTimeInSeconds', 'emitterCount', 'useNewVm', 'particles', 'springs',
                    'gpuResourceData_bytes', 'meshes', 'models', 'decals', 'sounds', 'curves', 'parameters',
                    'particle_debugNames'])
        w.writerows(rows_v)
    with open(os.path.join(out, 'vfx_particles.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['vfx_guid', 'particle_index', 'debugName', 'depth', 'stateSizeInBytes', 'parent', 'child',
                    'maxCount', 'initialState_bytes', 'code_content_hash', 'code_size', 'code_location',
                    'strippedCode_content_hash', 'strippedCode_size', 'strippedCode_location', 'state_members'])
        w.writerows(rows_p)
    evnames = ['OnPlace', 'OnPickup', 'OnTearDown', 'OnDestruction', 'OnFlatten', 'OnPileUp']
    rows_m = []
    for i, key in enumerate(k.res_keys):
        if key[1] != th_mf:
            continue
        o = dec.decode('keen::MaterialFeedback', k.read_resource(i))
        for cls in ('Tiny', 'Small', 'Medium', 'Large'):
            for ei, eff in enumerate(o[f'eventEffects{cls}']):
                if eff['vfx']:
                    rows_m.append([guid_str(key[0]), o['id'], '|'.join(o['eventTypeMask']['bits']), cls, evnames[ei], eff['description'],
                                   eff['vfx'], eff['vfx'] in vfx_guids, eff['flags']])
    with open(os.path.join(out, 'material_feedback_vfx.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['materialfeedback_guid', 'id', 'eventTypeMask', 'size_class', 'event', 'description',
                    'vfx_guid', 'vfx_is_VfxResource', 'flags'])
        w.writerows(rows_m)
    print(f'{len(rows_v)} VfxResources, {len(rows_p)} particles, {len(rows_m)} material-feedback vfx refs')


def build_content_tables(keys, vals, nbuckets):
    order = sorted(range(len(keys)), key=lambda j: keys[j][1] % nbuckets)
    counts = [0] * nbuckets
    for j in order:
        counts[keys[j][1] % nbuckets] += 1
    buckets, first = bytearray(), 0
    for c in counts:
        buckets += struct.pack('<II', first, c)
        first += c
    return {
        'content_buckets': (bytes(buckets), nbuckets),
        'content_keys': (b''.join(struct.pack('<IIII', *keys[j]) for j in order), len(keys)),
        'content_values': (b''.join(struct.pack('<IHHQ', *vals[j]) for j in order), len(vals)),
    }


def build_kfc_bytes(k, chunks, res_vals, resource_locations, tables=None):
    d = k.data
    b = bytearray(0x90)
    locs = {}
    tables = tables or {}
    def align(n):
        while len(b) % n:
            b.append(0)
    def put(name, blob, count):
        locs[name] = (len(b), count)
        b.extend(blob)
    def raw(name, elem):
        if name in tables:
            return tables[name]
        o, n, _ = k.loc[name]
        return d[o:o + n * elem], n
    put('version', k.version.encode(), len(k.version.encode())); align(8)
    put('containers', *raw('containers', 16)); align(8)
    put('resource_locations', b''.join(struct.pack('<III', *r) for r in resource_locations), len(resource_locations)); align(8)
    b.extend(struct.pack('<I', len(chunks)))
    put('resource_chunks', b''.join(struct.pack('<5I', *c) for c in chunks), len(chunks))
    put('resource_indices', *raw('resource_indices', 4))
    put('content_buckets', *raw('content_buckets', 8))
    put('content_keys', *raw('content_keys', 16)); align(8)
    put('content_values', *raw('content_values', 16))
    put('resource_buckets', *raw('resource_buckets', 8))
    put('resource_keys', *raw('resource_keys', 32)); align(8)
    put('resource_values', b''.join(struct.pack('<II', *v) for v in res_vals), len(res_vals))
    put('bundle_buckets', *raw('bundle_buckets', 8))
    put('bundle_keys', *raw('bundle_keys', 4))
    put('bundle_values', *raw('bundle_values', 12))
    size = len(b)
    align(0x1000)
    struct.pack_into('<4sIII', b, 0, b'KFC4', size, k.unk, k.pad)
    for i, n in enumerate(LOC_NAMES):
        fo = 0x10 + 8 * i
        if n in locs:
            o, c = locs[n]
            struct.pack_into('<II', b, fo, o - fo, c)
    return bytes(b)


def write_resources_file(k, path, replaced_chunks, extra_chunks):
    new = []
    with open(path, 'wb') as f:
        pos = 0
        allc = [(i, None) for i in range(len(k.chunks))] + [(None, e) for e in extra_chunks]
        for i, extra in allc:
            if extra is not None:
                comp, uoff, usize = extra
            else:
                c = k.chunks[i]
                comp = replaced_chunks.get(i) or k.chunk_raw(i)
                uoff, usize = c[3], c[4]
            fsize = (len(comp) + 0xfff) & ~0xfff
            f.write(comp + b'\0' * (fsize - len(comp)))
            new.append((pos, fsize, len(comp), uoff, usize))
            pos += fsize
    return new


def cmd_roundtrip(game_dir, out):
    k = KFC(game_dir)
    rebuilt = build_kfc_bytes(k, k.chunks, k.res_vals, k.resource_locations)
    same = rebuilt == k.data
    print(f'rebuilt kfc from parsed tables: {len(rebuilt)} bytes, byte-identical to original: {same}')
    if not same:
        diff = next(i for i in range(min(len(rebuilt), len(k.data))) if rebuilt[i] != k.data[i])
        print('first diff at', hex(diff))


def cmd_patch(game_dir, out, sel, repl_path, mode='auto', level=19):
    k = KFC(game_dir)
    names, _ = type_names(k, game_dir)
    idx = select(k, names, [sel])
    assert len(idx) == 1, idx
    i = idx[0]
    new = open(repl_path, 'rb').read()
    old_size = k.actual_sizes()[i]
    if mode == 'auto':
        mode = 'inplace' if len(new) == old_size else 'append'
    assert len(new) < RESOURCE_SIZE_MODULUS, 'append mode cannot express >=16MiB sizes'
    od = os.path.join(out, 'patched'); os.makedirs(od, exist_ok=True)
    res_vals = list(k.res_vals)
    replaced, extra = {}, []
    if mode == 'inplace':
        assert len(new) == old_size, 'inplace needs identical size'
        off = k.res_vals[i][0]
        c0 = k.chunk_index_for(off); c1 = k.chunk_index_for(off + old_size - 1)
        pos = 0
        for ci in range(c0, c1 + 1):
            c = k.chunks[ci]
            buf = bytearray(k.chunk(ci))
            s = max(off, c[3]); e = min(off + old_size, c[3] + c[4])
            buf[s - c[3]:e - c[3]] = new[pos:pos + (e - s)]; pos += e - s
            replaced[ci] = zstd.compress(bytes(buf), level=level)
    else:
        end = k.stream_end()
        start = (end + RESOURCE_ALIGNMENT - 1) & ~(RESOURCE_ALIGNMENT - 1)
        blob = b'\0' * (start - end) + new
        extra.append((zstd.compress(blob, level=level), end, len(blob)))
        res_vals[i] = (start, len(new))
    chunks = write_resources_file(k, os.path.join(od, 'enshrouded.kfc_resources'), replaced, extra)
    tot_u = max(c[3] + c[4] for c in chunks)
    rl = [(tot_u, sum(c[2] for c in chunks), k.resource_locations[0][2])] + k.resource_locations[1:]
    open(os.path.join(od, 'enshrouded.kfc'), 'wb').write(build_kfc_bytes(k, chunks, res_vals, rl))
    k2 = KFC(od)
    got = k2.read_resource(i)
    print(f'patched {k.res_qualified(i)} mode={mode} old={old_size} new={len(new)} readback_ok={got == new}')
    bad = 0
    sizes1, sizes2 = k.actual_sizes(), k2.actual_sizes()
    order1 = sorted(range(len(k.res_keys)), key=lambda j: k.res_vals[j][0])
    h1 = {j: hashlib.sha1(k.read_resource(j)).digest() for j in order1 if j != i}
    order2 = sorted(range(len(k2.res_keys)), key=lambda j: k2.res_vals[j][0])
    for j in order2:
        if j != i and hashlib.sha1(k2.read_resource(j)).digest() != h1[j]:
            bad += 1
    print(f'other resources unchanged: {bad == 0} (mismatches={bad}); chunks {len(k.chunks)} -> {len(chunks)}; '
          f'kfc_resources {os.path.getsize(k.res_path)} -> {os.path.getsize(k2.res_path)}')


if __name__ == '__main__':
    cmd, game_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == 'roundtrip':
        cmd_roundtrip(game_dir, out); sys.exit(0)
    if cmd == 'patch':
        os.makedirs(out, exist_ok=True)
        cmd_patch(game_dir, out, sys.argv[4], sys.argv[5], *(sys.argv[6:7] or ['auto']))
        sys.exit(0)
    if cmd == 'vfxscan':
        os.makedirs(out, exist_ok=True)
        cmd_vfxscan(game_dir, out, set(sys.argv[4:]))
        sys.exit(0)
    os.makedirs(out, exist_ok=True)
    if cmd == 'index':
        cmd_index(game_dir, out)
    elif cmd == 'verify':
        cmd_verify(game_dir, out)
    elif cmd == 'types':
        cmd_types(game_dir, out)
    elif cmd == 'extract':
        cmd_extract(game_dir, out, sys.argv[4:])
    elif cmd == 'decode':
        cmd_extract(game_dir, out, sys.argv[4:], decode=True)
    else:
        print('usage: kfc4.py index|verify|types|extract|decode|roundtrip|patch|vfxscan <game_dir> <out_dir> [args...]')
