# hokusei-siage-nippo.py
# 2025/10/31 スマホ安定版
# - 起動ハング対策（socket timeout）
# - スマホ入力改善（時間は空欄スタート＋全角/単位OK）
# - セッション安定化（boot_ok）
# - 二重送信ガード（is_sending）
# - 初回接続の事前確立（sheet_ready）

import socket
socket.setdefaulttimeout(10)

import re
import unicodedata
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

########################################
#  共通ユーティリティ
########################################

def parse_hours_maybe(s: str) -> float:
    """1.5, １．５, 1,5, 1.5h, 1.5時間 → 1.5 に直す。
       数字が無い/おかしい時は 0.0 を返す。
    """
    if not s:
        return 0.0
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("，", ".").replace("、", ".").replace("．", ".")
    s = re.sub(r"(時間|h|ｈ)", "", s, flags=re.IGNORECASE)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0


########################################
#  Googleシート接続まわり
########################################

GOOGLE_SHEET_ID = "1MXSg8qP_eT7lVczYpNB66sZGZP2NlWHIGz9jAWKH7Ss"
SHEET_NAME = None  # Noneなら sheet1 を使う

def _normalized_service_account_info():
    """secrets.tomlのgoogle_cloudから改行崩れを補正して辞書として返す"""
    info = dict(st.secrets["google_cloud"])
    if "private_key" in info and "\\n" in info["private_key"]:
        # Streamlit Cloudなどで \n が消えて1行になる事故対策
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info

@st.cache_resource(show_spinner=False)
def get_sheet_cached():
    """アプリ全体で1回だけGoogleシート接続してキャッシュする。
       これが安定してれば、以降のappend_rowsは速い＆セッション切断されにくい。
    """
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


def try_prepare_sheet():
    """最初の画面表示時点で一度だけシート接続を試す。
       成功したら st.session_state["sheet_ready"]=True にする。
       → スマホの「送信ボタン押した瞬間に初回認証で落ちる」パターンを減らす。
    """
    if "sheet_ready" not in st.session_state:
        st.session_state.sheet_ready = False

    if not st.session_state.sheet_ready:
        try:
            _ = get_sheet_cached()  # 接続テスト。成功すればキャッシュ済みになる
            st.session_state.sheet_ready = True
        except Exception as e:
            # ここで落ちてもアプリ自体は表示続行する
            st.warning(
                "シートとの初期接続中です。もし送信で失敗したら、もう一度送ってください。\n"
                f"(詳細: {e})"
            )


########################################
#  セッション安定化 + 送信中ガード
########################################

# boot_ok: True になるまで一度再実行して、セッションを安定させる
if "boot_ok" not in st.session_state:
    st.session_state.boot_ok = True
    # 初回アクセス時に sheet_ready のプリフライトも試す
    st.session_state.is_sending = False  # 送信中フラグ初期化
    # ここでr(erun)することで、モバイルSafariなどの超初回不安定状態を1回吐き出してから本描画
    st.rerun()

# 念のため送信中フラグが無ければ作る
if "is_sending" not in st.session_state:
    st.session_state.is_sending = False

# シート接続を先に試す（初回の認証待ちで送信が飛ばないように）
try_prepare_sheet()


########################################
#  UI
########################################

st.title('北青 仕上げ課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")

with st.expander("リリースノート（2025/10/15～2025/10/31更新）", expanded=False):
    st.markdown(
        "- メーカー名に **協豊** を追加\n"
        "- 一度に送信できる作業を **10件** に増加\n"
        "- メーカーに **東海鉄工所** を追加\n"
        "- 起動ハング対策（外部接続の遅延実行・タイムアウト）\n"
        "- スマホ入力改善：時間は空欄スタート＋全角/単位OK\n"
        "- セッション安定化と誤リロード対策を追加（2025/10/31）"
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
    (
        '選択してください',
        '吉田', "中村", "渡辺", "福田", "苫米地", "矢部", "小野",
        "塩入", "トム", "ユン", "ティエン", "チョン", "アイン", "ナム"
    )
)

if name != '選択してください':

    # 1ページ内で何件入力するかを管理
    if "form_count" not in st.session_state:
        st.session_state.form_count = 1

    ##############################
    # 入力フォームを1件ぶん生成
    ##############################
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

        # 作業内容（雑務は空欄、その他は選択必須）
        if customer not in ('選択してください', '雑務'):
            genre = st.selectbox(
                f'作業内容{index}',
                ('選択してください', '新規', '玉成', '設変', 'パネル', 'トライ', 'その他'),
                key=f'genre_{index}'
            )
        else:
            genre = ''

        # 工番（まだ作業内容が選択されてなければ表示しない＝従来仕様）
        number = (
            st.text_input(
                f'工番を入力{index}',
                key=f'number_{index}',
                placeholder="例: 51A111"
            ).upper()
            if genre != '選択してください' else ''
        )

        # 時間：空欄スタート、寛容パース
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

    ############################################
    # いまの form_count 個ぶんのフォームを描画
    ############################################
    inputs = [
        create_input_fields(i)
        for i in range(1, st.session_state.form_count + 1)
    ]

    # 「次へ」ボタンでフォームを増やす（最大10件）
    if st.session_state.form_count < 10:
        if st.button("次へ"):
            st.session_state.form_count += 1
            st.rerun()

    ############################################
    # バリデーション済みレコードだけ集める
    ############################################
    valid_inputs = []
    total_time = 0.0
    for inp in inputs:
        # 条件:
        #   customer が選ばれている
        #   genre が '選択してください' でない or customer が '雑務'
        #   number が空じゃない
        #   time が 0 より大きい
        if (
            inp["customer"] != "選択してください"
            and (inp["genre"] != "選択してください" or inp["customer"] == "雑務")
            and inp["number"] != ''
            and inp["time"] > 0
        ):
            total_time += inp["time"]
            valid_inputs.append(inp)

    if total_time > 0:
        st.markdown(f"### ✅ 合計時間: {total_time:.2f} 時間")

    ############################################
    # 送信ボタン（ステート付き）
    ############################################
    # 送信中フラグが True の間は押させない
    can_click_send = (not st.session_state.is_sending)

    if valid_inputs:
        if st.button("送信", disabled=(not can_click_send)):
            # 送信開始 → 連打防止
            st.session_state.is_sending = True
            st.rerun()

    # is_sending が True なら、ここで実際に送信処理を実行する
    if st.session_state.is_sending:
        try:
            # 念のためシートが準備済みか確認
            if not st.session_state.get("sheet_ready", False):
                # ここで失敗しやすいときはユーザーに「もう一回押して」と案内
                sheet = get_sheet_cached()
                st.session_state.sheet_ready = True
            else:
                sheet = get_sheet_cached()

            rows_to_append = []
            for idx, inp in enumerate(valid_inputs, start=1):
                is_last = (idx == len(valid_inputs))
                row = [
                    str(day),
                    name,
                    inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                    "" if inp["customer"] == "雑務" else inp["genre"],  # 雑務は作業内容を空にする
                    inp["number"],
                    inp["time"],
                    f"合計 {total_time:.2f} 時間" if is_last else ""
                ]
                rows_to_append.append(row)

            # Googleシートへ一括追加
            sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")

            # 完了メッセージ
            st.success("作業内容を送信しました。お疲れ様でした！ 🎉")

            # 次回入力用にフォームをリセット
            st.session_state.form_count = 1

        except Exception as e:
            st.error(f"送信に失敗しました: {e}")
            st.info(
                "• Secrets の private_key の改行（\\n）が壊れていないか\n"
                "• ネットワーク接続は安定しているか\n"
                "• ライブラリのバージョンは正しいか\n"
                "を確認してください。"
            )

        # 送信フラグを下ろす
        st.session_state.is_sending = False
        # フラグ変更を即反映
        st.rerun()


########################################
# 依存関係メモ：
# pip install streamlit gspread google-auth
########################################
