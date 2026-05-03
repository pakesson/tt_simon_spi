import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

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


async def wait_done(dut, timeout=1000000):
    saw_busy = False
    for i in range(timeout):
        busy = int(dut.user_project.core_busy.value)
        done = int(dut.user_project.core_done.value)
        if done == 1:
            assert saw_busy
            return
        if busy == 1:
            saw_busy = True
        if i == 10000 and not saw_busy:
            assert False, "core never started"
        await ClockCycles(dut.clk, 1)
    assert False, "core timeout"


async def run_core_encrypt_smoke(dut):
    key = bytes.fromhex("1f1e1d1c1b1a19181716151413121110")
    plain = bytes.fromhex("656b696c20646e75")
    dut.user_project.core_decrypt_pipe.value = 0
    dut.user_project.core.k_window.value = int.from_bytes(key, "big")
    dut.user_project.core.k_at_final.value = 0
    dut.user_project.core.z_lfsr.value = 0x5B  # LFSR state for z_idx=0
    dut.user_project.core.x_reg.value = int.from_bytes(plain[:4], "big")
    dut.user_project.core.y_reg.value = int.from_bytes(plain[4:], "big")
    dut.user_project.core_start_pipe.value = 1
    await ClockCycles(dut.clk, 1)
    dut.user_project.core_start_pipe.value = 0
    await wait_done(dut)
    out = int(dut.user_project.core.block_out.value).to_bytes(8, "big")
    assert out == simon_encrypt_ref(key, plain)


@cocotb.test()
async def test_core_direct_smoke(dut):
    clock = Clock(dut.clk, 1, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    await run_core_encrypt_smoke(dut)


@cocotb.test()
async def test_spi_write_paths_and_core_smoke(dut):
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

    await spi_write_cmd_and_payload(dut, CMD_WRITE_KEY_128, key)
    await spi_write_cmd_and_payload(dut, CMD_WRITE_BLOCK_64, plain)

    assert int(dut.user_project.core.k_window.value) == int.from_bytes(key, "big")
    assert int(dut.user_project.core.block_out.value) == int.from_bytes(plain, "big")

    await run_core_encrypt_smoke(dut)
