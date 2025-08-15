import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

st.set_page_config(page_title="教師教材調查", page_icon="📝", layout="centered")
st.title("📝 教師教材調查（本學期）")

# ----- 常用 -----
def slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", s)

def join_choices(values):
    if isinstance(values, (list, tuple)):
        return "、".join(map(str, values))
    return str(values)

# ----- 題目選項 -----
CLASS_OPTIONS = [
    "一甲A","一甲B","二甲A","二甲B","三甲A","三甲B",
    "四甲A","四甲B","五甲","六甲A","六甲B",
    "七甲A","七甲B","八甲"
]

STUDENT_MAT_OPTIONS = [
    "課本","習作","生字語詞簿甲本","生字語詞簿乙本","練習簿","單冊卷"
]

TEACHER_MAT_OPTIONS = [
    "教師版課本","教師版手冊","學生版課本","單冊卷解答","不需要教師版教材"
]

DELIVERY_OPTIONS = ["自取", "送至辦公室", "Other:"]

# ----- 表單 -----
with st.form("survey"):
    st.subheader("基本資料")
    name = st.text_input("👤 姓名 *", max_chars=50)

    st.subheader("🏫 請勾選您本學期任教的班級 *（可複選）")
    classes = st.multiselect(
        "任教班級（可複選）", options=CLASS_OPTIONS, placeholder="請選擇班級…"
    )
    class_other_chk = st.checkbox("Other（請勾選後填寫）")
    class_other_text = ""
    if class_other_chk:
        class_other_text = st.text_input("請輸入其他班級（可用逗號分隔多個）", max_chars=100)

    # 把 Other 輸入拆成多個班級
    other_classes = []
    if class_other_text.strip():
        other_classes = [c.strip() for c in re.split(r"[，,]+", class_other_text) if c.strip()]

    selected_classes = classes + other_classes

    st.markdown("---")
    st.subheader("為每個班級填寫教材與到貨後處理")

    per_class_inputs = {}
    for cls in selected_classes:
        sid = slug(cls)
        with st.expander(f"📚 {cls} — 點此展開填寫", expanded=True):
            # 學生教材（可複選 + Other）
            st.markdown("**各班學生教材選擇 *（可複選）**")
            student_mats = st.multiselect(
                f"[{cls}] 學生教材（可複選）",
                options=STUDENT_MAT_OPTIONS,
                key=f"{sid}_student_mats"
            )
            student_other_chk = st.checkbox(
                f"[{cls}] 其他學生教材（Other）",
                key=f"{sid}_student_other_chk"
            )
            student_other_text = ""
            if student_other_chk:
                student_other_text = st.text_input(
                    f"[{cls}] 請輸入其他學生教材",
                    max_chars=100,
                    key=f"{sid}_student_other_text"
                )

            # 教師版教材（可複選）
            st.markdown("**👨‍🏫 教師版教材 *（可複選）**")
            teacher_mats = st.multiselect(
                f"[{cls}] 教師版教材（可複選）",
                options=TEACHER_MAT_OPTIONS,
                key=f"{sid}_teacher_mats"
            )

            # 到貨後處理（單選 + Other）
            st.markdown("**教材到齊後 *（單選）**")
            delivery = st.radio(
                f"[{cls}] 到齊後處理方式",
                DELIVERY_OPTIONS,
                horizontal=True,
                key=f"{sid}_delivery"
            )
            delivery_other_text = ""
            if delivery == "Other:":
                delivery_other_text = st.text_input(
                    f"[{cls}] 請輸入其他到貨處理方式",
                    max_chars=60,
                    key=f"{sid}_delivery_other"
                )

            per_class_inputs[cls] = {
                "student_mats": student_mats,
                "student_other_text": student_other_text,
                "teacher_mats": teacher_mats,
                "delivery": delivery,
                "delivery_other_text": delivery_other_text
            }

    submitted = st.form_submit_button("送出")

# ----- 提交處理 -----
if submitted:
    errors = []
    if not name.strip():
        errors.append("請填寫姓名")
    if not selected_classes:
        errors.append("請至少選擇一個任教班級（或於 Other 填寫）")

    # 逐班驗證
    for cls in selected_classes:
        data = per_class_inputs.get(cls, {})
        # 學生教材至少要有一項或 Other 有填
        if not data.get("student_mats") and not data.get("student_other_text", "").strip():
            errors.append(f"[{cls}] 請至少選擇一項『學生教材』或填寫其他學生教材")
        # 教師版教材至少選一項（若勾選「不需要教師版教材」也算一項）
        if not data.get("teacher_mats"):
            errors.append(f"[{cls}] 請至少選擇一項『教師版教材』")
        # 到貨後 Other 要填內容
        if data.get("delivery") == "Other:" and not data.get("delivery_other_text", "").strip():
            errors.append(f"[{cls}] 請填寫『其他到貨處理方式』")

    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    # 寫入 Google Sheet
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc = gspread.authorize(creds)

        sh = gc.open_by_key(st.secrets["sheet_key"])
        ws_title = st.secrets.get("worksheet", "responses_by_class")
        try:
            ws = sh.worksheet(ws_title)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=ws_title, rows=2000, cols=20)
            ws.append_row([
                "timestamp_utc", "teacher_name", "class",
                "student_materials", "student_materials_other",
                "teacher_materials",
                "delivery_method", "delivery_other"
            ])

        # 逐班 append，一班一列
        ts = datetime.utcnow().isoformat(timespec="seconds")
        for cls in selected_classes:
            data = per_class_inputs[cls]
            student_str = join_choices(data["student_mats"])
            if data["student_other_text"].strip():
                # 學生教材 + Other 合併顯示；同時也單獨存一欄 Other
                student_str = ("、".join([c for c in [student_str, data["student_other_text"].strip()] if c])).strip("、")

            delivery_final = (
                data["delivery_other_text"].strip()
                if data["delivery"] == "Other:" else data["delivery"]
            )

            ws.append_row([
                ts,
                name.strip(),
                cls,
                student_str,
                data["student_other_text"].strip(),
                join_choices(data["teacher_mats"]),
                delivery_final,
                data["delivery_other_text"].strip()
            ], value_input_option="USER_ENTERED")

        st.success("✅ 已送出（每個班級已分開記錄）。感謝填寫！")
        st.balloons()

    except Exception as ex:
        st.error(f"寫入 Google Sheet 時發生錯誤：{ex}")
