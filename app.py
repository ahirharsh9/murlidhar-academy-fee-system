import streamlit as st
import gspread
import uuid
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from num2words import num2words
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from io import BytesIO
import pandas as pd

# ===================== SECURE LOGIN =====================

def secure_login():

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["login_attempts"] = 0
        st.session_state["login_time"] = None

    if st.session_state["authenticated"] and st.session_state["login_time"] is not None:
        if datetime.now() - st.session_state["login_time"] > timedelta(minutes=30):
            st.session_state["authenticated"] = False
            st.warning("Session Expired. Login Again.")
            st.stop()

    if not st.session_state["authenticated"]:

        password = st.text_input("Enter Password", type="password")

        if st.button("Login"):

            if st.session_state["login_attempts"] >= 5:
                st.error("Too many attempts. Restart App.")
                st.stop()

            if password == st.secrets["APP_PASSWORD"]:
                st.session_state["authenticated"] = True
                st.session_state["login_time"] = datetime.now()
                st.rerun()
            else:
                st.session_state["login_attempts"] += 1
                st.error("Wrong Password")

        st.stop()

secure_login()

# ===================== GOOGLE SHEETS =====================

scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["sheets"], scope)

client = gspread.authorize(creds)
sheet = client.open_by_key(st.secrets["SHEET_ID"])

students_sheet = sheet.worksheet("Students_Master")
payments_sheet = sheet.worksheet("Payments")

@st.cache_data(ttl=60)
def get_students():
    return students_sheet.get_all_records()

@st.cache_data(ttl=60)
def get_payments():
    return payments_sheet.get_all_records()

# ===================== RECEIPT NUMBER =====================

def generate_receipt_number():
    payments = get_payments()
    year = datetime.now().year
    numbers = []

    for p in payments:
        if str(p["Year"]) == str(year):
            numbers.append(int(p["Receipt_No"].split("-")[-1]))

    next_no = max(numbers)+1 if numbers else 1
    return f"MA-{year}-{str(next_no).zfill(4)}"

# ===================== PDF =====================

def generate_pdf(data_dict):

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>MURLIDHAR ACADEMY</b>", styles["Title"]))
    elements.append(Paragraph("Junagadh | Contact: 9999999999", styles["Normal"]))
    elements.append(Spacer(1, 20))

    table = Table([[k, v] for k, v in data_dict.items()], colWidths=[220, 300])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))

    elements.append(table)
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("Authorized Signature", styles["Normal"]))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    return pdf

# ===================== MAIN =====================

st.title("Murlidhar Academy Professional Fee System")

menu = st.sidebar.selectbox(
    "Select Option",
    ["New Payment", "Student Search", "Monthly Dashboard"]
)

# ===================== NEW PAYMENT =====================

if menu == "New Payment":

    st.header("New Payment Entry")

    phone = st.text_input("Student Phone (10 digit)")
    payment_amount = st.number_input("Payment Amount", min_value=0.0)
    payment_mode = st.selectbox("Payment Mode", ["Cash", "UPI", "Bank"])
    next_due_date = st.date_input("Next Due Date")

    if st.button("Generate Receipt"):

        students = get_students()
        payments = get_payments()

        student = next((s for s in students if str(s["Student_Phone"]) == phone), None)

        if not student:
            st.error("Student Not Found in Master Sheet")
            st.stop()

        total_paid_before = sum(float(p["Payment_Amount"])
                                for p in payments
                                if str(p["Student_Phone"]) == phone)

        total_fees = float(student["Total_Fees"])
        remaining_after = total_fees - total_paid_before - payment_amount

        if remaining_after < 0:
            st.error("Payment exceeds remaining amount")
            st.stop()

        installment_no = len([p for p in payments if str(p["Student_Phone"]) == phone]) + 1

        receipt_no = generate_receipt_number()

        payments_sheet.append_row([
            receipt_no,
            student["Student_ID"],
            phone,
            datetime.today().strftime("%d-%m-%Y"),
            payment_amount,
            payment_mode,
            installment_no,
            total_paid_before + payment_amount,
            remaining_after,
            next_due_date.strftime("%d-%m-%Y"),
            datetime.now().year
        ])

        data = {
            "Receipt No": receipt_no,
            "Student Name": student["Student_Name"],
            "Course": student["Course"],
            "Installment No": installment_no,
            "Paid Now": f"₹{payment_amount}",
            "Total Paid Till Date": f"₹{total_paid_before + payment_amount}",
            "Remaining": f"₹{remaining_after}",
            "Next Due Date": next_due_date.strftime("%d-%m-%Y"),
            "Amount in Words": num2words(payment_amount).title() + " Rupees Only"
        }

        pdf = generate_pdf(data)

        st.success("Payment Recorded Successfully")
        st.download_button("Download Receipt", pdf, f"{receipt_no}.pdf")

# ===================== STUDENT SEARCH =====================

elif menu == "Student Search":

    st.header("Student Search")

    search_phone = st.text_input("Enter Student Phone")

    if st.button("Search"):

        students = get_students()
        payments = get_payments()

        student = next((s for s in students if str(s["Student_Phone"]) == search_phone), None)

        if not student:
            st.error("Student Not Found")
        else:
            st.write(student)
            student_payments = [p for p in payments if str(p["Student_Phone"]) == search_phone]
            st.table(student_payments)

# ===================== MONTHLY DASHBOARD =====================

elif menu == "Monthly Dashboard":

    st.header("Monthly Collection Dashboard")

    payments = pd.DataFrame(get_payments())

    if payments.empty:
        st.warning("No Data Available")
    else:
        payments["Payment_Date"] = pd.to_datetime(payments["Payment_Date"], format="%d-%m-%Y")
        payments["Month"] = payments["Payment_Date"].dt.to_period("M")
        monthly = payments.groupby("Month")["Payment_Amount"].sum().reset_index()

        st.line_chart(monthly.set_index("Month"))
        st.dataframe(monthly)
