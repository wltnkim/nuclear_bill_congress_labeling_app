import streamlit as st
import pandas as pd
import time
from sqlalchemy import text

st.set_page_config(layout="wide", page_title="Nuclear Bill Labeling App (Only Admin)")

# ---------------------------------------------------------
# 1. [Modified] Admin Password Check Function
# ---------------------------------------------------------
def check_admin_password():
    """
    Checks if the password matches 'ADMIN_PASSWORD' in secrets.toml.
    Returns True if correct, False otherwise (keeping the input field).
    """
    def password_entered():
        # Read ADMIN_PASSWORD from .streamlit/secrets.toml and compare
        if st.session_state["admin_password"] == st.secrets["ADMIN_PASSWORD"]:
            st.session_state["admin_password_correct"] = True
            del st.session_state["admin_password"] # Delete password from session for security
        else:
            st.session_state["admin_password_correct"] = False

    # 1) If password hasn't been entered yet
    if "admin_password_correct" not in st.session_state:
        st.text_input("Admin Password", type="password", on_change=password_entered, key="admin_password")
        st.info("🔒 Admin Access Only. Please enter the password.")
        return False
    
    # 2) If password was incorrect
    elif not st.session_state["admin_password_correct"]:
        st.text_input("Admin Password", type="password", on_change=password_entered, key="admin_password")
        st.error("😕 Incorrect password. Please try again.")
        return False
    
    # 3) If password is correct
    else:
        return True

# ---------------------------------------------------------
# 2. MySQL Connection Settings (Server: 127.0.0.1, Port 3307)
# ---------------------------------------------------------
db_user = "root"
db_password = "password"
db_host = "127.0.0.1"
db_port = "3307" # Port matched to your server setup
db_name = "labeling_app"

# Create SQLAlchemy connection engine
db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
# conn = st.connection("mysql_db", type="sql", url=db_url, autocommit=True)
conn = st.connection(
    "mysql_db",
    type="sql",
    url=db_url,
    autocommit=True,
    pool_pre_ping=True,
    pool_recycle=3600
)

# ---------------------------------------------------------
# 3. Main App Logic (Runs only if password check passes)
# ---------------------------------------------------------
if check_admin_password():  # <--- Function call

    st.title("📊 DB Data Management (Admin Only)")

    # (1) Refresh Button
    if st.button("🔄 Refresh Data"):
        st.rerun()

    # (2) Fetch labels table (Newest first)
    st.subheader("Submitted Label Data (Labels)")
    try:
        df_labels = conn.query("SELECT * FROM labels ORDER BY timestamp DESC", ttl=0)
        st.dataframe(df_labels, use_container_width=True)
        
        # --- [Added] Statistics Logic ---
        total = len(df_labels)
        if 'label_round' in df_labels.columns and not df_labels.empty:
            r1 = len(df_labels[df_labels['label_round'] == 1])
            r2 = len(df_labels[df_labels['label_round'] == 2])
            # r_others = total - r1 - r2
        else:
            r1 = 0
            r2 = 0

        # Display counts using metrics for better visibility
        st.write("### 📈 Statistics")
        c1, c2, c3 = st.columns(3)
        c1.metric(label="Total Labels", value=total)
        c2.metric(label="Round 1", value=r1)
        c3.metric(label="Round 2", value=r2)

        st.write("#### 👤 Labels by User (Top Contributors)")
        
        if 'user_id' in df_labels.columns and not df_labels.empty:
            user_counts = df_labels['user_id'].value_counts().reset_index()
            user_counts.columns = ['User ID', 'Count']
            
            uc_col1, uc_col2 = st.columns([1, 2])
            
            with uc_col1:
                st.dataframe(user_counts, use_container_width=True, hide_index=True)
            
            with uc_col2:
                st.bar_chart(user_counts.set_index('User ID'))
        else:
            st.info("user_id information is not available yet.")
        
    except Exception as e:
        st.error(f"Error loading data: {e}")

    st.divider()

    # (3) Delete Data Functionality
    st.subheader("🗑️ Delete Data")
    st.warning("⚠️ Warning: This action cannot be undone. Please verify the 'id' number in the table above before deleting.")

    col1, col2 = st.columns([1, 3])

    with col1:
        with st.form("delete_form"):
            id_to_delete = st.number_input("ID to delete (from 'id' column)", min_value=1, step=1, value=None, placeholder="Ex: 5")
            submit_delete = st.form_submit_button("🚨 Delete this ID")

        if submit_delete and id_to_delete:
            try:
                with conn.session as s:
                    # First, check if the data exists
                    check_sql = text("SELECT COUNT(*) FROM labels WHERE id = :id")
                    exists = s.execute(check_sql, {"id": id_to_delete}).scalar()

                    if exists:
                        # Execute deletion
                        delete_sql = text("DELETE FROM labels WHERE id = :id")
                        s.execute(delete_sql, {"id": id_to_delete})
                        s.commit()
                        st.success(f"✅ Data with ID {id_to_delete} has been deleted.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ ID {id_to_delete} not found.")
            except Exception as e:
                st.error(f"Error during deletion: {e}")
