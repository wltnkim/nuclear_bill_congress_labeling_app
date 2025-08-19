import streamlit as st
import pandas as pd
import gspread
import hashlib
import time
import gdown  # Google Drive 다운로드를 위한 라이브러리
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ---------- Google Sheets 연결 (Streamlit Secrets 사용) ----------
# 이 함수는 Streamlit Cloud의 Secrets에서 인증 정보를 읽어옵니다.
def get_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("Nuclear Bill Responses").sheet1
    return sheet

# ---------- CSV 로딩 (Google Drive에서 다운로드) ----------
# 이 함수는 앱이 처음 실행될 때 Google Drive에서 대용량 CSV 파일을 다운로드합니다.
@st.cache_data
def load_summaries():
    # 사용자님이 제공한 Google Drive 링크의 파일 ID를 사용합니다.
    file_id = "1MKfanVsAriHRoaKXQSKcW5W04rF6VPGV"
    file_url = f'https://drive.google.com/uc?id={file_id}'
    output_path = "bill_summaries_text.csv"

    # st.cache_data 덕분에 이 다운로드는 앱이 처음 로딩될 때 딱 한 번만 실행됩니다.
    with st.spinner("Downloading data file... (200MB, may take a moment)"):
        gdown.download(file_url, output_path, quiet=False)

    # 다운로드한 파일을 Pandas로 읽습니다.
    df = pd.read_csv(output_path, encoding_errors='ignore')

    # 기존의 텍스트 클리닝 로직을 그대로 적용합니다.
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

# summary 또는 formats 기반 텍스트 추출 (NaN -> "nan" 변환 방지)
def compute_summary_text(row):
    s = row.get("Summary")
    if pd.isna(s) or str(s).strip() == "":
        s = row.get("formats", "")
    
    if pd.isna(s):
        return ""
        
    return str(s).strip()

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