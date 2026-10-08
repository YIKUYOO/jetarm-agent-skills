"""Project-authored readback guard extracted from the historical integration patch.

This is not a complete Hiwonder driver. See integration/README.md.
"""


def as_uint16_sequence(values, field_name, logger, servo_id):
    if values is None:
        return None
    cleaned = []
    for value in values:
        value = int(value)
        if value < 0 or value > 65535:
            logger.warn(f"ignore invalid bus servo {servo_id} {field_name}: {values}")
            return None
        cleaned.append(value)
    return cleaned
