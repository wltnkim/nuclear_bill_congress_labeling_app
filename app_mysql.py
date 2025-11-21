import streamlit as st
import pandas as pd
import time
from datetime import datetime
from collections import defaultdict
from sqlalchemy import text

st.set_page_config(layout="wide", page_title="Nuclear Bill Labeling App")

# --- 1. [설정] Password Protection ---
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

# --- 2. [수정] MySQL Database Connection ---
db_user = "root"
db_password = "password"
db_host = "localhost"
db_port = "3307"
db_name = "labeling_app"

db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
conn = st.connection("mysql_db", type="sql", url=db_url, autocommit=True)


# --- 3. Function Definitions ---
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


# --- 4. Main App Execution ---
if check_password():
    
    st.title("🗳️ Nuclear Bill Labeling App")
    st.info(
        """
        **Your task in this project is to identify congressional bills that may have been relevant to nuclear weapons.** The bill summaries each contain one or more elements (each sentence or paragraph), each of which relates to one or more provisions of the summarized bill. Bills count as “relevant to nuclear weapons” if they contain 
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
        if st.session_state.user_id_input_key: 
            st.session_state.user_id = st.session_state.user_id_input_key
            st.session_state.user_id_locked = True
            if "current_row" in st.session_state:
                del st.session_state["current_row"]

    if "user_id_locked" not in st.session_state:
        st.session_state.user_id_locked = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = ""

    if st.session_state.user_id_locked and st.session_state.user_id:
        user_id = st.session_state.user_id
        st.sidebar.text_input(
            "👤 User ID (Locked):",
            value=user_id,
            disabled=True,
            help="Please refresh to change User ID."
        )
    else:
        st.sidebar.text_input(
            "👤 Enter your User ID (RA name):",
            key="user_id_input_key",
            value=st.session_state.user_id,
            on_change=lock_user_id,
            help="Type ID and press Enter."
        )
        st.warning("Please enter your User ID and press Enter to begin.")
        st.stop()

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


    if submitted:
        existing_counts, existing_user_map = load_existing_label_info()

        if existing_counts.get(unique_id, 0) >= 2:
            st.warning("⚠️ This bill already has 2 completed labels. Loading next bill...")
            del st.session_state["current_row"]
            st.rerun()

        if user_id in existing_user_map.get(unique_id, set()):
            st.warning("⚠️ You already labeled this bill. Loading next bill...")
            del st.session_state["current_row"]
            st.rerun()

        is_nuclear_val = st.session_state[is_nuclear_key]
        certainty_val = st.session_state[certainty_key]
        notes_val = st.session_state[notes_key]

        try:
            # MySQL 호환성 수정: INSERT 문 안의 서브쿼리 제거 및 로직 분리
            with conn.session as s:
                # 1. 먼저 현재 몇 번째 라벨인지 확인 (SELECT)
                count_sql = text("SELECT COUNT(*) FROM labels WHERE unique_number = :uid")
                current_count = s.execute(count_sql, {"uid": unique_id}).scalar()
                
                next_round = current_count + 1

                # 2. 계산된 값으로 INSERT 수행
                insert_sql = text("""
                    INSERT INTO labels (
                        legislation_display, user_id, timestamp, 
                        is_nuclear, certainty, notes, 
                        unique_number, label_round
                    ) VALUES (
                        :leg, :user, :time, :nuc, :cert, :notes, :uid, :lbl_round
                    )
                """)
                
                s.execute(
                    insert_sql,
                    params={
                        "leg": legislation_display,
                        "user": user_id,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "nuc": 1 if is_nuclear_val == "Yes" else 0,
                        "cert": certainty_val,
                        "notes": notes_val,
                        "uid": unique_id,
                        "lbl_round": next_round
                    }
                )
                s.commit()

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
