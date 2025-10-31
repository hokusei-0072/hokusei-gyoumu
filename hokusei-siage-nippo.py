# hokusei-siage-nippo.py
# 2025/10/31 安定版(スマホOK / rerun無し / エラー表示しない)
# - streamlit古い環境でも動くように experimental_rerun を撤去
# - 送信後は session_state をリセットして「送信済みメッセージ」を出すだけ
# - 二重送信防止 is_sending あり
# - シート接続はキャッシュで高速化

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
    """1.5, １．５, 1,5, 1.5h, 1.5時間 → 1.5
       変換できなきゃ 0.0。
    """
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
    # secrets の private_key が "\\n" になってるとき <- Streamlit Cloudあるある
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

def prepare_sheet_once():
    """最初のアクセス時に一度だけシートに繋いでおく(モバイル安定用)"""
    if "sheet_ready" not in st.session_state:
        st.session_state.sheet_ready = False
    if not st.session_state.sheet_ready:
        try:
            _ = get_sheet_cached()
            st.session_state.sheet_ready = True
        except Exception as e:
            st.warning(f"シート接続準備中… ({e}) / 送信時に再試行します")

########################################
# セッション初期化
########################################

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.form_count = 1           # 表示する「作業◯」の数
    st.session_state.is_sending = False       # 送信中ロック
    st.session_state.just_sent = False        # 直近で送れたかどうか
    prepare_sheet_once()

########################################
# 画面ヘッダ
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
        "- **安定化**：送信後のrerun廃止（古いStreamlitでも赤エラーが出ない）"
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
    '名前',
    (
        '選択してください',
        '吉田', "中村", "渡辺", "福田", "苫米地", "矢部", "小野",
        "塩入", "トム", "ユン", "ティエン", "チョン", "アイン", "ナム"
    )
)

########################################
# just_sent メッセージ表示（送信直後だけ）
########################################
if st.session_state.just_sent:
    st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
    # just_sent は一度表示したら消しておく（F5しても毎回出ないように）
    st.session_state.just_sent = False

########################################
# 入力フォーム (名前が選択されたら表示)
########################################
if name != '選択してください':

    def create_input_fields(index: int):
        st.markdown(f"---\n### 作業 {index}")

        customer = st.selectbox(
            f'メーカー{index}',
            (
                '選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ', '浜岳',
                '三池', '東プレ', '協豊', '千代田', '東海鉄工所', '雑務', 'その他メーカー'
            ),
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
            st.text_input(
                f'工番を入力{index}',
                key=f'number_{index}',
                placeholder="例: 51A111"
            ).upper()
            if genre != '選択してください' else ''
        )

        # 時間（入力例いろいろOK・空からスタート）
        time_key = f'time_{index}'
        time_text = st.text_input(
            f'時間を入力{index}',
            key=time_key,
            placeholder="例: 1.5（１．５ / 1,5 / 1.5h / 1.5時間 もOK）"
        )
        hours = parse_hours_maybe(time_text)
        if time_text and hours == 0.0:
            st.info(
                f"時間{index}は数値で入力してください（1.5 / １．５ / 1,5 / 1.5h などOK）"
            )

        return {
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "number": number,
            "time": hours
        }

    # 既存の form_count 個ぶん描画
    inputs = [
        create_input_fields(i)
        for i in range(1, st.session_state.form_count + 1)
    ]

    # 「＋作業を追加」ボタン（最大10件）
    if st.session_state.form_count < 10:
        if st.button("＋作業を追加"):
            st.session_state.form_count += 1
            # rerunしない → 次の行はページ再読み込みしないと見えないけど
            # スマホ利用者は基本1～2件入力なのでOK。
            # もし即時反映したいならここだけ st.rerun() を使ってもいいPC環境なら安全。
            # 今回はスマホ安定優先で rerun なし。

    # 有効な行を抽出＋合計時間計算
    valid_inputs = []
    total_time = 0.0
    for inp in inputs:
        # 「雑務」は genre が空でもOKなので条件分岐
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

    # 送信ボタン
    if valid_inputs and not st.session_state.is_sending:
        if st.button("送信"):
            st.session_state.is_sending = True  # 連打防止

            try:
                sheet = get_sheet_cached()  # 必要ならここで再接続
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

                # 送れたのでフォームを初期状態に戻す
                st.session_state.form_count = 1
                st.session_state.is_sending = False
                st.session_state.just_sent = True

                # 各入力欄をクリアするために、使ったキーの値も空に戻しておく
                for i in range(1, 11):
                    for key in (
                        f'customer_{i}',
                        f'new_customer_{i}',
                        f'genre_{i}',
                        f'number_{i}',
                        f'time_{i}',
                    ):
                        if key in st.session_state:
                            # 初期値に戻したいものは戻す
                            if key.startswith("customer_"):
                                st.session_state[key] = '選択してください'
                            elif key.startswith("genre_"):
                                st.session_state[key] = '選択してください'
                            else:
                                st.session_state[key] = ""

                st.success("作業内容を送信しました。お疲れ様でした！ 🎉")

            except Exception as e:
                st.error(f"送信に失敗しました: {e}")
                st.session_state.is_sending = False
