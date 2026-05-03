import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from simon import SimonCipher
from simon_reference import simon_encrypt_ref

CMD_WRITE_KEY_128 = 0x10
CMD_WRITE_BLOCK_64 = 0x20
CMD_START_ENCRYPT = 0x30
CMD_START_DECRYPT = 0x31
CMD_READ_BLOCK_64 = 0x40
CMD_READ_STATUS = 0x50


async def _spi_idle(dut):
    dut.spi_cs_n.value = 1
    dut.spi_sck.value = 0
    dut.spi_mosi.value = 0
    await ClockCycles(dut.clk, 8)

async def spi_transfer_byte(dut, tx_byte):
    rx = 0
    for bit in range(8):
        mosi = (tx_byte >> (7 - bit)) & 0x1
        dut.spi_mosi.value = mosi

        dut.spi_sck.value = 0
        await ClockCycles(dut.clk, 10)

        dut.spi_sck.value = 1
        await ClockCycles(dut.clk, 6)
        rx = (rx << 1) | int(dut.spi_miso.value)
        await ClockCycles(dut.clk, 4)

        dut.spi_sck.value = 0
        await ClockCycles(dut.clk, 6)
    return rx

async def spi_write_cmd_and_payload(dut, cmd, payload):
    dut.spi_cs_n.value = 0
    await ClockCycles(dut.clk, 16)
    await spi_transfer_byte(dut, cmd)
    await ClockCycles(dut.clk, 8)
    for b in payload:
        await spi_transfer_byte(dut, b)
        await ClockCycles(dut.clk, 4)
    dut.spi_cs_n.value = 1
    await ClockCycles(dut.clk, 16)

async def spi_read_status(dut):
    dut.spi_cs_n.value = 0
    await ClockCycles(dut.clk, 16)
    await spi_transfer_byte(dut, CMD_READ_STATUS)
    status = await spi_transfer_byte(dut, 0x00)
    dut.spi_cs_n.value = 1
    await ClockCycles(dut.clk, 16)
    return status

async def spi_read_block64(dut):
    dut.spi_cs_n.value = 0
    await ClockCycles(dut.clk, 16)
    await spi_transfer_byte(dut, CMD_READ_BLOCK_64)
    data = []
    for _ in range(8):
        data.append(await spi_transfer_byte(dut, 0x00))
    dut.spi_cs_n.value = 1
    await ClockCycles(dut.clk, 16)
    return bytes(data)

async def spi_write_partial_payload(dut, cmd, payload_prefix):
    dut.spi_cs_n.value = 0
    await ClockCycles(dut.clk, 16)
    await spi_transfer_byte(dut, cmd)
    await ClockCycles(dut.clk, 8)
    for b in payload_prefix:
        await spi_transfer_byte(dut, b)
        await ClockCycles(dut.clk, 4)
    dut.spi_cs_n.value = 1
    await ClockCycles(dut.clk, 16)

async def wait_spi_status_bit(dut, bit_index, expected, polls=256):
    for _ in range(polls):
        status = await spi_read_status(dut)
        if ((status >> bit_index) & 0x1) == expected:
            return status
    assert False, f"Status bit {bit_index} did not become {expected}"

async def wait_spi_done(dut, polls=4096):
    status = await wait_spi_status_bit(dut, bit_index=2, expected=1, polls=polls)
    assert ((status >> 1) & 0x1) == 0 # Ensure core_busy == 0
    return status


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


@cocotb.test()
async def test_spi_status_read_and_block_read_path(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    status0 = await spi_read_status(dut)
    assert ((status0 >> 2) & 0x1) == 0
    assert ((status0 >> 1) & 0x1) == 0

    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    block = bytes.fromhex("0001020304050607")
    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, block)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])

    await wait_spi_done(dut)
    out_spi = await spi_read_block64(dut)
    assert out_spi == simon_encrypt_ref(key, block)


@cocotb.test()
async def test_spi_start_encrypt_end_to_end(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("0f0e0d0c0b0a09080706050403020100")
    plain = bytes.fromhex("1122334455667788")

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, plain)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)

    out_spi = await spi_read_block64(dut)
    assert out_spi == simon_encrypt_ref(key, plain)


@cocotb.test()
async def test_spi_start_encrypt_known_answer_vector(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("1b1a1918131211100b0a090803020100")
    plain = bytes.fromhex("656b696c20646e75")
    expected_ct = bytes.fromhex("44c8fc20b9dfa07a")

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, plain)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)

    out_spi = await spi_read_block64(dut)
    assert out_spi == expected_ct


@cocotb.test()
async def test_spi_start_decrypt_known_answer_vector(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("1b1a1918131211100b0a090803020100")
    cipher = bytes.fromhex("44c8fc20b9dfa07a")
    expected_pt = bytes.fromhex("656b696c20646e75")

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, cipher)
    await spi_write_cmd_and_payload(dut, CMD_START_DECRYPT, [])
    await wait_spi_done(dut)

    out_spi = await spi_read_block64(dut)
    assert out_spi == expected_pt


@cocotb.test()
async def test_spi_status_transitions_for_encrypt_then_decrypt(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("1b1a1918131211100b0a090803020100")
    plain = bytes.fromhex("656b696c20646e75")
    expected_ct = bytes.fromhex("44c8fc20b9dfa07a")

    status0 = await spi_read_status(dut)
    assert ((status0 >> 2) & 0x1) == 0
    assert ((status0 >> 1) & 0x1) == 0

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, plain)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])

    status_busy = await wait_spi_status_bit(dut, bit_index=1, expected=1)
    assert ((status_busy >> 2) & 0x1) == 0

    status_done = await wait_spi_status_bit(dut, bit_index=2, expected=1)
    assert ((status_done >> 1) & 0x1) == 0
    assert await spi_read_block64(dut) == expected_ct

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, expected_ct)
    await spi_write_cmd_and_payload(dut, CMD_START_DECRYPT, [])

    status_busy2 = await wait_spi_status_bit(dut, bit_index=1, expected=1)
    assert ((status_busy2 >> 2) & 0x1) == 0

    status_done2 = await wait_spi_status_bit(dut, bit_index=2, expected=1)
    assert ((status_done2 >> 1) & 0x1) == 0
    assert await spi_read_block64(dut) == plain


@cocotb.test()
async def test_spi_start_decrypt_end_to_end(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("1f1e1d1c1b1a19181716151413121110")
    plain = bytes.fromhex("656b696c20646e75")
    cipher = simon_encrypt_ref(key, plain)

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, cipher)
    await spi_write_cmd_and_payload(dut, CMD_START_DECRYPT, [])
    await wait_spi_done(dut)

    out_spi = await spi_read_block64(dut)
    assert out_spi == plain


@cocotb.test()
async def test_spi_aborted_payload_recovery_with_full_key_reload(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    good_key = bytes.fromhex("00112233445566778899aabbccddeeff")
    block = bytes.fromhex("0001020304050607")

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, good_key)
    await spi_write_partial_payload(dut, CMD_WRITE_KEY_128, [0xAA, 0xBB, 0xCC])
    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, good_key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, block)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)

    out_spi = await spi_read_block64(dut)
    assert out_spi == simon_encrypt_ref(good_key, block)


@cocotb.test()
async def test_block_write_clears_out_valid_and_blocks_result_read(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("1b1a1918131211100b0a090803020100")
    plain = bytes.fromhex("656b696c20646e75")
    next_block = bytes.fromhex("0011223344556677")

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, plain)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)

    status_done = await spi_read_status(dut)
    assert ((status_done >> 2) & 0x1) == 1

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, next_block)

    status_after_block_write = await spi_read_status(dut)
    assert ((status_after_block_write >> 2) & 0x1) == 0

    out_spi = await spi_read_block64(dut)
    assert out_spi == bytes(8)


@cocotb.test()
async def test_spi_back_to_back_frames(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("0123456789abcdeffedcba9876543210")
    b0 = bytes.fromhex("0001020304050607")
    b1 = bytes.fromhex("8899aabbccddeeff")

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, b0)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)
    c0 = await spi_read_block64(dut)
    assert c0 == simon_encrypt_ref(key, b0)

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, b1)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)
    c1 = await spi_read_block64(dut)
    assert c1 == simon_encrypt_ref(key, b1)


@cocotb.test()
async def test_spi_back_to_back_decrypt_frames(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("1f1e1d1c1b1a19181716151413121110")
    p0 = bytes.fromhex("656b696c20646e75")
    p1 = bytes.fromhex("1122334455667788")
    c0 = simon_encrypt_ref(key, p0)
    c1 = simon_encrypt_ref(key, p1)

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, c0)
    await spi_write_cmd_and_payload(dut, CMD_START_DECRYPT, [])
    await wait_spi_done(dut)
    out0 = await spi_read_block64(dut)
    assert out0 == p0

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, c1)
    await spi_write_cmd_and_payload(dut, CMD_START_DECRYPT, [])
    await wait_spi_done(dut)
    out1 = await spi_read_block64(dut)
    assert out1 == p1


@cocotb.test()
async def test_spi_mode_transition_encrypt_decrypt_encrypt(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await _spi_idle(dut)

    key = bytes.fromhex("0123456789abcdeffedcba9876543210")
    b0 = bytes.fromhex("0001020304050607")
    b1 = bytes.fromhex("8899aabbccddeeff")
    c0 = simon_encrypt_ref(key, b0)

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, b0)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)
    out_enc0 = await spi_read_block64(dut)
    assert out_enc0 == c0

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, c0)
    await spi_write_cmd_and_payload(dut, CMD_START_DECRYPT, [])
    await wait_spi_done(dut)
    out_dec0 = await spi_read_block64(dut)
    assert out_dec0 == b0

    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, b1)
    await spi_write_cmd_and_payload(dut, CMD_START_ENCRYPT, [])
    await wait_spi_done(dut)
    out_enc1 = await spi_read_block64(dut)
    assert out_enc1 == simon_encrypt_ref(key, b1)
