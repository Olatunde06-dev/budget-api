"""
test_api.py : checks that every address behaves.  Run it with:   python test_api.py

It uses a TEMPORARY database, so your real submissions.db is never touched.
Needs one extra install, once:   pip install httpx
"""
import os
import tempfile

# Point the database at a throw-away file BEFORE main.py is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db"), os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient   # noqa: E402  (must come after the line above)

from main import app   # noqa: E402

client = TestClient(app)

GOOD_PERSON = {
    "age": 33, "employment_status": "working", "relationship_status": "married",
    "monthly_income": 150000, "last_month_spending": 150000, "last_month_emergency": 0,
}
GOOD_SUBMISSION = {
    **GOOD_PERSON, "codename": "TestHeron123", "consent": True,
    "m2_spending": 140000, "m2_emergency": 10000, "m3_spending": 135000,
}


def check(name, condition):
    print(("PASS  " if condition else "FAIL  ") + name)
    if not condition:
        raise SystemExit(1)


# --- reading addresses ---
r = client.get("/health")
check("GET /health answers 200", r.status_code == 200 and r.json()["status"] == "ok")

r = client.get("/")
check("GET / serves the web page", r.status_code == 200 and "<form" in r.text)

r = client.get("/model-info")
check("GET /model-info lists 7 features", r.status_code == 200 and len(r.json()["features"]) == 7)

# --- /predict ---
r = client.post("/predict", json=GOOD_PERSON)
body = r.json()
check("POST /predict returns an estimate", r.status_code == 200 and body["estimate"] > 0)
check("estimate sits between low and high", body["low"] <= body["estimate"] <= body["high"])

r = client.post("/predict", json={**GOOD_PERSON, "age": "abc"})
check("age 'abc' is refused with 422", r.status_code == 422)

r = client.post("/predict", json={**GOOD_PERSON, "age": 10})
check("age 10 is refused (minimum 18)", r.status_code == 422)

r = client.post("/predict", json={**GOOD_PERSON, "employment_status": "retired"})
check("unknown employment word is refused", r.status_code == 422)

r = client.post("/predict", json={**GOOD_PERSON, "last_month_emergency": 999999})
check("emergency bigger than spending is refused", r.status_code == 422)

# --- /submit and /stats ---
before = client.get("/stats").json()["people"]
r = client.post("/submit", json=GOOD_SUBMISSION)
check("POST /submit saves and returns an estimate", r.status_code == 200 and r.json()["saved"] is True)
after = client.get("/stats").json()["people"]
check("/stats count went up by one", after == before + 1)

r = client.post("/submit", json={**GOOD_SUBMISSION, "consent": False})
check("submit without consent is refused", r.status_code == 422)

r = client.post("/submit", json={**GOOD_SUBMISSION, "codename": "me@email.com"})
check("an email as code name is refused", r.status_code == 422)

r = client.post("/submit", json={**GOOD_SUBMISSION, "codename": "call08012345678"})
check("a phone number as code name is refused", r.status_code == 422)

print("\nAll checks passed.")
