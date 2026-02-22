import streamlit as st
import gspread
import uuid
import urllib.parse
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from num2words import num2words
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from io import BytesIO
import pandas as pd

# ================= LOGIN =================

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

# ================= GOOGLE SHEET =================

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

# ================= RECEIPT NUMBER =================

def generate_receipt_number():
    payments = get_payments()
    year = datetime.now().year
    nums = [int(p["Receipt_No"].split("-")[-1])
            for p in payments if str(p["Year"]) == str(year)]
    next_no = max(nums)+1 if nums else 1
    return f"MA-{year}-{str(next_no).zfill(4)}"

# ================= BRANDED PDF =================

def generate_pdf(data):

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        name='Header',
        parent=styles['Title'],
        textColor=colors.white,
        backColor=colors.red
    )

    elements.append(Paragraph("MURLIDHAR ACADEMY", header_style))
    elements.append(Paragraph("Junagadh | Contact: 9999999999", styles["Normal"]))
    elements.append(Spacer(1, 20))

    table = Table([[k, v] for k, v in data.items()], colWidths=[220, 300])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.red),
        ('BACKGROUND', (0,0), (-1,0), colors.yellow)
    ]))

    elements.append(table)
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("Authorized Signature", styles["Normal"]))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ================= MAIN =================

st.title("Murlidhar Academy Fee System 2.0")

menu = st.sidebar.selectbox(
    "Select Option",
    ["Admission / Payment", "All-Time Dashboard"]
)

# ================= ADMISSION / PAYMENT =================

if menu == "Admission / Payment":

    phone = st.text_input("Student Phone")

    students = get_students()
    payments = get_payments()

    student = next((s for s in students if str(s["Student_Phone"]) == phone), None)

    # NEW STUDENT
    if phone and not student:

        st.subheader("New Admission")

        name = st.text_input("Student Name")
        parent = st.text_input("Parent Phone")
        address = st.text_area("Address")
        course = st.text_input("Course")
        batch = st.text_input("Batch")
        total_fees = st.number_input("Total Fees", min_value=0.0)
        duration = st.number_input("Duration (Months)", min_value=1)
        start_date = st.date_input("Start Date")
        payment_amount = st.number_input("First Payment", min_value=0.0)
        payment_mode = st.selectbox("Mode", ["Cash","UPI","Bank"])
        next_due = st.date_input("Next Due Date")

        if st.button("Create Admission"):

            student_id = "STU-" + str(uuid.uuid4())[:8]
            end_date = start_date + relativedelta(months=duration)

            students_sheet.append_row([
                student_id,name,phone,parent,address,course,batch,
                total_fees,duration,
                start_date.strftime("%d-%m-%Y"),
                end_date.strftime("%d-%m-%Y"),
                datetime.today().strftime("%d-%m-%Y"),
                "Active"
            ])

            remaining = total_fees - payment_amount
            receipt_no = generate_receipt_number()

            payments_sheet.append_row([
                receipt_no,student_id,phone,
                datetime.today().strftime("%d-%m-%Y"),
                payment_amount,payment_mode,1,
                payment_amount,remaining,
                next_due.strftime("%d-%m-%Y"),
                datetime.now().year
            ])

            pdf = generate_pdf({
                "Receipt No": receipt_no,
                "Student Name": name,
                "Paid": f"₹{payment_amount}",
                "Remaining": f"₹{remaining}",
                "Amount in Words": num2words(payment_amount).title()+" Rupees Only"
            })

            st.success("Admission Created")
            st.download_button("Download Receipt", pdf, f"{receipt_no}.pdf")

            msg = f"Hello {name}, Payment of ₹{payment_amount} received. Receipt No: {receipt_no}"
            wa = f"https://wa.me/91{phone}?text={urllib.parse.quote(msg)}"
            st.markdown(f"[Send Payment Confirmation WhatsApp]({wa})")

    # EXISTING STUDENT
    elif student:

        st.success("Student Found")
        st.write(student)

        total_paid = sum(float(p["Payment_Amount"])
                         for p in payments if str(p["Student_Phone"])==phone)

        total_fees = float(student["Total_Fees"])
        remaining = total_fees - total_paid

        st.info(f"Remaining: ₹{remaining}")

        pay = st.number_input("Payment Amount", min_value=0.0)
        mode = st.selectbox("Mode", ["Cash","UPI","Bank"])
        next_due = st.date_input("Next Due Date")

        if st.button("Generate Receipt"):

            receipt_no = generate_receipt_number()
            installment = len([p for p in payments if str(p["Student_Phone"])==phone])+1
            new_remaining = remaining - pay

            payments_sheet.append_row([
                receipt_no,student["Student_ID"],phone,
                datetime.today().strftime("%d-%m-%Y"),
                pay,mode,installment,
                total_paid+pay,new_remaining,
                next_due.strftime("%d-%m-%Y"),
                datetime.now().year
            ])

            pdf = generate_pdf({
                "Receipt No": receipt_no,
                "Student Name": student["Student_Name"],
                "Paid": f"₹{pay}",
                "Remaining": f"₹{new_remaining}",
                "Amount in Words": num2words(pay).title()+" Rupees Only"
            })

            st.download_button("Download Receipt", pdf, f"{receipt_no}.pdf")

            msg = f"Hello {student['Student_Name']}, Payment ₹{pay} received. Remaining ₹{new_remaining}"
            wa = f"https://wa.me/91{phone}?text={urllib.parse.quote(msg)}"
            st.markdown(f"[Send Payment Confirmation WhatsApp]({wa})")

# ================= ALL TIME DASHBOARD =================

elif menu == "All-Time Dashboard":

    students = get_students()
    payments = get_payments()

    report = []
    total_pending = 0
    total_fees_all = 0

    for s in students:
        if s["Status"]=="Active":

            phone = s["Student_Phone"]
            total_paid = sum(float(p["Payment_Amount"])
                             for p in payments if str(p["Student_Phone"])==phone)

            total_fees = float(s["Total_Fees"])
            pending = total_fees - total_paid

            total_pending += pending
            total_fees_all += total_fees

            wa_link = ""
            if pending>0:
                msg=f"Hello {s['Student_Name']}, Your pending fees is ₹{pending}. Kindly pay soon."
                wa_link=f"https://wa.me/91{phone}?text={urllib.parse.quote(msg)}"

            report.append({
                "Name": s["Student_Name"],
                "Phone": phone,
                "Course": s["Course"],
                "Total Fees": total_fees,
                "Paid": total_paid,
                "Pending": pending,
                "WhatsApp": wa_link
            })

    st.metric("Total Fees (All Active)", f"₹{total_fees_all}")
    st.metric("Total Pending (All Active)", f"₹{total_pending}")

    df = pd.DataFrame(report)
    st.dataframe(df)
