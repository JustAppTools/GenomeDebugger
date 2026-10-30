"""Replay original pre-versioned record shapes without rewriting their bytes."""
from .archives.mvp import engine as mvp
from .archives.reference import engine as reference
from .archives.annotations import engine as annotations
from . import legacy_unversioned_selection as selection
from . import legacy_engine_v050 as original_v050


def validate_unversioned(raw):
    if 'engine_version' in raw:
        raise ValueError('Expected an original pre-versioned record')
    # An early schema added defaults before comparator versions were explicit.
    # Preserve that original input shape for hashing, while the frozen models
    # and rules supply their own original validation/calculation semantics.
    source = raw['input']
    expected = {key:value for key,value in raw.items() if key != 'input'}
    for rules in (mvp, reference, annotations, selection, original_v050):
        class OriginalInput(rules.InvestigationInput):
            def model_dump(self, *args, **kwargs):
                return source
        try:
            rebuilt = rules.compare(OriginalInput.model_validate(source)).model_dump(mode='json',exclude={'input'})
            # Before the explicit version field, the original ID was the input
            # hash prefix. The versioned 0.5.0 compatibility implementation has
            # the same calculation but supplies its default version field.
            if rules is original_v050:
                rebuilt.pop('engine_version', None)
            if rebuilt == expected:
                return
        except (ValueError, TypeError, KeyError):
            continue
    raise ValueError('Pre-versioned investigation does not match any supported original replay format')
