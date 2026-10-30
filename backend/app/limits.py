# The data budget excludes model defaults. The larger wire budget allows every
# admitted input to be resubmitted with those defaults and a candidate envelope.
MAX_INPUT_DATA_BYTES = 1_000_000
MAX_INPUT_BYTES = 2_000_000
MAX_BUNDLE_BYTES = 32_000_000


class InputSizeError(Exception):
    pass


def validate_input_size(payload):
    if len(payload.model_dump_json(exclude_defaults=True).encode('utf-8')) > MAX_INPUT_DATA_BYTES:
        raise InputSizeError('Input data exceeds the 1 MB limit; split the input into smaller comparisons')
