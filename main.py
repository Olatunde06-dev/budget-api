"""
main.py : the API.  This is the file you run with:   uvicorn main:app --reload

The journey of one request (read this first, it is the whole project in 6 lines):

    1. A browser sends a request to an ADDRESS (like /predict).
    2. uvicorn (the server program) receives it and hands it to FastAPI (`app`).
    3. FastAPI finds the function you attached to that address with @app.get / @app.post.
    4. For POST requests, FastAPI first CHECKS the data against a class (Person / Submission).
       Bad data is refused automatically (error 422) and your function never runs.
    5. Your function runs: it asks the saved model for an estimate, and sometimes saves to the database.
    6. FastAPI turns what you `return` into JSON and sends it back to the browser.
"""
import json
import os
import re
from typing import Literal, Optional

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

import database   # our own file, database.py

# ---------------------------------------------------------------------------
# 1. FILE LOCATIONS
# ---------------------------------------------------------------------------
# __file__ is "this file".  We build paths from it so the code works no matter which folder
# you start the server from.  (If you used a bare "budget_model.pkl" like in the first lesson,
# it only works when the terminal is inside budget_api.)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "budget_model.pkl")      # your trained model
META_PATH = os.path.join(BASE_DIR, "model_meta.json")        # notes about the model (typical error, version)
FORM_PATH = os.path.join(BASE_DIR, "static", "index.html")   # the web page people fill in




# ---------------------------------------------------------------------------
# 2. LOADING THE MODEL (and noticing when retrain.py replaces it)
# ---------------------------------------------------------------------------
# `state` is a dictionary that remembers the loaded model between requests.
# Loading a model from disk is slow, so we do it once and keep it in memory.
# We also remember the file's "last modified" time: if retrain.py saves a new
# budget_model.pkl, the time changes and we reload it, without restarting the server.
state = {"model": None, "mtime": None, "meta": {"mae": 12000, "version": 1, "algorithm": "unknown"}}


def get_model():
    """Return the model, reloading it from disk if the file has changed."""
    mtime = os.path.getmtime(MODEL_PATH)       # FileNotFoundError here = budget_model.pkl is missing
    if state["model"] is None or mtime != state["mtime"]:
        state["model"] = joblib.load(MODEL_PATH)
        state["mtime"] = mtime
        if os.path.exists(META_PATH):
            with open(META_PATH) as f:
                state["meta"] = json.load(f)
    return state["model"]


get_model()             # load once at start-up, so a missing model fails immediately and loudly
database.init_db()      # create the submissions table if it is not there yet


# ---------------------------------------------------------------------------
# 3. THE APP
# ---------------------------------------------------------------------------
app = FastAPI(title="Next month's budget")

# CORS = the browser's safety rule that stops a web page on one address from calling an API on
# another address.  If the page is served by this same server (our case) we do not need it,
# but it saves you from a confusing error when you test the page from another tool (like Live
# Server on port 5500).  "*" means "any website may call this API".  Before a real launch,
# replace it with your own website's address.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# 4. THE FORMS (data shapes).  A class is a blank form: each line is a box and the type it holds.
#    FastAPI checks every incoming request against these before your function runs.
# ---------------------------------------------------------------------------
class Person(BaseModel):
    """What /predict needs.  Field(ge=18, le=70) means 'greater or equal 18, less or equal 70'."""
    age: int = Field(ge=18, le=70)
    # Literal[...] means: only these exact words are allowed.  Anything else is refused.
    employment_status: Literal["working", "unemployed"]
    relationship_status: Literal["single", "dating", "married"]
    monthly_income: float = Field(ge=0, le=100_000_000)
    last_month_spending: float = Field(ge=0, le=100_000_000)
    last_month_emergency: float = Field(default=0, ge=0)   # default 0 = optional

    # A validator is your own extra rule, run after the basic checks.
    @model_validator(mode="after")
    def emergency_fits_inside_spending(self):
        if self.last_month_emergency > self.last_month_spending:
            raise ValueError("last_month_emergency cannot be more than last_month_spending")
        return self


class Submission(Person):
    """What /submit needs.  `(Person)` means: start with every box Person has, then add more."""
    codename: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9_-]+$")
    m2_spending: Optional[float] = Field(default=None, ge=0, le=100_000_000)   # two months ago
    m2_emergency: float = Field(default=0, ge=0)
    m3_spending: Optional[float] = Field(default=None, ge=0, le=100_000_000)   # three months ago
    m3_emergency: float = Field(default=0, ge=0)
    consent: bool

    @field_validator("codename")
    @classmethod
    def codename_is_not_a_phone_number(cls, value):
        # The pattern above already blocks "@" (emails).  This blocks long digit strings (phone numbers).
        if re.search(r"\d{7,}", value):
            raise ValueError("code name looks like a phone number, use a code name instead")
        return value

    @field_validator("consent")
    @classmethod
    def consent_must_be_true(cls, value):
        if value is not True:
            raise ValueError("consent is required")
        return value

    @model_validator(mode="after")
    def older_months_make_sense(self):
        if self.m2_spending is None and self.m2_emergency > 0:
            raise ValueError("m2_emergency was given without m2_spending")
        if self.m3_spending is None and self.m3_emergency > 0:
            raise ValueError("m3_emergency was given without m3_spending")
        if self.m2_spending is not None and self.m2_emergency > self.m2_spending:
            raise ValueError("m2_emergency cannot be more than m2_spending")
        if self.m3_spending is not None and self.m3_emergency > self.m3_spending:
            raise ValueError("m3_emergency cannot be more than m3_spending")
        return self


# ---------------------------------------------------------------------------
# 5. THE ESTIMATE (the one place the model is used)
# ---------------------------------------------------------------------------
def make_estimate(person: Person) -> dict:
    model = get_model()

    # The model was trained on 7 numeric columns, in a specific order.  The form sends words like
    # "working", so we convert them to the same 0/1 columns that pd.get_dummies made in your notebook.
    row = {
        "age": person.age,
        "monthly_income": person.monthly_income,
        "last_month_spending": person.last_month_spending,
        "last_month_emergency": person.last_month_emergency,
        "employment_status_working": int(person.employment_status == "working"),
        "relationship_status_married": int(person.relationship_status == "married"),
        "relationship_status_single": int(person.relationship_status == "single"),
    }

    wanted = list(model.feature_names_in_)       # the exact column names the model remembers
    missing = [c for c in wanted if c not in row]
    if missing:
        # The model expects a column this code does not build.  That is a bug on OUR side, so 500.
        raise HTTPException(status_code=500, detail=f"model expects columns we do not build: {missing}")

    X = pd.DataFrame([row])[wanted]              # one-row table, columns in the model's order
    raw = max(float(model.predict(X)[0]), 0.0)   # never predict negative spending

    mae = state["meta"]["mae"]                   # the model's typical miss, in naira
    return {
        "estimate": round(raw),
        "low": max(0, round(raw - mae)),
        "high": round(raw + mae),
        "typical_miss": mae,
        "model_version": state["meta"]["version"],
    }


# ---------------------------------------------------------------------------
# 6. THE ADDRESSES (routes)
#    @app.get  = "someone is asking for something"
#    @app.post = "someone is sending me data"
# ---------------------------------------------------------------------------
@app.get("/")
def form_page():
    """The front door now serves the web page itself."""
    return FileResponse(FORM_PATH)


@app.get("/health")
def health():
    """Your original 'hello' door.  Hosting services call an address like this to see if you are alive."""
    return {"message": "hello", "status": "ok", "model_version": state["meta"]["version"]}


@app.get("/model-info")
def model_info():
    return {"features": list(get_model().feature_names_in_), **state["meta"]}


@app.get("/stats")
def stats():
    """Progress towards retraining.  Only a count: no personal data is ever exposed here."""
    return {"people": database.count_people()}


@app.post("/predict")
def predict(person: Person):
    """Estimate only.  Nothing is saved."""
    return make_estimate(person)


@app.post("/submit")
def submit(data: Submission):
    """Estimate AND save the answers (these become training data later)."""
    result = make_estimate(data)
    database.save_submission({
        "codename": data.codename,
        "age": data.age,
        "employment_status": data.employment_status,
        "relationship_status": data.relationship_status,
        "monthly_income": data.monthly_income,
        "m1_spending": data.last_month_spending,
        "m1_emergency": data.last_month_emergency,
        "m2_spending": data.m2_spending,
        "m2_emergency": data.m2_emergency if data.m2_spending is not None else None,
        "m3_spending": data.m3_spending,
        "m3_emergency": data.m3_emergency if data.m3_spending is not None else None,
        "predicted_next_month": result["estimate"],
        "model_version": result["model_version"],
    })
    return {**result, "saved": True, "codename": data.codename}
