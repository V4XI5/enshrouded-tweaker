import struct

M64 = 0xFFFFFFFFFFFFFFFF


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        b >>= 1
    return r


def _build_tables():
    sbox = [0] * 256
    for x in range(256):
        inv = 0
        if x:
            for y in range(1, 256):
                if _gmul(x, y) == 1:
                    inv = y
                    break
        b = inv
        s = b
        for k in range(1, 5):
            s ^= ((b << k) | (b >> (8 - k))) & 0xFF
        sbox[x] = s ^ 0x63
    inv_sbox = [0] * 256
    for x, s in enumerate(sbox):
        inv_sbox[s] = x
    assert sbox[0] == 0x63 and sbox[1] == 0x7C and inv_sbox[0] == 0x52
    m = [[14, 11, 13, 9], [9, 14, 11, 13], [13, 9, 14, 11], [11, 13, 9, 14]]
    tables = []
    for j in range(4):
        t = []
        for x in range(256):
            v = inv_sbox[x]
            t.append(sum(_gmul(v, m[i][j]) << (8 * i) for i in range(4)))
        tables.append(t)
    return sbox, inv_sbox, tables


_SBOX, _INV_SBOX, (_T0, _T1, _T2, _T3) = _build_tables()


def aesdec(state, key):
    c0, c1, c2, c3 = state
    k0, k1, k2, k3 = key
    o0 = _T0[c0 & 0xFF] ^ _T1[(c3 >> 8) & 0xFF] ^ _T2[(c2 >> 16) & 0xFF] ^ _T3[c1 >> 24] ^ k0
    o1 = _T0[c1 & 0xFF] ^ _T1[(c0 >> 8) & 0xFF] ^ _T2[(c3 >> 16) & 0xFF] ^ _T3[c2 >> 24] ^ k1
    o2 = _T0[c2 & 0xFF] ^ _T1[(c1 >> 8) & 0xFF] ^ _T2[(c0 >> 16) & 0xFF] ^ _T3[c3 >> 24] ^ k2
    o3 = _T0[c3 & 0xFF] ^ _T1[(c2 >> 8) & 0xFF] ^ _T2[(c1 >> 16) & 0xFF] ^ _T3[c0 >> 24] ^ k3
    return (o0, o1, o2, o3)


_LANE_INIT = [struct.unpack('<4I', bytes(range(16 * i, 16 * i + 16))) for i in range(4)]


def keen_hash128(data, seed=0):
    n = len(data)
    A, B, C, D = _LANE_INIT
    nblk = n >> 6
    if nblk:
        words = struct.unpack_from(f'<{nblk * 16}I', data, 0)
        dec = aesdec
        for i in range(0, nblk * 16, 16):
            A = dec(A, words[i:i + 4])
            B = dec(B, words[i + 4:i + 8])
            C = dec(C, words[i + 8:i + 12])
            D = dec(D, words[i + 12:i + 16])
    base = nblk << 6
    r = n - base
    nb16 = r >> 4
    if nb16 >= 3:
        C = aesdec(C, struct.unpack_from('<4I', data, base + 32))
    if nb16 >= 2:
        B = aesdec(B, struct.unpack_from('<4I', data, base + 16))
    if nb16 >= 1:
        A = aesdec(A, struct.unpack_from('<4I', data, base))
    t = r & 15
    if t:
        tail = data[base + (r & 0x30):n] + bytes(16 - t)
        D = aesdec(D, struct.unpack('<4I', tail))
    S = struct.unpack('<4I', struct.pack('<QQ', (seed - n) & M64, (seed + n + 1) & M64))
    D = aesdec(D, S)
    C = aesdec(C, S)
    B = aesdec(B, S)
    A = aesdec(A, S)
    C = aesdec(C, D)
    A = aesdec(A, B)
    C = aesdec(C, S)
    A = aesdec(A, C)
    A = aesdec(A, S)
    return struct.pack('<4I', *A)


def content_key(data):
    n = len(data)
    if n > 0x7FFFFFFF:
        raise ValueError('content too large (game returns error 0x23)')
    h = keen_hash128(data, 0)
    _, h0, h1, h2 = struct.unpack('<4I', h)
    return (n, h0, h1, h2)


def content_key_bytes(data):
    return struct.pack('<4I', *content_key(data))


if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        with open(path, 'rb') as f:
            d = f.read()
        print(path, content_key_bytes(d).hex(), ['0x%08X' % x for x in content_key(d)])
