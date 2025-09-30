### 2025/09/30 項目に自動運転を追加 ###

import gspread
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials

##### Google認証情報の読み込み #####
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


##### シート取得関数 #####　
# キャッシュ付きでシート情報を取得するので読み込みのたびにAPIに接続する必要がなくなり処理の高速化ができる。
@st.cache_resource
# @st.cache_resourceでキャッシュ機能をオンしている。

def get_sheets():# get_sheetsという関数として認証情報を定義。ここでキャッシュ機能がオンしていないとget_sheetsを呼び出すたびにAPIの認証等が行われ処理に時間がかかる。
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
    spreadsheet_id = "1XdfjbRSYWJhlYNB12okcUeVMXPzBLxsv85sw4dLoOjQ"#シートIDでシートを読み込み
    ss = gc.open_by_key(spreadsheet_id)
    # 前の処理で認証情報を定義した関数get_sheets()に取得したシートのシートタブを辞書型で定義する。
    return {
        "main": ss.worksheet("シート1"),        # 通常作業用
        "auto": ss.worksheet("自動運転")   # 自動運転用　辞書型でまとめてるのでキー("main""auto")でシートタブ(値)を呼び出せる
    }
    # ただシートタブを定義するだけだと関数内でシートタブを取得しているだけで関数を呼び出した先の処理ではシート情報が渡されないためシートの操作が出来ない。
    # そこでreturnを使うとget_sheets()を呼び出した側にもget_sheets()で取得したシートタブをまとめた辞書型が渡されるので同じように操作できるようになる。

sheets = get_sheets()
# 上で定義した関数を短く呼び出せるようにsheetsとして再定義


##### streamlitタイトル #####
st.title('北青 機械課 作業日報')
st.caption("メーカー名、工番、作業内容、時間を入力してください。")


##### リリースノート #####
# チェックボックスにチェックが入るとリリースノートを表示。
R_CHECK = st.checkbox("リリースノート(2025/09/30更新)")
if R_CHECK:
    st.text(
        "作業内容に自動運転を追加しました。\n●名前を選択していないと次の入力に進めない方式に変更しました。"
        "\n●一度に送信できる作業を10件まで増やしました。\n●メーカーに東海鉄工所を追加。")


##### 説明文 #####
st.text("工番に関わる仕事以外の場合はメーカー名の欄で雑務を選択し\n工番に作業の内容(機械の清掃など)を入力してください")

##### 日付、名前の選択 #####
# st.date_inputでstreamlitの日付選択機能を表示。指定しない場合デフォルトで今日の日付が選択されている。
day = st.date_input("日付を選択してください")
name = st.selectbox('名前', ('選択してください', '大地', '山岸', '坂本', '一條', '松本', '将', '出繩'))


##### 入力フォーム開始 #####
# 名前が"選択してください"以外なら入力フォームを表示。
if name != '選択してください':

    ##### セッション初期化 #####
    if "form_count" not in st.session_state:# もし"st.session_state"の中に"form_count"が存在しないなら。
        st.session_state.form_count = 1# form_count=1に設定。アプリ起動時には必ずform_countが存在しないのでカウントを1に設定する。ページの更新時にはカウントが存在するので1には戻らない。
    # streamlitの機能"st.session_state"=状態保持用のオブジェクト。通常streamlitではボタン操作のたびに全体が再実行されるので変数などの値が保持されない。
    #"st.session_state"に入れた変数はページが更新されてもユーザーのセッション中は保持され続ける。この機能を使って入力フォームの番号を管理している。

    ##### 入力フォーム定義 #####
    # 入力フォーム自体を関数として定義し、関数を呼び出すだけで繰り返し表示できるようにする。
    # 関数名＋引数(index)で定義することでこの後のループ処理に使う番号を引数(index=1やindex=2)として受け取れる。
    def create_input_fields(index):
        st.markdown(f"---\n### 作業 {index}")# ループ処理の際に渡される引数をフォームの番号｛index｝として表示

        ##### メーカー選択 #####
        customer = st.selectbox(
            f'メーカー{index}',
            ('選択してください', 'ジーテクト', 'ヨロズ', '城山', 'タチバナ', '浜岳', '三池', '東プレ', '千代田', '武部',
             'インフェック', '東海鉄工所', '雑務', 'その他メーカー'),
            key=f'customer_{index}'# 選択されたメーカー名とフォームの番号をセットにして保管するためのキー。
        )

        ##### メーカー名自由入力 #####
        new_customer = ''# new_customerを空欄として仮定義(中身のない関数としてpycharmに警告されないための対策)
        # メーカー名が"その他メーカー"ならメーカー名の自由入力欄を表示。
        if customer == 'その他メーカー':
            new_customer = st.text_input(f'メーカー名を入力{index}', key=f'new_customer_{index}',
                                         placeholder="メーカー名を入力")

        ##### 作業内容の選択 #####
        # メーカー名の選択が'選択してください'と'雑務'以外ならセレクトボックスを表示。
        if customer not in ('選択してください', '雑務'):
            genre = st.selectbox(
                f'作業内容{index}',
                ('選択してください', '新規', '改修', 'その他', '自動運転'),  # 自動運転を追加
                key=f'genre_{index}')
        else:
            genre = ''  # メーカー名が雑務なら作業内容は空欄にする。
            
　　　　number = '' # 仮定義

        ##### 工番の入力 #####
        # numberに文字列を渡す際に工番のAとaの交じりが無いように.upper()メソッドを使用して入力された文字列を全て大文字に変換している
        if genre != '選択してください':
            number = st.text_input(f'工番を入力{index}', key=f'number_{index}',
            placeholder="例: 51A111").upper()
        else: ''


        ##### 時間入力 #####
        # tryとexceptを使ってエラーの場合の処理を行う。このフォームでは時間の入力を求めるが、
        # 入力された時間の値が数字では無く文字の場合にエラー画面を表示させてPythonのエラーを回避している。
        time_input = st.text_input(f'時間を入力{index}', key=f'time_{index}', placeholder="例: 1.5")
        try:# 入力が空文字でなければ.strip()で空白を削除し、入力された数値をfloatに変換。空文字の場合は0.0を代入。
            time = float(time_input) if time_input.strip() != "" else 0.0

        except ValueError:# 入力された値が数字ではない場合floatに変換できずにPython側でエラー(ValueError)が発生する。
            st.warning(f"時間{index}は数値で入力してください")# そのエラーにst.warningが反応してエラーメッセージを表示する。
            time = 0.0# 入力された値が正しく直されないとエラーが止まらずアプリが落ちる可能性があるので、エラーが出たら0.0を代入してエラーのループを回避している。


        ##### 処理内容のまとめ #####
        # create_input_fields(index)の関数で入力フォームを定義しその中で入力された内容をこの関数の返り値として辞書型にまとめ、
        # 後で行うシートに書き込む処理に呼び出して使う。
        return {
            "customer": customer,
            "new_customer": new_customer,
            "genre": genre,
            "number": number,
            "time": time
        }

    ##### 入力フォームの表示 #####
    # 空のリストを作りそこに入力フォームの番号をループ処理で繰り返し保管していく。
    inputs = []
    for i in range(1, st.session_state.form_count + 1):
        inputs.append(create_input_fields(i))

    ##### 「次へ」ボタン（最大10件） #####
    # 入力フォームの番号が10まで"次へボタン"を表示。"次へボタン"を押すたびにフォームのカウントを＋1。
    if st.session_state.form_count < 10:
        if st.button("次へ"):
            st.session_state.form_count += 1
            st.rerun()
            # "次へボタン"を押すとstreamlitが上から再実行されるが、再描画までに時間がかかるのでst.rerun()を使って即時再描画するようにしている。


    ##### 有効データ抽出 #####
    valid_inputs = []# 有効なデータを集めるための空のリストを作成。ここで集めたデータをシートに書き込みに使う。
    total_time_normal = 0.0# 合計時間をカウントするために使う関数を定義(通常の作業用)
    total_time_auto = 0.0# 自動運転の合計時間用

    # create_input_fields(index)の返り値がinputsに辞書型として返ってくるのでそれをinpに繰り返し代入。
    for inp in inputs:# 各項目ごとに条件をつけて有効データの抽出開始
        if (
            inp["customer"] != "選択してください" # メーカー名が選択されている。
            and inp["genre"] != "選択してください" # 作業内容が選択されている。
            and inp["number"] != '' # 空文字ではない。
            and inp["time"] > 0 # 0より大きい数字が入力されている。
        ):
            if inp["genre"] == "自動運転": # 自動運転が選択されているなら自動運転の合計時間に加算。
                total_time_auto += inp["time"]
            else:
                total_time_normal += inp["time"] # 自動運転以外が選択されているなら通常の合計時間に加算。
            valid_inputs.append(inp)


    ##### 合計時間表示 #####
    # 各合計時間が0より大きいなら合計時間をマークダウンで表示。
    if total_time_normal > 0:
        st.markdown(f"### ✅ 合計時間: {total_time_normal:.2f} 時間")
    if total_time_auto > 0:
        st.markdown(f"### ✅ 合計時間(自動): {total_time_auto:.2f} 時間")


    ##### 送信ボタン #####
    if valid_inputs: # 有効データを集めたリストの中身があるならボタンを表示。
        if st.button("送信"):
            rows_main = [] # シートに書き込む際の行のデータを作るために使う空のリスト(通常の作業用)。
            rows_auto = [] # 自動運転用。このリストに並んだ順番でシートの1列目から書き込む。

            for inp in valid_inputs: # 有効データをシートの書式に合わせて整列してrowに追加する処理をフォームの数の分だけ繰り返す。
                row = [
                    str(day), # 日付を1列目に追加
                    name, # 名前を2列目に追加
                    inp["new_customer"] if inp["customer"] == "その他メーカー" else inp["customer"],
                    # メーカー名がその他メーカーなら自由入力を3列目に追加、その他ではないならメーカー名を3列目に追加
                    "" if inp["customer"] == "雑務" else inp["genre"],
                    # メーカー名が雑務なら空文字を4列目に追加、それ以外なら作業内容を4列目に追加。
                    inp["number"], # 工番を5列目に追加
                    inp["time"] # 時間を6列目に追加
                ]
                if inp["genre"] == "自動運転": # 作業内容が自動運転ならrow(行に対応したデータ)を自動運転用のリストに追加。
                    rows_auto.append(row)
                else:
                    rows_main.append(row) # 作業内容がそれ以外ならrow(行に対応したデータ)を通常の作業用のリストに追加。


            ##### 通常作業シートへの書き込み #####
            if rows_main: # 通常の作業用のリストが空ではないなら処理を開始。
                current_rows = len(sheets["main"].get_all_values()) # ↓
                # シートの最終行を調べるために現在のシートの行を全て取得し最後の行番号を代入(100行あれば100を代入)。

                sheets["main"].append_rows(rows_main) # シートに書き込む処理。
                start_row = current_rows + 1 # 書き込む行番号を計算(上で取得した行数＋1、つまり最終行の1つ下の行番号)
                for i in range(len(rows_main)):
                    if i == len(rows_main) - 1:  # 今回の処理で追加する行の最後の行だけを対象にする(インデックス-1 = 最後)
                        sheets["main"].update_cell(start_row + i, 7, f"合計 {total_time_normal:.2f} 時間")
                        # 最後の行の７列目だけに"合計〇〇時間"の項目を追加して書き込む。


            ##### 自動運転シートへの書き込み #####
            if rows_auto: # 自動運転用のリストが空ではないなら処理を開始。
                sheets["auto"].append_rows(rows_auto)# 自動運転用のシートは最終行に合計時間を書き込まないので、現在のシートの最終行に追加するだけ。

            ##### 書き込み成功の表示 #####
            st.success("作業内容を送信しました。お疲れ様でした！ 🎉")
            st.session_state.form_count = 1 # 書き込み後にフォームのカウントをリセット。

##### プログラムエンド #####
