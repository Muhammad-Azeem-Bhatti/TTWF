from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import pandas as pd

# 1. Initialize the App
app = FastAPI()


# 2. Define the Data Structure
# This ensures the user sends specific data types (text, numbers).
class Item(BaseModel):
    name: str
    quantity: int
    price: float


class SalesData(BaseModel):
    items: List[Item]


# 3. Create the Logic (The Endpoint)
@app.post("/calculate-sales")
def calculate_sales(data: SalesData):
    # Convert the user's data (JSON) into a Python list
    raw_data = [item.dict() for item in data.items]

    # Load it into a Pandas DataFrame
    df = pd.DataFrame(raw_data)

    # --- Perform Calculations ---
    # Calculate revenue per item (Quantity * Price)
    df['revenue'] = df['quantity'] * df['price']

    # Calculate totals
    total_revenue = df['revenue'].sum()
    total_items = df['quantity'].sum()
    avg_price = df['price'].mean()

    # Return the results
    return {
        "message": "Calculation successful",
        "total_revenue": round(total_revenue, 2),
        "total_items_sold": int(total_items),
        "average_unit_price": round(avg_price, 2)
    }


# 4. Simple Home Page
@app.get("/")
def home():
    return {"message": "API is Online. Go to /docs to test it."}