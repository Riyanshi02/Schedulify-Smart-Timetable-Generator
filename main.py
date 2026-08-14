import streamlit as st
import pandas as pd
from pathlib import Path
import copy
import io

# ==========================================
# 📅 PAGE CONFIG & THEME
# ==========================================
st.set_page_config(page_title="Schedulify - Smart Timetable Generator ", page_icon="📅", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def apply_custom_theme():
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #fdf2f8 50%, #eef2ff 100%);
        color: #1f2937;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #4c1d95 0%, #6d28d9 45%, #db2777 100%);
        color: white;
    }
    section[data-testid="stSidebar"] * { color: white !important; }
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #7e22ce; font-weight: 800; }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.82);
        border-radius: 18px; padding: 18px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.08);
        border: 1px solid rgba(255,255,255,0.7);
    }
    div.stButton > button {
        background: linear-gradient(90deg, #9333ea 0%, #db2777 100%);
        color: white; border: none; border-radius: 12px;
        font-weight: 700; padding: 0.6rem 1.2rem;
        box-shadow: 0 6px 18px rgba(147,51,234,0.35);
    }
    div.stButton > button:hover {
        background: linear-gradient(90deg, #7e22ce 0%, #be185d 100%);
    }
    .stDataFrame, .stTable {
        background: rgba(255,255,255,0.88);
        border-radius: 18px; padding: 8px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.06);
    }
    div[data-baseweb="input"], div[data-baseweb="select"], textarea {
        background: rgba(255,255,255,0.94) !important;
        border-radius: 12px !important;
    }
    .stAlert { border-radius: 14px; }
    .main-card {
        background: rgba(255,255,255,0.75);
        padding: 2.5rem; border-radius: 28px;
        box-shadow: 0 12px 40px rgba(0,0,0,0.09);
        backdrop-filter: blur(12px);
    }
    .hero-title {
        font-size: 4.2rem; font-weight: 900; text-align: center;
        margin-bottom: 0.3rem;
        background: linear-gradient(90deg, #7c3aed, #db2777, #60a5fa);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .hero-subtitle {
        text-align: center; font-size: 1.25rem; color: #6b7280; margin-top: 0.3rem;
    }
    .hero-badge {
        display: inline-block; padding: 0.6rem 1.4rem; border-radius: 999px;
        background: rgba(255,255,255,0.82); box-shadow: 0 8px 25px rgba(0,0,0,0.08);
        color: #9333ea; font-weight: 700; margin-bottom: 1.2rem;
    }
    .feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 1rem; }
    .feature-card {
        background: rgba(255,255,255,0.78); padding: 1.2rem; border-radius: 16px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.06); border-left: 4px solid #9333ea;
    }
    .timetable-cell { padding: 8px; border-radius: 8px; margin: 4px 0; font-size: 0.9rem; line-height: 1.4; }
    .cell-theory { background: #dbeafe; color: #1e40af; }
    .cell-lab { background: #dcfce7; color: #166534; }
    .cell-tutorial { background: #ffedd5; color: #9a3412; }
    .cell-elective { background: #f3e8ff; color: #6b21a8; }
    .cell-lunch { background: #f3f4f6; color: #4b5563; font-style: italic; }
    .cell-empty { background: #ffffff; color: #9ca3af; }
    </style>
    """, unsafe_allow_html=True)


apply_custom_theme()

# ==========================================
# 1. DATA UTILITIES
# ==========================================
def load_csv(file_name, columns):
    file_path = DATA_DIR / file_name
    if file_path.exists():
        try:
            df = pd.read_csv(file_path)
            for col in columns:
                if col not in df.columns:
                    df[col] = ""
            return df[columns]
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)


def save_csv(df, file_name):
    df.to_csv(DATA_DIR / file_name, index=False)


def is_duplicate(df, column, value):
    return value.strip().upper() in df[column].astype(str).str.upper().values


def is_duplicate_row(df, criteria: dict):
    if df.empty:
        return False
    mask = pd.Series([True] * len(df))
    for col, val in criteria.items():
        if col not in df.columns:
            return False
        mask &= df[col].astype(str).str.strip().str.upper() == str(val).strip().upper()
    return mask.any()


def init_data():
    teachers = load_csv("teachers.csv", ["teacher_code", "teacher_name", "department"])
    subjects = load_csv("subjects.csv", ["subject_code", "subject_name", "subject_type",
                                         "l_hours", "t_hours", "p_hours",
                                         "requires_lab_room", "continuous_slots_required"])
    classes = load_csv("classes.csv", ["session_name", "batch_year", "semester", "section", "program", "strength"])
    rooms = load_csv("rooms.csv", ["room_name", "room_type", "capacity"])
    preferences = load_csv("preferences.csv", ["session_name", "teacher_code", "subject_code", "preference_order"])
    class_subjects = load_csv("class_subjects.csv", ["session_name", "batch_year", "semester", "section",
                                                     "subject_code", "l_hours", "t_hours", "p_hours",
                                                     "is_lab", "lab_continuous_slots", "elective_group"])
    return teachers, subjects, classes, rooms, preferences, class_subjects


teachers_df, subjects_df, classes_df, rooms_df, preferences_df, class_subjects_df = init_data()

# Clean legacy short_name if exists
if "short_name" in teachers_df.columns:
    teachers_df = teachers_df.drop(columns=["short_name"])
    save_csv(teachers_df, "teachers.csv")

# ==========================================
# 2. SESSION STATE
# ==========================================
for key in ["timetable", "allocations", "unscheduled", "base_timetable"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "unscheduled" else []

for key in ["edit_teacher_idx", "edit_subject_idx", "edit_class_idx",
            "edit_room_idx", "edit_pref_idx", "edit_cs_idx"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ==========================================
# 3. TEACHER ALLOCATION ENGINE
# ==========================================
def allocate_teachers(session, class_subjects_df, preferences_df, teachers_df):
    allocations = []
    teacher_load = {t: 0 for t in teachers_df["teacher_code"].tolist()}
    MAX_HOURS = 24

    session_subjects = class_subjects_df[class_subjects_df["session_name"] == session]
    session_prefs = preferences_df[preferences_df["session_name"] == session]

    for _, row in session_subjects.iterrows():
        class_key = f"{int(row['semester'])} Sem - {row['section']}"
        subject_code = row["subject_code"]
        l_hrs, t_hrs, p_hrs = int(row["l_hours"]), int(row["t_hours"]), int(row["p_hours"])
        total_hours = l_hrs + (t_hrs * 2) + (p_hrs * 2)
        elective_group = row["elective_group"] if "elective_group" in row else ""

        interested = session_prefs[session_prefs["subject_code"] == subject_code].sort_values("preference_order")
        allocated = None
        for _, pref in interested.iterrows():
            tc = pref["teacher_code"]
            if tc in teacher_load and teacher_load[tc] + total_hours <= MAX_HOURS:
                allocated = tc
                teacher_load[tc] += total_hours
                break

        allocations.append({
            "semester": int(row["semester"]),
            "class": class_key,
            "subject_code": subject_code,
            "teacher_code": allocated or "UNALLOCATED",
            "l_hours": l_hrs,
            "t_hours": t_hrs,
            "p_hours": p_hrs,
            "is_lab": bool(row["is_lab"]) if "is_lab" in row else False,
            "lab_continuous_slots": int(row["lab_continuous_slots"]) if "lab_continuous_slots" in row and pd.notna(row["lab_continuous_slots"]) else 1,
            "elective_group": elective_group if pd.notna(elective_group) else ""
        })

    return pd.DataFrame(allocations), teacher_load

# ==========================================
# 4. TIMETABLE GENERATION ENGINE
# ==========================================
def generate_schedule(allocations_df, subjects_df, rooms_df):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    slot_labels = {
        1: "09:00", 2: "09:55", 3: "10:50", 4: "11:45",
        5: "12:40 (LUNCH)", 6: "13:35", 7: "14:30", 8: "15:25"
    }
    slots = list(slot_labels.keys())
    lunch = 5

    teacher_busy, room_busy = set(), set()
    class_busy_g1, class_busy_g2 = set(), set()
    class_subject_day = set()

    all_classes = allocations_df["class"].unique() if not allocations_df.empty else []
    class_daily_load = {c: {d: 0 for d in days} for c in all_classes}
    teacher_daily_load = {
        t: {d: 0 for d in days}
        for t in allocations_df["teacher_code"].unique()
        if t != "UNALLOCATED"
    } if not allocations_df.empty else {}

    all_timetables = {}
    for c in all_classes:
        df = pd.DataFrame("", index=days, columns=[slot_labels[s] for s in slots])
        for d in days:
            df.loc[d, slot_labels[lunch]] = "LUNCH"
        all_timetables[c] = df

    unscheduled = []

    def append_cell(existing, new):
        return new if not existing or pd.isna(existing) else f"{existing}\n---\n{new}"

    def find_paired_g1g2(class_key, teacher, duration, room_type, avoid=None):
        best_score, best = float("inf"), None
        for day in days:
            if avoid and (class_key, avoid, day) in class_subject_day:
                continue
            for start in range(1, max(slots) + 1):
                if start == lunch:
                    continue
                b1 = list(range(start, start + duration))
                b2 = list(range(start + duration, start + 2 * duration))
                if any(s > max(slots) or s == lunch for s in b1 + b2):
                    continue
                if any((class_key, day, s) in class_busy_g1 or (class_key, day, s) in class_busy_g2 for s in b1 + b2):
                    continue
                if any((teacher, day, s) in teacher_busy for s in b1 + b2):
                    continue

                avail = [
                    r for r in rooms_df[rooms_df["room_type"] == room_type]["room_name"].tolist()
                    if all((r, day, s) not in room_busy for s in b1 + b2)
                ]
                if len(avail) < 2:
                    continue

                score = start * 8

                existing_slots = sorted(list(set(
                    [s for (cc, dd, s) in class_busy_g1 if cc == class_key and dd == day] +
                    [s for (cc, dd, s) in class_busy_g2 if cc == class_key and dd == day]
                )))

                if existing_slots:
                    nearest_distance = min(min(abs(s - ex) for ex in existing_slots) for s in b1 + b2)
                    score += nearest_distance * 15

                    block_min = min(b1 + b2)
                    block_max = max(b1 + b2)

                    if block_min < min(existing_slots):
                        score += (min(existing_slots) - block_min) * 10
                    elif block_max > max(existing_slots):
                        score += (block_max - max(existing_slots)) * 4

                score += class_daily_load[class_key][day] * 12

                if room_type == "LAB" and start < lunch:
                    score += 20
                if room_type == "CLASSROOM" and start > lunch:
                    score += 10

                if score < best_score:
                    best_score, best = score, (day, b1, b2, avail[:2])
        return best

    def find_single_slot(class_keys, teachers, duration, room_type, is_g1=True, is_g2=True, avoid=None):
        best_score, best = float("inf"), None
        for day in days:
            if avoid and any((c, avoid, day) in class_subject_day for c in class_keys):
                continue
            for slot in slots:
                if slot == lunch:
                    continue
                check = list(range(slot, slot + duration))
                if any(s > max(slots) or s == lunch for s in check):
                    continue
                if any((c, day, s) in class_busy_g1 for c in class_keys for s in check if is_g1):
                    continue
                if any((c, day, s) in class_busy_g2 for c in class_keys for s in check if is_g2):
                    continue
                if any((t, day, s) in teacher_busy for t in teachers for s in check):
                    continue

                avail = [
                    r for r in rooms_df[rooms_df["room_type"] == room_type]["room_name"].tolist()
                    if all((r, day, s) not in room_busy for s in check)
                ]
                if len(avail) < len(teachers):
                    continue

                score = slot * 8

                for c in class_keys:
                    current_day_slots_g1 = sorted([s for (cc, dd, s) in class_busy_g1 if cc == c and dd == day])
                    current_day_slots_g2 = sorted([s for (cc, dd, s) in class_busy_g2 if cc == c and dd == day])
                    existing_slots = sorted(list(set(current_day_slots_g1 + current_day_slots_g2)))

                    score += class_daily_load[c][day] * 12
                    if class_daily_load[c][day] >= 5:
                        score += 100

                    if existing_slots:
                        nearest_distance = min(abs(slot - ex) for ex in existing_slots)
                        score += nearest_distance * 15

                        if slot < min(existing_slots):
                            score += (min(existing_slots) - slot) * 10
                        elif slot > max(existing_slots):
                            score += (slot - max(existing_slots)) * 4

                for t in teachers:
                    if t in teacher_daily_load:
                        score += teacher_daily_load[t][day] * 10
                        if teacher_daily_load[t][day] >= 4:
                            score += 100

                if room_type == "LAB" and slot < lunch:
                    score += 20
                if room_type == "CLASSROOM" and slot > lunch:
                    score += 10

                if score < best_score:
                    best_score, best = score, (day, check, avail[:len(teachers)])
        return best

    def commit(classes, teachers, day, slots_list, rooms, texts, g1=True, g2=True):
        for s in slots_list:
            col = slot_labels[s]
            for i, c in enumerate(classes):
                txt = texts[i] if i < len(texts) else texts[0]
                all_timetables[c].loc[day, col] = append_cell(all_timetables[c].loc[day, col], txt)
                if g1:
                    class_busy_g1.add((c, day, s))
                if g2:
                    class_busy_g2.add((c, day, s))
            for t in teachers:
                teacher_busy.add((t, day, s))
            for r in rooms:
                room_busy.add((r, day, s))

        for c in classes:
            class_daily_load[c][day] += len(slots_list)
        for t in teachers:
            if t in teacher_daily_load:
                teacher_daily_load[t][day] += len(slots_list)

    def schedule_electives(semester, group, rows):
        classes_inv = rows["class"].unique().tolist()
        offerings = rows[["subject_code", "teacher_code"]].drop_duplicates().to_dict("records")
        teachers_inv = [o["teacher_code"] for o in offerings]

        if any(t == "UNALLOCATED" for t in teachers_inv):
            unscheduled.append(f"Elective {group}: Unallocated teachers.")
            return

        for stype, hcol in [("L", "l_hours"), ("T", "t_hours"), ("P", "p_hours")]:
            hrs = int(rows.iloc[0][hcol])
            if hrs == 0:
                continue

            need_lab, max_dur = False, 1
            for o in offerings:
                sm = subjects_df[subjects_df["subject_code"] == o["subject_code"]]
                if not sm.empty:
                    sr = sm.iloc[0]
                    if str(sr.get("subject_type", "")).upper() == "LAB" or bool(sr.get("requires_lab_room", False)) or bool(rows.iloc[0].get("is_lab", False)):
                        need_lab = True
                    max_dur = max(max_dur, int(sr.get("continuous_slots_required", 1)))

            rtype = "LAB" if (stype == "P" and need_lab) else "CLASSROOM"
            dur = int(rows.iloc[0].get("lab_continuous_slots", max_dur)) if stype == "P" else 1
            if dur < 1:
                dur = 1
            to_sched = 1 if stype == "P" else hrs

            for _ in range(to_sched):
                p = find_single_slot(classes_inv, teachers_inv, dur, rtype, True, True)
                if p:
                    day, ch_slots, ch_rooms = p
                    lines = [f"{o['subject_code']}-{stype} ({o['teacher_code']}) [{ch_rooms[i]}]" for i, o in enumerate(offerings)]
                    txt = "=== Electives ===\n" + "\n".join(lines)
                    commit(classes_inv, teachers_inv, day, ch_slots, ch_rooms, [txt] * len(classes_inv), True, True)
                    for c in classes_inv:
                        class_subject_day.add((c, f"ELEC_{group}", day))
                else:
                    unscheduled.append(f"Elective {group}-{stype}: Could not schedule.")

    def schedule_normal(row, sub_info):
        c, sub, tc = row["class"], row["subject_code"], row["teacher_code"]
        if tc == "UNALLOCATED":
            return

        for _ in range(int(row["l_hours"])):
            p = find_single_slot([c], [tc], 1, "CLASSROOM", True, True, sub)
            if p:
                day, sl, rm = p
                commit([c], [tc], day, sl, rm, [f"{sub}-L\n({tc})\n{rm[0]}"], True, True)
                class_subject_day.add((c, sub, day))
            else:
                unscheduled.append(f"{c}: {sub}-L unscheduled.")

        if int(row["t_hours"]) > 0:
            paired = find_paired_g1g2(c, tc, 1, "CLASSROOM", sub)
            if paired:
                day, b1, b2, rms = paired
                commit([c], [tc], day, b1, [rms[0]], [f"{sub}-T(G1)\n({tc})\n{rms[0]}"], True, False)
                commit([c], [tc], day, b2, [rms[1]], [f"{sub}-T(G2)\n({tc})\n{rms[1]}"], False, True)
            else:
                for g, g1f, g2f in [("G1", True, False), ("G2", False, True)]:
                    for _ in range(int(row["t_hours"])):
                        p = find_single_slot([c], [tc], 1, "CLASSROOM", g1f, g2f)
                        if p:
                            day, sl, rm = p
                            commit([c], [tc], day, sl, rm, [f"{sub}-T({g})\n({tc})\n{rm[0]}"], g1f, g2f)
                        else:
                            unscheduled.append(f"{c}: {sub}-T({g}) unscheduled.")

        if int(row["p_hours"]) > 0:
            rtype = "LAB" if (
                str(sub_info.get("subject_type", "")).upper() == "LAB"
                or bool(sub_info.get("requires_lab_room", False))
                or bool(row.get("is_lab", False))
            ) else "CLASSROOM"
            dur = int(row.get("lab_continuous_slots", sub_info.get("continuous_slots_required", 1)))
            if dur < 1:
                dur = 1
            paired = find_paired_g1g2(c, tc, dur, rtype)
            if paired:
                day, b1, b2, rms = paired
                commit([c], [tc], day, b1, [rms[0]], [f"{sub}-P(G1)\n({tc})\n{rms[0]}"], True, False)
                commit([c], [tc], day, b2, [rms[1]], [f"{sub}-P(G2)\n({tc})\n{rms[1]}"], False, True)
            else:
                for g, g1f, g2f in [("G1", True, False), ("G2", False, True)]:
                    p = find_single_slot([c], [tc], dur, rtype, g1f, g2f)
                    if p:
                        day, sl, rm = p
                        commit([c], [tc], day, sl, rm, [f"{sub}-P({g})\n({tc})\n{rm[0]}"], g1f, g2f)
                    else:
                        unscheduled.append(f"{c}: {sub}-P({g}) unscheduled.")

    if not allocations_df.empty:
        allocations_df = allocations_df.copy()
        allocations_df["total_load"] = (
            allocations_df["l_hours"].fillna(0).astype(int)
            + allocations_df["t_hours"].fillna(0).astype(int)
            + allocations_df["p_hours"].fillna(0).astype(int)
        )
        allocations_df["priority"] = allocations_df.apply(
            lambda r: (
                0 if str(r.get("elective_group", "")).strip() else 1,
                0 if int(r.get("p_hours", 0)) > 0 else 1,
                -int(r.get("lab_continuous_slots", 1)),
                -int(r["total_load"])
            ),
            axis=1
        )
        allocations_df = allocations_df.sort_values("priority").drop(columns=["total_load", "priority"]).reset_index(drop=True)

    elec_rows, norm_rows = [], []
    for _, r in allocations_df.iterrows():
        eg = str(r.get("elective_group", "")).strip()
        (elec_rows if eg else norm_rows).append(r)

    if elec_rows:
        for (sem, grp), gr in pd.DataFrame(elec_rows).groupby(["semester", "elective_group"]):
            schedule_electives(sem, grp, gr)
    if norm_rows:
        for _, r in pd.DataFrame(norm_rows).iterrows():
            sm = subjects_df[subjects_df["subject_code"] == r["subject_code"]]
            if sm.empty:
                unscheduled.append(f"{r['class']}: {r['subject_code']} missing.")
                continue
            schedule_normal(r, sm.iloc[0])

    return all_timetables, unscheduled

# ==========================================
# 5. TIMETABLE COMPACTION
# ==========================================
def compact_timetables(timetables):
    compacted = copy.deepcopy(timetables)
    ordered_slots = ["09:00", "09:55", "10:50", "11:45", "12:40 (LUNCH)", "13:35", "14:30", "15:25"]
    morning_slots = ["09:00", "09:55", "10:50", "11:45"]
    afternoon_slots = ["13:35", "14:30", "15:25"]

    for class_key, df in compacted.items():
        for day in df.index:
            row = df.loc[day].to_dict()

            morning_vals = []
            for s in morning_slots:
                val = str(row.get(s, "")).strip()
                if val and val != "LUNCH":
                    morning_vals.append(val)

            afternoon_vals = []
            for s in afternoon_slots:
                val = str(row.get(s, "")).strip()
                if val and val != "LUNCH":
                    afternoon_vals.append(val)

            new_row = {slot: "" for slot in ordered_slots}
            new_row["12:40 (LUNCH)"] = "LUNCH"

            for i, val in enumerate(morning_vals):
                if i < len(morning_slots):
                    new_row[morning_slots[i]] = val

            for i, val in enumerate(afternoon_vals):
                if i < len(afternoon_slots):
                    new_row[afternoon_slots[i]] = val

            for slot in ordered_slots:
                df.at[day, slot] = new_row[slot]

    return compacted

# ==========================================
# 6. LEAVE MANAGEMENT
# ==========================================
def adjust_for_leave(timetables, teacher, day):
    adj = copy.deepcopy(timetables)
    slots_list = ["09:00", "09:55", "10:50", "11:45", "12:40 (LUNCH)", "13:35", "14:30", "15:25"]
    for ck, df in adj.items():
        sched = df.loc[day].tolist()
        for i, cell in enumerate(sched):
            cs = str(cell)
            if f"({teacher})" in cs:
                if "=== Electives ===" in cs:
                    sched[i] = "\n".join(l for l in cs.split("\n") if f"({teacher})" not in l).strip()
                else:
                    sched[i] = ""
        for ei in range(len(sched)):
            if slots_list[ei] == "12:40 (LUNCH)" or sched[ei] != "":
                continue
            for li in range(ei + 1, len(sched)):
                if slots_list[li] == "12:40 (LUNCH)":
                    continue
                if sched[li] != "" and "=== Electives ===" not in str(sched[li]):
                    sched[ei], sched[li] = sched[li], ""
                    break
        adj[ck].loc[day] = sched
    return adj

# ==========================================
# 7. SIDEBAR
# ==========================================
st.sidebar.title("📚 Schedulify")
page = st.sidebar.radio("Navigation", [
    "Dashboard", "Generator", "Timetable Viewer", "Teacher Leave Manager",
    "Teachers", "Subjects", "Classes / Sections", "Rooms", "Teacher Preferences", "Class Subject Mapping"
])
st.sidebar.markdown("---")
st.sidebar.success("✅ G1/G2 Paired Scheduling")
st.sidebar.success("✅ Zero Gap Optimization")
st.sidebar.success("✅ Smart Room Allocation")
st.sidebar.success("✅ Excel Export Ready")

# ==========================================
# 8. DASHBOARD
# ==========================================
if page == "Dashboard":
    st.markdown("""
    <div class="main-card" style="text-align:center;">
        <div class="hero-badge">🎓 D.A.V. Institute of Engineering & Technology - CSE Department</div>
        <div class="hero-title">SCHEDULIFY</div>
        <p class="hero-subtitle">Your Brain for Better Scheduling</p>
        <p style="font-size:1.1rem; color:#4b5563; max-width:700px; margin:0 auto;">
            Effortlessly generate smart timetables, manage teachers, allocate rooms,
            and eliminate scheduling conflicts with precision.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("👨‍🏫 Teachers", len(teachers_df))
    c2.metric("📘 Subjects", len(subjects_df))
    c3.metric("🏫 Classes", len(classes_df))
    c4, c5, c6 = st.columns(3)
    c4.metric("🚪 Rooms", len(rooms_df))
    c5.metric("⭐ Preferences", len(preferences_df))
    c6.metric("🧩 Mappings", len(class_subjects_df))

    st.markdown("---")
    st.subheader("✨ Core Features")
    st.markdown("""
    <div class="feature-grid">
        <div class="feature-card"><b>🔄 G1/G2 Paired Scheduling</b><br>Labs & Tutorials scheduled back-to-back. Zero wasted hours.</div>
        <div class="feature-card"><b>🎨 Colored Timetables</b><br>Theory, Lab, Tutorial & Electives color-coded for instant readability.</div>
        <div class="feature-card"><b>📊 Excel Export</b><br>Download professional .xlsx files for printing & sharing.</div>
        <div class="feature-card"><b>🛡️ Duplicate Protection</b><br>Smart validation prevents overlapping codes & entries.</div>
        <div class="feature-card"><b>🩺 Leave Manager</b><br>Auto-compress schedules when teachers are absent.</div>
        <div class="feature-card"><b>⚡ Constraint Engine</b><br>Hard & soft constraints optimized for academic excellence.</div>
    </div>
    """, unsafe_allow_html=True)

    if not classes_df.empty:
        st.subheader("📌 Dynamic Section Summary")
        st.dataframe(
            classes_df.groupby(["session_name", "batch_year", "semester"])["section"].apply(list).reset_index(),
            use_container_width=True
        )

# ==========================================
# 9. GENERATOR
# ==========================================
elif page == "Generator":
    st.title("⚙️ Generate Optimized Timetable")
    if any(df.empty for df in [class_subjects_df, preferences_df, rooms_df, subjects_df, teachers_df]):
        st.warning("⚠️ Please complete all master data pages first.")
    else:
        sessions = sorted(class_subjects_df["session_name"].dropna().unique())
        sel = st.selectbox("Select Session", sessions)
        if st.button("🚀 Generate Timetable", type="primary"):
            with st.spinner("Running constraint optimizer..."):
                alloc, _ = allocate_teachers(sel, class_subjects_df, preferences_df, teachers_df)
                tt, unsch = generate_schedule(alloc, subjects_df, rooms_df)
                tt = compact_timetables(tt)

                st.session_state["allocations"] = alloc
                st.session_state["timetable"] = tt
                st.session_state["base_timetable"] = copy.deepcopy(tt)
                st.session_state["unscheduled"] = unsch
            st.success("✅ Timetable generated successfully.")

        if st.session_state["allocations"] is not None:
            st.subheader("📌 Teacher Allocations")
            st.dataframe(st.session_state["allocations"], use_container_width=True)

        if st.session_state["unscheduled"]:
            st.subheader("⚠️ Unscheduled Items")
            for i in st.session_state["unscheduled"]:
                st.warning(i)
        elif st.session_state["timetable"] is not None:
            st.info("🎉 All sessions scheduled successfully.")

# ==========================================
# 10. TIMETABLE VIEWER
# ==========================================
elif page == "Timetable Viewer":
    st.title("🗓 Timetable Viewer")
    if st.session_state["timetable"] is None:
        st.warning("Please generate the timetable first.")
    else:
        classes = sorted(st.session_state["timetable"].keys())
        sel = st.selectbox("Select Class", classes)
        if sel:
            df = st.session_state["timetable"][sel]
            st.subheader(f"Timetable for {sel}")

            html = "<table style='width:100%; border-collapse:collapse; font-family:sans-serif;'>"
            html += "<tr style='background:#f8fafc; font-weight:bold;'><th style='padding:10px; border:1px solid #e5e7eb;'>Day</th>"
            for col in df.columns:
                html += f"<th style='padding:10px; border:1px solid #e5e7eb;'>{col}</th>"
            html += "</tr>"

            for idx, row in df.iterrows():
                html += f"<tr><td style='padding:10px; border:1px solid #e5e7eb; font-weight:bold; background:#f3f4f6;'>{idx}</td>"
                for val in row:
                    v = str(val)
                    cls = "cell-empty"
                    if "LUNCH" in v:
                        cls = "cell-lunch"
                    elif "-L" in v:
                        cls = "cell-theory"
                    elif "-P" in v:
                        cls = "cell-lab"
                    elif "-T" in v:
                        cls = "cell-tutorial"
                    elif "Electives" in v:
                        cls = "cell-elective"
                    html += f"<td style='padding:8px; border:1px solid #e5e7eb;'><div class='timetable-cell {cls}'>{v.replace(chr(10), '<br>')}</div></td>"
                html += "</tr>"
            html += "</table>"
            st.markdown(html, unsafe_allow_html=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Timetable', index=True)

            st.download_button(
                "📥 Download Excel (.xlsx)",
                output.getvalue(),
                f"{sel.replace(' ', '_')}_timetable.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ==========================================
# 11. LEAVE MANAGER
# ==========================================
elif page == "Teacher Leave Manager":
    st.title("🩺 Teacher Leave & Adjustment")
    if st.session_state["base_timetable"] is None:
        st.warning("Generate timetable first.")
    else:
        c1, c2 = st.columns(2)

        teacher_options_df = teachers_df.dropna(subset=["teacher_code"]).copy()
        teacher_options_df["teacher_display"] = teacher_options_df.apply(
            lambda r: f"{r['teacher_code']} - {r['teacher_name']}" if str(r.get("teacher_name", "")).strip() else str(r["teacher_code"]),
            axis=1
        )

        teacher_display_map = dict(zip(teacher_options_df["teacher_display"], teacher_options_df["teacher_code"]))
        selected_teacher_display = c1.selectbox("Teacher on Leave", sorted(teacher_display_map.keys()))
        teacher = teacher_display_map[selected_teacher_display]

        day = c2.selectbox("Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Adjust Schedule", type="primary"):
                adjusted = adjust_for_leave(st.session_state["base_timetable"], teacher, day)
                adjusted = compact_timetables(adjusted)
                st.session_state["timetable"] = adjusted
                st.success(f"✅ Schedule compressed for {selected_teacher_display} on {day}.")

        with col2:
            if st.button("Reset Original"):
                st.session_state["timetable"] = copy.deepcopy(st.session_state["base_timetable"])
                st.info("🔄 Original restored.")

# ==========================================
# 12. TEACHERS
# ==========================================
elif page == "Teachers":
    st.title("👨‍🏫 Teachers")
    with st.form("teacher_form"):
        code = st.text_input("Teacher Code")
        name = st.text_input("Teacher Name")
        dept = st.text_input("Department", "CSE")
        if st.form_submit_button("Add Teacher"):
            if not code or not name:
                st.error("Code & Name required.")
            elif is_duplicate(teachers_df, "teacher_code", code):
                st.error("Teacher code already exists.")
            else:
                teachers_df = pd.concat([
                    teachers_df,
                    pd.DataFrame([{
                        "teacher_code": code.strip(),
                        "teacher_name": name.strip(),
                        "department": dept.strip()
                    }])
                ], ignore_index=True)
                save_csv(teachers_df, "teachers.csv")
                st.success("✅ Added.")
                st.rerun()

    st.markdown("---")
    st.subheader("Teacher List")
    if teachers_df.empty:
        st.info("No teachers yet.")
    else:
        if st.session_state["edit_teacher_idx"] is not None:
            idx = st.session_state["edit_teacher_idx"]
            row = teachers_df.loc[idx]
            with st.form("edit_teacher_form"):
                nc = st.text_input("Code", str(row["teacher_code"]))
                nn = st.text_input("Name", str(row["teacher_name"]))
                nd = st.text_input("Department", str(row["department"]))
                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 Save"):
                    teachers_df.at[idx, "teacher_code"] = nc.strip()
                    teachers_df.at[idx, "teacher_name"] = nn.strip()
                    teachers_df.at[idx, "department"] = nd.strip()
                    save_csv(teachers_df, "teachers.csv")
                    st.session_state["edit_teacher_idx"] = None
                    st.success("✅ Updated.")
                    st.rerun()
                if c2.form_submit_button("❌ Cancel"):
                    st.session_state["edit_teacher_idx"] = None
                    st.rerun()

        h = st.columns([2, 3, 2, 1, 1])
        h[0].markdown("**Code**")
        h[1].markdown("**Name**")
        h[2].markdown("**Dept**")
        h[3].markdown("**Edit**")
        h[4].markdown("**Del**")

        for i, r in teachers_df.iterrows():
            c1, c2, c3, c4, c5 = st.columns([2, 3, 2, 1, 1])
            c1.write(r["teacher_code"])
            c2.write(r["teacher_name"])
            c3.write(r["department"])
            if c4.button("✏️", key=f"et{i}"):
                st.session_state["edit_teacher_idx"] = i
                st.rerun()
            if c5.button("🗑️", key=f"dt{i}"):
                teachers_df = teachers_df.drop(i).reset_index(drop=True)
                save_csv(teachers_df, "teachers.csv")
                st.success("✅ Deleted.")
                st.rerun()

# ==========================================
# 13. SUBJECTS
# ==========================================
elif page == "Subjects":
    st.title("📘 Subjects")
    with st.form("subject_form"):
        code, name = st.text_input("Code"), st.text_input("Name")
        stype = st.selectbox("Type", ["THEORY", "LAB", "ELECTIVE", "OPEN_ELECTIVE"])
        req_lab = st.checkbox("Requires Lab Room")
        l, t, p = st.columns(3)
        lh = l.number_input("L", 0, 10, 3)
        th = t.number_input("T", 0, 10, 0)
        ph = p.number_input("P", 0, 10, 0)
        cs = st.number_input("Continuous Slots", 1, 4, 1)
        if st.form_submit_button("Add Subject"):
            if not code or not name:
                st.error("Code & Name required.")
            elif is_duplicate(subjects_df, "subject_code", code):
                st.error("Subject code already exists.")
            else:
                subjects_df = pd.concat([
                    subjects_df,
                    pd.DataFrame([{
                        "subject_code": code.strip(),
                        "subject_name": name.strip(),
                        "subject_type": stype,
                        "l_hours": lh,
                        "t_hours": th,
                        "p_hours": ph,
                        "requires_lab_room": req_lab,
                        "continuous_slots_required": cs
                    }])
                ], ignore_index=True)
                save_csv(subjects_df, "subjects.csv")
                st.success("✅ Added.")
                st.rerun()

    st.markdown("---")
    st.subheader("Subject List")
    if subjects_df.empty:
        st.info("No subjects yet.")
    else:
        if st.session_state["edit_subject_idx"] is not None:
            idx = st.session_state["edit_subject_idx"]
            row = subjects_df.loc[idx]
            with st.form("edit_subject_form"):
                nc = st.text_input("Code", str(row["subject_code"]))
                nn = st.text_input("Name", str(row["subject_name"]))
                opts = ["THEORY", "LAB", "ELECTIVE", "OPEN_ELECTIVE"]
                nt_sel = st.selectbox("Type", opts, index=opts.index(str(row["subject_type"])) if str(row["subject_type"]) in opts else 0)
                nr = st.checkbox("Requires Lab", bool(row["requires_lab_room"]))
                c1, c2, c3, c4 = st.columns(4)
                nl = c1.number_input("L", 0, 10, int(row["l_hours"]))
                nt2 = c2.number_input("T", 0, 10, int(row["t_hours"]))
                np = c3.number_input("P", 0, 10, int(row["p_hours"]))
                ncs = c4.number_input("Slots", 1, 4, int(row["continuous_slots_required"]))
                s1, s2 = st.columns(2)
                if s1.form_submit_button("💾 Save"):
                    subjects_df.at[idx, "subject_code"] = nc.strip()
                    subjects_df.at[idx, "subject_name"] = nn.strip()
                    subjects_df.at[idx, "subject_type"] = nt_sel
                    subjects_df.at[idx, "l_hours"] = nl
                    subjects_df.at[idx, "t_hours"] = nt2
                    subjects_df.at[idx, "p_hours"] = np
                    subjects_df.at[idx, "requires_lab_room"] = nr
                    subjects_df.at[idx, "continuous_slots_required"] = ncs
                    save_csv(subjects_df, "subjects.csv")
                    st.session_state["edit_subject_idx"] = None
                    st.success("✅ Updated.")
                    st.rerun()
                if s2.form_submit_button("❌ Cancel"):
                    st.session_state["edit_subject_idx"] = None
                    st.rerun()

        h = st.columns([2, 3, 2, 1, 1, 1, 2, 1, 1])
        for x, y in zip(h, ["**Code**", "**Name**", "**Type**", "**L**", "**T**", "**P**", "**Slots**", "**Edit**", "**Del**"]):
            x.markdown(y)

        for i, r in subjects_df.iterrows():
            c = st.columns([2, 3, 2, 1, 1, 1, 2, 1, 1])
            c[0].write(r["subject_code"])
            c[1].write(r["subject_name"])
            c[2].write(r["subject_type"])
            c[3].write(int(r["l_hours"]))
            c[4].write(int(r["t_hours"]))
            c[5].write(int(r["p_hours"]))
            c[6].write(int(r["continuous_slots_required"]))
            if c[7].button("✏️", key=f"es{i}"):
                st.session_state["edit_subject_idx"] = i
                st.rerun()
            if c[8].button("🗑️", key=f"ds{i}"):
                subjects_df = subjects_df.drop(i).reset_index(drop=True)
                save_csv(subjects_df, "subjects.csv")
                st.success("✅ Deleted.")
                st.rerun()

# ==========================================
# 14. CLASSES / SECTIONS
# ==========================================
elif page == "Classes / Sections":
    st.title("🏫 Classes / Sections")
    with st.form("class_form"):
        sess = st.text_input("Session", "2025-26-even")
        c1, c2, c3 = st.columns(3)
        yr = c1.number_input("Batch Year", 2020, 2035, 2024)
        sem = c2.number_input("Semester", 1, 8, 4)
        sec = c3.text_input("Section", "A")
        prog = st.text_input("Program", "CSE")
        strn = st.number_input("Strength", 1, 200, 60)
        if st.form_submit_button("Add Class"):
            if not sess or not sec:
                st.error("Session & Section required.")
            elif is_duplicate_row(classes_df, {
                "session_name": sess,
                "batch_year": yr,
                "semester": sem,
                "section": sec,
                "program": prog
            }):
                st.error("This class/section already exists.")
            else:
                classes_df = pd.concat([
                    classes_df,
                    pd.DataFrame([{
                        "session_name": sess.strip(),
                        "batch_year": yr,
                        "semester": sem,
                        "section": sec.strip(),
                        "program": prog.strip(),
                        "strength": strn
                    }])
                ], ignore_index=True)
                save_csv(classes_df, "classes.csv")
                st.success("✅ Added.")
                st.rerun()

    st.markdown("---")
    st.subheader("Class Sections")
    if classes_df.empty:
        st.info("No classes yet.")
    else:
        if st.session_state["edit_class_idx"] is not None:
            idx = st.session_state["edit_class_idx"]
            row = classes_df.loc[idx]
            with st.form("edit_class_form"):
                ns = st.text_input("Session", str(row["session_name"]))
                c1, c2, c3 = st.columns(3)
                ny = c1.number_input("Year", 2020, 2035, int(row["batch_year"]))
                nsem = c2.number_input("Sem", 1, 8, int(row["semester"]))
                nsec = c3.text_input("Section", str(row["section"]))
                npg = st.text_input("Program", str(row["program"]))
                nst = st.number_input("Strength", 1, 200, int(row["strength"]))
                s1, s2 = st.columns(2)
                if s1.form_submit_button("💾 Save"):
                    classes_df.at[idx, "session_name"] = ns.strip()
                    classes_df.at[idx, "batch_year"] = ny
                    classes_df.at[idx, "semester"] = nsem
                    classes_df.at[idx, "section"] = nsec.strip()
                    classes_df.at[idx, "program"] = npg.strip()
                    classes_df.at[idx, "strength"] = nst
                    save_csv(classes_df, "classes.csv")
                    st.session_state["edit_class_idx"] = None
                    st.success("✅ Updated.")
                    st.rerun()
                if s2.form_submit_button("❌ Cancel"):
                    st.session_state["edit_class_idx"] = None
                    st.rerun()

        for i, r in classes_df.iterrows():
            c = st.columns([2, 2, 1, 1, 2, 1, 1, 1])
            c[0].write(r["session_name"])
            c[1].write(r["program"])
            c[2].write(int(r["batch_year"]))
            c[3].write(f"Sem {int(r['semester'])}")
            c[4].write(f"Sec {r['section']}")
            c[5].write(int(r["strength"]))
            if c[6].button("✏️", key=f"ec{i}"):
                st.session_state["edit_class_idx"] = i
                st.rerun()
            if c[7].button("🗑️", key=f"dc{i}"):
                classes_df = classes_df.drop(i).reset_index(drop=True)
                save_csv(classes_df, "classes.csv")
                st.success("✅ Deleted.")
                st.rerun()

# ==========================================
# 15. ROOMS
# ==========================================
elif page == "Rooms":
    st.title("🚪 Rooms")
    with st.form("room_form"):
        name = st.text_input("Room Name")
        rtype = st.selectbox("Type", ["CLASSROOM", "LAB"])
        cap = st.number_input("Capacity", 1, 300, 60)
        if st.form_submit_button("Add Room"):
            if not name:
                st.error("Name required.")
            elif is_duplicate(rooms_df, "room_name", name):
                st.error("Room name already exists.")
            else:
                rooms_df = pd.concat([
                    rooms_df,
                    pd.DataFrame([{
                        "room_name": name.strip(),
                        "room_type": rtype,
                        "capacity": cap
                    }])
                ], ignore_index=True)
                save_csv(rooms_df, "rooms.csv")
                st.success("✅ Added.")
                st.rerun()

    st.markdown("---")
    st.subheader("Room List")
    if rooms_df.empty:
        st.info("No rooms yet.")
    else:
        if st.session_state["edit_room_idx"] is not None:
            idx = st.session_state["edit_room_idx"]
            row = rooms_df.loc[idx]
            with st.form("edit_room_form"):
                nn = st.text_input("Name", str(row["room_name"]))
                opts = ["CLASSROOM", "LAB"]
                nt = st.selectbox("Type", opts, index=opts.index(str(row["room_type"])) if str(row["room_type"]) in opts else 0)
                nc = st.number_input("Capacity", 1, 300, int(row["capacity"]))
                s1, s2 = st.columns(2)
                if s1.form_submit_button("💾 Save"):
                    rooms_df.at[idx, "room_name"] = nn.strip()
                    rooms_df.at[idx, "room_type"] = nt
                    rooms_df.at[idx, "capacity"] = nc
                    save_csv(rooms_df, "rooms.csv")
                    st.session_state["edit_room_idx"] = None
                    st.success("✅ Updated.")
                    st.rerun()
                if s2.form_submit_button("❌ Cancel"):
                    st.session_state["edit_room_idx"] = None
                    st.rerun()

        h = st.columns([3, 2, 2, 1, 1])
        for x, y in zip(h, ["**Name**", "**Type**", "**Capacity**", "**Edit**", "**Del**"]):
            x.markdown(y)

        for i, r in rooms_df.iterrows():
            c = st.columns([3, 2, 2, 1, 1])
            c[0].write(r["room_name"])
            c[1].write(r["room_type"])
            c[2].write(int(r["capacity"]))
            if c[3].button("✏️", key=f"er{i}"):
                st.session_state["edit_room_idx"] = i
                st.rerun()
            if c[4].button("🗑️", key=f"dr{i}"):
                rooms_df = rooms_df.drop(i).reset_index(drop=True)
                save_csv(rooms_df, "rooms.csv")
                st.success("✅ Deleted.")
                st.rerun()

# ==========================================
# 16. TEACHER PREFERENCES
# ==========================================
elif page == "Teacher Preferences":
    st.title("⭐ Teacher Preferences")
    if teachers_df.empty or subjects_df.empty:
        st.warning("Add teachers & subjects first.")
    else:
        with st.form("pref_form"):
            sess = st.text_input("Session", "2025-26-even")
            c1, c2 = st.columns(2)
            tc = c1.selectbox("Teacher", teachers_df["teacher_code"].dropna().tolist())
            sc = c2.selectbox("Subject", subjects_df["subject_code"].dropna().tolist())
            pref = st.number_input("Priority (1=Highest)", 1, 10, 1)
            if st.form_submit_button("Add Preference"):
                if is_duplicate_row(preferences_df, {
                    "session_name": sess,
                    "teacher_code": tc,
                    "subject_code": sc
                }):
                    st.error("This preference already exists.")
                else:
                    preferences_df = pd.concat([
                        preferences_df,
                        pd.DataFrame([{
                            "session_name": sess.strip(),
                            "teacher_code": tc,
                            "subject_code": sc,
                            "preference_order": pref
                        }])
                    ], ignore_index=True)
                    save_csv(preferences_df, "preferences.csv")
                    st.success("✅ Added.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Preference List")
    if preferences_df.empty:
        st.info("No preferences yet.")
    else:
        if st.session_state["edit_pref_idx"] is not None:
            idx = st.session_state["edit_pref_idx"]
            row = preferences_df.loc[idx]
            with st.form("edit_pref_form"):
                ns = st.text_input("Session", str(row["session_name"]))
                c1, c2 = st.columns(2)
                tco = teachers_df["teacher_code"].dropna().tolist()
                sco = subjects_df["subject_code"].dropna().tolist()
                ntc = c1.selectbox("Teacher", tco, index=tco.index(str(row["teacher_code"])) if str(row["teacher_code"]) in tco else 0)
                nsc = c2.selectbox("Subject", sco, index=sco.index(str(row["subject_code"])) if str(row["subject_code"]) in sco else 0)
                npref = st.number_input("Priority", 1, 10, int(row["preference_order"]))
                s1, s2 = st.columns(2)
                if s1.form_submit_button("💾 Save"):
                    preferences_df.at[idx, "session_name"] = ns.strip()
                    preferences_df.at[idx, "teacher_code"] = ntc
                    preferences_df.at[idx, "subject_code"] = nsc
                    preferences_df.at[idx, "preference_order"] = npref
                    save_csv(preferences_df, "preferences.csv")
                    st.session_state["edit_pref_idx"] = None
                    st.success("✅ Updated.")
                    st.rerun()
                if s2.form_submit_button("❌ Cancel"):
                    st.session_state["edit_pref_idx"] = None
                    st.rerun()

        h = st.columns([2, 2, 2, 1, 1, 1])
        for x, y in zip(h, ["**Session**", "**Teacher**", "**Subject**", "**Priority**", "**Edit**", "**Del**"]):
            x.markdown(y)

        for i, r in preferences_df.iterrows():
            c = st.columns([2, 2, 2, 1, 1, 1])
            c[0].write(r["session_name"])
            c[1].write(r["teacher_code"])
            c[2].write(r["subject_code"])
            c[3].write(int(r["preference_order"]))
            if c[4].button("✏️", key=f"ep{i}"):
                st.session_state["edit_pref_idx"] = i
                st.rerun()
            if c[5].button("🗑️", key=f"dp{i}"):
                preferences_df = preferences_df.drop(i).reset_index(drop=True)
                save_csv(preferences_df, "preferences.csv")
                st.success("✅ Deleted.")
                st.rerun()

# ==========================================
# 17. CLASS SUBJECT MAPPING
# ==========================================
elif page == "Class Subject Mapping":
    st.title("🧩 Class Subject Mapping")
    if classes_df.empty or subjects_df.empty:
        st.warning("Add classes & subjects first.")
    else:
        with st.form("cs_form"):
            sess = st.text_input("Session", "2025-26-even")
            c1, c2, c3, c4 = st.columns(4)
            yr = c1.selectbox("Batch Year", sorted(classes_df["batch_year"].dropna().unique()))
            sem = c2.selectbox("Semester", sorted(classes_df["semester"].dropna().unique()))
            sec = c3.text_input("Section", "A")
            sc = c4.selectbox("Subject", subjects_df["subject_code"].dropna().tolist())
            c5, c6, c7 = st.columns(3)
            lh = c5.number_input("L", 0, 10, 3)
            th = c6.number_input("T", 0, 10, 0)
            ph = c7.number_input("P", 0, 10, 0)
            c8, c9 = st.columns(2)
            islab = c8.checkbox("Is Lab")
            lslots = c9.number_input("Lab Slots", 1, 4, 2)
            eg = st.text_input("Elective Group (leave blank for normal)", "")
            if st.form_submit_button("Add Mapping"):
                if not sess or not sec or not sc:
                    st.error("Session, Section & Subject required.")
                elif is_duplicate_row(class_subjects_df, {
                    "session_name": sess,
                    "batch_year": yr,
                    "semester": sem,
                    "section": sec,
                    "subject_code": sc
                }):
                    st.error("This class-subject mapping already exists.")
                else:
                    class_subjects_df = pd.concat([
                        class_subjects_df,
                        pd.DataFrame([{
                            "session_name": sess.strip(),
                            "batch_year": yr,
                            "semester": sem,
                            "section": sec.strip(),
                            "subject_code": sc,
                            "l_hours": lh,
                            "t_hours": th,
                            "p_hours": ph,
                            "is_lab": islab,
                            "lab_continuous_slots": lslots,
                            "elective_group": eg.strip()
                        }])
                    ], ignore_index=True)
                    save_csv(class_subjects_df, "class_subjects.csv")
                    st.success("✅ Added.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Mappings")
    if class_subjects_df.empty:
        st.info("No mappings yet.")
    else:
        if st.session_state["edit_cs_idx"] is not None:
            idx = st.session_state["edit_cs_idx"]
            row = class_subjects_df.loc[idx]
            with st.form("edit_cs_form"):
                ns = st.text_input("Session", str(row["session_name"]))
                c1, c2, c3, c4 = st.columns(4)
                ny = c1.number_input("Year", 2020, 2035, int(row["batch_year"]))
                nsem = c2.number_input("Sem", 1, 8, int(row["semester"]))
                nsec = c3.text_input("Section", str(row["section"]))
                sco = subjects_df["subject_code"].dropna().tolist()
                nsc = c4.selectbox("Subject", sco, index=sco.index(str(row["subject_code"])) if str(row["subject_code"]) in sco else 0)
                c5, c6, c7 = st.columns(3)
                nl = c5.number_input("L", 0, 10, int(row["l_hours"]))
                ntv = c6.number_input("T", 0, 10, int(row["t_hours"]))
                npv = c7.number_input("P", 0, 10, int(row["p_hours"]))
                c8, c9 = st.columns(2)
                nil = c8.checkbox("Is Lab", bool(row["is_lab"]))
                nls = c9.number_input("Slots", 1, 4, int(row["lab_continuous_slots"]))
                neg = st.text_input("Elective Group", str(row["elective_group"]) if pd.notna(row["elective_group"]) else "")
                s1, s2 = st.columns(2)
                if s1.form_submit_button("💾 Save"):
                    class_subjects_df.at[idx, "session_name"] = ns.strip()
                    class_subjects_df.at[idx, "batch_year"] = ny
                    class_subjects_df.at[idx, "semester"] = nsem
                    class_subjects_df.at[idx, "section"] = nsec.strip()
                    class_subjects_df.at[idx, "subject_code"] = nsc
                    class_subjects_df.at[idx, "l_hours"] = nl
                    class_subjects_df.at[idx, "t_hours"] = ntv
                    class_subjects_df.at[idx, "p_hours"] = npv
                    class_subjects_df.at[idx, "is_lab"] = nil
                    class_subjects_df.at[idx, "lab_continuous_slots"] = nls
                    class_subjects_df.at[idx, "elective_group"] = neg.strip()
                    save_csv(class_subjects_df, "class_subjects.csv")
                    st.session_state["edit_cs_idx"] = None
                    st.success("✅ Updated.")
                    st.rerun()
                if s2.form_submit_button("❌ Cancel"):
                    st.session_state["edit_cs_idx"] = None
                    st.rerun()

        temp = class_subjects_df.copy()
        temp["total"] = (
            temp["l_hours"].fillna(0).astype(int)
            + temp["t_hours"].fillna(0).astype(int)
            + temp["p_hours"].fillna(0).astype(int)
        )
        h = st.columns([2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1])
        for x, y in zip(h, ["**Session**", "**Sem**", "**Sec**", "**Subject**", "**L-T-P**", "**Total**", "**Lab**", "**Slots**", "**Elective**", "**Edit**", "**Del**"]):
            x.markdown(y)

        for i, r in temp.iterrows():
            c = st.columns([2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1])
            c[0].write(r["session_name"])
            c[1].write(int(r["semester"]))
            c[2].write(r["section"])
            c[3].write(r["subject_code"])
            c[4].write(f"{int(r['l_hours'])}-{int(r['t_hours'])}-{int(r['p_hours'])}")
            c[5].write(int(r["total"]))
            c[6].write("✅" if bool(r["is_lab"]) else "❌")
            c[7].write(int(r["lab_continuous_slots"]))
            c[8].write(str(r["elective_group"]) if pd.notna(r["elective_group"]) and str(r["elective_group"]).strip() != "" else "-")
            if c[9].button("✏️", key=f"ecs{i}"):
                st.session_state["edit_cs_idx"] = i
                st.rerun()
            if c[10].button("🗑️", key=f"dcs{i}"):
                class_subjects_df = class_subjects_df.drop(i).reset_index(drop=True)
                save_csv(class_subjects_df, "class_subjects.csv")
                st.success("✅ Deleted.")
                st.rerun()
