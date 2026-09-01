from tests.factories import make_case


def test_list_cases_returns_page(client, db_session):
    make_case(db_session, dispute_id="DSP-000001")
    make_case(db_session, dispute_id="DSP-000002", reason_code="duplicate_charge")

    resp = client.get("/cases")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["page"] == 1


def test_list_cases_filters_by_reason_code(client, db_session):
    make_case(db_session, dispute_id="DSP-000001", reason_code="goods_not_received")
    make_case(db_session, dispute_id="DSP-000002", reason_code="duplicate_charge")

    resp = client.get("/cases", params={"reason_code": "duplicate_charge"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["reason_code"] == "duplicate_charge"


def test_list_cases_pagination(client, db_session):
    for i in range(5):
        make_case(db_session, dispute_id=f"DSP-00000{i}")

    resp = client.get("/cases", params={"page": 1, "page_size": 2})
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_get_case_returns_full_detail(client, db_session):
    make_case(db_session, dispute_id="DSP-000001")

    resp = client.get("/cases/DSP-000001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dispute_id"] == "DSP-000001"
    assert "transaction" in body
    assert "customer" in body
    assert body["transaction"]["transaction_id"] == "TXN-DSP-000001"
    assert body["customer"]["customer_id"] == "CUST-DSP-000001"


def test_get_case_not_found(client, db_session):
    resp = client.get("/cases/DSP-999999")
    assert resp.status_code == 404


def test_score_endpoint_is_implemented_in_phase_2(client, db_session):
    """/score was a Phase 1 stub; Phase 2 implements it.

    This assertion was intentionally inverted when the risk model landed --
    it is the one Phase 1 expectation Phase 2 is supposed to change. The
    endpoint's behavior is covered in depth by tests/test_score_api.py.
    503 is accepted for environments where model artifacts have not been
    built (see README: python scripts/train_model.py).
    """
    make_case(db_session, dispute_id="DSP-000001")
    resp = client.post("/cases/DSP-000001/score")
    assert resp.status_code in (200, 503)
    assert resp.status_code != 501, "/score must no longer be a stub"


def test_decision_endpoint_not_implemented(client, db_session):
    make_case(db_session, dispute_id="DSP-000001")
    resp = client.post("/cases/DSP-000001/decision")
    assert resp.status_code == 501


def test_draft_endpoint_not_implemented(client, db_session):
    make_case(db_session, dispute_id="DSP-000001")
    resp = client.post("/cases/DSP-000001/draft")
    assert resp.status_code == 501
