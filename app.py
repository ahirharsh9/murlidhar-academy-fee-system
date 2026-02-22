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
        st.session_state.authenticated = False

    login_time = st.session_state.get("login_time", None)

    if st.session_state.authenticated and login_time:
        if datetime.now() - login_time > timedelta(minutes=30):
            st.session_state.authenticated = False
            st.session_state.login_time = None
            st.warning("Session Expired. Login Again.")
            st.stop()

    if not st.session_state.authenticated:
        password = st.text_input("Enter Password", type="password")
        if st.button("Login"):
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.session_state.login_time = datetime.now()
                st.rerun()
            else:
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
    numbers = [int(p["Receipt_No"].split("-")[-1])
               for p in payments if str(p["Year"]) == str(year)]
    next_no = max(numbers)+1 if numbers else 1
    return f"MA-{year}-{str(next_no).zfill(4)}"

# ===================== PDF =====================

def generate_pdf(data_dict):

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>MURLIDHAR ACADEMY</b>", styles["Title"]))
    elements.append(Spacer(1, 20))

    table = Table([[k, v] for k, v in data_dict.items()], colWidths=[220, 300])
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))

    elements.append(table)
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("Authorized Signature", styles["Normal"]))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ===================== MAIN =====================

st.title("Murlidhar Academy Fee System")

menu = st.sidebar.selectbox("Select Option",
                            ["New Payment / Admission",
                             "Student Search",
                             "Monthly Dashboard"])

# ===================== NEW PAYMENT / ADMISSION =====================

if menu == "New Payment / Admission":

    st.header("Student Payment System")

    phone = st.text_input("Student Phone (10 digit)")

    students = get_students()
    payments = get_payments()

    student = next((s for s in students if str(s["Student_Phone"]) == phone), None)

    # -------- IF NEW STUDENT --------
    if phone and not student:

        st.subheader("New Admission Form")

        name = st.text_input("Student Name")
        parent_phone = st.text_input("Parent Phone")
        address = st.text_area("Address")
        course = st.text_input("Course")
        batch = st.text_input("Batch")
        total_fees = st.number_input("Total Fees", min_value=0.0)
        duration = st.number_input("Course Duration (Months)", min_value=1)
        start_date = st.date_input("Course Start Date")

        payment_amount = st.number_input("First Payment", min_value=0.0)
        payment_mode = st.selectbox("Payment Mode", ["Cash", "UPI", "Bank"])
        next_due_date = st.date_input("Next Due Date")

        if st.button("Create Admission & Generate Receipt"):

            student_id = "STU-" + str(uuid.uuid4())[:8]
            end_date = start_date + relativedelta(months=duration)
            admission_date = datetime.today()

            students_sheet.append_row([
                student_id,
                name,
                phone,
                parent_phone,
                address,
                course,
                batch,
                total_fees,
                duration,
                start_date.strftime("%d-%m-%Y"),
                end_date.strftime("%d-%m-%Y"),
                admission_date.strftime("%d-%m-%Y"),
                "Active"
            ])

            remaining = total_fees - payment_amount
            receipt_no = generate_receipt_number()

            payments_sheet.append_row([
                receipt_no,
                student_id,
                phone,
                admission_date.strftime("%d-%m-%Y"),
                payment_amount,
                payment_mode,
                1,
                payment_amount,
                remaining,
                next_due_date.strftime("%d-%m-%Y"),
                datetime.now().year
            ])

            pdf = generate_pdf({
                "Receipt No": receipt_no,
                "Student Name": name,
                "Course": course,
                "Paid Now": f"₹{payment_amount}",
                "Remaining": f"₹{remaining}",
                "Amount in Words": num2words(payment_amount).title() + " Rupees Only"
            })

            st.success("Admission Created Successfully")
            st.download_button("Download Receipt", pdf, f"{receipt_no}.pdf")

    # -------- EXISTING STUDENT --------
    elif student:

        st.success("Existing Student Found")
        st.write(student)

        total_paid_before = sum(float(p["Payment_Amount"])
                                for p in payments
                                if str(p["Student_Phone"]) == phone)

        total_fees = float(student["Total_Fees"])
        remaining_before = total_fees - total_paid_before

        st.info(f"Remaining Before Payment: ₹{remaining_before}")

        payment_amount = st.number_input("Payment Amount", min_value=0.0)
        payment_mode = st.selectbox("Payment Mode", ["Cash", "UPI", "Bank"])
        next_due_date = st.date_input("Next Due Date")

        if st.button("Generate Receipt"):

            remaining_after = remaining_before - payment_amount

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

            pdf = generate_pdf({
                "Receipt No": receipt_no,
                "Student Name": student["Student_Name"],
                "Installment No": installment_no,
                "Paid Now": f"₹{payment_amount}",
                "Remaining": f"₹{remaining_after}",
                "Amount in Words": num2words(payment_amount).title() + " Rupees Only"
            })

            st.success("Payment Recorded Successfully")
            st.download_button("Download Receipt", pdf, f"{receipt_no}.pdf")

# ===================== MONTHLY DASHBOARD =====================

elif menu == "Monthly Dashboard":

    payments = pd.DataFrame(get_payments())

    if not payments.empty:
        payments["Payment_Date"] = pd.to_datetime(payments["Payment_Date"], format="%d-%m-%Y")
        payments["Month"] = payments["Payment_Date"].dt.to_period("M")
        monthly = payments.groupby("Month")["Payment_Amount"].sum().reset_index()
        st.line_chart(monthly.set_index("Month"))
        st.dataframe(monthly)
