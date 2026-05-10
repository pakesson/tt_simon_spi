import argparse

from pyftdi.ftdi import Ftdi
from pyftdi.spi import SpiController


CMD_WRITE_KEY_128 = 0x10
CMD_WRITE_BLOCK_64 = 0x20
CMD_START_ENCRYPT = 0x30
CMD_START_DECRYPT = 0x31
CMD_READ_BLOCK_64 = 0x40
CMD_READ_STATUS = 0x50


def spi_write_cmd_and_payload(spi, cmd, payload=None):
    tx = bytes([cmd])
    if payload:
        tx += bytes(payload)
    spi.write(tx, start=True, stop=True)


def spi_read_status(spi):
    spi.write(bytes([CMD_READ_STATUS]), start=True, stop=False)
    status = spi.read(1, start=False, stop=True)
    if status[0] & 0x1 == 0: # The low bit should always be 1
        raise ValueError("Invalid status response")
    return status


def spi_read_block64(spi):
    spi.write(bytes([CMD_READ_BLOCK_64]), start=True, stop=False)
    data = spi.read(8, start=False, stop=True)
    return data


def wait_spi_done(spi, max_polls=1000):
    for _ in range(max_polls):
        status = spi_read_status(spi)
        if ((status[0] >> 2) & 0x1) == 1:
            return True
    return False


def encrypt(spi, plaintext, key):
    if len(key) != 16:
        raise ValueError("Key must be 16 bytes for SIMON64/128")
    if len(plaintext) != 8:
        raise ValueError("Plaintext must be 8 bytes")

    spi_write_cmd_and_payload(spi, CMD_WRITE_KEY_128, key)
    spi_write_cmd_and_payload(spi, CMD_WRITE_BLOCK_64, plaintext)
    spi_write_cmd_and_payload(spi, CMD_START_ENCRYPT)

    if not wait_spi_done(spi):
        raise TimeoutError("Encryption did not complete")
    return spi_read_block64(spi)


def decrypt(spi, ciphertext, key):
    if len(key) != 16:
        raise ValueError("Key must be 16 bytes for SIMON64/128")
    if len(ciphertext) != 8:
        raise ValueError("Ciphertext must be 8 bytes")

    spi_write_cmd_and_payload(spi, CMD_WRITE_KEY_128, key)
    spi_write_cmd_and_payload(spi, CMD_WRITE_BLOCK_64, ciphertext)
    spi_write_cmd_and_payload(spi, CMD_START_DECRYPT)

    if not wait_spi_done(spi):
        raise TimeoutError("Decryption did not complete")
    return spi_read_block64(spi)


def parse_hex_bytes(name, value, expected_len):
    value = value.strip()
    if value.startswith("0x") or value.startswith("0X"):
        value = value[2:]

    if len(value) != expected_len * 2:
        raise ValueError(
            f"{name} must be exactly {expected_len} bytes ({expected_len * 2} hex chars)"
        )

    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid hex string") from exc


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Encrypt/decrypt using SIMON64/128 over SPI via pyftdi"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available FTDI devices and exit",
    )
    parser.add_argument(
        "--device",
        default="ftdi://ftdi:2232:/2",
        help="FTDI URL for SpiController.configure() (default: ftdi://ftdi:2232:/2)",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--encrypt", action="store_true", help="Encrypt data")
    mode_group.add_argument("--decrypt", action="store_true", help="Decrypt data")

    parser.add_argument(
        "--key",
        help="128-bit key as hex string (16 bytes / 32 hex chars)",
    )
    parser.add_argument(
        "--data",
        help="64-bit plaintext/ciphertext as hex string (8 bytes / 16 hex chars)",
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.list_devices:
        Ftdi.show_devices()
        return

    if not args.encrypt and not args.decrypt:
        parser.error("Specify one operation: --encrypt or --decrypt")
    if not args.key:
        parser.error("--key is required for --encrypt/--decrypt")
    if not args.data:
        parser.error("--data is required for --encrypt/--decrypt")

    key = parse_hex_bytes("key", args.key, 16)
    data = parse_hex_bytes("data", args.data, 8)

    ctrl = SpiController()
    ctrl.configure(args.device)
    spi = ctrl.get_port(cs=0, freq=6_000_000, mode=0)

    try:
        if args.encrypt:
            result = encrypt(spi, data, key)
            print(f"Ciphertext: {result.hex()}")
        else:
            result = decrypt(spi, data, key)
            print(f"Plaintext: {result.hex()}")
    finally:
        ctrl.terminate()


if __name__ == "__main__":
    main()
