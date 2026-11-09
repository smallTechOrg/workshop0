"""C8 Topic taxonomy — the 40-topic seed, public/admin topic endpoints, admin create/rename/
deactivate, slug derivation, `topic_exists` collisions (PostgreSQL)."""

from sqlalchemy import text

from tests.conftest import opportunity_body

# spec/data-model.md §topic — written out independently of the migration (not imported).
EXPECTED_SEED = [
    ("Languages", ["python", "javascript", "typescript", "java", "go", "rust", "dotnet", "kotlin"]),
    ("Web & Mobile", ["react", "nextjs", "nodejs", "angular", "vuejs", "flutter", "android", "ios-swift"]),
    ("AI & Data", ["machine-learning", "deep-learning", "generative-ai", "agentic-ai",
                   "prompt-engineering", "data-engineering", "sql-analytics", "mlops"]),
    ("Cloud & DevOps", ["aws", "gcp", "azure", "docker", "kubernetes", "ci-cd", "terraform", "linux"]),
    ("Engineering Practice", ["system-design", "apis-microservices", "testing-qa", "git-github",
                              "cybersecurity", "agile-scrum", "product-management", "ux-design"]),
]
EXPECTED_NAMES = {
    "dotnet": "C# / .NET",
    "ios-swift": "iOS / Swift",
    "generative-ai": "Generative AI & LLMs",
    "agentic-ai": "Agentic AI (LangChain / LangGraph)",
    "sql-analytics": "SQL & Data Analysis",
    "gcp": "Google Cloud",
    "ci-cd": "CI/CD",
    "ux-design": "UI / UX Design",
}


def _count(sql: str, **params) -> int:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return int(session.execute(text(sql), params).scalar_one())


def _public_topics(client) -> list[dict]:
    response = client.get("/api/public/topics")
    assert response.status_code == 200, response.text
    return response.json()["data"]["topics"]


def _admin_topics(client, admin_headers) -> list[dict]:
    response = client.get("/api/admin/topics", headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["topics"]


# --------------------------------------------------------------------------- seed


def test_seed_is_exactly_40_active_topics_in_5_categories_of_8_in_position_order(client):
    topics = _public_topics(client)
    assert len(topics) == 40
    expected_order = [(cat, slug) for cat, slugs in EXPECTED_SEED for slug in slugs]
    assert [(t["category"], t["slug"]) for t in topics] == expected_order
    assert len({t["slug"] for t in topics}) == 40
    assert len({t["name"] for t in topics}) == 40
    for slug, name in EXPECTED_NAMES.items():
        assert next(t["name"] for t in topics if t["slug"] == slug) == name
    assert all(set(t) == {"slug", "name", "category", "open_count"} for t in topics)
    assert all(t["open_count"] == 0 for t in topics)


def test_admin_topics_lists_positions_0_to_39_with_ids_and_counts(client, admin_headers):
    topics = _admin_topics(client, admin_headers)
    assert [t["position"] for t in topics] == list(range(40))
    assert all(t["active"] is True and t["opportunity_count"] == 0 for t in topics)
    assert set(topics[0]) == {"id", "slug", "name", "category", "position", "active", "opportunity_count"}


def test_open_count_counts_only_effective_open_listings(client, create_opportunity, admin_headers):
    create_opportunity(["python", "rust"], status="open")
    create_opportunity(["python"], status="open")
    create_opportunity(["python"])  # draft
    closed = create_opportunity(["python"], status="open")
    client.patch(f"/api/admin/opportunities/{closed['id']}", json={"status": "closed"}, headers=admin_headers)

    counts = {t["slug"]: t["open_count"] for t in _public_topics(client)}
    assert counts["python"] == 2 and counts["rust"] == 1 and counts["go"] == 0
    admin = {t["slug"]: t["opportunity_count"] for t in _admin_topics(client, admin_headers)}
    assert admin["python"] == 4 and admin["rust"] == 1  # any status


# --------------------------------------------------------------------------- admin create


def test_create_topic_derives_slug_appends_position_and_shows_publicly_with_zero(client, admin_headers):
    response = client.post(
        "/api/admin/topics", json={"name": "  C# / .NET 2 ", "category": "Languages"}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    topic = response.json()["data"]["topic"]
    assert topic["slug"] == "c-net-2"
    assert topic["name"] == "C# / .NET 2"
    assert topic["position"] == 40 and topic["active"] is True and topic["opportunity_count"] == 0

    public = _public_topics(client)
    assert len(public) == 41
    assert public[-1] == {"slug": "c-net-2", "name": "C# / .NET 2", "category": "Languages", "open_count": 0}


def test_slug_is_capped_at_48_chars_without_a_trailing_dash(client, admin_headers):
    name = "Advanced " + "x" * 38 + " tail of the name"
    topic = client.post(
        "/api/admin/topics", json={"name": name, "category": "Languages"}, headers=admin_headers
    ).json()["data"]["topic"]
    assert len(topic["slug"]) <= 48 and not topic["slug"].endswith("-")
    assert topic["slug"].startswith("advanced-xxx")


def test_duplicate_name_in_another_case_is_409_and_creates_nothing(client, admin_headers):
    assert client.post(
        "/api/admin/topics", json={"name": "Elixir", "category": "Languages"}, headers=admin_headers
    ).status_code == 200
    before = _count("SELECT count(*) FROM topic")
    audit_before = _count("SELECT count(*) FROM facilitator_action")
    for name in ("elixir", "ELIXIR", "Python"):
        response = client.post(
            "/api/admin/topics", json={"name": name, "category": "Languages"}, headers=admin_headers
        )
        assert response.status_code == 409, name
        assert response.json()["detail"]["code"] == "topic_exists"
    assert _count("SELECT count(*) FROM topic") == before
    assert _count("SELECT count(*) FROM facilitator_action") == audit_before


def test_slug_collision_with_a_different_name_is_409(client, admin_headers):
    # "Python!" derives slug `python` (seeded) though the name differs.
    response = client.post(
        "/api/admin/topics", json={"name": "Python!", "category": "Languages"}, headers=admin_headers
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "topic_exists"


def test_topic_create_validation(client, admin_headers):
    cases = [
        ({"name": "x", "category": "Languages"}, "name: must be 2–80 characters"),
        ({"name": "y" * 81, "category": "Languages"}, "name: must be 2–80 characters"),
        ({"name": "Elixir", "category": " L "}, "category: must be 2–48 characters"),
        ({"name": "Elixir"}, "category: Field required"),
        ({"name": "!!!", "category": "Languages"}, "name: must contain at least one letter or digit"),
    ]
    for body, message in cases:
        response = client.post("/api/admin/topics", json=body, headers=admin_headers)
        assert response.status_code == 422, body
        assert response.json()["detail"] == {"code": "validation_error", "message": message}
    assert _count("SELECT count(*) FROM topic") == 40


# --------------------------------------------------------------------------- admin update


def test_rename_keeps_slug_and_rename_collision_is_409(client, admin_headers, topic_ids):
    rust = topic_ids["rust"]
    response = client.patch(f"/api/admin/topics/{rust}", json={"name": "Rust (systems)"}, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["topic"]["slug"] == "rust"
    assert response.json()["data"]["topic"]["name"] == "Rust (systems)"

    clash = client.patch(f"/api/admin/topics/{rust}", json={"name": "PYTHON"}, headers=admin_headers)
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "topic_exists"
    assert _count("SELECT count(*) FROM topic WHERE name = 'Rust (systems)'") == 1

    # renaming to its own name in a different case is not a collision
    same = client.patch(f"/api/admin/topics/{rust}", json={"name": "rust (SYSTEMS)"}, headers=admin_headers)
    assert same.status_code == 200


def test_update_unknown_topic_is_404_and_null_name_is_rejected(client, admin_headers, topic_ids):
    assert client.patch("/api/admin/topics/9999", json={"active": False}, headers=admin_headers).status_code == 404
    response = client.patch(f"/api/admin/topics/{topic_ids['go']}", json={"name": None}, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "name: cannot be empty"


def test_deactivated_topic_hidden_publicly_rejected_for_new_use_but_kept_on_listing(
    client, admin_headers, topic_ids, create_opportunity
):
    listing = create_opportunity(["kotlin", "java"], status="open")
    kotlin = topic_ids["kotlin"]
    response = client.patch(f"/api/admin/topics/{kotlin}", json={"active": False}, headers=admin_headers)
    assert response.status_code == 200 and response.json()["data"]["topic"]["active"] is False

    # hidden from public filters, still listed (inactive) for admins
    assert "kotlin" not in {t["slug"] for t in _public_topics(client)}
    assert len(_public_topics(client)) == 39
    admin = {t["slug"]: t for t in _admin_topics(client, admin_headers)}
    assert admin["kotlin"]["active"] is False and admin["kotlin"]["opportunity_count"] == 1

    # rejected in NEW topic_ids (create, and adding to another listing)
    body = opportunity_body([kotlin])
    created = client.post("/api/admin/opportunities", json=body, headers=admin_headers)
    assert created.status_code == 422
    assert created.json()["detail"]["message"] == f"topic_ids: topic {kotlin} is inactive"
    other = create_opportunity(["go"])
    added = client.patch(
        f"/api/admin/opportunities/{other['id']}", json={"topic_ids": [topic_ids["go"], kotlin]},
        headers=admin_headers,
    )
    assert added.status_code == 422

    # still serialized on the listing that already carries it — public and admin
    public = client.get(f"/api/public/opportunities/{listing['id']}").json()["data"]["opportunity"]
    assert [t["slug"] for t in public["topics"]] == ["java", "kotlin"]
    admin_detail = client.get(f"/api/admin/opportunities/{listing['id']}", headers=admin_headers)
    assert {"slug": "kotlin", "active": False}.items() <= next(
        t for t in admin_detail.json()["data"]["opportunity"]["topics"] if t["slug"] == "kotlin"
    ).items()
    # ...and editing that listing while keeping its inactive topic is allowed
    kept = client.patch(
        f"/api/admin/opportunities/{listing['id']}",
        json={"topic_ids": [topic_ids["java"], kotlin], "summary": "Edited summary"},
        headers=admin_headers,
    )
    assert kept.status_code == 200, kept.text


def test_reactivated_topic_returns_to_public_filters(client, admin_headers, topic_ids):
    go = topic_ids["go"]
    client.patch(f"/api/admin/topics/{go}", json={"active": False}, headers=admin_headers)
    client.patch(f"/api/admin/topics/{go}", json={"active": True}, headers=admin_headers)
    assert "go" in {t["slug"] for t in _public_topics(client)}
