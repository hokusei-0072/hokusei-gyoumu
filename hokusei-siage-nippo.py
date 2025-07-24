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
def get_sheet():
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
    spreadsheet_id = "1MXSg8qP_eT7lVczYpNB66sZGZP2NlWHIGz9jAWKH7Ss"

    return gc.open_by_key(spreadsheet_id).sheet1

sheet = get_sheet()

# --- UI ---
st.title('北青 仕上げ課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

day = st.date_input("日付を選択してください")
name = st.selectbox('名前', ('選択してください', '吉田',"中村","渡辺","福田","矢部","小野",
                             "塩入","トム","ユン","ティエン","チョン","アイン","ナム"))

# --- セッション初期化 ---
if "form_count" not in st.session_state:
    st.session_state.form_count = 1

# --- 入力フォーム定義 ---
def create_input_fields(index):
    st.markdown(f"---\n### 作業 {index}")

    customer = st.selectbox(
        f'メーカー{index}',
        ('選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ', '浜岳', '三池', '東プレ', '千代田',  'その他'),
        key=f'customer_{index}'
    )

    new_customer = ''
    if customer == 'その他':
        new_customer = st.text_input(f'メーカー名を入力{index}', key=f'new_customer_{index}', placeholder="メーカー名を入力")

    genre = st.selectbox(
        f'作業内容{index}',
        ('選択してください', '新規', '玉成','設変','パネル','トライ','その他'),
        key=f'genre_{index}'
    ) if customer != '選択してください' else '選択してください'

    number = st.text_input(f'工番を入力{index}', key=f'number_{index}', placeholder="例: 51a111") if genre != '選択してください' else ''

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

# --- 「次へ」ボタン（最大5件） ---
if st.session_state.form_count < 5:
    if st.button("次へ"):
        st.session_state.form_count += 1
        st.rerun()  # ✅ 即時再描画で次のフォームを表示！

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

# --- 送信ボタン（有効データがある時だけ表示） ---
if valid_inputs:
    if st.button("送信"):
        rows_to_append = []
        for inp in valid_inputs:
            row = [
                str(day),
                name,
                inp["new_customer"] if inp["customer"] == "その他" else inp["customer"],
                inp["genre"],
                inp["number"],
                inp["time"]
            ]
            rows_to_append.append(row)

        # ✅ 現在のシート行数を取得
        current_rows = len(sheet.get_all_values())

        # ✅ 一括送信
        sheet.append_rows(rows_to_append)

        # ✅ 送信した最初の行番号（1オリジン）
        start_row = current_rows + 1
        end_row = start_row + len(rows_to_append) - 1

        # ✅ 同じ日付＋名前の最後の行にだけ total_time を入れる
        for i in range(len(rows_to_append)):
            if i == len(rows_to_append) - 1:  # 最後の行だけ
                sheet.update_cell(start_row + i, 7, f"合計 {total_time:.2f} 時間")

        st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
        st.session_state.form_count = 1
