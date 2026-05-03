import os
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

TEST_DIR = Path(__file__).resolve().parent
SRC_DIR = TEST_DIR.parent / "src"
PDK_ROOT = Path(os.getenv("PDK_ROOT", ""))

SIM = os.getenv("SIM", "icarus")
WAVES = os.getenv("WAVES", "1") not in ("0", "no", "false", "False")
GL_TEST = os.getenv("GATES", "no") in ("yes", "1", "true", True)

PROJECT_SOURCES = [
    "tt_um_pakesson_simon64_128.v",
    "spi_peripheral.v",
    "simon64_128_core.v",
]


def _top_sources(tb_file: str):
    if GL_TEST:
        return [
            TEST_DIR / "gate_level_netlist.v",
            SRC_DIR / "chip_art.v",
            PDK_ROOT / "sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v",
            PDK_ROOT / "sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v",
            TEST_DIR / tb_file,
        ]
    return [*(SRC_DIR / name for name in PROJECT_SOURCES), TEST_DIR / tb_file]


def _rtl_sources(*src_names: str, tb_file: str):
    return [*(SRC_DIR / name for name in src_names), TEST_DIR / tb_file]

def _run(tb_name: str, test_module: str, sources):
    runner = get_runner(SIM)
    defines = {}
    if GL_TEST:
        defines = {
            "GL_TEST": True,
            "FUNCTIONAL": True,
            "USE_POWER_PINS": True,
            "SIM": True,
            #"UNIT_DELAY": "#1",
        }

    runner.build(
        sources=[str(s) for s in sources],
        hdl_toplevel=tb_name,
        always=True,
        build_dir=str(TEST_DIR / "sim_build" / ("gl" if GL_TEST else "rtl") / tb_name),
        defines=defines,
    )
    runner.test(
        hdl_toplevel=tb_name,
        test_module=test_module,
        waves=WAVES,
    )

def test_tt_um_pakesson_simon64_128():
    _run(
        "tb",
        "test_tt_um_pakesson_simon64_128",
        _top_sources("tb_tt_um_pakesson_simon64_128.v"),
    )
