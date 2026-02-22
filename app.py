import streamlit as st
import gspread
import qrcode
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dateutil.relativedelta import relativedelta
from num2words import num2words
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
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

menu = st.sidebar.selectbox(
    "Select Option",
    ["New Payment", "Student Search", "All-Time Report"]
)

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

# ---------------- HELPERS ----------------

def generate_receipt_number():
    records = payments_sheet.get_all_records()
    current_year = datetime.now().year
    year_records = [r for r in records if str(r["Year"]) == str(current_year)]

    if not year_records:
        return f"MA-{current_year}-0001"

    last_receipt = year_records[-1]["Receipt_No"]
    last_number = int(last_receipt.split("-")[-1])
    return f"MA-{current_year}-{str(last_number+1).zfill(4)}"

def get_student(phone):
    records = students_sheet.get_all_records()
    for r in records:
        if str(r["Student_Phone"]).strip() == str(phone).strip():
            return r
    return None

def calculate_total_paid(phone):
    records = payments_sheet.get_all_records()
    return sum(float(r["Payment_Amount"]) for r in records if str(r["Student_Phone"]) == str(phone))

def update_student_status():
    records = students_sheet.get_all_records()
    today = datetime.today()
    for idx, r in enumerate(records, start=2):
        if r["Course_End_Date"]:
            end_date = datetime.strptime(r["Course_End_Date"], "%d-%m-%Y")
            status = "Active" if today <= end_date else "Deactive"
            students_sheet.update_cell(idx, 13, status)

update_student_status()

# =====================================================
# ================= NEW PAYMENT =======================
# =====================================================

if menu == "New Payment":

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

        existing = get_student(phone)

        if existing:
            total_paid = calculate_total_paid(phone)
            remaining = float(existing["Total_Fees"]) - total_paid
            installment_no = len([r for r in payments_sheet.get_all_records() if str(r["Student_Phone"]) == str(phone)]) + 1
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

        if not existing:
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

        # PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("<b>MURLIDHAR ACADEMY</b>", styles["Title"]))
        elements.append(Spacer(1, 20))

        amount_words = num2words(payment_amount, to='cardinal', lang='en').title()

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
            ["Next Due Date", due_date.strftime("%d-%m-%Y")],
            ["Amount in Words", amount_words + " Rupees Only"]
        ]

        table = Table(data, colWidths=[200, 300])
        table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.grey)]))
        elements.append(table)
        elements.append(Spacer(1, 30))

        qr_data = f"Receipt: {receipt_no}\nStudent: {name}\nRemaining: {remaining}"
        qr = qrcode.make(qr_data)
        qr_buffer = BytesIO()
        qr.save(qr_buffer)
        qr_buffer.seek(0)
        elements.append(Image(qr_buffer, width=120, height=120))

        doc.build(elements)
        pdf = buffer.getvalue()

        st.download_button("Download Receipt", pdf, f"{receipt_no}.pdf")

# =====================================================
# ================= STUDENT SEARCH ====================
# =====================================================

elif menu == "Student Search":

    st.header("Student Search")

    search_phone = st.text_input("Enter Student Phone")

    if st.button("Search"):

        student = get_student(search_phone)

        if not student:
            st.error("Student Not Found")
        else:
            st.write(student)

            payments = payments_sheet.get_all_records()
            student_payments = [p for p in payments if str(p["Student_Phone"]) == str(search_phone)]

            st.subheader("Payment History")
            st.table(student_payments)

            total_paid = sum(float(p["Payment_Amount"]) for p in student_payments)
            total_fees = float(student["Total_Fees"])
            remaining = total_fees - total_paid

            st.success(f"Total Paid: ₹{total_paid}")
            st.warning(f"Remaining: ₹{remaining}")

            if remaining > 0:
                msg = f"Hello {student['Student_Name']},\nRemaining Fees: ₹{remaining}"
                url = f"https://wa.me/91{search_phone}?text={urllib.parse.quote(msg)}"
                st.markdown(f"[Send WhatsApp Reminder]({url})")

# =====================================================
# ================= ALL TIME REPORT ===================
# =====================================================

elif menu == "All-Time Report":

    students = students_sheet.get_all_records()
    payments = payments_sheet.get_all_records()

    total_collection = sum(float(p["Payment_Amount"]) for p in payments)

    total_students = len(students)
    active_students = len([s for s in students if s["Status"] == "Active"])
    deactive_students = total_students - active_students

    total_pending = 0
    report_data = []

    for student in students:
        phone = student["Student_Phone"]
        total_paid = sum(float(p["Payment_Amount"]) for p in payments if str(p["Student_Phone"]) == str(phone))
        total_fees = float(student["Total_Fees"])
        remaining = total_fees - total_paid
        total_pending += remaining

        report_data.append({
            "Name": student["Student_Name"],
            "Phone": phone,
            "Course": student["Course"],
            "Paid": total_paid,
            "Remaining": remaining,
            "Status": student["Status"]
        })

    st.subheader("Dashboard Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Students", total_students)
    col2.metric("Active Students", active_students)
    col3.metric("Total Collection", f"₹{total_collection}")

    st.metric("Total Pending Amount", f"₹{total_pending}")

    st.subheader("All Students")
    st.table(report_data)

    st.subheader("Pending Students Only")
    pending_only = [r for r in report_data if r["Remaining"] > 0]
    st.table(pending_only)
