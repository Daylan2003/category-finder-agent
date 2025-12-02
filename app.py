import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from dotenv import load_dotenv

# Load GOOGLE_API_KEY from category_agent/.env so ADK/Gemini works inside Streamlit
load_dotenv(Path("category_agent") / ".env")

from google.adk.runners import InMemoryRunner
from google.genai import types

from category_agent.agent import root_agent



#First load dataset
PRODUCTS_PATH = Path("category_agent") / "products.json"

with PRODUCTS_PATH.open("r", encoding="utf-8") as f:
    PRODUCTS: List[Dict[str, Any]] = json.load(f)

# Explicit categories for each product id in this small catalog
CATEGORY_BY_ID: Dict[int, str] = {
    0: "clothing",    # UBC Hoodie
    5: "clothing",    # Running Shoes
    7: "clothing",    # T-Shirt
    8: "clothing",    # Denim Jacket

    1: "electronics",  # MacBook Air
    2: "electronics",  # Bluetooth Headphones
    3: "electronics",  # Smartwatch
    4: "electronics",  # USB-C Hub

    6: "accessories",  # Backpack

    9:  "groceries",   # Organic Apples
    10: "groceries",   # Whole Wheat Bread
    11: "groceries",   # Almond Milk
    12: "groceries",   # Brown Rice
}


def normalize_category(cat: Optional[str]) -> Optional[str]:
    #similar names to fall into one
    if cat is None:
        return None
    c = cat.strip().lower()
    if c in {"clothing", "clothes", "apparel", "wearables"}:
        return "clothing"
    if c in {"electronics", "devices", "tech"}:
        return "electronics"
    if c in {"groceries", "grocery", "food"}:
        return "groceries"
    if c in {"accessories", "bags", "backpacks"}:
        return "accessories"
    return c  


def filter_products(
    category: Optional[str],
    max_price: Optional[float],
    min_price: Optional[float],
) -> List[Dict[str, Any]]:

    #Normalize products
    norm_cat = normalize_category(category)

    #to store results, (List of Dictionaries)
    results: List[Dict[str, Any]] = []

    for p in PRODUCTS:
        price = float(p["price"])

        #sort based on prices
        if max_price is not None and price > max_price:
            continue
        if min_price is not None and price < min_price:
            continue

        # Category is not included in the json data so this is used to sort category data
        if norm_cat is not None:
            pid = int(p["id"])
            p_cat = CATEGORY_BY_ID.get(pid)
            if p_cat != norm_cat:
                continue

        #add valid data to results        
        results.append(
            {
                "id": p["id"],
                "name": p["name"],
                "description": p["description"],
                "price": price,
                "image": p["image"],
                "category": CATEGORY_BY_ID.get(int(p["id"])),
            }
        )

    # Stable ordering → same filters → same output
    results.sort(key=lambda r: (r["price"], r["name"]))
    return results



#User speaks to the Agent
#function takes the user's message and returns a dictionary iwth the filter values
def get_filters_from_agent(user_query: str) -> Dict[str, Any]:


    # Create a small in-memory runner for this call.
    runner = InMemoryRunner(agent=root_agent, app_name="category_agent")
    user_id = "web_user"

    async def _run_once() -> List[Any]:

      
        session = await runner.session_service.create_session(
            app_name="category_agent",
            user_id=user_id,
        )

        events: List[Any] = []

  
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_query)],
            ),
        ):
            events.append(event)

        return events

  
    events = asyncio.run(_run_once())

    final_text = ""
    for ev in reversed(events):
        content = getattr(ev, "content", None)
        if content and getattr(content, "parts", None):
            part = content.parts[0]
            if getattr(part, "text", None):
                final_text = part.text.strip()
                break



    #agent should resturn a JSON object string
    try:
        filters = json.loads(final_text)
    except json.JSONDecodeError:

        filters = {"category": None, "max_price": None, "min_price": None}

   
    for key in ("max_price", "min_price"):
        val = filters.get(key, None)
        if isinstance(val, str) and val.strip() == "":
            filters[key] = None

    return filters




# Streamlit UI


st.set_page_config(page_title="Category Finder Agent", layout="wide")
st.title("Category Finder Agent (ADK + Deterministic Catalog)")

st.markdown(
    "Type a request like **'Show me all clothing products'** or "
    "**'What clothing items are available under $50?'**"
)

user_query = st.text_input("Your request:")

if st.button("Ask") and user_query.strip():
    with st.spinner("Asking agent..."):
        filters = get_filters_from_agent(user_query.strip())

    st.subheader("Parsed filters")
    st.json(filters)

    products = filter_products(
        category=filters.get("category"),
        max_price=filters.get("max_price"),
        min_price=filters.get("min_price"),
    )

    st.subheader("Results")

    if not products:
        st.warning("No products match these filters.")
    else:

        cols = st.columns(3)  

        for i, p in enumerate(products):
            with cols[i % 3]:
                st.markdown(
                    f"""
                    <div style="
                        border: 1px solid #ddd;
                        border-radius: 10px;
                        padding: 12px;
                        margin-bottom: 20px;
                        background-color: #fafafa;
                        text-align: center;
                    ">
                        <img src="{p['image']}" style="width:100%; border-radius: 5px;">
                        <h4 style="margin-top: 10px;">{p['name']}</h4>
                        <p style="color: gray;">{p['description']}</p>
                        <p><strong>${p['price']:.2f}</strong></p>
                        <p style="font-size: 12px; color: #666;">
                            Category: {p['category']}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

