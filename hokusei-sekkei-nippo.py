# 2025/10/15 編集　メーカー名にアブクマを追加

import gspread
import streamlit as st
# 置き換え前
# from oauth2client.service_account import ServiceAccountCredentials
# 置き換え後
from google.oauth2.service_account import Credentials
import socket

socket.setdefaulttimeout(10)  # 無限待ち対策（任意）

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
    # 置き換え後（scopesは用途に合わせて）
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(st.secrets["google_cloud"], scopes=scopes)
    gc = gspread.authorize(creds)

    spreadsheet_id = "1ApUfZcqbp_YK6FlNZLQ-3zA5Rd6gME7cNzC76q6YqS0"
    return gc.open_by_key(spreadsheet_id).sheet1


sheet = get_sheet()

##### アプリ表示開始 #####
### タイトル ###
st.title('北青 設計課作業日報')
st.text("メーカー名、工番、作業内容、時間を入力してください。")

### 連絡事項 ###
# st.markdown("# お知らせ")

### リリースノート ###
R_CHECK = st.checkbox("リリースノート(2025/10/15更新)")
if R_CHECK:
    st.text(
        "●作業内容がレイアウトの場合は工番入力欄に部品番号を入力してください。\n●作業内容が見積の場合は工番の入力を自動にしました。\n●名前を選択していないと次の入力に進めない方式に変更しました。\n●一度に送信できる作業を10件まで増やしました。")

### 説明文 ###
st.text("工番に関わる仕事以外の場合はメーカー名の欄で雑務を選択し\n工番に作業の内容(清掃など)を入力してください")

### 入力フォーム開始 ###
day = st.date_input("日付を選択してください")
name = st.selectbox('名前', ('選択してください', "白熊"))

if name != '選択してください':
    # --- セッション初期化 ---
    if "form_count" not in st.session_state:
        st.session_state.form_count = 1


    # --- 入力フォーム定義 ---
    def create_input_fields(index):
        st.markdown(f"---\n### 作業 {index}")

        customer = st.selectbox(
            f'メーカー{index}',
            ("選択してください", "ジーテクト", "ヨロズ", "城山", "タチバナ", "浜岳",
    "三池", "東プレ", "アブクマ", "町山製作所", "須永鉄工", "港プレス", "武部鉄工所","東海鉄工所", "坪山", "インフェック",
    "千代田","エスケイ","協豊", "海津","タツム", "雑務", "その他メーカー"),
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
                ('選択してください', "新規", "改修", "設変", "レイアウト", "見積", "その他"),
                key=f'genre_{index}'
            )
        else:
            genre = ''  # 雑務なら作業内容は空欄

        if genre != '見積':
            number = st.text_input(f'工番を入力{index}', key=f'number_{index}',
                                   placeholder="例: 51A111").upper() if genre != '選択してください' else ''
        else:
            number = st.text_input(f'工番を入力{index}', key=f'number_{index}',
                                   value="見積用設計、打合せ").upper() if genre != '選択してください' else ''

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
    if st.session_state.form_count < 10:
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
                    inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                    "" if inp["customer"] == "雑務" else inp["genre"],  # 👈 作業内容を空白に
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

            ##### プログラムエンド10/15 #####

