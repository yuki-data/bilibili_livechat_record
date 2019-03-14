# Bilibili Live Chat Recorder
ビリビリ動画という動画配信サイトでの生放送でチャット欄のコメントを取得するスクリプトです。
チャット欄のコメントのデータを取得してからcsvファイルに保存します。

Python言語で書かれています。

利用には、MITライセンスを適用します。

## 使い方
### 事前準備
chromium-chromedriverのインストール

    apt install chromium-chromedriver


必要ライブラリのインストール

    pip install selenium
    pip install beautifulsoup4

### データの取得
生放送ページのurlが"https://live.bilibili.com/XXX"だった場合、以下のように使います。

    # 生放送ページへのアクセス
    chat_record = BilibiliChatRecord()
    url = "https://live.bilibili.com/650"
    chat_record.get("https://live.bilibili.com/XXX")

    # 現時点でのチャットデータの取得
    comments, timestamp = chat_record.get_chat_comments()

    # 一定時間チャットデータを取得し続ける
    # 3秒間隔で20回データを取得し、data.csvにデータを保存する
    chat_record.loop_chat_comment_retrieval(max_loop_count=20, interval=3, path_to_file="data.csv")

    # データ取得を再開し、すでに取得したデータは再取得しない
    chat_record.loop_chat_comment_retrieval(max_loop_count=20, interval=3,
                                            path_to_file="data.csv",
                                            reset_timestamp=False)
    # driverを終了する
    chat_record.close()
