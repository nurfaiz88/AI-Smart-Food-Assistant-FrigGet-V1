import streamlit as st
from picamera2 import Picamera2
from PIL import Image
import datetime, os, socket, json, io, base64
from openai import OpenAI

# ---------------- CONFIG ----------------
# ❗ DO NOT hardcode keys in production
os.environ["OPENAI_API_KEY"] = "YOUR_OPENAI_KEY"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="Fridgeify (Pi Optimized)", layout="wide")

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# ---------------- STATE ----------------
if "inventory" not in st.session_state:
    if os.path.exists("inventory.json"):
        with open("inventory.json", "r") as f:
            st.session_state.inventory = json.load(f)
    else:
        st.session_state.inventory = []

if "page" not in st.session_state:
    st.session_state.page = "scan"

if "camera_open" not in st.session_state:
    st.session_state.camera_open = False

# ---------------- HEADER ----------------
st.title("🧊 Fridgeify AI (Pi Optimized)")

# ---------------- NAV ----------------
c1, c2, c3 = st.columns(3)
if c1.button("📸 Scan"):
    st.session_state.page = "scan"
if c2.button("🧊 Inventory"):
    st.session_state.page = "inventory"
if c3.button("🍳 Recipes"):
    st.session_state.page = "recipes"

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
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        return res.output_text
    except Exception:
        return "Nutrition unavailable."

# ---------------- CAMERA HELPER ----------------
@st.cache_resource
def get_camera():
    picam = Picamera2()
    config = picam.create_preview_configuration(
        main={"size": (320, 240)}  # Pi 3 friendly
    )
    picam.configure(config)
    picam.start()
    return picam

# ---------------- SCAN PAGE ----------------
if st.session_state.page == "scan":
    st.subheader("📸 Scan Food")

    if st.button("Open Camera"):
        st.session_state.camera_open = True

    frame = None

    if st.session_state.camera_open:
        try:
            picam = get_camera()
            frame = picam.capture_array()
            st.image(frame, width=400)
        except Exception as e:
            st.error(f"Camera error: {e}")
            st.session_state.camera_open = False

        if st.button("Take Photo") and frame is not None:
            st.session_state.camera_open = False
            today = datetime.date.today()

            img = Image.fromarray(frame)
            img = img.resize((320, 320))  # reduce hallucination

            filename = f"food_{today}.png"
            image_path = os.path.join(IMAGE_DIR, filename)
            img.save(image_path)

            st.success("Photo captured!")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64_image = base64.b64encode(buf.getvalue()).decode()

            # ---------------- AI ANALYSIS ----------------
            with st.spinner("Analyzing food..."):
                try:
                    res = client.responses.create(
                        model="gpt-4.1-mini",
                        input=[{
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": """
You are scanning food items for a fridge inventory system.

Rules:
- Only identify actual food items you are confident about.
- Do NOT guess.
- Do NOT describe cooked meals unless clearly visible.
- Prefer raw, whole ingredients.
- If the image is unclear, return: unknown

Return format:
- comma-separated list
- lowercase
- no extra text

What food items are visible in this image?
"""
                                },
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{b64_image}"
                                }
                            ]
                        }]
                    )

                    foods = [
                        f.strip().lower()
                        for f in res.output_text.split(",")
                        if f.strip() and f.strip() != "unknown"
                    ]

                except Exception as e:
                    st.error(f"AI analysis failed: {e}")
                    foods = []

            added = []
            for food in foods:
                if not any(i["name"] == food for i in st.session_state.inventory):
                    st.session_state.inventory.append({
                        "name": food,
                        "added": str(today),
                        "expiry": str(today + datetime.timedelta(days=5)),
                        "image_path": image_path
                    })
                    added.append(food)

            save_inventory()

            if added:
                st.success(f"Added: {', '.join(added)}")
            else:
                st.warning("No confident food detected.")

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

            # ✅ FIX APPLIED HERE
            if item.get("image_path") and os.path.exists(item["image_path"]):
                cols[0].image(Image.open(item["image_path"]), width=120)

            if days <= 1:
                cols[1].error(f"{item['name'].title()} expiring soon!")
            else:
                cols[1].write(f"{item['name'].title()} ({days} days left)")

            if cols[1].button(
                f"Show nutrition for {item['name']}",
                key=f"nutr_{idx}"
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
                    res = client.responses.create(
                        model="gpt-4.1-mini",
                        input=prompt
                    )
                    st.text(res.output_text)
                except Exception as e:
                    st.error(f"Recipe generation failed: {e}")
