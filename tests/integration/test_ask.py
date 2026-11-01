"""Natural-language search: the decision gate, server-side SQL execution, and limits.

A fake assistant replaces OpenAI, so these tests need no API key or network.
"""

from contextlib import closing
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.ai import DECISION_MODEL, OpenAIQueryAssistant, get_assistant, to_decision
from app.main import app
from app.models import GeneratedQuery, PromptDecision
from tests.conftest import AS_OF


class FakeAssistant:
    def __init__(self, intent="read", sql="SELECT 1", parameters=()):
        self.decision = PromptDecision(intent=intent, confidence=0.9, modify_probability=0.0)
        self.query = GeneratedQuery(sql=sql, parameters=list(parameters), explanation="test")
        self.generate_calls = []

    def decide(self, question):
        return self.decision

    def generate_sql(self, question, schema, as_of, max_rows, asker=""):
        self.generate_calls.append((question, schema, as_of, max_rows))
        self.asker = asker
        return self.query


@pytest.fixture
def use_assistant():
    def install(assistant):
        app.dependency_overrides[get_assistant] = lambda: assistant
        return assistant

    yield install
    app.dependency_overrides.pop(get_assistant, None)


def ask(client, question="Which lab follow-ups are open?", **body):
    return client.post("/api/ask", json={"question": question, "as_of_date": AS_OF, **body})


def test_read_question_runs_generated_sql_with_bound_parameters(client, use_assistant):
    assistant = use_assistant(FakeAssistant(
        sql="SELECT followup_id FROM followups WHERE action_type = ? AND status = ? ORDER BY followup_id",
        parameters=["lab", "open"],
    ))
    response = ask(client, max_rows=50)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"]["intent"] == "read"
    assert body["parameters"] == ["lab", "open"]
    assert body["result"]["rows"] == [["F001"], ["F002"], ["F007"]]
    question, schema, as_of, max_rows = assistant.generate_calls[0]
    assert "CREATE TABLE followups" in schema
    assert (as_of.isoformat(), max_rows) == (AS_OF, 50)


@pytest.mark.parametrize("intent, code", [
    ("modify", "modification_not_allowed"),
    ("unrelated", "unsupported_question"),
])
def test_rejected_prompts_never_generate_sql(client, use_assistant, intent, code):
    assistant = use_assistant(FakeAssistant(intent=intent))
    response = ask(client, "Mark F001 as done")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code
    assert assistant.generate_calls == []


@pytest.mark.parametrize("sql", [
    "UPDATE followups SET status = 'done'",
    "DELETE FROM patients",
    "SELECT 1; DROP TABLE visits",
])
def test_generated_writes_are_blocked_even_when_the_gate_accepts(client, database, use_assistant, sql):
    use_assistant(FakeAssistant(sql=sql))
    assert ask(client).status_code == 422
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM followups WHERE status = 'open'").fetchone() == (6,)
        assert connection.execute("SELECT COUNT(*) FROM patients").fetchone() == (2,)


def test_contact_details_read_as_null(client, use_assistant):
    use_assistant(FakeAssistant(sql="SELECT name, phone, email FROM patients WHERE patient_id = 'P001'"))
    assert ask(client).json()["result"]["rows"] == [["Alice Example", None, None]]


def test_unusable_generated_query_is_a_clear_error(client, use_assistant):
    use_assistant(FakeAssistant(sql="   "))
    response = ask(client)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_generated_query"


@pytest.mark.parametrize("body", [{"question": "   "}, {"question": "x", "max_rows": 0}, {"question": "x", "sql": "SELECT 1"}])
def test_invalid_ask_requests_are_rejected(client, use_assistant, body):
    use_assistant(FakeAssistant())
    assert client.post("/api/ask", json=body).status_code == 422


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = ask(client)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_unavailable"


def predicate(probability):
    return SimpleNamespace(type="predicate", name="modify", probability=probability)


def choice(value, confidence=0.9):
    return SimpleNamespace(type="choice", name="intent", choice=value, confidence=confidence)


REFUSED_MODIFY = SimpleNamespace(type="refusal", name="modify")
REFUSED_INTENT = SimpleNamespace(type="refusal", name="intent")


@pytest.mark.parametrize("answers, intent", [
    ([predicate(0.05), choice("read")], "read"),
    ([predicate(0.05), choice("unrelated")], "unrelated"),
    ([predicate(0.05), choice("modify")], "modify"),
    ([predicate(0.4), choice("read")], "modify"),  # fail closed below the choice's own pick
    ([REFUSED_MODIFY, choice("read")], "modify"),
    ([predicate(0.05), REFUSED_INTENT], "unrelated"),
])
def test_decision_answers_fail_closed(answers, intent):
    assert to_decision(answers).intent == intent


def test_decide_sends_only_the_prompt_to_the_decisions_api():
    calls = []

    class Decisions:
        def create(self, **request):
            calls.append(request)
            return SimpleNamespace(answers=[predicate(0.01), choice("read")])

    assistant = OpenAIQueryAssistant(api_key="test", sql_model="test")
    assistant.client = SimpleNamespace(decisions=Decisions())
    assert assistant.decide("lab follow-ups due this week").intent == "read"
    request = calls[0]
    assert (request["model"], request["input"]) == (DECISION_MODEL, "lab follow-ups due this week")
    assert {question["name"] for question in request["questions"]} == {"modify", "intent"}


@pytest.mark.parametrize("env, model", [
    ({"OPENAI_MODELS": "gpt-a, gpt-b"}, "gpt-a"),
    ({"OPENAI_MODELS": "gpt-a", "OPENAI_SQL_MODEL": "gpt-c"}, "gpt-c"),
])
def test_sql_model_comes_from_environment(monkeypatch, env, model):
    for name in ("OPENAI_MODELS", "OPENAI_SQL_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert get_assistant().sql_model == model


# --- staff who are not managers ask about their own follow-ups only ------------

NURSE_EMAIL = "sample@clinic.test"  # S002, assigned only F003 (patient P002)


def nurse_asks(use_assistant, sql):
    use_assistant(FakeAssistant(sql=sql))
    with TestClient(app) as client:
        assert client.post("/api/session", json={"email": NURSE_EMAIL}).status_code == 200
        return ask(client)


@pytest.mark.parametrize(("sql", "rows"), [
    ("SELECT followup_id FROM followups ORDER BY followup_id", [["F003"]]),
    ("SELECT COUNT(*) FROM followups", [[1]]),
    ("SELECT patient_id, phone FROM patients", [["P002", None]]),
    ("SELECT DISTINCT episode_id FROM visits", [["E002"]]),
    ("SELECT COUNT(*) FROM followups f JOIN visits v ON v.visit_id = f.visit_id WHERE v.patient_id = 'P001'", [[0]]),
    ("WITH mine AS (SELECT followup_id FROM followups) SELECT COUNT(*) FROM mine", [[1]]),
])
def test_staff_questions_see_only_their_follow_ups(database, use_assistant, sql, rows):
    response = nurse_asks(use_assistant, sql)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["rows"] == rows


@pytest.mark.parametrize("sql", [
    "SELECT followup_id FROM main.followups",
    "SELECT name FROM main.patients",
    "WITH followups AS (SELECT * FROM main.followups) SELECT COUNT(*) FROM followups",
    "SELECT sql FROM sqlite_temp_schema",
])
def test_staff_questions_cannot_step_around_the_limit(database, use_assistant, sql):
    response = nurse_asks(use_assistant, sql)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "query_not_allowed"


def test_staff_limit_is_removed_after_the_question(database, use_assistant):
    nurse_asks(use_assistant, "SELECT 1")
    use_assistant(FakeAssistant(sql="SELECT COUNT(*) FROM followups"))
    with TestClient(app) as manager:
        manager.post("/api/session", json={"email": "manager@clinic.test"})
        assert ask(manager).json()["result"]["rows"] == [[7]]


def test_the_model_is_told_who_is_asking_by_staff_id_only(database, use_assistant):
    assistant = FakeAssistant(sql="SELECT COUNT(*) FROM followups")
    use_assistant(assistant)
    with TestClient(app) as client:
        client.post("/api/session", json={"email": NURSE_EMAIL})
        ask(client)
    assert "staff member S002" in assistant.asker and "need no staff filter" in assistant.asker
    assert "Nurse Sample" not in assistant.asker
    with TestClient(app) as client:
        client.post("/api/session", json={"email": "manager@clinic.test"})
        ask(client)
    assert "S005, a manager" in assistant.asker
