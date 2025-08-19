# --- Secrets 디버깅을 위한 임시 코드 ---
import streamlit as st

st.title("Secrets Debugging Tool 🕵️‍♂️")

st.write("Streamlit 앱이 현재 인식하고 있는 Secrets 목록입니다.")
st.write("---")

# st.secrets에 어떤 키(key)들이 있는지 직접 출력해 봅니다.
try:
    st.write("#### 발견된 Secret Keys:")
    st.write(st.secrets.keys())
except Exception as e:
    st.error(f"Secrets를 읽는 중 에러 발생: {e}")

st.write("---")
st.write("#### 필수 키 확인:")

# 'APP_PASSWORD' 키가 있는지 확인
if "APP_PASSWORD" in st.secrets:
    st.success("✅ 'APP_PASSWORD' 키를 찾았습니다!")
else:
    st.error("❌ 'APP_PASSWORD' 키를 찾지 못했습니다. Streamlit Cloud의 Secrets 설정을 다시 확인해주세요.")

# 'gcp_service_account' 키가 있는지 확인
if "gcp_service_account" in st.secrets:
    st.success("✅ 'gcp_service_account' 키를 찾았습니다!")
else:
    st.error("❌ 'gcp_service_account' 키를 찾지 못했습니다.")