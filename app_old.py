import streamlit as st
import pandas as pd
import gspread
import hashlib
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ---------- Google Sheets 연결 ----------
def get_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open("Nuclear Bill Responses").sheet1
    return sheet

# ---------- CSV 로딩 ----------
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

# ---------- 모든 사용자 응답 해시 불러오기 ----------
@st.cache_data
def load_existing_hashes(_sheet):
    records = _sheet.get_all_records()
    return set(r["summary_hash"] for r in records)

# --- 이 부분이 수정되었습니다 ---
# summary 또는 formats 기반 텍스트 추출 (NaN -> "nan" 변환 방지)
def compute_summary_text(row):
    s = row.get("Summary")
    if pd.isna(s) or str(s).strip() == "":
        s = row.get("formats", "")
    
    # 두 열이 모두 비어있는(NaN) 경우, "nan" 텍스트 대신 진짜 빈 문자열을 반환합니다.
    if pd.isna(s):
        return ""
        
    return str(s).strip()
# --- 여기까지 수정되었습니다 ---

# ---------- 앱 시작 ----------
st.title("🗳️ Nuclear Bill Labeling App")

# ---------- 사용자 ID 입력 ----------
user_id = st.sidebar.text_input("👤 Enter your User ID (RA name):")
if not user_id:
    st.warning("Please enter your User ID to begin.")
    st.stop()

# ---------- 데이터 로딩 ----------
sheet = get_gsheet()
summaries = load_summaries()
existing_hashes = load_existing_hashes(sheet)

# ---------- 해시 계산
texts = summaries.apply(compute_summary_text, axis=1)
summary_hashes = texts.map(lambda t: hashlib.md5(t.encode("utf-8")).hexdigest())
summaries["summary_text"] = texts
summaries["summary_hash"] = summary_hashes

# 요약 텍스트가 비어있는 항목들을 미리 목록에서 제외합니다.
# (이제 compute_summary_text가 ""를 반환하므로 이 로직이 정상 작동합니다)
summaries.dropna(subset=['summary_text'], inplace=True)
summaries = summaries[summaries['summary_text'].str.strip() != '']

# ---------- 중복 제거
filtered = summaries[~summaries["summary_hash"].isin(existing_hashes)]
if filtered.empty:
    st.success("🎉 All summaries have been labeled by someone!")
    st.stop()

# ---------- 상태 초기화
if "current_row" not in st.session_state:
    st.session_state.current_row = filtered.sample(1).iloc[0]
if "is_nuclear" not in st.session_state:
    st.session_state.is_nuclear = "No"
if "certainty" not in st.session_state:
    st.session_state.certainty = 3
if "notes" not in st.session_state:
    st.session_state.notes = ""

# ---------- 현재 row 정보
row = st.session_state.current_row
summary_text = row["summary_text"]
summary_hash = row["summary_hash"]

# ---------- 정보 출력 ----------
st.markdown("### 🔢 Legislation Number")
st.write(row.get("legislation_number", "[Missing]"))
st.markdown("### 🏷️ Title")
st.write(row.get("title", "[Missing]"))
st.markdown("### 📄 Summary")
st.write(summary_text.replace('$', '\$'))

# ---------- 평가 입력 (st.form 사용) ----------
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

# ---------- 제출 ----------
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
    del st.session_state.is_nuclear
    del st.session_state.certainty
    del st.session_state.notes
    st.rerun()