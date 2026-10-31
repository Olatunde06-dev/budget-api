from fastapi import FastAPI
from pydantic import BaseModel
import joblib

class Person(BaseModel):
  age: int
  employment_status: str
  relationship_status:str
  monthly_income: float
  last_month_spending: float
  last_month_emergency: float = 0

app = FastAPI()
model = joblib.load("budget_model.pkl")
@app.get("/")
def home():
  return{"message": "hello"}

@app.get("/model-info")
def model_info():
  return{"features": list(model.feature_names_in_)}

@app.post("/predict")
def predict(person : Person):
  return{"received": person.model_dump}