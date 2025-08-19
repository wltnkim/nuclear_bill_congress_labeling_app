import streamlit as st
import pandas as pd
import gspread
import hashlib
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# --- FUNCTION DEFINITIONS ---

# Connects to Google Sheets using a local 'credentials.json' file.
def get_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open("Nuclear Bill Responses").sheet1
    return sheet

# Loads the bill summaries from a local CSV file and cleans up text encoding issues.
# @st.cache_data ensures this heavy operation runs only once.
@st.cache_data
def load_summaries():
    df = pd.read_csv("bill_summaries_text.csv", encoding_errors='ignore')
    replacements = {
        '¬¨‚Ä†': ' ', 'â€™': "'", 'â€œ': '"', 'â€': '"',
        'â€“': '-', 'â€”': '-', 'â€¦': '...', 'Â ': ' '
    }
    text_columns = ['Summary', 'formats', 'title']
    for col in text_columns:
        if col in df.columns:
            for garbled, clean in replacements.items():
                df[col] = df[col].str.replace(garbled, clean, regex=False)
    return df

# Fetches all existing summary hashes from Google Sheets to prevent duplicate work.
@st.cache_data
def load_existing_hashes(_sheet):
    records = _sheet.get_all_records()
    return set(r["summary_hash"] for r in records)

# Computes a single summary text from 'Summary' or 'formats' columns, handling empty values.
def compute_summary_text(row):
    s = row.get("Summary")
    if pd.isna(s) or str(s).strip() == "":
        s = row.get("formats", "")
    
    # If both columns are empty (NaN), return a true empty string instead of "nan".
    if pd.isna(s):
        return ""
        
    return str(s).strip()

# --- MAIN APP LOGIC ---
st.title("🗳️ Nuclear Bill Labeling App")

# Get user ID from the sidebar.
user_id = st.sidebar.text_input("👤 Enter your User ID (RA name):")
if not user_id:
    st.warning("Please enter your User ID to begin.")
    st.stop()

# Load and process data from local files and Google Sheets.
sheet = get_gsheet()
summaries = load_summaries()
existing_hashes = load_existing_hashes(sheet)

# Create a unique hash for each summary text to use as an ID.
texts = summaries.apply(compute_summary_text, axis=1)
summary_hashes = texts.map(lambda t: hashlib.md5(t.encode("utf-8")).hexdigest())
summaries["summary_text"] = texts
summaries["summary_hash"] = summary_hashes

# Filter out rows with empty summaries and those already labeled.
summaries.dropna(subset=['summary_text'], inplace=True)
summaries = summaries[summaries['summary_text'].str.strip() != '']
filtered = summaries[~summaries["summary_hash"].isin(existing_hashes)]

if filtered.empty:
    st.success("🎉 All summaries have been labeled by someone!")
    st.stop()

# Initialize session state to hold the current bill being labeled and user inputs.
if "current_row" not in st.session_state:
    st.session_state.current_row = filtered.sample(1).iloc[0]
if "is_nuclear" not in st.session_state:
    st.session_state.is_nuclear = "No"
if "certainty" not in st.session_state:
    st.session_state.certainty = 3
if "notes" not in st.session_state:
    st.session_state.notes = ""

# Get the current bill's data from session state.
row = st.session_state.current_row
summary_text = row["summary_text"]
summary_hash = row["summary_hash"]

# --- UI DISPLAY ---
# Display the information for the current bill.
st.markdown("### 🔢 Legislation Number")
st.write(row.get("legislation_number", "[Missing]"))
st.markdown("### 🏷️ Title")
st.write(row.get("title", "[Missing]"))
st.markdown("### 📄 Summary")
st.write(summary_text.replace('$', '\$')) # Escape '$' to prevent LaTeX rendering.

# --- USER INPUT FORM ---
# Create a form for user evaluation to prevent reruns on every widget interaction.
st.markdown("### 🧠 Your Evaluation")
with st.form(key="evaluation_form"):
    st.radio("Is this related to nuclear weapons?", ["No", "Yes"], key="is_nuclear")
    confidence_labels = {
        1: "1: Very Uncertain", 2: "2: Somewhat Uncertain", 3: "3: Moderately Confident",
        4: "4: Confident", 5: "5: Highly Certain"
    }
    st.select_slider(
        "How confident are you?",
        options=confidence_labels.keys(),
        format_func=lambda key: confidence_labels[key],
        key="certainty"
    )
    st.text_area("Explain your decision or highlight key elements:", key="notes")
    submitted = st.form_submit_button("✅ Submit")

# --- SUBMISSION LOGIC ---
# This block runs when the user clicks the "Submit" button.
if submitted:
    # Prepare the new row for Google Sheets.
    new_row = [
        row.get("legislation_number", "N/A"), user_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        1 if st.session_state.is_nuclear == "Yes" else 0,
        st.session_state.certainty, st.session_state.notes, summary_hash
    ]
    
    # Append the row and show a success message.
    with st.spinner("Saving response..."):
        sheet.append_row(new_row)
        st.success("✅ Response saved!")
        time.sleep(0.5)

    # Select the next bill to label.
    new_filtered = filtered[filtered["summary_hash"] != summary_hash]
    if new_filtered.empty:
        st.success("🎉 All summaries have been labeled!")
        st.stop()
    
    # Update session state with the new bill and reset input fields.
    st.session_state.current_row = new_filtered.sample(1).iloc[0]
    del st.session_state.is_nuclear
    del st.session_state.certainty
    del st.session_state.notes
    
    st.rerun()
