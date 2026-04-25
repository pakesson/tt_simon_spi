def _rol32(x, n):
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def simon_round_keys(key_bytes):
    c = 0xFFFFFFFC
    z = 0b11110000101100111001010001001000000111101001100011010111011011
    z_len = 62
    key = int.from_bytes(key_bytes, "big")
    k = [
        key & 0xFFFFFFFF,
        (key >> 32) & 0xFFFFFFFF,
        (key >> 64) & 0xFFFFFFFF,
        (key >> 96) & 0xFFFFFFFF,
    ]
    out = []
    z_shift = z
    for _ in range(44):
        out.append(k[0])
        s3 = _rol32(k[3], 29)
        mix0 = s3 ^ k[1]
        s1 = _rol32(mix0, 31)
        newk = (c ^ (z_shift & 1) ^ k[0] ^ mix0 ^ s1) & 0xFFFFFFFF
        k = [k[1], k[2], k[3], newk]
        z_shift = ((z_shift >> 1) | ((z_shift & 1) << (z_len - 1))) & ((1 << z_len) - 1)
    return out


def simon_encrypt_ref(key_bytes, block_bytes):
    rk = simon_round_keys(key_bytes)
    x = int.from_bytes(block_bytes[:4], "big")
    y = int.from_bytes(block_bytes[4:], "big")
    for i in range(44):
        f = ((_rol32(x, 1) & _rol32(x, 8)) ^ _rol32(x, 2)) & 0xFFFFFFFF
        x, y = (y ^ f ^ rk[i]) & 0xFFFFFFFF, x
    return ((x << 32) | y).to_bytes(8, "big")
