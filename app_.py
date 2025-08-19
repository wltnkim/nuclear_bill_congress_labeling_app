import streamlit as st

# --- 비밀번호 확인 기능 ---
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

# --- 여기까지 비밀번호 기능 ---


# 비밀번호가 맞는지 확인하고, 맞을 경우에만 전체 앱을 실행합니다.
if check_password():
    # --- 라이브러리 임포트 ---
    import pandas as pd
    import gspread
    import hashlib
    import time
    import gdown
    from datetime import datetime
    from oauth2client.service_account import ServiceAccountCredentials

    # --- 함수 정의 ---
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

    # --- 메인 앱 로직 ---
    st.title("🗳️ Nuclear Bill Labeling App")
    
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

    st.markdown("### 🔢 Legislation Number")
    st.write(row.get("legislation_number", "[Missing]"))
    st.markdown("### 🏷️ Title")
    st.write(row.get("title", "[Missing]"))
    st.markdown("### 📄 Summary")
    st.write(summary_text.replace('$', '\$'))

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

    if submitted:
        new_row = [
            row.get("legislation_number", "N/A"), user_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            1 if st.session_state.is_nuclear == "Yes" else 0,
            st.session_state.certainty, st.session_state.notes, summary_hash
        ]
        with st.spinner("Saving response..."):
            sheet.append_row(new_row)
            st.success("✅ Response saved!")
            time.sleep(0.5)

        new_filtered = filtered[filtered["summary_hash"] != summary_hash]
        if new_filtered.empty:
            st.success("🎉 All summaries have been labeled!")
            st.stop()
        
        st.session_state.current_row = new_filtered.sample(1).iloc[0]
        if "is_nuclear" in st.session_state: del st.session_state.is_nuclear
        if "certainty" in st.session_state: del st.session_state.certainty
        if "notes" in st.session_state: del st.session_state.notes
        
        st.rerun()