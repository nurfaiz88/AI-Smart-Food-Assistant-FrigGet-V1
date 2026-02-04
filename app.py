import streamlit as st
from PIL import Image
import io, os, base64, datetime, socket, json
import qrcode
import requests
from openai import OpenAI

# ---------------- CONFIG ----------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
st.set_page_config(page_title="Fridgeify", layout="wide")

# ---------------- STATE ----------------
if "inventory" not in st.session_state:
    if os.path.exists("inventory.json"):
        with open("inventory.json", "r") as f:
            st.session_state.inventory = json.load(f)
    else:
        st.session_state.inventory = []

if "page" not in st.session_state:
    st.session_state.page = "scan"

# ---------------- HEADER ----------------
st.title("🧊 Fridgeify AI")

# ---------------- NAV ----------------
c1, c2, c3 = st.columns(3)
if c1.button("📸 Scan"):
    st.session_state.page = "scan"
if c2.button("🧊 Inventory"):
    st.session_state.page = "inventory"
if c3.button("🍳 Recipes"):
    st.session_state.page = "recipes"

# ---------------- QR ----------------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return None

ip = get_local_ip()
if ip:
    url = f"http://{ip}:8501"
    qr_img = qrcode.make(url)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    st.image(buf.getvalue(), width=150)
    st.caption(f"Open on phone: {url}")

# ---------------- HELPERS ----------------
def save_inventory():
    with open("inventory.json", "w") as f:
        json.dump(st.session_state.inventory, f, indent=2)

def nutrition(food):
    prompt = f"""Give nutrition info for {food} in simple text:
Calories:
Protein:
Carbs:
Fat:"""
    try:
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return r.choices[0].message.content
    except:
        return "Nutrition unavailable."

# ---------------- SCAN PAGE ----------------
if st.session_state.page == "scan":
    st.subheader("📸 Scan Food")
    img = st.camera_input("Take photo")

    if img:
        image = Image.open(img)
        image.thumbnail((400, 400))
        st.image(image, caption="Captured")

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        with st.spinner("Analyzing with AI..."):
            try:
                res = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "List foods in this image, comma separated"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                        ]
                    }],
                    max_tokens=200
                )
                foods = [f.strip().lower() for f in res.choices[0].message.content.split(",")]
            except:
                foods = []

        added = []
        for food in foods:
            if food and not any(i["name"] == food for i in st.session_state.inventory):
                st.session_state.inventory.append({
                    "name": food,
                    "added": str(datetime.date.today()),
                    "expiry": str(datetime.date.today() + datetime.timedelta(days=5))
                })
                added.append(food)

        save_inventory()

        if added:
            st.success(f"Added: {', '.join(added)}")
        else:
            st.warning("No new foods detected.")

# ---------------- INVENTORY PAGE ----------------
if st.session_state.page == "inventory":
    st.subheader("🧊 Inventory")

    today = datetime.date.today()

    if not st.session_state.inventory:
        st.info("No food yet. Scan something.")
    else:
        for item in st.session_state.inventory:
            expiry_date = datetime.datetime.strptime(item["expiry"], "%Y-%m-%d").date()
            days = (expiry_date - today).days

            if days <= 1:
                st.error(f"{item['name'].title()} expiring soon!")
            else:
                st.write(f"{item['name'].title()} ({days} days left)")

            if st.button(f"Show nutrition for {item['name']}", key=item["name"]):
                info = nutrition(item["name"])
                st.text(info)

# ---------------- RECIPES PAGE ----------------
if st.session_state.page == "recipes":
    st.subheader("🍳 Recipes")

    if not st.session_state.inventory:
        st.warning("Scan food first.")
    else:
        if st.button("Generate Recipe"):
            foods = ", ".join(i["name"] for i in st.session_state.inventory)

            prompt = f"""
Create a recipe using: {foods}

Include:
- Recipe name
- Ingredients list
- Steps
- Estimated calories
Keep it clear and readable.
"""

            with st.spinner("Generating recipe..."):
                try:
                    r = client.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=600
                    )
                    recipe_text = r.choices[0].message.content
                    st.text(recipe_text)
                except:
                    st.error("Recipe generation failed.")


