"""Versioned colour-profile payload used by the POV calibration protocol.

The payload is deliberately a fixed binary layout. It is small enough for the
board's UART transport, easy for native firmware to parse, and gives the host
the exact transfer functions needed to turn captured APA102 drive values back
into a monitor preview.
"""

import struct


MAGIC = b"PCAL"
VERSION = 1
LED_COUNT = 54
PWM_KNOTS = 17
GB_LEVELS = 32
Q15_ONE = 32767
MATRIX_Q = 4096

_HEADER = struct.Struct("<4sBBHI")
_CONTROLS = struct.Struct("<BHHHHHHBB")
_MATRIX = struct.Struct("<9h")
PAYLOAD_BYTES = (
    _HEADER.size
    + _CONTROLS.size
    + _MATRIX.size
    + LED_COUNT * 2
    + GB_LEVELS * 2
    + 3 * PWM_KNOTS * 2
)


class ColorProfileError(ValueError):
    pass


def _linear_knots(count):
    denominator = 2 * (count - 1)
    return [(2 * index * Q15_ONE + (count - 1)) // denominator for index in range(count)]


def _srgb_encode(linear):
    if linear <= 0.0:
        return 0
    if linear >= 1.0:
        return 255
    if linear <= 0.0031308:
        encoded = linear * 12.92
    else:
        encoded = 1.055 * pow(linear, 1.0 / 2.4) - 0.055
    return max(0, min(255, int(encoded * 255.0 + 0.5)))


def _interpolate(knots, code):
    code = max(0, min(255, int(code)))
    scaled = code * (len(knots) - 1)
    index = scaled // 255
    fraction = scaled % 255
    if index >= len(knots) - 1:
        return knots[-1]
    return (knots[index] * (255 - fraction) + knots[index + 1] * fraction + 127) // 255


class ColorProfile:
    """Calibrated conversion from APA102 drive values to preview RGB.

    Numeric fields are intentionally public: the calibration UI owns their
    editing lifecycle, while this class owns binary validation and rendering.
    Matrix rows map measured LED linear R/G/B light to preview linear RGB.
    """

    def __init__(
        self,
        generation,
        source_eotf,
        source_gamma_milli,
        master_milli,
        white_balance,
        radial_exponent_milli,
        gb_floor,
        gb_ceiling,
        preview_matrix,
        led_trims,
        global_response,
        pwm_response,
    ):
        self.generation = int(generation)
        self.source_eotf = int(source_eotf)
        self.source_gamma_milli = int(source_gamma_milli)
        self.master_milli = int(master_milli)
        self.white_balance = tuple(int(value) for value in white_balance)
        self.radial_exponent_milli = int(radial_exponent_milli)
        self.gb_floor = int(gb_floor)
        self.gb_ceiling = int(gb_ceiling)
        self.preview_matrix = tuple(int(value) for value in preview_matrix)
        self.led_trims = tuple(int(value) for value in led_trims)
        self.global_response = tuple(int(value) for value in global_response)
        self.pwm_response = tuple(tuple(int(value) for value in row) for row in pwm_response)
        self._validate()

    @classmethod
    def default(cls, generation=0):
        return cls(
            generation=generation,
            source_eotf=0,  # sRGB
            source_gamma_milli=2200,
            master_milli=1000,
            white_balance=(1000, 1000, 1000),
            radial_exponent_milli=1000,
            gb_floor=1,
            gb_ceiling=31,
            preview_matrix=(MATRIX_Q, 0, 0, 0, MATRIX_Q, 0, 0, 0, MATRIX_Q),
            led_trims=(1024,) * LED_COUNT,
            global_response=_linear_knots(GB_LEVELS),
            pwm_response=(_linear_knots(PWM_KNOTS),) * 3,
        )

    def _validate_q15_curve(self, name, values, expected_length):
        if len(values) != expected_length:
            raise ColorProfileError("%s has %d values, expected %d" % (name, len(values), expected_length))
        previous = -1
        for value in values:
            if not 0 <= value <= Q15_ONE:
                raise ColorProfileError("%s is outside Q15 range" % name)
            if value < previous:
                raise ColorProfileError("%s is not monotonic" % name)
            previous = value

    def _validate(self):
        if not 0 <= self.generation <= 0xFFFFFFFF:
            raise ColorProfileError("generation is outside uint32 range")
        if self.source_eotf not in (0, 1):
            raise ColorProfileError("unknown source transfer")
        if not 1000 <= self.source_gamma_milli <= 4000:
            raise ColorProfileError("source gamma is outside supported range")
        if not 0 <= self.master_milli <= 4000:
            raise ColorProfileError("master brightness is outside supported range")
        if len(self.white_balance) != 3 or any(not 0 <= value <= 4000 for value in self.white_balance):
            raise ColorProfileError("invalid white balance")
        if not 0 <= self.radial_exponent_milli <= 4000:
            raise ColorProfileError("radial exponent is outside supported range")
        if not 0 <= self.gb_floor <= self.gb_ceiling <= 31:
            raise ColorProfileError("invalid APA102 global-brightness range")
        if len(self.preview_matrix) != 9 or not any(self.preview_matrix):
            raise ColorProfileError("invalid preview matrix")
        if any(not -32768 <= value <= 32767 for value in self.preview_matrix):
            raise ColorProfileError("preview matrix is outside int16 range")
        if len(self.led_trims) != LED_COUNT or any(not 0 <= value <= 4096 for value in self.led_trims):
            raise ColorProfileError("invalid LED trims")
        self._validate_q15_curve("global response", self.global_response, GB_LEVELS)
        if len(self.pwm_response) != 3:
            raise ColorProfileError("expected three PWM response curves")
        for channel, curve in enumerate(self.pwm_response):
            self._validate_q15_curve("PWM response %d" % channel, curve, PWM_KNOTS)

    def to_bytes(self):
        self._validate()
        body = bytearray()
        body.extend(_CONTROLS.pack(
            self.source_eotf,
            self.source_gamma_milli,
            self.master_milli,
            self.white_balance[0],
            self.white_balance[1],
            self.white_balance[2],
            self.radial_exponent_milli,
            self.gb_floor,
            self.gb_ceiling,
        ))
        body.extend(_MATRIX.pack(*self.preview_matrix))
        body.extend(struct.pack("<%dH" % LED_COUNT, *self.led_trims))
        body.extend(struct.pack("<%dH" % GB_LEVELS, *self.global_response))
        for curve in self.pwm_response:
            body.extend(struct.pack("<%dH" % PWM_KNOTS, *curve))
        payload = _HEADER.pack(MAGIC, VERSION, 0, PAYLOAD_BYTES, self.generation) + bytes(body)
        if len(payload) != PAYLOAD_BYTES:
            raise AssertionError("colour profile layout drifted")
        return payload

    @classmethod
    def from_bytes(cls, payload, schema_version=None, generation=None):
        if len(payload) < _HEADER.size:
            raise ColorProfileError("profile is shorter than its header")
        magic, version, reserved, declared_length, payload_generation = _HEADER.unpack_from(payload)
        if magic != MAGIC:
            raise ColorProfileError("unknown profile magic")
        if version != VERSION:
            raise ColorProfileError("unsupported profile version %d" % version)
        if reserved != 0:
            raise ColorProfileError("unsupported profile flags")
        if declared_length != PAYLOAD_BYTES or len(payload) != declared_length:
            raise ColorProfileError("invalid profile length")
        if schema_version is not None and int(schema_version) != version:
            raise ColorProfileError("command/profile schema versions disagree")
        if generation is not None and int(generation) != payload_generation:
            raise ColorProfileError("command/profile generations disagree")

        offset = _HEADER.size
        values = _CONTROLS.unpack_from(payload, offset)
        offset += _CONTROLS.size
        preview_matrix = _MATRIX.unpack_from(payload, offset)
        offset += _MATRIX.size
        led_trims = struct.unpack_from("<%dH" % LED_COUNT, payload, offset)
        offset += LED_COUNT * 2
        global_response = struct.unpack_from("<%dH" % GB_LEVELS, payload, offset)
        offset += GB_LEVELS * 2
        pwm_response = []
        for _ in range(3):
            pwm_response.append(struct.unpack_from("<%dH" % PWM_KNOTS, payload, offset))
            offset += PWM_KNOTS * 2
        if offset != len(payload):
            raise ColorProfileError("profile trailing data mismatch")

        return cls(
            generation=payload_generation,
            source_eotf=values[0],
            source_gamma_milli=values[1],
            master_milli=values[2],
            white_balance=values[3:6],
            radial_exponent_milli=values[6],
            gb_floor=values[7],
            gb_ceiling=values[8],
            preview_matrix=preview_matrix,
            led_trims=led_trims,
            global_response=global_response,
            pwm_response=pwm_response,
        )

    def decode_preview_rgb(self, global_byte, blue_pwm, green_pwm, red_pwm):
        """Decode one raw APA102 datum into monitor-sRGB preview bytes."""
        if (global_byte & 0xE0) != 0xE0:
            return (0, 0, 0)
        brightness = global_byte & 0x1F
        if brightness == 0:
            return (0, 0, 0)

        global_light = self.global_response[brightness]
        led_light = (
            global_light * _interpolate(self.pwm_response[0], red_pwm) / (Q15_ONE * Q15_ONE),
            global_light * _interpolate(self.pwm_response[1], green_pwm) / (Q15_ONE * Q15_ONE),
            global_light * _interpolate(self.pwm_response[2], blue_pwm) / (Q15_ONE * Q15_ONE),
        )
        preview_linear = []
        for row in range(3):
            base = row * 3
            value = sum(self.preview_matrix[base + channel] * led_light[channel] for channel in range(3))
            preview_linear.append(max(0.0, value / MATRIX_Q))
        return tuple(_srgb_encode(value) for value in preview_linear)


DEFAULT_PROFILE = ColorProfile.default()
