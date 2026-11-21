import uuid

from app.db import SessionLocal
from app.domain_models import TaxEntity
from app.models import Document, Submission


def test_client_creates_default_tax_entity(api):
    headers = {"X-User": "tenant-admin"}
    response = api.post(
        "/clients",
        json={"name": "Cong ty A", "tax_id": "0012345678"},
        headers=headers,
    )
    assert response.status_code == 201
    client_id = response.json()["id"]

    with SessionLocal() as db:
        entities = db.query(TaxEntity).filter_by(client_id=client_id).all()
        assert len(entities) == 1
        assert entities[0].tax_id == "0012345678"
        assert entities[0].legal_name == "Cong ty A"


def test_batch_requires_entity_when_client_has_multiple_entities(api):
    headers = {"X-User": "tenant-admin"}
    client = api.post(
        "/clients",
        json={"name": "Cong ty A", "tax_id": "0012345678"},
        headers=headers,
    ).json()
    client_id = client["id"]
    headers["X-Client-Ids"] = client_id

    entity_response = api.post(
        f"/clients/{client_id}/entities",
        json={"tax_id": "0098765432", "legal_name": "Chi nhanh B"},
        headers=headers,
    )
    assert entity_response.status_code == 201
    entity_id = entity_response.json()["id"]

    ambiguous = api.post(
        "/batches",
        json={"client_id": client_id, "engagement_id": "E-AMB"},
        headers=headers,
    )
    assert ambiguous.status_code == 400
    assert ambiguous.json()["error_code"] == "entity_selection_required"

    selected = api.post(
        "/batches",
        json={"client_id": client_id, "engagement_id": "E-B", "entity_id": entity_id},
        headers=headers,
    )
    assert selected.status_code == 201
    assert selected.json()["entity_id"] == entity_id


def test_batch_rejects_entity_from_another_client(api):
    headers = {"X-User": "tenant-admin"}
    first = api.post("/clients", json={"name": "A", "tax_id": "0100000001"}, headers=headers).json()
    second = api.post("/clients", json={"name": "B", "tax_id": "0100000002"}, headers=headers).json()
    headers["X-Client-Ids"] = first["id"]
    second_entity = None
    with SessionLocal() as db:
        second_entity = db.query(TaxEntity).filter_by(client_id=second["id"]).one().id

    response = api.post(
        "/batches",
        json={"client_id": first["id"], "engagement_id": "E-X", "entity_id": second_entity},
        headers=headers,
    )
    assert response.status_code == 404


def test_tax_domain_tables_are_registered(api):
    with SessionLocal() as db:
        assert db.query(TaxEntity).count() == 0
        assert db.query(Document).count() == 0
        assert db.query(Submission).count() == 0
