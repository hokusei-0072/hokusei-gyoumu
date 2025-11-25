# hokusei-siage-nippo.py
# 2025/10/31 安定版 v10-31b
# - 送信自体は成功してるのに「失敗しました」と表示される問題を修正
# - 後片付け(フォーム初期化)でエラーしても赤いバナーを出さない
# - rerunなし、スマホOK、二重送信防止

import socket
socket.setdefaulttimeout(10)

import re
import unicodedata
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

########################################
# ユーティリティ
########################################

def parse_hours_maybe(s: str) -> float:
    """1.5, １．５, 1,5, 1.5h, 1.5時間 → 1.5 / 変換できなきゃ0.0"""
    if not s:
        return 0.0
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("，", ".").replace("、", ".").replace("．", ".")
    s = re.sub(r"(時間|h|ｈ)", "", s, flags=re.IGNORECASE)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0

########################################
# Googleシート接続
########################################

GOOGLE_SHEET_ID = "1MXSg8qP_eT7lVczYpNB66sZGZP2NlWHIGz9jAWKH7Ss"
SHEET_NAME = None  # Noneなら sheet1

def _normalized_service_account_info():
    info = dict(st.secrets["google_cloud"])
    # secretsのprivate_keyが"\\n"になっていたら復元（Cloud/Secretsのあるある）
    if "private_key" in info and "\\n" in info["private_key"]:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info

@st.cache_resource(show_spinner=False)
def get_sheet_cached():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(
        _normalized_service_account_info(),
        scopes=scopes
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    return sh.worksheet(SHEET_NAME) if SHEET_NAME else sh.sheet1

def ensure_sheet_ready():
    if "sheet_ready" not in st.session_state:
        st.session_state.sheet_ready = False
    if not st.session_state.sheet_ready:
        try:
            _ = get_sheet_cached()
            st.session_state.sheet_ready = True
        except Exception:
            # ここで失敗しても送信時にもう一度やるので黙っておく
            pass

########################################
# セッション初期化
########################################

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.form_count = 1            # 表示する作業フォーム数
    st.session_state.is_sending = False        # 送信中ロック
    st.session_state.just_sent = False         # 直前に成功したか
    ensure_sheet_ready()

########################################
# ヘッダ表示
########################################

st.title('北青 仕上げ課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

with st.expander("リリースノート（2025/10/31更新）", expanded=False):
    st.markdown(
        "- メーカー名に **協豊** を追加\n"
        "- 一度に送信できる作業を **10件** に増加\n"
        "- メーカーに **東海鉄工所** を追加\n"
        "- 起動ハング対策（外部接続の遅延実行・タイムアウト）\n"
        "- **スマホ入力改善**：時間の初期値なし/全角OK/『1.5h』などもOK\n"
        "- rerunを使わずに安定化\n"
        "- 送信後エラーバナーが出る問題を修正（後処理のエラーは握りつぶし）"
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

########################################
# 日付・名前
########################################

day = st.date_input("日付を選択してください", value=date.today())
name = st.selectbox(
    "名前",
    (
        '選択してください',
        '吉田', "中村", "渡辺", "福田", "苫米地", "矢部", "小野",
        "塩入", "トム", "ユン", "ティエン", "チョン", "アイン", "ナム"
    )
)

# 直前に送れたフラグがあるなら一度だけ表示
if st.session_state.just_sent:
    st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
    st.session_state.just_sent = False  # 次回は出さないように

########################################
# 入力フォーム
########################################

if name != '選択してください':

    def create_input_fields(i: int):
        st.markdown(f"---\n### 作業 {i}")

        customer = st.selectbox(
            f"メーカー{i}",
            (
                '選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ',
                '浜岳', '三池', '東プレ', '協豊', '千代田',
                'アブクマ','武部鉄工', '雑務', 'その他メーカー'
            ),
            key=f"customer_{i}"
        )

        new_customer = ""
        if customer == "その他メーカー":
            new_customer = st.text_input(
                f"メーカー名を入力{i}",
                key=f"new_customer_{i}",
                placeholder="メーカー名を入力"
            )

        # 雑務以外のときだけ作業内容を選ばせる
        if customer not in ('選択してください', '雑務'):
            genre = st.selectbox(
                f"作業内容{i}",
                ('選択してください', '新規', '玉成', '設変', 'パネル', 'トライ', 'その他'),
                key=f"genre_{i}"
            )
        else:
            genre = ""

        number = (
            st.text_input(
                f"工番を入力{i}",
                key=f"number_{i}",
                placeholder="例: 51A111"
            ).upper()
            if genre != '選択してください' else ''
        )

        time_txt = st.text_input(
            f"時間を入力{i}",
            key=f"time_{i}",
            placeholder="例: 1.5（１．５ / 1,5 / 1.5h / 1.5時間 もOK）"
        )
        hours = parse_hours_maybe(time_txt)
        if time_txt and hours == 0.0:
            st.info(
                f"時間{i}は数値で入力してください（1.5 / １．５ / 1,5 / 1.5h などOK）"
            )

        return {
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "number": number,
            "time": hours
        }

    # 今表示すべきフォーム数ぶん生成
    inputs = [create_input_fields(i) for i in range(1, st.session_state.form_count + 1)]

    # 追加ボタン（最大10件）
    if st.session_state.form_count < 10:
        if st.button("＋作業を追加"):
            st.session_state.form_count += 1
            # rerunなし。即座に行を増やして見せたい場合は st.rerun() が必要だけど
            # 古いStreamlit端末では使えないのでここは我慢。

    # 入力チェック＋合計時間
    valid_inputs = []
    total_time = 0.0
    for inp in inputs:
        genre_ok = (
            inp["genre"] != "選択してください"
            or inp["customer"] == "雑務"
        )
        if (
            inp["customer"] != "選択してください"
            and genre_ok
            and inp["number"] != ''
            and inp["time"] > 0
        ):
            total_time += inp["time"]
            valid_inputs.append(inp)

    if total_time > 0:
        st.markdown(f"### ✅ 合計時間: {total_time:.2f} 時間")

    # 送信ボタン（送信中ロック中は押せない）
    if valid_inputs and not st.session_state.is_sending:
        if st.button("送信"):
            st.session_state.is_sending = True  # 二重押し防止

            # === ① Googleシートへの書き込みだけ try/exceptで扱う ===
            send_ok = False
            error_msg = ""

            try:
                # シート確保（準備で失敗してた場合もここで再try）
                sheet = get_sheet_cached()

                rows_to_append = []
                for idx, inp in enumerate(valid_inputs, start=1):
                    is_last = (idx == len(valid_inputs))
                    rows_to_append.append([
                        str(day),
                        name,
                        inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                        "" if inp["customer"] == "雑務" else inp["genre"],
                        inp["number"],
                        inp["time"],
                        f"合計 {total_time:.2f} 時間" if is_last else ""
                    ])

                sheet.append_rows(
                    rows_to_append,
                    value_input_option="USER_ENTERED"
                )

                send_ok = True

            except Exception as e:
                send_ok = False
                error_msg = str(e)

            # === ② UIへのメッセージ表示（ここは絶対に落とさない） ===
            if send_ok:
                st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
                st.session_state.just_sent = True
            else:
                st.error(f"送信に失敗しました: {error_msg}")

            # === ③ 後片付け（フォーム初期化）は別枠でやる
            #     ここで失敗してもユーザーには赤いエラーを出さない
            try:
                # フォームを1件に戻す／ロック解除
                st.session_state.form_count = 1
                st.session_state.is_sending = False

                # 各入力欄を初期値に戻す
                for i in range(1, 11):
                    # セレクト系は「選択してください」に戻す
                    cust_key = f"customer_{i}"
                    genre_key = f"genre_{i}"
                    if cust_key in st.session_state:
                        st.session_state[cust_key] = '選択してください'
                    if genre_key in st.session_state:
                        st.session_state[genre_key] = '選択してください'

                    # フリーテキストは空に戻す
                    for text_key in (
                        f"new_customer_{i}",
                        f"number_{i}",
                        f"time_{i}",
                    ):
                        if text_key in st.session_state:
                            st.session_state[text_key] = ""

            except Exception:
                # ここは握りつぶす。送信自体はもう終わってるので
                st.session_state.is_sending = False
                pass

    # 送信中ロックが残ってしまった場合の保険
    if st.session_state.is_sending:
        st.info("送信処理中です…数秒待ってください。")
