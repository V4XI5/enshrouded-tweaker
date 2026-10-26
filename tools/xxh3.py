import struct

M64 = 0xFFFFFFFFFFFFFFFF
P32_1, P32_2, P32_3 = 0x9E3779B1, 0x85EBCA77, 0xC2B2AE3D
P64_1, P64_2, P64_3, P64_4, P64_5 = (0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9,
                                     0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5)
MIX_1, MIX_2 = 0x165667919E3779F9, 0x9FB21C651E98DF25
SECRET = bytes.fromhex(
    'b8fe6c3923a44bbe7c01812cf721ad1cded46de9839097db7240a4a4b7b3671fcb79e64eccc0e578825ad07dccff7221b8084674f743248e'
    'e03590e6813a264c3c2852bb91c300cb88d0658b1b532ea371644897a20df94e3819ef46a9deacd8a8fa763fe39c343ff9dcbbc7c70b4f1d'
    '8a51e04bcdb45931c89f7ec9d9787364eac5ac8334d3ebc3c581a0fffa1363eb170ddd51b7f0da49d316552629d4689e2b16be587d47a1fc'
    '8ff8b8d17ad031ce45cb3a8f95160428afd7fbcabb4b407e')
STRIPE, ACCS = 64, 8
STRIPES_PER_BLOCK = (len(SECRET) - STRIPE) // 8
BLOCK = STRIPE * STRIPES_PER_BLOCK


def _r64(b, o):
    return struct.unpack_from('<Q', b, o)[0]


def _r32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & M64


def _fold(a, b):
    p = a * b
    return (p & M64) ^ (p >> 64)


def _avalanche(h):
    h ^= h >> 37
    h = (h * MIX_1) & M64
    return h ^ (h >> 32)


def _avalanche64(h):
    h ^= h >> 33
    h = (h * P64_2) & M64
    h ^= h >> 29
    h = (h * P64_3) & M64
    return h ^ (h >> 32)


def _rrmxmx(h, n):
    h ^= _rotl(h, 49) ^ _rotl(h, 24)
    h = (h * MIX_2) & M64
    h ^= (h >> 35) + n
    h = (h * MIX_2) & M64
    return h ^ (h >> 28)


def _mix16(d, o, so):
    return _fold(_r64(d, o) ^ _r64(SECRET, so), _r64(d, o + 8) ^ _r64(SECRET, so + 8))


def _short(d):
    n = len(d)
    if n > 8:
        lo = _r64(d, 0) ^ (_r64(SECRET, 24) ^ _r64(SECRET, 32))
        hi = _r64(d, n - 8) ^ (_r64(SECRET, 40) ^ _r64(SECRET, 48))
        swapped = int.from_bytes(lo.to_bytes(8, 'little'), 'big')
        return _avalanche((n + swapped + hi + _fold(lo, hi)) & M64)
    if n >= 4:
        v = (_r32(d, n - 4) + (_r32(d, 0) << 32)) & M64
        return _rrmxmx(v ^ (_r64(SECRET, 8) ^ _r64(SECRET, 16)), n)
    if n:
        c = (d[0] << 16) | (d[n >> 1] << 24) | d[n - 1] | (n << 8)
        return _avalanche64(c ^ (_r32(SECRET, 0) ^ _r32(SECRET, 4)))
    return _avalanche64(_r64(SECRET, 56) ^ _r64(SECRET, 64))


def _medium(d):
    n = len(d)
    acc = n * P64_1
    if n <= 128:
        if n > 32:
            if n > 64:
                if n > 96:
                    acc += _mix16(d, 48, 96) + _mix16(d, n - 64, 112)
                acc += _mix16(d, 32, 64) + _mix16(d, n - 48, 80)
            acc += _mix16(d, 16, 32) + _mix16(d, n - 32, 48)
        acc += _mix16(d, 0, 0) + _mix16(d, n - 16, 16)
        return _avalanche(acc & M64)
    for i in range(8):
        acc += _mix16(d, 16 * i, 16 * i)
    acc = _avalanche(acc & M64)
    for i in range(8, n // 16):
        acc += _mix16(d, 16 * i, 16 * (i - 8) + 3)
    acc += _mix16(d, n - 16, 136 - 17)
    return _avalanche(acc & M64)


def _long(d):
    n = len(d)
    acc = [P32_3, P64_1, P64_2, P64_3, P64_4, P32_2, P64_5, P32_1]

    def accumulate(off, so):
        data, keys = struct.unpack_from('<8Q', d, off), struct.unpack_from('<8Q', SECRET, so)
        for i in range(ACCS):
            v = data[i]
            x = v ^ keys[i]
            acc[i ^ 1] = (acc[i ^ 1] + v) & M64
            acc[i] = (acc[i] + (x & 0xFFFFFFFF) * (x >> 32)) & M64

    blocks = (n - 1) // BLOCK
    scramble = struct.unpack_from('<8Q', SECRET, len(SECRET) - STRIPE)
    for b in range(blocks):
        for s in range(STRIPES_PER_BLOCK):
            accumulate(b * BLOCK + s * STRIPE, s * 8)
        for i in range(ACCS):
            a = acc[i] ^ (acc[i] >> 47) ^ scramble[i]
            acc[i] = (a * P32_1) & M64
    for s in range(((n - 1) - BLOCK * blocks) // STRIPE):
        accumulate(blocks * BLOCK + s * STRIPE, s * 8)
    accumulate(n - STRIPE, len(SECRET) - STRIPE - 7)
    res = n * P64_1
    for i in range(4):
        res += _fold(acc[2 * i] ^ _r64(SECRET, 11 + 16 * i), acc[2 * i + 1] ^ _r64(SECRET, 11 + 16 * i + 8))
    return _avalanche(res & M64)


def xxh3_64(data):
    d = bytes(data)
    if len(d) <= 16:
        return _short(d)
    if len(d) <= 240:
        return _medium(d)
    return _long(d)


def check():
    return (xxh3_64(b'') == 0x2D06800538D394C2 and len(SECRET) == 192
            and SECRET[:8] == bytes.fromhex('b8fe6c3923a44bbe'))
