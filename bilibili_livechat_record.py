"""
# 事前の準備

# chromium-chromedriverのインストール
apt install chromium-chromedriver

# インストールできていれば、ここでバージョンが表示される
chromium-browser --version

# ライブラリのインストール
pip install selenium
pip install beautifulsoup4
"""

from selenium import webdriver
from bs4 import BeautifulSoup
import time
import csv
import os
from datetime import datetime, timezone, timedelta


class ChatNotFoundError(NameError):
    pass


class BilibiliChatRecord:
    """bilibili生放送のチャット欄のコメントを取得する

    Attributes:
        _url (str): bilibili生放送のページのurl
        _driver (webdriver): webdriver
        _chat_item_list_strage (list of dict): チャットデータ
        _timestamp (str): 直近のチャットデータのタイムスタンプ
        _reference_items_count (int): コメントデータの重複を解消するために参照する既存データの数

    Usage:
        # 生放送ページへのアクセス
        chat_record = BilibiliChatRecord()
        url = "https://live.bilibili.com/650"
        chat_record.get("https://live.bilibili.com/650")

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

    注意:
        chat_record.close()を最後に実行しないと、ヘッドレスブラウザが残り続けるため、
        メモリを消費します。
        エラー対策のため、以下のように、try文やコンテキストマネージャを使ってください。

        try:
            chat_record = BilibiliChatRecord()
            chat_record.get(args.url)
            comments, timestamp = chat_record.get_chat_comments()
        finally:
            chat_record.close()
    """

    def __init__(self):
        self._set_webdriver()
        self._chat_item_list_strage = []
        self._timestamp = None
        self._reference_items_count = 500

    def _set_webdriver(self):
        """chromiumのwebdriverを指定してseleniumを使う

        chromium以外のブラウザを使う場合には、overrideする。
        """
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        self._driver = webdriver.Chrome('chromedriver', options=options)

    def close(self):
        """quit webdriver"""
        self._driver.quit()

    def get(self, url):
        """bilibili生放送のページにアクセスする

        Args:
            url (str): https://live.bilibili.com/XXX のような文字列。XXXは一般に数字。
        """
        self._url = url
        self._driver.get(url)

    def get_chat_comments(self, latest_timestamp=None):
        """現時点でのチャットコメントを取得する

        Args:
            latest_timestamp (int or None): 直近のチャット取得時のタイムスタンプ
                latest_timestampよりも新しいコメントのみを取得する。

        Returns:
            chat_item_list (list of dicts): チャットデータのリスト
            latest_timestamp (int): チャット取得時のタイムスタンプ
        """
        soup = BeautifulSoup(self._driver.page_source, "lxml")
        chat = soup.find(id="chat-history-list")
        if not chat:
            raise ChatNotFoundError("#chat-history-list 要素がありません")
        chat_items = chat.find_all(class_="chat-item")
        if not chat_items:
            raise ChatNotFoundError(".chat-item 要素がありません")

        chat_item_list = []
        for chat_item in chat_items:
            d = {}
            timestamp = chat_item.get("data-ts")
            # チャット欄にはコメントではないものもある(入室メッセージなど)
            # コメント以外にはタイムスタンプはつかない
            # コメント以外なら次のループへ
            if not timestamp:
                continue
            timestamp = int(timestamp)
            # 前回のタイムスタンプより古ければ次のループへ
            if latest_timestamp:
                if timestamp < latest_timestamp:
                    continue

            d["timestamp"] = timestamp  # コメントが流れた時刻(unix timestamp)
            d["data_ct"] = chat_item.get("data-ct")  # コメントのuniqueなID
            d["data_uname"] = chat_item.get("data-uname")  # ユーザー名
            d["data_danmaku"] = chat_item.get("data-danmaku")  # コメント
            d["data_uid"] = chat_item.get("data-uid")  # ユーザーID

            chat_item_list.append(d)

        if len(chat_item_list):
            latest_timestamp = chat_item_list[-1]["timestamp"]
        return chat_item_list, latest_timestamp

    @staticmethod
    def _drop_duplicated_items(chat_item_list, reference_list, unique_key="data_ct"):
        """chat_item_listの要素のうち、reference_listと重複したものを除外して返す

        Args:
            chat_item_list (list of dict): 重複がないかチェックするリスト
            reference_list (list of dict): リファレンスのリスト
            unique_key (str): unique_keyの値に関して重複を確認する

        Returns:
            chat_item_list (list of dict): reference_listとの重複が解消されたリスト
        """
        if not reference_list:
            return chat_item_list

        latest_data_ct_list = [chat_item[unique_key]
                               for chat_item in reference_list]
        chat_item_list = [chat_item for chat_item in chat_item_list
                          if chat_item[unique_key] not in latest_data_ct_list]
        return chat_item_list

    def loop_chat_comment_retrieval(self, max_loop_count=10, interval=5,
                                    reset_timestamp=True,
                                    store_chat_data=True,
                                    write_data_to_file=True,
                                    path_to_file="chatdata.csv"):
        """チャットデータを連続的に取得し続ける。

        Args:
            max_loop_count (int): データ取得の回数
            interval (int): データ取得一回あたりのインターバル(秒単位)
            reset_timestamp (bool): 前回セットされたタイムスタンプ以降のデータのみ取得する
            store_chat_data (bool): データをself._chat_item_list_strageで保持する
            write_data_to_file (bool): データをファイルに書き出す
            path_to_file (str): データを書き出すファイルのパス
        """
        if reset_timestamp:
            self._timestamp = None

        for i in range(max_loop_count):
            chat_item_list, self._timestamp = self.get_chat_comments(
                self._timestamp)

            chat_item_list = self._drop_duplicated_items(
                chat_item_list, self._chat_item_list_strage[-self._reference_items_count:], unique_key="data_ct")

            if store_chat_data:
                self._chat_item_list_strage.extend(chat_item_list)
            if write_data_to_file and len(chat_item_list):
                self._write_chatdata(chat_item_list, path_to_file)
            time.sleep(interval)

    def _write_chatdata(self, chat_item_list, path_to_file="chatdata.csv"):
        """チャットデータをcsvファイルに書き出す。

        ファイルパスにファイルが存在しない場合、新規にファイルを作成し、
        ヘッダーをと共にデータを書き出す。
        すでにファイルが存在する場合、ヘッダーを書き出さずにデータを追記する。

        Args:
            chat_item_list (list of dicts): チャットデータのリスト
            path_to_file (str): ファイルパス
        """
        if os.path.exists(path_to_file):
            self._write_list_of_dict_to_csv(
                chat_item_list, path_to_file, writeheader=False, mode="a")
        else:
            self._write_list_of_dict_to_csv(
                chat_item_list, path_to_file, writeheader=True, mode="w")

    @staticmethod
    def _write_list_of_dict_to_csv(list_of_dict, path_to_file, writeheader=True, mode="w"):
        """dictのlistをcsvファイルに書き出す"""
        keys = list_of_dict[0].keys()
        with open(path_to_file, mode) as f:
            w = csv.DictWriter(f, keys)
            if writeheader:
                w.writeheader()
            w.writerows(list_of_dict)

    def show_chat_item_strage(self):
        """loop_chat_comment_retrieval(store_chat_data=True)で保存したデータを返す"""
        return self._chat_item_list_strage

    @staticmethod
    def convert_unix_timestamp_to_datetime(unix_timestamp, hours_difference=9,
                                           timezone_name="JST", format_str="%Y-%m-%d_%H:%M"):
        """タイムスタンプをdatetimeに変換"""
        time_zone = timezone(timedelta(hours=hours_difference), timezone_name)
        return datetime.fromtimestamp(unix_timestamp, tz=time_zone).strftime(format_str)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        prog="bilibili生放送のチャットデータを取得する",
        usage="bilibili_livechat_record.py --url 生放送ページのurl",
        description="bilibili生放送のチャットデータを取得する",
        add_help=True
    )
    parser.add_argument("-u", "--url",  # オプション引数
                        help="bilibili生放送のwebページのurl。https://live.bilibili.com/XXX のような文字列。XXXは一般に数字。",
                        type=str,
                        required=True  # 引数の省略を不可にする
                        )
    args = parser.parse_args()

    try:
        chat_record = BilibiliChatRecord()
        chat_record.get(args.url)
        comments, timestamp = chat_record.get_chat_comments()
    finally:
        chat_record.close()

    print(comments)
    if timestamp:
        print("最後のコメントの取得日時は{}".format(
            chat_record.convert_unix_timestamp_to_datetime(timestamp)))
