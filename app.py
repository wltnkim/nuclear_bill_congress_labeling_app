import streamlit as st

# --- Password Protection ---
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.write("Please enter the password to access the labeling app.")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False
    else:
        return True

# --- Main App Execution ---
if check_password():
    # --- Library Imports ---
    import pandas as pd
    import gspread
    import hashlib
    import time
    import gdown
    from datetime import datetime
    from oauth2client.service_account import ServiceAccountCredentials

    # --- Function Definitions ---
    def get_gsheet():
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Nuclear Bill Responses").sheet1
        return sheet

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

    @st.cache_data
    def load_existing_hashes(_sheet):
        records = _sheet.get_all_records()
        return set(r["summary_hash"] for r in records)

    def compute_summary_text(row):
        s = row.get("Summary")
        if pd.isna(s) or str(s).strip() == "":
            s = row.get("formats", "")
        if pd.isna(s):
            return ""
        return str(s).strip()

    def format_congress(congress_number):
        if pd.isna(congress_number):
            return "[Congress # Missing]"
        try:
            num = int(congress_number)
            if 11 <= (num % 100) <= 13:
                suffix = 'th'
            else:
                suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(num % 10, 'th')
            return f"{num}{suffix} Congress"
        except (ValueError, TypeError):
            return str(congress_number)

    # --- Main App Logic ---
    st.title("🗳️ Nuclear Bill Labeling App")
    
    st.info(
        """
        **Your task in this project is to identify congressional bills that may have been relevant to nuclear weapons.** The bill summaries each contain one or more elements (each sentence or paragraph), each of which relates to 
        one or more provisions of the summarized bill. Bills count as “relevant to nuclear weapons” if they contain 
        *any* elements that would be related to nuclear weapons, even if the bill also touches on lots of other subjects. 
        **To reiterate: if *any element* is relevant, count the whole bill as relevant.**

        Bill elements may be related to nuclear weapons for lots of different possible reasons. Examples include: 
        research and development of nuclear weapons; manufacture of nuclear weapons; siting (e.g., at military bases) 
        or platform for deployment (e.g., submarines); command and control; international agreements or limitations 
        on their use (e.g., arms control agreements); responses to the actions of other countries; the United States’s 
        own nuclear posture (e.g., “no first use”); nuclear negotiations; nuclear triad; and many others. 

        As you consider the summary, think broadly and creatively and ask yourself: would making this bill provision 
        the law of the land affect any policy pertaining to nuclear weapons? If so, it’s probably relevant for our purposes.
        """
    )

    user_id = st.sidebar.text_input("👤 Enter your User ID (RA name):")
    if not user_id:
        st.warning("Please enter your User ID to begin.")
        st.stop()

    sheet = get_gsheet()
    summaries = load_summaries()
    existing_hashes = load_existing_hashes(sheet)

    texts = summaries.apply(compute_summary_text, axis=1)
    summary_hashes = texts.map(lambda t: hashlib.md5(t.encode("utf-8")).hexdigest())
    summaries["summary_text"] = texts
    summaries["summary_hash"] = summary_hashes

    summaries.dropna(subset=['summary_text'], inplace=True)
    summaries = summaries[summaries['summary_text'].str.strip() != '']

    filtered = summaries[~summaries["summary_hash"].isin(existing_hashes)]
    if filtered.empty:
        st.success("🎉 All summaries have been labeled by someone!")
        st.stop()

    if "current_row" not in st.session_state:
        st.session_state.current_row = filtered.sample(1).iloc[0]
    
    row = st.session_state.current_row
    summary_text = row["summary_text"]
    summary_hash = row["summary_hash"]

    # --- UI Display ---
    st.markdown("### 🔢 Legislation Number")
    congress_info = format_congress(row.get("congress"))
    bill_number = row.get("legislation_number", "[Bill # Missing]")
    legislation_display = f"{congress_info}, {bill_number}"
    st.write(legislation_display)

    st.markdown("### 🏷️ Title")
    st.write(row.get("title", "[Missing]"))
    st.markdown("### 📄 Summary")
    st.write(summary_text.replace('$', '\$'))

    # --- User Input Form ---
    st.markdown("### 🧠 Your Evaluation")

    # Ensure widget keys exist with sensible defaults so we can reliably reset them after submit
    if "is_nuclear" not in st.session_state:
        st.session_state.is_nuclear = "No"
    if "certainty" not in st.session_state:
        st.session_state.certainty = 3
    if "notes" not in st.session_state:
        st.session_state.notes = ""

    # --- Form UI ---
    with st.form(key="evaluation_form"):
        # --- THIS PART IS FIXED ---
        # Added backslash \ to escape the markdown numbered list formatting.
        st.radio(
            "1\. Is *any element* of the bill summary displayed above likely to be relevant to nuclear weapons?", 
            ["No", "Yes"], 
            key="is_nuclear"
        )
        
        confidence_labels = {
            1: "1: Very Uncertain", 
            2: "2: Somewhat Uncertain", 
            3: "3: Moderately Certain",
            4: "4: Certain", 
            5: "5: Highly Certain"
        }
        st.select_slider(
            "2\. How certain are you in your response to the previous question?",
            options=list(confidence_labels.keys()),
            format_func=lambda key: confidence_labels[key],
            key="certainty"
        )
        
        st.text_area(
            "3\. Please explain your response to the previous questions, in one or two sentences (three at most). "
            "Feel free to copy-paste language from the summary itself if it’d be helpful, or just explain your reasoning.", 
            key="notes"
        )
        # --- END OF FIX ---
        submitted = st.form_submit_button("✅ Submit")

    # Handle submission (runs in the main script after the form is submitted)
    if submitted:
        new_row = [
            legislation_display, user_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            1 if st.session_state.get("is_nuclear") == "Yes" else 0,
            st.session_state.get("certainty"), st.session_state.get("notes", ""), summary_hash
        ]
        with st.spinner("Saving response..."):
            sheet.append_row(new_row)
            st.success("✅ Response saved!")
            time.sleep(0.5)

        new_filtered = filtered[filtered["summary_hash"] != summary_hash]
        if new_filtered.empty:
            st.success("🎉 All summaries have been labeled!")
            st.stop()

        # advance to a new random summary
        st.session_state.current_row = new_filtered.sample(1).iloc[0]

        # clear the form widget state so next form appears blank/default
        st.session_state.pop("is_nuclear", None)
        st.session_state.pop("certainty", None)
        st.session_state.pop("notes", None)