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


def main():
    # In this example we are using the second interface of an FT2232H breakout board,
    # but you can use any compatible FTDI device.
    # Use python/pyftdi_list_devices.py to find your device URL,
    # or if only one FTDI device is connected, use `/1` for the first interface etc.
    ctrl = SpiController()
    ctrl.configure("ftdi:///2")  # Replace with your serial

    # SPI mode 0, CS0
    # Pin mapping for FT2232H:
    # CS0  -> uio[0]
    # SCLK -> uio[1]
    # MOSI -> uio[2]
    # MISO -> uio[3]
    spi = ctrl.get_port(cs=0, freq=6_000_000, mode=0)

    key = bytes.fromhex("1b1a1918131211100b0a090803020100")
    plain = bytes.fromhex("656b696c20646e75")
    expected_ct = bytes.fromhex("44c8fc20b9dfa07a")

    try:
        ct = encrypt(spi, plain, key)
        print(f"Ciphertext: {ct.hex()}")
        if ct != expected_ct:
            raise RuntimeError("Encryption failed")

        pt = decrypt(spi, ct, key)
        print(f"Decrypted plaintext: {pt.hex()}")
        if pt != plain:
            raise RuntimeError("Decryption failed")

        print("OK: Encryption and decryption passed")
    finally:
        ctrl.terminate()


if __name__ == "__main__":
    main()
