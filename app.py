import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dateutil.relativedelta import relativedelta
from num2words import num2words
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from io import BytesIO
import urllib.parse

# ---------------- LOGIN ----------------

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

# ---------------- GOOGLE SHEET ----------------

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["sheets"], scope)

client = gspread.authorize(creds)
sheet = client.open_by_key(st.secrets["SHEET_ID"])

students_sheet = sheet.worksheet("Students_Master")
payments_sheet = sheet.worksheet("Payments")

# ---------------- HELPER FUNCTIONS ----------------

def generate_receipt_number():
    records = payments_sheet.get_all_records()
    current_year = datetime.now().year
    year_records = [r for r in records if str(current_year) in str(r["Year"])]

    if not year_records:
        return f"MA-{current_year}-0001"

    last_receipt = year_records[-1]["Receipt_No"]
    last_number = int(last_receipt.split("-")[-1])
    new_number = str(last_number + 1).zfill(4)
    return f"MA-{current_year}-{new_number}"

def get_student(phone):
    records = students_sheet.get_all_records()
    for r in records:
        if r["Student_Phone"] == phone:
            return r
    return None

def calculate_total_paid(phone):
    records = payments_sheet.get_all_records()
    total = 0
    for r in records:
        if r["Student_Phone"] == phone:
            total += float(r["Payment_Amount"])
    return total

# ---------------- FORM ----------------

st.header("New Payment Entry")

name = st.text_input("Student Name")
phone = st.text_input("Student Phone")
parent_phone = st.text_input("Parent Phone")
address = st.text_area("Address")
course = st.text_input("Course Name")
duration = st.number_input("Course Duration (Months)", min_value=1)
total_fees = st.number_input("Total Course Fees", min_value=0.0)
payment_amount = st.number_input("Payment Amount", min_value=0.0)
mode = st.selectbox("Payment Mode", ["Cash", "UPI", "Bank"])

today = datetime.today()
payment_date = st.date_input("Payment Date", today)
due_date = st.date_input("Next Installment Due Date", today + relativedelta(months=1))

if st.button("Generate Receipt"):

    existing_student = get_student(phone)

    if existing_student:
        total_paid = calculate_total_paid(phone)
        remaining = float(existing_student["Total_Fees"]) - total_paid
        installment_no = len([r for r in payments_sheet.get_all_records() if r["Student_Phone"] == phone]) + 1
    else:
        total_paid = 0
        remaining = total_fees
        installment_no = 1

    if payment_amount > remaining:
        st.error("Payment cannot exceed remaining fees.")
        st.stop()

    receipt_no = generate_receipt_number()
    total_paid += payment_amount
    remaining -= payment_amount

    # Save new student if not exist
    if not existing_student:
        start_date = payment_date
        end_date = start_date + relativedelta(months=duration)

        students_sheet.append_row([
            f"STU-{phone[-4:]}",
            name,
            phone,
            parent_phone,
            address,
            course,
            "",
            total_fees,
            duration,
            start_date.strftime("%d-%m-%Y"),
            end_date.strftime("%d-%m-%Y"),
            start_date.strftime("%d-%m-%Y"),
            "Active"
        ])

    # Save payment
    payments_sheet.append_row([
        receipt_no,
        f"STU-{phone[-4:]}",
        phone,
        payment_date.strftime("%d-%m-%Y"),
        payment_amount,
        mode,
        installment_no,
        total_paid,
        remaining,
        due_date.strftime("%d-%m-%Y"),
        today.year
    ])

    # -------- PDF --------
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>MURLIDHAR ACADEMY</b>", styles["Title"]))
    elements.append(Spacer(1, 20))

    data = [
        ["Receipt No", receipt_no],
        ["Student Name", name],
        ["Phone", phone],
        ["Course", course],
        ["Installment No", installment_no],
        ["Total Fees", f"₹{total_fees}"],
        ["Paid Now", f"₹{payment_amount}"],
        ["Total Paid", f"₹{total_paid}"],
        ["Remaining", f"₹{remaining}"],
        ["Next Due Date", due_date.strftime("%d-%m-%Y")]
    ]

    table = Table(data, colWidths=[200, 250])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()

    st.download_button(
        "Download Receipt",
        pdf,
        file_name=f"{receipt_no}.pdf",
        mime="application/pdf"
    )

    message = f"""
Hello {name},

Receipt No: {receipt_no}
Total Fees: ₹{total_fees}
Paid: ₹{payment_amount}
Remaining: ₹{remaining}
Next Due Date: {due_date.strftime("%d-%m-%Y")}

Regards,
Murlidhar Academy
"""

    encoded = urllib.parse.quote(message)
    st.markdown(f"[Send to WhatsApp](https://wa.me/91{phone}?text={encoded})")

    st.success("Receipt Generated Successfully")
