import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles


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