# homes登記連携アプリ - Streamlit
# バージョン：v1.0（Google Sheets対応 / HOMES＋登記PDF解析）

import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
import re
import datetime
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------
# Streamlit UI（初期設定）
# -----------------------------
st.set_page_config(page_title="HOMES登記連携アプリ", layout="wide")
st.title("🏠 HOMES×登記簿 自動スプレッド記入アプリ")

# -----------------------------
# Google Sheets認証設定
# -----------------------------
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# secrets.tomlで定義された認証情報を使用
credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPE
)
gc = gspread.authorize(credentials)
SPREADSHEET_URL = st.secrets["other"]["spreadsheet_url"]
sh = gc.open_by_url(SPREADSHEET_URL)
ws = sh.sheet1

# -----------------------------
# 機能：PDFから情報抽出
# -----------------------------
def extract_pdf_data(uploaded_file):
    text = fitz.open(stream=uploaded_file.read(), filetype="pdf").get_page_text(0)

    # オーナー名
    owner_match = re.search(r"所有者[\s\S]+?\n\s*(.+?)\s*\n", text)
    owner = owner_match.group(1).strip() if owner_match else "❌（自動取得不可）"

    # 号室
    room_match = re.search(r"家屋番号.*?の(\d{3})", text)
    room = room_match.group(1) if room_match else "❌"

    # 床面積（例：２３：１８）
    floor_match = re.search(r"床\s*面\s*積[\s\S]+?(\d{1,3})[:：](\d{2})", text)
    floor_area = f"{floor_match.group(1)}.{floor_match.group(2)}" if floor_match else "❌"

    # 敷地権割合 → 専有面積計算用
    shikichi = re.search(r"敷地権.+?(\d{2,6})分の(\d{2,6})", text)
    if shikichi:
        numerator = int(shikichi.group(2))
        exclusive_area = round(numerator / 100, 2)
    else:
        exclusive_area = "❌"

    # 借入額・借入日
    loan_amt = re.search(r"債権額\s*金([\d，,]+)万円", text)
    loan_date = re.search(r"金銭消費貸借.*?(令和|平成)(\d+)年(\d+)月(\d+)日", text)

    if loan_amt:
        amount = int(loan_amt.group(1).replace("，", "").replace(",", ""))
    else:
        amount = None

    if loan_date:
        era = loan_date.group(1)
        year = int(loan_date.group(2)) + (2018 if era == "平成" else 0)
        if era == "令和": year += 2018  # 令和元年=2019
        dt = datetime.date(year, int(loan_date.group(3)), int(loan_date.group(4)))
    else:
        dt = None

    return owner, room, floor_area, exclusive_area, amount, dt

# -----------------------------
# 機能：HOMES URLから物件情報を取得
# -----------------------------
def extract_homes_data(url):
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.content, "html.parser")
        text = soup.get_text()

        # 物件名
        title_tag = soup.find("h1")
        name = title_tag.get_text().strip() if title_tag else "❌"

        # 所在地
        addr_match = re.search(r"所在地\s*：\s*(東京都.+?)\n", text)
        address = addr_match.group(1).strip() if addr_match else "❌"

        # 駅情報（2つまで）
        stations = re.findall(r"(.+?)駅\s*徒歩(\d+)分", text)
        station1 = f"{stations[0][0]}駅 徒歩{stations[0][1]}分" if len(stations) > 0 else "❌"
        station2 = f"{stations[1][0]}駅 徒歩{stations[1][1]}分" if len(stations) > 1 else "❌"

        # 階建て
        floor_match = re.search(r"階建て\s*：\s*(\d+)階建", text)
        floors = floor_match.group(1) if floor_match else "❌"

        # 総戸数
        units_match = re.search(r"総戸数\s*：\s*(\d+)戸", text)
        total_units = units_match.group(1) if units_match else "❌"

        return name, address, station1, station2, floors, total_units
    except:
        return "❌", "❌", "❌", "❌", "❌", "❌"

# -----------------------------
# UI：ファイル・URL入力欄
# -----------------------------
with st.form("entry_form"):
    homes_url = st.text_input("HOMESのURLを入力")
    uploaded_pdf = st.file_uploader("登記簿謄本のPDFをアップロード", type="pdf")
    submit = st.form_submit_button("スプレッドシートに書き込む")

if submit and homes_url and uploaded_pdf:
    with st.spinner("情報を抽出中..."):
        owner, room, floor_area, exclusive_area, loan_amount, loan_date = extract_pdf_data(uploaded_pdf)
        name, address, station1, station2, floors, total_units = extract_homes_data(homes_url)

        # 結果をスプレッドシートに書き込み（例：A2～などは調整可）
        ws.update("A2", [[owner]])
        ws.update("D2", [[name]])
        ws.update("J2", [[room]])
        ws.update("E7", [[floor_area]])
        ws.update("F7", [[exclusive_area]])
        ws.update("H7", [[total_units]])
        ws.update("J7", [[floors]])
        ws.update("D12", [[station1]])
        ws.update("H12", [[station2]])
        ws.update("D17", [[address]])
        st.success("✅ スプレッドシートに書き込みました！")
