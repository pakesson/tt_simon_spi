import cocotb

from simon import SimonCipher
from simon_reference import simon_encrypt_ref

@cocotb.test()
async def test_reference_implementation(dut):
    key = bytes.fromhex("1f1e1d1c1b1a19181716151413121110")
    pt = bytes.fromhex("656b696c20646e75")
    ct = simon_encrypt_ref(key, pt)

    key_int = int.from_bytes(key, byteorder='big', signed=False)
    pt_int = int.from_bytes(pt, byteorder='big', signed=False)
    ct_int = int.from_bytes(ct, byteorder='big', signed=False)
    cipher = SimonCipher(key_int, key_size=128, block_size=64)
    assert cipher.encrypt(pt_int) == ct_int
    assert cipher.decrypt(ct_int) == pt_int


@cocotb.test()
async def test_known_answer_vector_reference_and_library(dut):
    key = bytes.fromhex("1b1a1918131211100b0a090803020100")
    pt = bytes.fromhex("656b696c20646e75")
    expected_ct = bytes.fromhex("44c8fc20b9dfa07a")

    ref_ct = simon_encrypt_ref(key, pt)
    assert ref_ct == expected_ct

    cipher = SimonCipher(int.from_bytes(key, "big"), key_size=128, block_size=64)
    lib_ct = cipher.encrypt(int.from_bytes(pt, "big"))
    assert lib_ct == int.from_bytes(expected_ct, "big")
    assert cipher.decrypt(lib_ct) == int.from_bytes(pt, "big")
