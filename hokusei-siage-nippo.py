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
from datetime import date, datetime, timedelta, timezone
JST = timezone(timedelta(hours=9))  # 日本時間（UTC+9）

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

def quantize_quarter(x: float) -> float:
    """0.25単位に丸める（例: 1.12 → 1.0 / 1.13 → 1.25）"""
    return round(x * 4) / 4.0

def split_hours_quarter(total_hours: float, count: int) -> list[float]:
    """合計時間を count 個に 0.25単位で配分（余りは0.25ずつ先頭から順に配る）"""
    if count <= 0:
        return []
    total_q = quantize_quarter(total_hours)
    # 0.25 を 1 unit として整数配分（float誤差を避ける）
    units = int(round(total_q * 4))
    per = units // count
    rem = units % count

    # まず全員に均等配分
    out_units = [per] * count
    # 余りを 0.25 (=1 unit) ずつ、先頭から順に配る
    for idx in range(rem):
        out_units[idx] += 1

    return [u / 4.0 for u in out_units]

def fmt_hours(x: float) -> str:
    """スプレッドシート送信用の表示（0.75 / 1.5 のように余計な0を落とす）"""
    s = f"{x:.2f}"
    s = s.rstrip("0").rstrip(".")
    return s

def make_job_sequence(job1: str, count: int) -> list[str] | None:
    """工番1から連番を作る。末尾3桁を繰り上げ（例: 12A345 → 12A346 ...）"""
    if count <= 0:
        return []
    base = (job1 or "").strip().upper()
    if not base:
        return None
    m = re.match(r"^(.+?)(\d{3})$", base)
    if not m:
        return None
    prefix = m.group(1)
    start = int(m.group(2))
    return [f"{prefix}{start + k:03d}" for k in range(count)]
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
    "●『パネル』『社内トライ』『客先トライ』で複数工番を同時に作業した場合は、\n"
    "  作業内容を選ぶと専用フォームが表示されます（工程数・工番・時間を入力）。\n"
    "  ※『客先トライ』は移動時間と同行者も入力できます。"
)
st.text(
    "●複数の工番をまとめて(例 51A001～51A005)入力すると集計に不具合が出るので、\n"
    "  専用フォームの『工程数』で工番を分割して入力してください。"
)
st.text(
    "●工番に関わる仕事以外の場合はメーカー名で「雑務」を選択し、\n"
    "  工番欄に作業の内容(例: 工場内清掃)を入力してください。"
)

########################################
# 日付・名前
########################################

day = st.date_input("日付を選択してください", value=datetime.now(JST).date())

name = st.selectbox(
    "名前",
    (
        '選択してください',
        '吉田', "中村", "渡辺", "福田", "苫米地", "矢部", "小野",
        "塩入", "小野(和)", "トム", "ユン", "ティエン", "チョン", "アイン"
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
                "選択してください", "ジーテクト", "ヨロズ", "城山", "タチバナ", "浜岳",
                "三池", "東プレ", "アブクマ", "町山製作所", "須永鉄工", "港プレス", "武部鉄工所", "東海鉄工所",
                "インフェック",
                "千代田", "エスケイ", "協豊", "海津", "タツム", "雑務", "その他メーカー"
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
                ('選択してください', '新規', '玉成', '設変', 'パネル', '社内トライ', '客先トライ', 'その他'),
                key=f"genre_{i}"
            )
        else:
            genre = ""

        # 入力欄を出して良い条件（メーカー選択済み＋作業内容選択済み / 雑務は作業内容なし）
        ready = (
                customer != '選択してください'
                and (
                        customer == '雑務'
                        or (customer != '雑務' and genre != '選択してください')
                )
        )

        special_genres = ('社内トライ', 'パネル', '客先トライ')
        is_special = (genre in special_genres)

        # ==============================
        # 専用フォーム（社内トライ/パネル/客先トライ）
        # ==============================
        steps = 1
        job_numbers: list[str] = []
        work_time_txt = ""
        work_hours_raw = 0.0
        move_time_txt = ""
        move_hours = 0.0
        companion_count = 0
        companion_names: list[str] = []

        if ready and is_special:
            # 客先トライのみ：移動時間
            if genre == '客先トライ':
                move_time_txt = st.text_input(
                    f"移動時間{i}",
                    key=f"move_time_{i}",
                    placeholder="例: 1.0"
                )
                move_hours = parse_hours_maybe(move_time_txt)
                if move_time_txt and move_hours == 0.0:
                    st.info(f"移動時間{i}は数値で入力してください（例: 1 / 1.5 / １．５）")

            # 工程数（選択：1〜10 / 初期値=1）
            steps = st.selectbox(
                f"工程数{i}",
                options=list(range(1, 11)),
                index=0,  # 初期値=1
                key=f"steps_{i}"
            )

            # 工番：工程数ぶん表示（工番1の入力から連番自動入力）
            job1_key = f"job_{i}_1"
            job1_now = st.session_state.get(job1_key, "")
            auto_jobs = make_job_sequence(job1_now, steps)

            old_auto_jobs = st.session_state.get(f"auto_jobs_{i}")
            if auto_jobs is not None:
                for k in range(2, steps + 1):
                    kkey = f"job_{i}_{k}"
                    cur = st.session_state.get(kkey, "")
                    old = None
                    if isinstance(old_auto_jobs, list) and len(old_auto_jobs) >= k:
                        old = old_auto_jobs[k - 1]
                    # 空欄 or 前回の自動入力のままなら更新する（手入力で崩した場合は上書きしない）
                    if cur == "" or (old is not None and cur == old):
                        st.session_state[kkey] = auto_jobs[k - 1]
                st.session_state[f"auto_jobs_{i}"] = auto_jobs

            for k in range(1, steps + 1):
                job = st.text_input(
                    f"工番{k}",
                    key=f"job_{i}_{k}",
                    placeholder="例: 12A345" if k == 1 else ""
                )
                job_numbers.append(job.upper().strip())

            if auto_jobs is None and job1_now:
                st.info("工番1の末尾が3桁数字ではないため、工番2以降の連番自動入力ができません。")

            # 作業時間（合計）
            work_time_txt = st.text_input(
                f"時間{i}",
                key=f"work_time_{i}",
                placeholder="例: 4.75"
            )
            work_hours_raw = parse_hours_maybe(work_time_txt)
            if work_time_txt and work_hours_raw == 0.0:
                st.info(f"時間{i}は数値で入力してください（例: 4.75 / ４．７５）")

            # 同行者（客先トライ：作業番号に関係なく入力OK）
            if genre == "客先トライ":
                companion_sel = st.selectbox(
                    f"同行者（作業{i}）",
                    ["同行者なし"] + [str(n) for n in range(1, 11)],
                    key=f"companion_count_{i}"
                )
                if companion_sel != "同行者なし":
                    companion_count = int(companion_sel)
                    for j in range(1, companion_count + 1):
                        cn = st.selectbox(
                            f"同行者の名前{j}（作業{i}）",
                            (
                                "選択してください",
                                "吉田", "中村", "渡辺", "福田", "苫米地", "矢部", "小野",
                                "塩入", "トム", "ユン", "ティエン", "チョン", "アイン"
                            ),
                            key=f"companion_name_{i}_{j}"
                        )
                        companion_names.append(cn)

            # 「工番＋時間」確認表示（時間は0.25単位で配分）
            st.markdown("#### 工番＋時間（確認）")
            if steps >= 1 and all(job_numbers) and work_hours_raw > 0:
                work_q = quantize_quarter(work_hours_raw)
                if abs(work_q - work_hours_raw) > 1e-9:
                    st.info(f"時間{i}は0.25単位で配分するため、{work_hours_raw} → {work_q} に丸めて計算します。")

                alloc = split_hours_quarter(work_q, steps)
                preview_rows = []
                for jb, hh in zip(job_numbers, alloc):
                    preview_rows.append({"工番": jb, "時間": f"{fmt_hours(hh)}時間"})
                st.table(preview_rows)
            else:
                st.caption("工程数・工番・時間を入力すると、ここに配分結果が表示されます。")

        # ==============================
        # 通常フォーム
        # ==============================
        number = ""
        time_txt = ""
        hours = 0.0

        if ready and not is_special:
            number = st.text_input(
                f"工番を入力{i}",
                key=f"number_{i}",
                placeholder="例: 51A111"
            ).upper().strip()

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
        elif not ready:
            st.caption("メーカーと作業内容（雑務以外）を選択すると入力欄が表示されます。")

        return {
            "i": i,
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "is_special": is_special,

            # 通常フォーム
            "number": number,
            "time": hours,

            # 専用フォーム
            "steps": steps,
            "job_numbers": job_numbers,
            "work_hours_raw": work_hours_raw,
            "move_hours": move_hours,
            "companion_names": companion_names,
        }


    # 今表示すべきフォーム数ぶん生成
    inputs = [create_input_fields(i) for i in range(1, st.session_state.form_count + 1)]

    # 追加ボタン（最大10件）
    if st.session_state.form_count < 10:
        if st.button("＋作業を追加"):
            st.session_state.form_count += 1
            # rerunなし。即座に行を増やして見せたい場合は st.rerun() が必要だけど
            # 古いStreamlit端末では使えないのでここは我慢。

    # 入力チェック＋合計時間（専用フォームは複数行送信に展開）
    valid_inputs = []
    total_time = 0.0

    for inp in inputs:
        genre_ok = (
            inp["genre"] != "選択してください"
            or inp["customer"] == "雑務"
        )

        if inp["customer"] == "選択してください" or not genre_ok:
            continue

        # 専用フォーム（社内トライ/パネル/客先トライ）
        if inp["is_special"]:
            steps = int(inp["steps"])
            job_numbers = inp["job_numbers"][:steps]
            work_q = quantize_quarter(inp["work_hours_raw"])

            # 必須チェック
            if steps < 1 or not all(job_numbers) or work_q <= 0:
                continue

            # 同行者（客先トライ：作業番号に関係なく）：名前が未選択なら送信不可
            if inp["genre"] == "客先トライ" and inp["companion_names"]:
                if any(nm == "選択してください" for nm in inp["companion_names"]):
                    continue

            inp["alloc_hours"] = split_hours_quarter(work_q, steps)
            inp["work_hours_q"] = work_q

            task_total = work_q
            if inp["genre"] == "客先トライ":
                # 移動時間は0でも送れる（0なら0の行が入る）
                task_total += max(0.0, inp["move_hours"])
            inp["task_total"] = task_total

            total_time += task_total
            valid_inputs.append(inp)
            continue

        # 通常フォーム
        if inp["number"] != '' and inp["time"] > 0:
            inp["task_total"] = inp["time"]
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

                # 送信日時（この送信処理全体で共通 / JST固定）
                now_dt = datetime.now(JST)
                sent_dt_text = f"{now_dt.month}月{now_dt.day}日{now_dt.hour}時{now_dt.minute}分"

                def make_sent_header_row(person_name: str) -> list[str]:
                    # 1列目=送信日時 / 2列目=名前 / 3列目=実際の送信日時
                    # 既存の列数に合わせて4〜7列目は空欄
                    return ["送信日時", person_name, sent_dt_text, "", "", "", ""]

                rows_main: list[list[str]] = []

                # 本人分（作業追加も含めて全部）
                for inp in valid_inputs:
                    cust_cell = inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"]

                    if inp["is_special"]:
                        # 客先トライは先頭に「移動」行を追加
                        if inp["genre"] == "客先トライ":
                            rows_main.append([
                                str(day),
                                name,
                                "雑務",
                                "",
                                "移動",
                                fmt_hours(max(0.0, inp["move_hours"])),
                                ""
                            ])

                        for jb, hh in zip(inp["job_numbers"][:inp["steps"]], inp["alloc_hours"]):
                            rows_main.append([
                                str(day),
                                name,
                                cust_cell,
                                inp["genre"],
                                jb,
                                fmt_hours(hh),
                                ""
                            ])
                    else:
                        rows_main.append([
                            str(day),
                            name,
                            cust_cell,
                            "" if inp["customer"] == "雑務" else inp["genre"],
                            inp["number"],
                            fmt_hours(inp["time"]),
                            ""
                        ])

                # 「合計」表示は本人分の最後の行だけに付ける
                if rows_main:
                    rows_main[-1][6] = f"合計 {total_time:.2f} 時間"

                # 本人ブロックの先頭に「送信日時」行を追加
                if rows_main:
                    rows_main = [make_sent_header_row(name)] + rows_main

                # 同行者分（同行者が入力された「客先トライ」作業ごとに複製して送信）
                rows_companions: list[list[str]] = []

                for src in valid_inputs:
                    if not (src.get("genre") == "客先トライ" and src.get("companion_names")):
                        continue

                    cust_cell_src = src["new_customer"] if src["customer"] == "その他メーカー" else src["customer"]

                    # 同行者の合計は「その作業の客先トライ分だけ」（他作業は含めない）
                    comp_total = float(src.get("task_total", 0.0))
                    comp_total_text = f"合計 {comp_total:.2f} 時間"

                    for comp_name in src["companion_names"]:
                        # 同行者ブロックの先頭に「送信日時」行を追加
                        rows_companions.append(make_sent_header_row(comp_name))

                        # 「移動」行
                        rows_companions.append([
                            str(day),
                            comp_name,
                            "雑務",
                            "",
                            "移動",
                            fmt_hours(max(0.0, src["move_hours"])),
                            ""
                        ])

                        # 工番配分行（最後の工番行の位置を覚える）
                        last_job_row_idx = None
                        for jb, hh in zip(src["job_numbers"][:src["steps"]], src["alloc_hours"]):
                            rows_companions.append([
                                str(day),
                                comp_name,
                                cust_cell_src,
                                "客先トライ",
                                jb,
                                fmt_hours(hh),
                                ""
                            ])
                            last_job_row_idx = len(rows_companions) - 1

                        # 同行者ごとの「合計」は“工番配分の最後の行”に固定
                        if last_job_row_idx is not None:
                            rows_companions[last_job_row_idx][6] = comp_total_text

                rows_to_append = rows_main + rows_companions

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

                    # 専用フォーム系（工程数・工番群・時間など）
                    steps_key = f"steps_{i}"
                    if steps_key in st.session_state:
                        st.session_state[steps_key] = 1

                    for text_key in (
                        f"new_customer_{i}",
                        f"number_{i}",
                        f"time_{i}",
                        f"work_time_{i}",
                        f"move_time_{i}",
                    ):
                        if text_key in st.session_state:
                            st.session_state[text_key] = ""

                    # 工番群（最大50までリセット）
                    for k in range(1, 51):
                        jk = f"job_{i}_{k}"
                        if jk in st.session_state:
                            st.session_state[jk] = ""

                    # 自動入力キャッシュ
                    ak = f"auto_jobs_{i}"
                    if ak in st.session_state:
                        del st.session_state[ak]

                # 同行者（作業1〜10）
                for i in range(1, 11):
                    ck = f"companion_count_{i}"
                    if ck in st.session_state:
                        st.session_state[ck] = "同行者なし"
                    for j in range(1, 11):
                        nk = f"companion_name_{i}_{j}"
                        if nk in st.session_state:
                            st.session_state[nk] = "選択してください"

            except Exception:
                # ここは握りつぶす。送信自体はもう終わってるので
                st.session_state.is_sending = False
                pass


    # 送信中ロックが残ってしまった場合の保険
    if st.session_state.is_sending:
        st.info("送信処理中です…数秒待ってください。")
