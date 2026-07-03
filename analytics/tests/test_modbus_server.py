from analytics.mock.modbus_server import next_registers


def test_next_registers_shape():
    registers = next_registers()
    assert len(registers) == 3
    assert all(isinstance(value, int) for value in registers)
