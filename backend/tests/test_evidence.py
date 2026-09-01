from tests.factories import make_case


def test_get_case_evidence(client, db_session):
    make_case(db_session, dispute_id="DSP-000001")

    resp = client.get("/cases/DSP-000001/evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["evidence_type"] == "delivery_confirmed"
    assert body[0]["available"] is True


def test_get_case_evidence_not_found(client, db_session):
    resp = client.get("/cases/DSP-999999/evidence")
    assert resp.status_code == 404
