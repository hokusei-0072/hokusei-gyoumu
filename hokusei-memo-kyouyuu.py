import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Streamlit secrets から認証情報を取得
service_account_info = st.secrets["google_cloud"]

# 認証オブジェクトを作成
creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://spreadsheets.google.com/feeds",
            'https://www.googleapis.com/auth/spreadsheets',
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"]
    )

#  gspread  クライアント作成
client = gspread.authorize(creds)

# スプレッドシートを開く（名前）
#sheet = client.open("memo_kyouyuu").sheet1
# スプレッドシートを開く（id）
sheet = client.open_by_key("1owRvyJDQj2Na_4ENEyJ7gooabtTzUM2GjqBcw-_HoqM").sheet1


############################################
day1 = str()
name = "入力してください"
m_name = "入力してください"
number = "入力してください"
day2 = str()
memo = "入力してください"

############################################
st.title("金型メモ共有アプリ")
st.text("型の改修内容や期限、出荷、トライ日程などメモ帳として使用してください")
st.text("記入日、記入者名、メーカー、工番等、期限や日程、内容の順に入力してください")
st.text("共有シートを開き、完了したものや取り消したいものはチェックをつけると取り消し線が入ります")
# スプレッドシートURLを表示
spreadsheet_url = "https://docs.google.com/spreadsheets/d/1owRvyJDQj2Na_4ENEyJ7gooabtTzUM2GjqBcw-_HoqM/edit?gid=1386834576#gid=1386834576"

st.markdown(f"[📄 共有シートを開く]({spreadsheet_url})", unsafe_allow_html=True)

day1 = st.date_input("記入日を選択してください")

name = st.text_input(
    "記入者名",placeholder="入力してください")

m_name = st.text_input(
    "メーカー",placeholder="入力してください")

number = st.text_input(
    "工番等",placeholder="入力してください")

day2 = st.date_input("日付を選択してください")

memo = st.text_input(
    "内容",placeholder="入力してください")

############ 送信ボタン################
submit_btn = st.button('送信')

if submit_btn:
    # B列を取得（1-index なので 2列目）
    b_values = sheet.col_values(2)  # B列全体

    target_row = None

    # 5行目以降で空白セルを探す
    for i in range(4, len(b_values)):
        if b_values[i].strip() == "":
            target_row = i + 1  # 実際の行番号に合わせて +1
            break

    # B列がすべて埋まっている場合は最後に追加
    if target_row is None:
        target_row = len(b_values) + 1

    # 書き込むデータ（B列〜G列＝6項目）
    row_data = [str(day1), name, m_name, number, str(day2), memo]

    # B列〜G列に書き込む（A列は無視）
    sheet.update(f"B{target_row}:G{target_row}", [row_data])

    st.success("送信しました！")
