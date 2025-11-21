import pandas as pd
from sqlalchemy import create_engine, text, types
import pymysql

# ---------------------------------------------------------
# [설정] MySQL 접속 정보
# ---------------------------------------------------------
DB_CONFIG = {
    "user": "root",
    "password": "password", 
    "host": "localhost",
    "port": "3307",
    "database": "labeling_app"
}

print("Starting database initialization for MySQL...")

# 1. CSV 로드 및 전처리
output_path = "bill_summaries_text.csv"
try:
    df = pd.read_csv(output_path, encoding_errors='ignore', dtype={'unique_number': str})
except ValueError:
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

if 'unique_number' not in df.columns:
    print("ERROR: 'unique_number' column not in CSV.")
    exit()

# unique_number 빈 값 제거
df = df.dropna(subset=['unique_number'])

# 2. MySQL 연결
db_url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"

try:
    engine = create_engine(db_url)
    conn = engine.connect()
    print(f"Connected to MySQL database '{DB_CONFIG['database']}'.")
except Exception as e:
    print(f"Connection Failed: {e}")
    exit()

# 3. [초기화] 기존 테이블 삭제 (labels 먼저 삭제해야 함)
print("Cleaning up old tables...")
with engine.begin() as connection:
    connection.execute(text("DROP TABLE IF EXISTS labels;"))
    connection.execute(text("DROP TABLE IF EXISTS bills;"))

# 4. [테이블 1] 'bills' 테이블 생성
print("Creating 'bills' table...")

def compute_summary_text(row):
    s = row.get("Summary")
    if pd.isna(s) or str(s).strip() == "":
        s = row.get("formats", "")
    if pd.isna(s):
        return ""
    return str(s).strip()

df["summary_text"] = df.apply(compute_summary_text, axis=1)
df = df.set_index('unique_number')

# to_sql용 타입 지정
dtype_dict = {
    'unique_number': types.VARCHAR(100),
    'summary_text': types.TEXT,
}

# 데이터 삽입
df.to_sql('bills', engine, if_exists='replace', index=True, dtype=dtype_dict)

# [핵심 수정 1] bills 테이블의 unique_number 설정을 강제로 지정 (Charset + Collation)
print("Setting Primary Key and Collation on 'bills'...")
with engine.begin() as connection:
    # 여기서 COLLATE utf8mb4_unicode_ci를 명시해서 확실하게 맞춥니다.
    connection.execute(text(
        "ALTER TABLE bills MODIFY unique_number VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL;"
    ))
    connection.execute(text("ALTER TABLE bills ADD PRIMARY KEY (unique_number);"))

print("'bills' table created and PK set.")

# 5. [테이블 2] 'labels' 테이블 생성
print("Creating 'labels' table...")

# [핵심 수정 2] labels 테이블의 unique_number도 똑같이 COLLATE utf8mb4_unicode_ci로 지정
create_labels_sql = """
CREATE TABLE IF NOT EXISTS labels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    legislation_display TEXT,
    user_id VARCHAR(255),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_nuclear TINYINT(1),
    certainty INT,
    notes TEXT,
    unique_number VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, 
    label_round INT,
    FOREIGN KEY (unique_number) REFERENCES bills (unique_number) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

with engine.begin() as connection:
    connection.execute(text(create_labels_sql))

print("'labels' table created.")
conn.close()
print("Database initialization complete. You can now run the app.")
