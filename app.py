import streamlit as st
import json
import os
import io
import google.generativeai as genai
from PIL import Image
from pypdf import PdfReader, PdfWriter
from st_copy_button import st_copy_button

# --- 1. SETUP & THEME ---
st.set_page_config(page_title="Solar Interconnection Assistant", layout="wide")

# Custom CSS: High Contrast Inputs + MENU FIX + LOGO GLOW
st.markdown("""
    <style>
    /* 1. Force input fields to be white with black text */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
        border: 1px solid #ccc !important;
    }
    
    /* 2. Force the LABELS above the inputs to be WHITE */
    div[data-testid="stTextInput"] label {
        color: #ffffff !important;
        font-size: 14px !important;
        font-weight: bold !important;
    }
    div[data-testid="stTextInput"] p {
        color: #ffffff !important;
    }

    /* 3. Style disabled inputs (results) */
    div[data-testid="stTextInput"] input:disabled {
        background-color: #e9ecef !important;
        color: #2c3e50 !important;
        -webkit-text-fill-color: #2c3e50 !important;
        opacity: 1 !important;
    }

    /* 4. FIX FOR THE UNREADABLE MENU (Three Dots) */
    div[data-testid="stPopoverBody"] { color: white !important; }
    li[role="option"] div { color: white !important; }
    div[data-testid="stToolbar"] { color: white !important; }

    /* 5. IMAGE STYLING (Logo & Previews) - THE FADED BORDER FIX */
    /* This targets the logo and adds a soft white glow + rounded corners */
    div[data-testid="stImage"] img {
        border-radius: 12px; /* Smooth corners */
        box-shadow: 0 0 15px rgba(255, 255, 255, 0.15); /* The "Faded Border" glow */
        border: 1px solid rgba(255, 255, 255, 0.1); /* Thin defining line */
    }

    /* 6. General UI tweaks */
    div[data-baseweb="popover"] ul { background-color: #333333 !important; }
    div[data-baseweb="popover"] li { color: white !important; }
    
    .stButton>button { 
        width: 100%; border-radius: 8px; height: 3.5em; 
        background-color: #2e7bcf; color: white; font-weight: bold; 
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. API KEY SETUP (CLOUD READY) ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    else:
        # Fallback for local testing
        genai.configure(api_key="AIzaSyDEg7dghFxbdmQigr4JqQuB5zo2UOVDsWw")
except FileNotFoundError:
    genai.configure(api_key="AIzaSyDEg7dghFxbdmQigr4JqQuB5zo2UOVDsWw")

# --- SESSION STATE ---
if 'extraction_results' not in st.session_state:
    st.session_state['extraction_results'] = None
if 'file_buffers' not in st.session_state:
    st.session_state['file_buffers'] = {}

# --- SMART MODEL CONNECT ---
def get_working_model():
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        if available_models:
            for m in available_models:
                if 'flash' in m: return genai.GenerativeModel(m)
            return genai.GenerativeModel(available_models[0])
    except:
        pass
    return None

active_model = get_working_model()

SETTINGS_FILE = "coordinator_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

def process_file_for_ai(uploaded_file):
    if uploaded_file is not None:
        return {"mime_type": uploaded_file.type, "data": uploaded_file.getvalue()}
    return None

# --- 3. APP UI ---

# HEADER SECTION (Title + Logo)
col_header_1, col_header_2 = st.columns([4, 1], vertical_alignment="center")

with col_header_1:
    st.title("☀️ Solar Interconnection Assistant")

with col_header_2:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.write("") 

tab1, tab2 = st.tabs(["🚀 Application", "👤 Coordinator Settings"])

# --- TAB 2: SETTINGS ---
with tab2:
    st.header("Coordinator Profile")
    st.info("ℹ️ Enter your details here. We use a 'Form' to ensure everything saves correctly.")
    
    s = load_settings()
    
    with st.form("coordinator_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            c_name = st.text_input("Name", value=s.get("name", ""))
            c_comp = st.text_input("Company", value=s.get("company", ""))
            c_lic = st.text_input("License #", value=s.get("license", "C1556"))
            
        with col_b:
            c_email = st.text_input("Email", value=s.get("email", ""))
            c_phone = st.text_input("Phone", value=s.get("phone", ""))
            c_addr = st.text_input("Address", value=s.get("address", ""))
        
        submitted = st.form_submit_button("💾 Save Profile Settings")
        
        if submitted:
            new_settings = {
                "name": c_name, "company": c_comp, "license": c_lic,
                "email": c_email, "phone": c_phone, "address": c_addr
            }
            save_settings(new_settings)
            st.success("✅ Settings Saved Successfully!")

# --- TAB 1: APPLICATION ---
with tab1:
    col_left, col_right = st.columns([1, 1], vertical_alignment="top")
    
    with col_left:
        utility = st.selectbox("Select Utility", ["PGE", "Pac Power"])
        
        plan_set = st.file_uploader("Solar Plan Set (PDF)", type="pdf")
        contract = st.file_uploader("Signed Contract (PDF)", type="pdf")
        bill = st.file_uploader("Utility Bill", type=["pdf", "jpg", "jpeg", "png"])
        meter_img = st.file_uploader("Meter Photo (JPG)", type=["jpg", "jpeg"])

    with col_right:
        if st.button("🚀 Submit & Process Application"):
            if plan_set and contract and bill:
                if not active_model:
                    st.error("❌ API Connection Failed. Please check your API key.")
                else:
                    with st.spinner("AI analyzing documents..."):
                        st.session_state['file_buffers'] = {}
                        
                        ai_contract = process_file_for_ai(contract)
                        ai_plan = process_file_for_ai(plan_set)
                        ai_bill = process_file_for_ai(bill)

                        # --- MASTER PROMPTS ---
                        if utility == "Pac Power":
                            fields = """
                            Customer Name, Customer Mailing Address, Customer Email, Customer Phone, 
                            Site Address, Meter Number, Account Number (format: xxxxxxxx xxx x), 
                            Energy Source, Generation Technology, System Mounting Method,
                            Inverter Manufacturer, Inverter Model, Inverter Qty, Inverter Efficiency,
                            Panel Manufacturer, Panel Model, Panel Qty, Panel PTC Rating, 
                            Tilt, Azimuth, Tracking (Fixed/Single Axis),
                            System Rating (kW DC), Total System Export (kW), Inverter Rating (kW AC),
                            Installation Phasing (Single/3-Phase), Installation Voltage, 
                            Electrical Service Phasing, Electrical Service Voltage,
                            AC Disconnect Manufacturer, AC Disconnect Model, 
                            Disconnect Location (Manually operated/Lockable/Visible?), 
                            Planned Date of Operation
                            """
                        else: # PGE
                            fields = "Customer Name, Address, Account Number, Service Type, Main Service Amps, Nameplate Capacity (kW DC), Inverter Model, Panel Model"

                        prompt = f"Extract these specific fields for a {utility} application. Return a JSON object with keys matching the field names exactly. If a field is not found, return 'N/A' instead of omitting it: {fields}."
                        
                        try:
                            # 1. GENERATE AI CONTENT
                            response = active_model.generate_content([prompt, ai_contract, ai_plan, ai_bill])
                            json_text = response.text.replace('```json', '').replace('```', '').strip()
                            data = json.loads(json_text)

                            # 2. INJECT COORDINATOR INFO
                            coord_settings = load_settings()
                            
                            final_data = {
                                "Preparer Name": coord_settings.get("name", ""),
                                "Preparer Company": coord_settings.get("company", ""),
                                "Preparer Address": coord_settings.get("address", ""),
                                "Preparer Email": coord_settings.get("email", ""),
                                "Preparer Phone": coord_settings.get("phone", ""),
                                "Preparer License": coord_settings.get("license", "")
                            }
                            final_data.update(data)
                            
                            # 3. SAVE RESULTS
                            st.session_state['extraction_results'] = final_data
                            
                            # 4. ROBUST PDF PROCESSING
                            try:
                                plan_set.seek(0)
                                reader = PdfReader(plan_set)
                                num_pages = len(reader.pages)
                                
                                if num_pages >= 3:
                                    sp_w = PdfWriter(); sp_w.add_page(reader.pages[2])
                                    sp_io = io.BytesIO(); sp_w.write(sp_io)
                                    st.session_state['file_buffers']['site_plan'] = sp_io.getvalue()
                                else:
                                    st.session_state['file_buffers']['site_plan_error'] = f"PDF is too short ({num_pages} pages)"
                                
                                if num_pages >= 8:
                                    ol_w = PdfWriter(); ol_w.add_page(reader.pages[7])
                                    ol_io = io.BytesIO(); ol_w.write(ol_io)
                                    st.session_state['file_buffers']['one_line'] = ol_io.getvalue()
                                else:
                                    st.session_state['file_buffers']['one_line_error'] = f"PDF is too short ({num_pages} pages)"

                            except Exception as pdf_err:
                                st.warning(f"Could not split PDF: {pdf_err}")

                            # 5. CONVERT METER PHOTO
                            if meter_img:
                                try:
                                    img = Image.open(meter_img).convert("RGB")
                                    meter_pdf_io = io.BytesIO()
                                    img.save(meter_pdf_io, format="PDF")
                                    st.session_state['file_buffers']['meter_pdf'] = meter_pdf_io.getvalue()
                                except Exception as img_err:
                                    st.warning(f"Meter photo error: {img_err}")

                            st.success("Extraction Complete!")
                            
                        except Exception as e:
                            st.error(f"AI Processing Error: {e}")
            else:
                st.warning("Please upload all files.")

        # --- DISPLAY RESULTS ---
        if st.session_state['extraction_results']:
            st.divider()
            st.subheader("📋 Application Data")
            
            data = st.session_state['extraction_results']
            
            for i, (f, v) in enumerate(data.items()):
                c1, c2 = st.columns([3, 1])
                with c1: 
                    st.text_input(f, value=str(v), disabled=True, key=f"input_{i}")
                with c2: 
                    st_copy_button(text=str(v), before_copy_label="Copy", after_copy_label="Copied!", key=f"copy_{i}")
            
            # Downloads Section
            st.subheader("📥 Downloads")
            
            buffers = st.session_state['file_buffers']
            c_d1, c_d2, c_d3 = st.columns(3)
            
            with c_d1:
                if 'site_plan' in buffers:
                    st.download_button("Download Site Plan (Pg 3)", buffers['site_plan'], "SitePlan.pdf")
                elif 'site_plan_error' in buffers:
                    st.error(buffers['site_plan_error'])
                else:
                    st.info("No Site Plan generated")

            with c_d2:
                if 'one_line' in buffers:
                    st.download_button("Download One-Line (Pg 8)", buffers['one_line'], "OneLine.pdf")
                elif 'one_line_error' in buffers:
                    st.error(buffers['one_line_error'])
                else:
                    st.info("No One-Line generated")
                
            with c_d3:
                if 'meter_pdf' in buffers:
                    st.download_button("Download Meter Photo", buffers['meter_pdf'], "MeterPhoto.pdf")
                else:
                    st.info("No Meter Photo uploaded")


