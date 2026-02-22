import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from num2words import num2words
import qrcode
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import styles
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from io import BytesIO
import urllib.parse

# ---------------- PASSWORD LOGIN ----------------

def check_login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        password = st.text_input("Enter Password", type="password")
        if st.button("Login"):
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Wrong Password")
        st.stop()

check_login()

st.title("Murlidhar Academy Fee System")

# ---------------- GOOGLE SHEET CONNECTION ----------------

scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["sheets"], scope)

client = gspread.authorize(creds)
sheet = client.open(st.secrets["SHEET_NAME"])

students_sheet = sheet.worksheet("Students_Master")
payments_sheet = sheet.worksheet("Payments")

# ---------------- FORM ----------------

st.header("New Payment Entry")

name = st.text_input("Student Name")
phone = st.text_input("Student Phone")
parent_phone = st.text_input("Parent Phone")
address = st.text_area("Address")
course = st.text_input("Course Name")
duration = st.number_input("Course Duration (Months)", min_value=1)
total_fees = st.number_input("Total Course Fees", min_value=0)
payment_amount = st.number_input("Payment Amount", min_value=0)
mode = st.selectbox("Payment Mode", ["Cash", "UPI", "Bank"])

today = datetime.today()
payment_date = st.date_input("Payment Date", today)
due_date = st.date_input("Next Installment Due Date", today + relativedelta(months=1))

if st.button("Generate Receipt"):

    if payment_amount > total_fees:
        st.error("Payment cannot exceed total fees.")
        st.stop()

    receipt_no = f"MA-{today.year}-001"

    total_paid = payment_amount
    remaining = total_fees - total_paid

    # Save to Google Sheet (Simple initial version)
    students_sheet.append_row([
        "STU-001",
        name,
        phone,
        parent_phone,
        address,
        course,
        "",
        total_fees,
        duration,
        payment_date.strftime("%d-%m-%Y"),
        (payment_date + relativedelta(months=duration)).strftime("%d-%m-%Y"),
        payment_date.strftime("%d-%m-%Y"),
        "Active"
    ])

    payments_sheet.append_row([
        receipt_no,
        "STU-001",
        phone,
        payment_date.strftime("%d-%m-%Y"),
        payment_amount,
        mode,
        1,
        total_paid,
        remaining,
        due_date.strftime("%d-%m-%Y"),
        today.year
    ])

    # ----------- GENERATE PDF -----------

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    style = styles.getSampleStyleSheet()

    elements.append(Paragraph("<b>MURLIDHAR ACADEMY</b>", style['Title']))
    elements.append(Spacer(1, 12))

    data = [
        ["Student Name:", name],
        ["Phone:", phone],
        ["Course:", course],
        ["Installment:", "1"],
        ["Total Fees:", f"₹{total_fees}"],
        ["Paid:", f"₹{payment_amount}"],
        ["Remaining:", f"₹{remaining}"],
        ["Due Date:", due_date.strftime("%d-%m-%Y")]
    ]

    table = Table(data)
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)

    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    st.download_button(
        label="Download Receipt PDF",
        data=pdf,
        file_name="receipt.pdf",
        mime="application/pdf"
    )

    # WhatsApp Message
    message = f"""
Hello {name},

Receipt No: {receipt_no}
Total Fees: ₹{total_fees}
Paid: ₹{payment_amount}
Remaining: ₹{remaining}
Due Date: {due_date.strftime("%d-%m-%Y")}

Regards,
Murlidhar Academy
"""

    encoded = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/91{phone}?text={encoded}"

    st.markdown(f"[Send to Student WhatsApp]({whatsapp_url})")

    st.success("Receipt Generated Successfully")
