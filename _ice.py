"""ICE level-0 cipher — encrypt only + size-limited header decrypt.

Implements just enough of the ICE algorithm
for BDO music file creation.  There is no general-purpose decrypt function.
The only decrypt capability is limited to extracting the owner ID from
single-note files (< 512 bytes).
"""


_KA = b'\xa3\x71\x8f\x92\x46\xb2\xc8\x55'
_KB = b'\xf2\x82\x80\x83\x42\x96\xa2\x55'

# S-box parameters
_SMOD = (
    (333, 313, 505, 369),
    (379, 375, 319, 391),
    (361, 445, 451, 397),
    (397, 425, 395, 505),
)
_SXOR = (
    (0x83, 0x85, 0x9B, 0xCD),
    (0xCC, 0xA7, 0xAD, 0x41),
    (0x4B, 0x2E, 0xD4, 0x33),
    (0xEA, 0xCB, 0x2E, 0x04),
)
_PBOX = (
    0x00000001, 0x00000080, 0x00000400, 0x00002000,
    0x00080000, 0x00200000, 0x01000000, 0x40000000,
    0x00000008, 0x00000020, 0x00000100, 0x00004000,
    0x00010000, 0x00800000, 0x04000000, 0x20000000,
    0x00000004, 0x00000010, 0x00000200, 0x00008000,
    0x00020000, 0x00400000, 0x08000000, 0x10000000,
    0x00000002, 0x00000040, 0x00000800, 0x00001000,
    0x00040000, 0x00100000, 0x02000000, 0x80000000,
)
_KEYROT = (0, 1, 2, 3, 2, 1, 3, 0, 1, 3, 2, 0, 3, 1, 0, 2)

# Precomputed S-boxes (built once on import)
_sbox = [None] * 4


def _perm32(x):
    result = 0
    i = 0
    while x:
        if x & 1:
            result |= _PBOX[i]
        i += 1
        x >>= 1
    return result


def _gf_mult(a, b, m):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a <<= 1
        b >>= 1
        if a >= 256:
            a ^= m
    return result


def _gf_exp7(b, m):
    if b == 0:
        return 0
    x = _gf_mult(b, b, m)
    x = _gf_mult(b, x, m)
    x = _gf_mult(x, x, m)
    return _gf_mult(b, x, m)


def _init_sbox():
    for i in range(4):
        _sbox[i] = [0] * 1024
    for i in range(1024):
        col = (i >> 1) & 0xFF
        row = (i & 0x1) | ((i & 0x200) >> 8)
        _sbox[0][i] = _perm32(_gf_exp7(col ^ _SXOR[0][row], _SMOD[0][row]) << 24)
        _sbox[1][i] = _perm32(_gf_exp7(col ^ _SXOR[1][row], _SMOD[1][row]) << 16)
        _sbox[2][i] = _perm32(_gf_exp7(col ^ _SXOR[2][row], _SMOD[2][row]) << 8)
        _sbox[3][i] = _perm32(_gf_exp7(col ^ _SXOR[3][row], _SMOD[3][row]))


def _build_key_schedule():
    """Build level-0 (8-round) key schedule from the obfuscated key."""
    key = bytes(a ^ b for a, b in zip(_KA, _KB))
    ks = [[0, 0, 0] for _ in range(8)]
    kb = [0] * 4
    for i in range(4):
        kb[3 - i] = (key[i * 2] << 8) | key[i * 2 + 1]
    for i in range(8):
        kr = _KEYROT[i]
        for j in range(15):
            for k in range(4):
                t = (kr + k) & 3
                kbb = kb[t]
                bit = kbb & 1
                ks[i][j % 3] = (ks[i][j % 3] << 1) | bit
                kb[t] = (kbb >> 1) | ((bit ^ 1) << 15)
    return ks


def _ice_f(p, sk):
    tl = ((p >> 16) & 0x3FF) | (((p >> 14) | (p << 18)) & 0xFFC00)
    tr = (p & 0x3FF) | ((p << 2) & 0xFFC00)
    al = sk[2] & (tl ^ tr)
    ar = al ^ tr ^ sk[1]
    al ^= tl ^ sk[0]
    return _sbox[0][al >> 10] | _sbox[1][al & 0x3FF] | _sbox[2][ar >> 10] | _sbox[3][ar & 0x3FF]


# Initialize on import
_init_sbox()
_KS = _build_key_schedule()


def _encrypt_block(data, offset=0):
    """Encrypt a single 8-byte block. Returns list of 8 ints."""
    l = r = 0
    for i in range(4):
        t = 24 - i * 8
        l |= (data[offset + i] & 0xFF) << t
        r |= (data[offset + i + 4] & 0xFF) << t
    for i in range(0, 8, 2):
        l ^= _ice_f(r, _KS[i])
        r ^= _ice_f(l, _KS[i + 1])
    out = [0] * 8
    for i in range(4):
        out[3 - i] = r & 0xFF
        out[7 - i] = l & 0xFF
        r >>= 8
        l >>= 8
    return out


def encrypt(plaintext):
    """Encrypt plaintext bytes with ICE level-0. Processes full 8-byte blocks."""
    out = bytearray()
    i = 0
    remaining = len(plaintext)
    while remaining >= 8:
        out.extend(_encrypt_block(plaintext, i))
        i += 8
        remaining -= 8
    if remaining > 0:
        out.extend(plaintext[i:])
    return bytes(out)


def _decrypt_block(data, offset=0):
    """Decrypt a single 8-byte block"""
    l = r = 0
    for i in range(4):
        t = 24 - i * 8
        l |= (data[offset + i] & 0xFF) << t
        r |= (data[offset + i + 4] & 0xFF) << t
    for i in range(7, 0, -2):
        l ^= _ice_f(r, _KS[i])
        r ^= _ice_f(l, _KS[i - 1])
    out = [0] * 8
    for i in range(4):
        out[3 - i] = r & 0xFF
        out[7 - i] = l & 0xFF
        r >>= 8
        l >>= 8
    return out


# Maximum encrypted payload size for owner ID extraction (single-note file).
# 512 gives comfortable margin.
_MAX_OWNER_FILE_SIZE = 512


def decrypt_owner_header(ciphertext):
    """Decrypt the payload of a small BDO file for owner ID extraction.

    Only accepts files with payloads up to 512 bytes (single-note files).
    Raises ValueError if the data is too large.

    Args:
        ciphertext: The encrypted payload (after the 4-byte version header).

    Returns:
        Decrypted plaintext bytes.
    """
    if len(ciphertext) > _MAX_OWNER_FILE_SIZE:
        raise ValueError(
            "File too large for owner ID extraction — "
            "use a single-note file saved in-game")
    out = bytearray()
    i = 0
    remaining = len(ciphertext)
    while remaining >= 8:
        out.extend(_decrypt_block(ciphertext, i))
        i += 8
        remaining -= 8
    if remaining > 0:
        out.extend(ciphertext[i:])
    return bytes(out)
