# hokusei-siage-nippo.py
# 2025/10/15 協豊追加 / 起動ハング対策＋スマホ入力改善（時間は空欄＋寛容パース／チップ無し）

import socket
socket.setdefaulttimeout(10)

import re, unicodedata
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# === ユーティリティ（時間の寛容パース） ===
def parse_hours_maybe(s: str) -> float:
    if not s:
        return 0.0
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("，", ".").replace("、", ".").replace("．", ".")
    s = re.sub(r"(時間|h|ｈ)", "", s, flags=re.IGNORECASE)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0

# === 認証 ===
GOOGLE_SHEET_ID = "1MXSg8qP_eT7lVczYpNB66sZGZP2NlWHIGz9jAWKH7Ss"
SHEET_NAME = None

def _normalized_service_account_info():
    info = dict(st.secrets["google_cloud"])
    if "private_key" in info and "\\n" in info["private_key"]:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info

@st.cache_resource(show_spinner=False)
def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(_normalized_service_account_info(), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    return sh.worksheet(SHEET_NAME) if SHEET_NAME else sh.sheet1

# === UI ===
st.title('北青 仕上げ課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

with st.expander("リリースノート（2025/10/15更新）", expanded=False):
    st.markdown(
        "- メーカー名に **協豊** を追加\n"
        "- 一度に送信できる作業を **10件** に増加\n"
        "- メーカーに **東海鉄工所** を追加\n"
        "- 起動ハング対策（外部接続の遅延実行・タイムアウト）\n"
        "- **スマホ入力改善：時間は空欄スタート＋全角/単位OK**"
    )

st.text(
    "●パネル取りやトライで複数工番を同時に作業した場合は、作業内容「パネル」「トライ」を選択し、\n"
    "  １工程目の工番(ブランクやドローの工番)を入力してください。"
)
st.text(
    "●複数の工番をまとめて(例 51A001～51A005)入力すると集計に不具合が出るので、\n"
    "  １工程ずつ日報を入力してください。"
)
st.text(
    "●工番に関わる仕事以外の場合はメーカー名で「雑務」を選択し、\n"
    "  工番欄に作業の内容(例: 工場内清掃)を入力してください。"
)

day = st.date_input("日付を選択してください", value=date.today())
name = st.selectbox(
    '名前',
    ('選択してください', '吉田', "中村", "渡辺", "福田", "苫米地", "矢部", "小野",
     "塩入", "トム", "ユン", "ティエン", "チョン", "アイン", "ナム")
)

if name != '選択してください':
    if "form_count" not in st.session_state:
        st.session_state.form_count = 1

    def create_input_fields(index: int):
        st.markdown(f"---\n### 作業 {index}")

        customer = st.selectbox(
            f'メーカー{index}',
            ('選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ', '浜岳', '三池', '東プレ', '協豊',
             '千代田', '東海鉄工所', '雑務', 'その他メーカー'),
            key=f'customer_{index}'
        )

        new_customer = ''
        if customer == 'その他メーカー':
            new_customer = st.text_input(
                f'メーカー名を入力{index}',
                key=f'new_customer_{index}',
                placeholder="メーカー名を入力"
            )

        if customer not in ('選択してください', '雑務'):
            genre = st.selectbox(
                f'作業内容{index}',
                ('選択してください', '新規', '玉成', '設変', 'パネル', 'トライ', 'その他'),
                key=f'genre_{index}'
            )
        else:
            genre = ''  # 雑務なら空欄

        number = (
            st.text_input(f'工番を入力{index}', key=f'number_{index}', placeholder="例: 51A111")
            .upper()
            if genre != '選択してください' else ''
        )

        # 時間：空欄スタート（テキスト＋寛容パース）
        time_key = f'time_{index}'
        time_text = st.text_input(
            f'時間を入力{index}',
            key=time_key,
            placeholder="例: 1.5（１．５ / 1,5 / 1.5h / 1.5時間 もOK）"
        )
        hours = parse_hours_maybe(time_text)
        if time_text and hours == 0.0:
            st.info(f"時間{index}は数値で入力してください（1.5 / １．５ / 1,5 / 1.5h などOK）")

        return {
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "number": number,
            "time": hours
        }

    inputs = [create_input_fields(i) for i in range(1, st.session_state.form_count + 1)]

    if st.session_state.form_count < 10 and st.button("次へ"):
        st.session_state.form_count += 1
        st.rerun()

    valid_inputs = []
    total_time = 0.0
    for inp in inputs:
        if (
            inp["customer"] != "選択してください"
            and inp["genre"] != "選択してください"
            and inp["number"] != ''
            and inp["time"] > 0
        ):
            total_time += inp["time"]
            valid_inputs.append(inp)

    if total_time > 0:
        st.markdown(f"### ✅ 合計時間: {total_time:.2f} 時間")

    if valid_inputs and st.button("送信"):
        try:
            sheet = get_sheet()
            rows_to_append = []
            for idx, inp in enumerate(valid_inputs, start=1):
                is_last = (idx == len(valid_inputs))
                row = [
                    str(day),
                    name,
                    inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                    "" if inp["customer"] == "雑務" else inp["genre"],
                    inp["number"],
                    inp["time"],
                    f"合計 {total_time:.2f} 時間" if is_last else ""
                ]
                rows_to_append.append(row)

            sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
            st.session_state.form_count = 1

        except Exception as e:
            st.error(f"送信に失敗しました: {e}")
            st.info(
                "• Secrets の private_key の改行（\\n）が消えていないか\n"
                "• ネットワーク疎通\n"
                "• ライブラリのバージョン\n"
                "を確認してください。"
            )

# 依存関係メモ：
# pip install streamlit gspread google-auth
