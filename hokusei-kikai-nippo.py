import gspread
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials

# --- 認証情報読み込み  ---
google_cloud_secret = st.secrets["google_cloud"]
service_account_info = {
    "type": google_cloud_secret["type"],
    "project_id": google_cloud_secret["project_id"],
    "private_key_id": google_cloud_secret["private_key_id"],
    "private_key": google_cloud_secret["private_key"],
    "client_email": google_cloud_secret["client_email"],
    "client_id": google_cloud_secret["client_id"],
    "auth_uri": google_cloud_secret["auth_uri"],
    "token_uri": google_cloud_secret["token_uri"],
    "auth_provider_x509_cert_url": google_cloud_secret["auth_provider_x509_cert_url"],
    "client_x509_cert_url": google_cloud_secret["client_x509_cert_url"],
    "universe_domain": google_cloud_secret["universe_domain"]
}


# ✅ キャッシュ付きシート取得関数
@st.cache_resource
def get_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        service_account_info,
        [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    gc = gspread.authorize(creds)
    spreadsheet_id = "1XdfjbRSYWJhlYNB12okcUeVMXPzBLxsv85sw4dLoOjQ"
    ss = gc.open_by_key(spreadsheet_id)
    return {
        "main": ss.worksheet("シート1"),        # 通常作業用
        "auto": ss.worksheet("自動運転")   # 自動運転用
    }


sheets = get_sheets()

# --- UI ---
st.title('テスト北青 機械課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

# リリースノート
R_CHECK = st.checkbox("リリースノート(2025/09/04更新)")
if R_CHECK:
    st.text(
        "●名前を選択していないと次の入力に進めない方式に変更しました。\n●一度に送信できる作業を10件まで増やしました。\n●メーカーに東海鉄工所を追加。")

# 説明文
st.text("工番に関わる仕事以外の場合はメーカー名の欄で雑務を選択し\n工番に作業の内容(機械の清掃など)を入力してください")

day = st.date_input("日付を選択してください")
name = st.selectbox('名前', ('選択してください', '大地', '山岸', '坂本', '一條', '松本', '将', '出繩'))

if name != '選択してください':
    # --- セッション初期化 ---
    if "form_count" not in st.session_state:
        st.session_state.form_count = 1

    # --- 入力フォーム定義 ---
    def create_input_fields(index):
        st.markdown(f"---\n### 作業 {index}")

        customer = st.selectbox(
            f'メーカー{index}',
            ('選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ', '浜岳', '三池', '東プレ', '千代田', '武部',
             'インフェック', '東海鉄工所', '雑務', 'その他メーカー'),
            key=f'customer_{index}'
        )

        new_customer = ''
        if customer == 'その他メーカー':
            new_customer = st.text_input(f'メーカー名を入力{index}', key=f'new_customer_{index}',
                                         placeholder="メーカー名を入力")

        # 👇 作業内容の選択肢：雑務以外なら表示
        if customer not in ('選択してください', '雑務'):
            genre = st.selectbox(
                f'作業内容{index}',
                ('選択してください', '新規', '改修', 'その他', '自動運転'),  # ← 自動運転を追加
                key=f'genre_{index}'
            )
        else:
            genre = ''  # 雑務なら作業内容は空欄

        number = st.text_input(f'工番を入力{index}', key=f'number_{index}',
                               placeholder="例: 51A111").upper() if genre != '選択してください' else ''

        # --- 時間入力（プレースホルダ付きテキスト） ---
        time_input = st.text_input(f'時間を入力{index}', key=f'time_{index}', placeholder="例: 1.5")
        try:
            time = float(time_input) if time_input.strip() != "" else 0.0
        except ValueError:
            st.warning(f"時間{index}は数値で入力してください")
            time = 0.0

        return {
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "number": number,
            "time": time
        }

    # --- 入力フォームの表示 ---
    inputs = []
    for i in range(1, st.session_state.form_count + 1):
        inputs.append(create_input_fields(i))

    # --- 「次へ」ボタン（最大10件） ---
    if st.session_state.form_count < 10:
        if st.button("次へ"):
            st.session_state.form_count += 1
            st.rerun()  # ✅ 即時再描画で次のフォームを表示！

    # --- 有効データ抽出 ---
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

    # --- 合計時間表示 ---
    if total_time_normal > 0:
        st.markdown(f"### ✅ 合計時間: {total_time_normal:.2f} 時間")

    if total_time_auto > 0:
        st.markdown(f"### ✅ 合計時間(自動): {total_time_auto:.2f} 時間")

    # --- 送信ボタン（有効データがある時だけ表示） ---
    if valid_inputs:
        if st.button("送信"):
            rows_main = []
            rows_auto = []

            for inp in valid_inputs:
                row = [
                    str(day),
                    name,
                    inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                    "" if inp["customer"] == "雑務" else inp["genre"],
                    inp["number"],
                    inp["time"]
                ]
                if inp["genre"] == "自動運転":
                    rows_auto.append(row)
                else:
                    rows_main.append(row)

            # --- 通常作業シートへの書き込み ---
            if rows_main:
                current_rows = len(sheets["main"].get_all_values())
                sheets["main"].append_rows(rows_main)

                start_row = current_rows + 1
                for i in range(len(rows_main)):
                    if i == len(rows_main) - 1:  # 最後の行だけ
                        sheets["main"].update_cell(start_row + i, 7, f"合計 {total_time_normal:.2f} 時間")

            # --- 自動運転シートへの書き込み ---
            if rows_auto:
                sheets["auto"].append_rows(rows_auto)
                # ✅ 7列目には何も書かない

            st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
            st.session_state.form_count = 1

    ##### プログラムエンド #####

