"""Small synthetic lessons whose answers are checked against real comparator output."""
from pathlib import Path

from pydantic import Field

from .engine import compare
from .models import InvestigationInput, InvestigationResult, StrictModel

FIXTURES = Path(__file__).resolve().parents[2]/'fixtures/mysteries'
MISSIONS = [
    {'id':'vanishing-transcript', 'number':'01', 'title':'The Vanishing Transcript', 'theme':'coverage',
     'skill':'Follow the missing row', 'brief':'Same variant. Same selected transcript. One analysis has an extra prediction. Where did it go?',
     'question':'What does the evidence establish?', 'clues':['Count every transcript, including additional rows.', 'Distinguish a missing output from an explanation for its absence.'],
     'hypotheses':[{'id':'allele','label':'The analyses describe different alleles.'},
                   {'id':'coverage','label':'Transcript coverage differs; the reason for the omission is unknown.'},
                   {'id':'clinical','label':'The missing row proves a clinical classification changed.'}]},
    {'id':'different-disguise', 'number':'02', 'title':'Same Variant, Different Disguise', 'theme':'identity',
     'skill':'Look past the coordinates', 'brief':'One edit says AC → AT. The other says C → T. Is this a different variant, or a different way to write it?',
     'question':'How far can this comparison take us?', 'clues':['Inspect the shared reference context.', 'Look at which representation differences are meaningful.'],
     'hypotheses':[{'id':'different','label':'Different coordinates always mean different alleles.'},
                   {'id':'reference','label':'An independent reference assembly has been authenticated.'},
                   {'id':'local','label':'The substitutions match within the supplied local context.'}]},
    {'id':'database-time-machine', 'number':'03', 'title':'The Database Time Machine', 'theme':'provenance',
     'skill':'Know when to leave a case open', 'brief':'A database release advances and the predicted consequence changes. A tempting suspect—but is the cause proven?',
     'question':'Which conclusion is supported?', 'clues':['Check the source release and selected transcript.', 'A correlated change is not a controlled causal replay.'],
     'hypotheses':[{'id':'proven','label':'The release change definitely caused the consequence change.'},
                   {'id':'unproven','label':'The release changed; its causal role remains unproven.'},
                   {'id':'transcript','label':'Only the selected transcript changed.'}]},
]


class MysteryChoice(StrictModel):
    hypothesis_id: str = Field(min_length=1, max_length=100)


def mission(id_: str) -> dict:
    return next(item for item in MISSIONS if item['id'] == id_)


def replay(id_: str) -> InvestigationResult:
    mission(id_)  # Restrict file access to the catalog.
    payload = InvestigationInput.model_validate_json((FIXTURES/f'{id_}.json').read_text(encoding='utf-8'))
    if not payload.synthetic or payload.reference_check or payload.annotation_check:
        raise ValueError('Mysteries require synthetic inputs without external checks')
    return compare(payload)


def assess(id_: str, choice: str, result: InvestigationResult) -> dict:
    item = mission(id_)
    if choice not in {option['id'] for option in item['hypotheses']}:
        raise ValueError('Choose one of this mystery’s hypotheses')
    if id_ == 'vanishing-transcript':
        differences = [d for d in result.differences if d.field.startswith('annotations[') and
                       d.field.endswith('.presence') and d.before == 'present' and d.after is None]
        valid = result.identity.status == 'verified' and len(differences) == 1
        answer, conclusion = 'coverage', 'A transcript row is missing from analysis B.'
        explanation = 'The complete row comparison detects the omission. It does not establish why the producing analysis omitted that transcript.'
    elif id_ == 'different-disguise':
        differences = [d for d in result.differences if d.category == 'representation']
        valid = result.identity.status == 'verified' and bool(differences) and not any(d.meaningful for d in result.differences)
        answer, conclusion = 'local', 'The substitution edits match in the supplied context.'
        explanation = result.identity.explanation + ' This synthetic context is not an independently authenticated assembly observation.'
    else:
        differences = [d for d in result.differences if d.field in {'source_release', 'consequence'}]
        valid = ({d.field for d in differences} == {'source_release','consequence'} and
                 any(f.cause == 'source release' and f.status == 'possible' for f in result.findings) and
                 not any(f.status == 'verified' for f in result.findings))
        answer, conclusion = 'unproven', 'The release is a possible explanation; causation stays open.'
        explanation = 'The same selected transcript has a different consequence and source release. No controlled historical replay isolates the release change. Unresolved is the supported causal conclusion.'
    if not valid:
        raise ValueError('This lesson no longer matches its engine evidence; the mystery cannot be graded')
    ids = list(dict.fromkeys(['identity-inputs', *(eid for d in differences for eid in d.evidence_ids)]))
    return {'hypothesis_id':choice, 'matches_evidence':choice == answer, 'conclusion':conclusion,
            'explanation':explanation, 'evidence_ids':ids}
