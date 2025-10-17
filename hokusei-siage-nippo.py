# hokusei-siage-nippo.py
# 2025/10/15 協豊追加 / 起動ハング対策版

import socket
socket.setdefaulttimeout(10)  # 外部I/Oの無限待ちを根絶

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# =========================
# 認証まわり
# =========================
# st.secrets["google_cloud"] はサービスアカウントJSONをそのまま入れてください
# 例）.streamlit/secrets.toml:
# [google_cloud]
# type = "service_account"
# project_id = "..."
# private_key_id = "..."
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "..."
# client_id = "..."
# auth_uri = "https://accounts.google.com/o/oauth2/auth"
# token_uri = "https://oauth2.googleapis.com/token"
# auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
# client_x509_cert_url = "..."
# universe_domain = "googleapis.com"
#
# ※ private_key の改行は \n を含む文字列で格納（よく消えます）

GOOGLE_SHEET_ID = "1MXSg8qP_eT7lVczYpNB66sZGZP2NlWHIGz9jAWKH7Ss"
SHEET_NAME = None  # None=sheet1 を使用。指定するなら "main" など。

def _normalized_service_account_info():
    info = dict(st.secrets["google_cloud"])
    # 改行が消えていた場合の救済
    if "private_key" in info and "\\n" in info["private_key"]:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info

@st.cache_resource(show_spinner=False)
def get_sheet():
    """遅延接続 & 共有: アプリ全体で1回だけ接続し、再利用"""
    service_account_info = _normalized_service_account_info()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    return sh.worksheet(SHEET_NAME) if SHEET_NAME else sh.sheet1


# =========================
# UI
# =========================
st.title('北青 仕上げ課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

# リリースノート
with st.expander("リリースノート（2025/10/15更新）", expanded=False):
    st.markdown(
        "- メーカー名に **協豊** を追加\n"
        "- 一度に送信できる作業を **10件** までに増加\n"
        "- メーカーに **東海鉄工所** を追加\n"
        "- 起動ハング対策（外部接続の遅延実行・タイムアウト）"
    )

# 説明文
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
    # --- セッション初期化 ---
    if "form_count" not in st.session_state:
        st.session_state.form_count = 1

    # --- 入力フォーム定義 ---
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

        # 作業内容（雑務は空欄）
        if customer not in ('選択してください', '雑務'):
            genre = st.selectbox(
                f'作業内容{index}',
                ('選択してください', '新規', '玉成', '設変', 'パネル', 'トライ', 'その他'),
                key=f'genre_{index}'
            )
        else:
            genre = ''  # 雑務なら空欄

        # 工番（「作業内容が選択してください」の間は入力させない）
        number = (
            st.text_input(f'工番を入力{index}', key=f'number_{index}', placeholder="例: 51A111")
            .upper()
            if genre != '選択してください' else ''
        )

        # 時間
        time_input = st.text_input(f'時間を入力{index}', key=f'time_{index}', placeholder="例: 1.5")
        try:
            hours = float(time_input) if time_input.strip() != "" else 0.0
        except ValueError:
            st.warning(f"時間{index}は数値で入力してください")
            hours = 0.0

        return {
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "number": number,
            "time": hours
        }

    # --- 入力フォームの表示 ---
    inputs = [create_input_fields(i) for i in range(1, st.session_state.form_count + 1)]

    # --- 「次へ」ボタン（最大10件） ---
    cols_next = st.columns([1, 1, 6])
    with cols_next[0]:
        if st.session_state.form_count < 10 and st.button("次へ"):
            st.session_state.form_count += 1
            st.rerun()  # すぐに次のフォームを描画

    # --- 有効データ抽出 ---
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

    # --- 合計時間表示 ---
    if total_time > 0:
        st.markdown(f"### ✅ 合計時間: {total_time:.2f} 時間")

    # --- 送信ボタン ---
    if valid_inputs:
        if st.button("送信"):
            try:
                sheet = get_sheet()  # ここで初めて接続（遅延実行）

                rows_to_append = []
                for idx, inp in enumerate(valid_inputs, start=1):
                    is_last = (idx == len(valid_inputs))
                    row = [
                        str(day),
                        name,
                        inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                        "" if inp["customer"] == "雑務" else inp["genre"],  # 雑務は作業内容空欄
                        inp["number"],
                        inp["time"],
                        f"合計 {total_time:.2f} 時間" if is_last else ""  # 7列目に合計（最後の行だけ）
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

# =========================
# 依存関係メモ（任意）
# =========================
# pip install streamlit gspread google-auth
# （pandas等は本画面では未使用。必要なら追加）
