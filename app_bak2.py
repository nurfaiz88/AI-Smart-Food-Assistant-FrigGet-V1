import streamlit as st
from PIL import Image
import io, os, base64, datetime, socket, json
import qrcode
from openai import OpenAI

# ---------------- CONFIG ----------------
client = OpenAI()
st.set_page_config(page_title="Fridgeify", layout="wide")

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)  # ✅ NEW

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
    except Exception:
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
    prompt = f"""
Give nutrition info for {food} in simple text:
Calories:
Protein:
Carbs:
Fat:
"""
    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        return r.output_text
    except Exception:
        return "Nutrition unavailable."

# ---------------- SCAN PAGE ----------------
if st.session_state.page == "scan":
    st.subheader("📸 Scan Food")
    img = st.camera_input("Take photo")

    if img:
        image = Image.open(img)
        image.thumbnail((400, 400))
        st.image(image, caption="Captured")

        # Convert to base64 for AI
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        with st.spinner("Analyzing with AI..."):
            try:
                res = client.responses.create(
                    model="gpt-4.1-mini",
                    input=[{
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "List foods in this image, comma separated"},
                            {"type": "input_image", "image_base64": b64}
                        ]
                    }]
                )

                foods = [
                    f.strip().lower()
                    for f in res.output_text.split(",")
                    if f.strip()
                ]
            except Exception as e:
                st.error(f"AI error: {e}")
                foods = []

        added = []
        today = datetime.date.today()

        for food in foods:
            if not any(i["name"] == food for i in st.session_state.inventory):

                # ✅ SAVE IMAGE TO DISK (BEST PRACTICE)
                filename = f"{food}_{today}.png".replace(" ", "_")
                image_path = os.path.join(IMAGE_DIR, filename)
                image.save(image_path)

                st.session_state.inventory.append({
                    "name": food,
                    "added": str(today),
                    "expiry": str(today + datetime.timedelta(days=5)),
                    "image_path": image_path  # ✅ NEW
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
        for idx, item in enumerate(st.session_state.inventory):
            expiry_date = datetime.datetime.strptime(
                item["expiry"], "%Y-%m-%d"
            ).date()
            days = (expiry_date - today).days

            cols = st.columns([1, 3])

            # ✅ SHOW STORED IMAGE
            if "image_path" in item and os.path.exists(item["image_path"]):
                cols[0].image(Image.open(item["image_path"]), width=120)

            if days <= 1:
                cols[1].error(f"{item['name'].title()} expiring soon!")
            else:
                cols[1].write(f"{item['name'].title()} ({days} days left)")

            if cols[1].button(
                f"Show nutrition for {item['name']}",
                key=f"nutrition_{idx}"
            ):
                cols[1].text(nutrition(item["name"]))

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
                    r = client.responses.create(
                        model="gpt-4.1-mini",
                        input=prompt
                    )
                    st.text(r.output_text)
                except Exception as e:
                    st.error(f"Recipe generation failed: {e}")
