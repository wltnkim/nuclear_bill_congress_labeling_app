import streamlit as st
import pandas as pd
import time
from datetime import datetime
from collections import defaultdict
from sqlalchemy import text

# --- 1. [추가] Password Protection ---
# app_cloud.py에서 그대로 복사한 함수입니다.
# st.secrets는 .streamlit/secrets.toml 파일을 자동으로 읽습니다.
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        # .streamlit/secrets.toml 파일에서 APP_PASSWORD를 읽어옵니다.
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

# --- 2. [기존] Streamlit DB Connection ---
conn = st.connection("local_db", type="sql", url="sqlite:///main.db?mode=rwc", autocommit=True)

# --- 3. [기존] Function Definitions ---
@st.cache_data(ttl=3600) 
def load_all_bills():
    df = conn.query("SELECT * FROM bills", ttl=3600)
    df['unique_number'] = df['unique_number'].astype(str)
    df.dropna(subset=['summary_text'], inplace=True)
    df = df[df['summary_text'].str.strip() != '']
    return df

def load_existing_label_info():
    df_labels = conn.query("SELECT unique_number, user_id FROM labels", ttl=0)
    
    counts = defaultdict(int)
    user_map = defaultdict(set)

    if df_labels.empty:
        return {}, {}

    df_labels['unique_number'] = df_labels['unique_number'].astype(str)
    df_labels['user_id'] = df_labels['user_id'].astype(str)

    for _, row in df_labels.iterrows():
        uid_val_str = row['unique_number']
        counts[uid_val_str] += 1
        user_map[uid_val_str].add(row['user_id'])

    return dict(counts), dict((k, set(v)) for k, v in user_map.items())

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


# --- 4. [수정] Main App Execution (Password Check) ---
# 메인 앱 로직 전체를 check_password()로 감쌉니다.
if check_password():

    
    
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

    def lock_user_id():
        """Callback: 사용자가 ID를 입력하고 Enter를 누르면 ID를 잠급니다."""
        if st.session_state.user_id_input_key: 
            st.session_state.user_id = st.session_state.user_id_input_key
            st.session_state.user_id_locked = True
            # 사용자가 바뀌었으므로, 현재 법안을 삭제하여 새로 샘플링합니다.
            if "current_row" in st.session_state:
                del st.session_state["current_row"]

    # 세션 상태 초기화 (페이지 새로고침 시 항상 실행됨)
    if "user_id_locked" not in st.session_state:
        st.session_state.user_id_locked = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = ""

    # 1. ID가 "잠금" 상태일 때 (st.session_state에 기록된 경우)
    if st.session_state.user_id_locked and st.session_state.user_id:
        user_id = st.session_state.user_id
        # ID를 보여주되, 수정은 못하게 비활성화 (disabled=True)
        st.sidebar.text_input(
            "👤 User ID (Locked):",
            value=user_id,
            disabled=True,
            help="ID가 잠겼습니다. 변경하려면 페이지를 새로고침하세요."
        )
        
    # 2. ID가 "잠금" 상태가 아닐 때 (처음 접속 또는 새로고침 시)
    else:
        # ID를 입력받는 활성화된 입력창
        st.sidebar.text_input(
            "👤 Enter your User ID (RA name):",
            key="user_id_input_key",
            value=st.session_state.user_id, # 새로고침 시 입력 필드 비우기
            on_change=lock_user_id, # Enter 누르면 lock_user_id 콜백 실행
            help="ID를 입력하고 'Enter' 키를 누르거나 다른 곳을 클릭하세요."
        )
        st.warning("Please enter your User ID and press Enter to begin.")
        st.stop() # ID가 입력(잠금)될 때까지 앱의 나머지 부분 실행 중지

    summaries = load_all_bills()
    existing_counts, existing_user_map = load_existing_label_info()

    def get_filtered_pool(current_user_id, counts, user_map, all_summaries):
        def need_second_mask(uid):
            return (counts.get(uid, 0) == 1) and (str(current_user_id) not in user_map.get(uid, set()))
        def need_first_mask(uid):
            return (counts.get(uid, 0) == 0)

        need_second = all_summaries[all_summaries["unique_number"].map(need_second_mask)]
        need_first = all_summaries[all_summaries["unique_number"].map(need_first_mask)]
        
        return need_second if not need_second.empty else need_first

    filtered = get_filtered_pool(user_id, existing_counts, existing_user_map, summaries)

    if filtered.empty:
        st.success("🎉 All summaries have been labeled by someone or by you!")
        st.stop()

    if "current_row" not in st.session_state:
        st.session_state.current_row = filtered.sample(1).iloc[0]

    row = st.session_state.current_row
    summary_text = row["summary_text"]
    unique_id = str(row["unique_number"])

    st.markdown("### 🔢 Legislation Number")
    congress_info = format_congress(row.get("congress"))
    bill_number = row.get("legislation_number", "[Bill # Missing]")
    legislation_display = f"{congress_info}, {bill_number}"
    st.write(legislation_display)

    st.markdown("### 🏷️ Title")
    st.write(row.get("title", "[Missing]"))
    st.markdown("### 📄 Summary")
    st.write(summary_text.replace('$', '\$'))

    st.markdown("### 🧠 Your Evaluation")

    is_nuclear_key = f"is_nuclear_{unique_id}"
    certainty_key = f"certainty_{unique_id}"
    notes_key = f"notes_{unique_id}"

    with st.form(key=f"evaluation_form_{unique_id}"):
        st.radio(
            "1. Is *any element* of the bill relevant to nuclear weapons?", 
            ["No", "Yes"], 
            key=is_nuclear_key
        )
        confidence_labels = {1: "Very Uncertain", 2: "Somewhat Uncertain", 3: "Moderately Certain",
                             4: "Certain", 5: "Highly Certain"}
        st.select_slider(
            "2. Certainty Level:",
            options=confidence_labels.keys(),
            format_func=lambda key: confidence_labels[key],
            key=certainty_key,
            value=3
        )
        st.text_area("3. Notes (optional):", key=notes_key)
        submitted = st.form_submit_button("✅ Submit")


    # ✅ 수정된 핵심 부분: 제출 시 최신 상태 다시 확인하여 label_round = 3 방지
    if submitted:
        # 최신 DB 상태 다시 로드
        existing_counts, existing_user_map = load_existing_label_info()

        # 이미 2명의 라벨 완료 → 중단
        if existing_counts.get(unique_id, 0) >= 2:
            st.warning("⚠️ This bill already has 2 completed labels. Loading next bill...")
            del st.session_state["current_row"]
            st.rerun()

        # 사용자가 이미 라벨 → 중단
        if user_id in existing_user_map.get(unique_id, set()):
            st.warning("⚠️ You already labeled this bill. Loading next bill...")
            del st.session_state["current_row"]
            st.rerun()

        is_nuclear_val = st.session_state[is_nuclear_key]
        certainty_val = st.session_state[certainty_key]
        notes_val = st.session_state[notes_key]

        try:
            with conn.session as s:
                s.execute(
                    text("""
                    INSERT INTO labels (
                        legislation_display, user_id, timestamp, 
                        is_nuclear, certainty, notes, 
                        unique_number, label_round
                    ) VALUES (
                        :leg, :user, :time, :nuc, :cert, :notes, :uid,
                        (SELECT COUNT(*) FROM labels WHERE unique_number = :uid) + 1
                    )
                    """),
                    params={
                        "leg": legislation_display,
                        "user": user_id,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "nuc": 1 if is_nuclear_val == "Yes" else 0,
                        "cert": certainty_val,
                        "notes": notes_val,
                        "uid": unique_id
                    }
                )

            st.success("✅ Response saved!")
            time.sleep(0.5)

            existing_counts, existing_user_map = load_existing_label_info()
            next_pool = get_filtered_pool(user_id, existing_counts, existing_user_map, summaries)

            if next_pool.empty:
                st.success("🎉 All summaries have been labeled!")
                del st.session_state["current_row"]
                st.stop()

            st.session_state.current_row = next_pool.sample(1).iloc[0]
            st.rerun()

        except Exception as e:
            st.error(f"Could not save response. Error: {e}")
            st.error("Please try submitting again.")