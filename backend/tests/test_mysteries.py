import json

import pytest
from fastapi.testclient import TestClient

from app import main, mysteries
from app.bundle import create_bundle, verify_bundle
from app.engine import compare
from app.models import InvestigationInput
from app.regression import create_case, run_case
from app.storage import load

ANSWERS = {'vanishing-transcript':'coverage', 'different-disguise':'local', 'database-time-machine':'unproven'}


@pytest.mark.parametrize('id_,answer', ANSWERS.items())
def test_mystery_answers_come_from_engine_and_practice_does_not_save(tmp_path, monkeypatch, id_, answer):
    monkeypatch.setattr(main, 'DB', tmp_path/'practice.db')
    api = TestClient(main.app)
    detail = api.get(f'/api/mysteries/{id_}')
    assert detail.status_code == 200
    body = detail.json()
    payload = InvestigationInput.model_validate(body['result']['input'])
    assert payload.synthetic and body['result'] == compare(payload).model_dump(mode='json')
    for option in body['mission']['hypotheses']:
        checked = api.post(f'/api/mysteries/{id_}/check', json={'hypothesis_id':option['id']})
        assert checked.status_code == 200
        data = checked.json()
        assert data['assessment']['matches_evidence'] == (option['id'] == answer)
        assert data['result'] == body['result']
        assert set(data['assessment']['evidence_ids']) <= {e['id'] for e in data['result']['evidence']}
    assert not main.DB.exists()
    # An explicit workbench save uses the same input, and remains portable and pinnable.
    response = api.post('/api/investigations', json=payload.model_dump(mode='json'))
    assert response.status_code == 200
    saved = load(main.DB, response.json()['id'])
    assert verify_bundle(create_bundle(main.DB, saved))[0] == saved
    assert run_case(create_case(saved, 'Mystery baseline')).status == 'passed'


def test_unknown_case_or_hypothesis_never_grades_a_different_case(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path/'practice.db')
    api = TestClient(main.app)
    assert len(api.get('/api/mysteries').json()) == 3
    assert api.get('/api/mysteries/missing').status_code == 404
    assert api.post('/api/mysteries/missing/check', json={'hypothesis_id':'local'}).status_code == 404
    assert api.post('/api/mysteries/vanishing-transcript/check', json={'hypothesis_id':'local'}).status_code == 422
    assert not main.DB.exists()


@pytest.mark.parametrize('id_', ANSWERS)
def test_changed_fixture_cannot_retain_a_canned_correct_answer(id_):
    result = mysteries.replay(id_)
    # Replace B with A: the lesson's claimed discrepancy no longer exists.
    payload = result.input.model_copy(deep=True)
    payload.snapshots[1] = payload.snapshots[0].model_copy(deep=True)
    payload.snapshots[1].id = 'changed-B'
    with pytest.raises(ValueError, match='no longer matches'):
        mysteries.assess(id_, ANSWERS[id_], compare(payload))


def test_practice_refuses_a_non_synthetic_fixture(tmp_path, monkeypatch):
    payload = mysteries.replay('different-disguise').input.model_dump(mode='json')
    payload['synthetic'] = False
    (tmp_path/'different-disguise.json').write_text(json.dumps(payload))
    monkeypatch.setattr(mysteries, 'FIXTURES', tmp_path)
    with pytest.raises(ValueError, match='synthetic inputs'):
        mysteries.replay('different-disguise')
