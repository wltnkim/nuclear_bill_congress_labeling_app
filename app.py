import streamlit as st

# --- PASSWORD PROTECTION ---
# This section defines a function to check for a password stored in Streamlit's secrets.
# It prevents unauthorized access to the app.
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password.
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.write("Please enter the password to access the labeling app.")
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True

# --- MAIN APP EXECUTION ---
# The entire app runs only if the password check is successful.
if check_password():
    # --- LIBRARY IMPORTS ---
    # Import necessary libraries after the password check for better performance.
    import pandas as pd
    import gspread
    import hashlib
    import time
    import gdown
    from datetime import datetime
    from oauth2client.service_account import ServiceAccountCredentials

    # --- FUNCTION DEFINITIONS ---

    # Connects to Google Sheets using credentials from Streamlit Secrets.
    def get_gsheet():
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Nuclear Bill Responses").sheet1
        return sheet

    # Downloads the large CSV file from Google Drive and cleans up text encoding issues.
    # @st.cache_data ensures this heavy operation runs only once.
    @st.cache_data
    def load_summaries():
        file_id = "1MKfanVsAriHRoaKXQSKcW5W04rF6VPGV"
        file_url = f'https://drive.google.com/uc?id={file_id}'
        output_path = "bill_summaries_text.csv"
        with st.spinner("Downloading data file... (200MB, may take a moment)"):
            gdown.download(file_url, output_path, quiet=False)
        df = pd.read_csv(output_path, encoding_errors='ignore')
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

    # Load and process data.
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

    # Initialize session state to hold the current bill being labeled.
    if "current_row" not in st.session_state:
        st.session_state.current_row = filtered.sample(1).iloc[0]
    
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
        st.radio("1. Is any element of the bill summary displayed above likely to be relevant to nuclear weapons?", ["No", "Yes"], key="is_nuclear")
        confidence_labels = {
            1: "1: Very Uncertain", 2: "2: Somewhat Uncertain", 3: "3: Moderately Certain",
            4: "4: Certain", 5: "5: Highly Certain"
        }
        st.select_slider(
            "2. How certain are you in your response to the previous question?",
            options=confidence_labels.keys(),
            format_func=lambda key: confidence_labels[key],
            key="certainty"
        )
        st.text_area("Please explain your response to the previous questions, in one or two sentences (three at most). Feel free to copy-paste language from the summary itself if it’d be helpful, or just explain your reasoning.", key="notes")
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
        if "is_nuclear" in st.session_state: del st.session_state.is_nuclear
        if "certainty" in st.session_state: del st.session_state.certainty
        if "notes" in st.session_state: del st.session_state.notes
        
        st.rerun()