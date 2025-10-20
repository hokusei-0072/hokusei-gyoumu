# 北青 機械課 作業日報（自動運転対応）
# 2025/09/30 自動運転追加 / 起動ハング対策・認証方式更新版

import socket
socket.setdefaulttimeout(10)  # 外部I/Oの無限待ちを物理的に防止

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# ====== Google 認証情報 ======
# st.secrets["google_cloud"] にサービスアカウントJSONをそのまま入れてください
# private_key の改行は "...\n...\n" 形式で
def _service_account_info():
    info = dict(st.secrets["google_cloud"])
    if "private_key" in info and "\\n" in info["private_key"]:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info

SPREADSHEET_ID = "1XdfjbRSYWJhlYNB12okcUeVMXPzBLxsv85sw4dLoOjQ"  # 機械日報シート

@st.cache_resource(show_spinner=False)
def get_sheets():
    """シート接続（初回のみ）。以降は共有して再利用。"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(_service_account_info(), scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    return {
        "main": ss.worksheet("シート1"),    # 通常作業用
        "auto": ss.worksheet("自動運転"),   # 自動運転用
    }

# ====== UI ======
st.title('北青 機械課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

# リリースノート
with st.expander("リリースノート（2025/09/30 更新）", expanded=False):
    st.text(
        "・作業内容に『自動運転』を追加\n"
        "・名前を選択していないと次に進めない方式に変更\n"
        "・一度に送信できる作業を10件までに増加\n"
        "・メーカーに東海鉄工所を追加"
    )

# 説明
st.text("工番に関わる仕事以外の場合はメーカー名の欄で『雑務』を選択し、工番に作業内容（例: 機械清掃）を入力してください。")

# 基本入力
day = st.date_input("日付を選択してください", value=date.today())
name = st.selectbox('名前', ('選択してください', '大地', '山岸', '坂本', '一條', '松本', '将', '出繩'))

if name != '選択してください':
    # セッション初期化
    if "form_count" not in st.session_state:
        st.session_state.form_count = 1

    # 入力フォーム定義
    def create_input_fields(index: int):
        st.markdown(f"---\n### 作業 {index}")

        customer = st.selectbox(
            f'メーカー{index}',
            ('選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ', '浜岳', '三池', '東プレ',
             '千代田', '武部', 'インフェック', '東海鉄工所', '雑務', 'その他メーカー'),
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
                ('選択してください', '新規', '改修', 'その他', '自動運転'),
                key=f'genre_{index}'
            )
        else:
            genre = ''  # 雑務は空欄

        if genre != '選択してください':
            number = st.text_input(
                f'工番を入力{index}',
                key=f'number_{index}',
                placeholder="例: 51A111"
            ).upper()
        else:
            number = ''

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

    # 入力フォームの表示
    inputs = [create_input_fields(i) for i in range(1, st.session_state.form_count + 1)]

    # 「次へ」（最大10件）
    if st.session_state.form_count < 10:
        if st.button("次へ"):
            st.session_state.form_count += 1
            st.rerun()

    # 有効データ抽出 & 合計
    valid_inputs = []
    total_time_normal = 0.0
    total_time_auto = 0.0

    for inp in inputs:
        if (
            inp["customer"] != "選択してください"
            and inp["genre"] != "選択してください"
            and inp["number"] != ''
            and inp["time"] > 0
        ):
            if inp["genre"] == "自動運転":
                total_time_auto += inp["time"]
            else:
                total_time_normal += inp["time"]
            valid_inputs.append(inp)

    # 合計表示
    if total_time_normal > 0:
        st.markdown(f"### ✅ 合計時間: {total_time_normal:.2f} 時間")
    if total_time_auto > 0:
        st.markdown(f"### ✅ 合計時間(自動): {total_time_auto:.2f} 時間")

    # 送信
    if valid_inputs and st.button("送信"):
        try:
            sheets = get_sheets()  # ここで初めて外部接続（遅延実行）

            rows_main = []
            rows_auto = []

            for inp in valid_inputs:
                row = [
                    str(day),
                    name,
                    inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                    "" if inp["customer"] == "雑務" else inp["genre"],
                    inp["number"],
                    inp["time"],
                ]
                if inp["genre"] == "自動運転":
                    rows_auto.append(row)
                else:
                    rows_main.append(row)

            # 通常作業：最後の行だけ 7列目に合計を入れて一括追加
            if rows_main:
                if total_time_normal > 0:
                    rows_main[-1] = rows_main[-1] + [f"合計 {total_time_normal:.2f} 時間"]
                # 7列目が存在しない行には空文字で合わせる
                rows_main = [r if len(r) == 7 else (r + [""]) for r in rows_main]
                sheets["main"].append_rows(rows_main, value_input_option="USER_ENTERED")

            # 自動運転：合計は書かずに追加
            if rows_auto:
                sheets["auto"].append_rows(rows_auto, value_input_option="USER_ENTERED")

            st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
            st.session_state.form_count = 1

        except Exception as e:
            st.error(f"送信に失敗しました: {e}")
            st.info("Secretsのprivate_keyの改行(\\n)やシートの共有権限を確認してください。")

# 依存関係メモ：
# requirements.txt 例
#   streamlit==1.37.*
#   gspread==6.1.*
#   google-auth==2.34.*
