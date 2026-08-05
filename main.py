import streamlit as st
import pandas as pd
from pathlib import Path
import copy

st.set_page_config(
    page_title="Pro Timetable Engine",
    page_icon="📅",
    layout="wide"
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


# ==========================================
# 1. UTILITY & DATA LOADING
# ==========================================
def load_csv(file_name, columns):
    file_path = DATA_DIR / file_name
    if file_path.exists():
        try:
            return pd.read_csv(file_path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)


def save_csv(df, file_name):
    df.to_csv(DATA_DIR / file_name, index=False)


def init_data():
    teachers = load_csv("teachers.csv", [
        "teacher_code", "teacher_name", "short_name", "department"
    ])
    subjects = load_csv("subjects.csv", [
        "subject_code", "subject_name", "subject_type",
        "l_hours", "t_hours", "p_hours",
        "requires_lab_room", "continuous_slots_required"
    ])
    classes = load_csv("classes.csv", [
        "session_name", "batch_year", "semester", "section", "program", "strength"
    ])
    rooms = load_csv("rooms.csv", [
        "room_name", "room_type", "capacity"
    ])
    preferences = load_csv("preferences.csv", [
        "session_name", "teacher_code", "subject_code", "preference_order"
    ])
    class_subjects = load_csv("class_subjects.csv", [
        "session_name", "batch_year", "semester", "section",
        "subject_code", "l_hours", "t_hours", "p_hours",
        "is_lab", "lab_continuous_slots", "elective_group"
    ])
    return teachers, subjects, classes, rooms, preferences, class_subjects


teachers_df, subjects_df, classes_df, rooms_df, preferences_df, class_subjects_df = init_data()


# ==========================================
# 2. SESSION STATE
# ==========================================
if "timetable" not in st.session_state:
    st.session_state["timetable"] = None
if "allocations" not in st.session_state:
    st.session_state["allocations"] = None
if "unscheduled" not in st.session_state:
    st.session_state["unscheduled"] = []
if "base_timetable" not in st.session_state:
    st.session_state["base_timetable"] = None

# Edit state flags
for key in [
    "edit_teacher_idx", "edit_subject_idx", "edit_class_idx",
    "edit_room_idx", "edit_pref_idx", "edit_cs_idx"
]:
    if key not in st.session_state:
        st.session_state[key] = None


# ==========================================
# 3. TEACHER ALLOCATION ENGINE
# ==========================================
def allocate_teachers(session, class_subjects_df, preferences_df, teachers_df):
    allocations = []
    teacher_load = {teacher: 0 for teacher in teachers_df["teacher_code"].tolist()}
    MAX_HOURS_PER_TEACHER = 24

    session_subjects = class_subjects_df[class_subjects_df["session_name"] == session]
    session_prefs = preferences_df[preferences_df["session_name"] == session]

    for _, row in session_subjects.iterrows():
        class_key = f"{int(row['semester'])} Sem - {row['section']}"
        subject_code = row["subject_code"]

        l_hrs = int(row["l_hours"])
        t_hrs = int(row["t_hours"])
        p_hrs = int(row["p_hours"])
        total_hours = l_hrs + (t_hrs * 2) + (p_hrs * 2)

        elective_group = row["elective_group"] if "elective_group" in row else ""

        interested_teachers = session_prefs[
            session_prefs["subject_code"] == subject_code
        ].sort_values(by="preference_order")

        allocated_teacher = None
        for _, pref_row in interested_teachers.iterrows():
            tc = pref_row["teacher_code"]
            if tc in teacher_load and teacher_load[tc] + total_hours <= MAX_HOURS_PER_TEACHER:
                allocated_teacher = tc
                teacher_load[tc] += total_hours
                allocations.append({
                    "semester": int(row["semester"]),
                    "class": class_key,
                    "subject_code": subject_code,
                    "teacher_code": allocated_teacher,
                    "l_hours": l_hrs,
                    "t_hours": t_hrs,
                    "p_hours": p_hrs,
                    "elective_group": elective_group if pd.notna(elective_group) else ""
                })
                break

        if not allocated_teacher:
            allocations.append({
                "semester": int(row["semester"]),
                "class": class_key,
                "subject_code": subject_code,
                "teacher_code": "UNALLOCATED",
                "l_hours": l_hrs,
                "t_hours": t_hrs,
                "p_hours": p_hrs,
                "elective_group": elective_group if pd.notna(elective_group) else ""
            })

    return pd.DataFrame(allocations), teacher_load


# ==========================================
# 4. TIMETABLE GENERATION ENGINE
# ==========================================
def generate_schedule(allocations_df, subjects_df, rooms_df):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    slot_labels = {
        1: "09:00",
        2: "09:55",
        3: "10:50",
        4: "11:45",
        5: "12:40 (LUNCH)",
        6: "13:35",
        7: "14:30",
        8: "15:25"
    }
    slots = list(slot_labels.keys())
    lunch_slot = 5

    teacher_busy = set()
    room_busy = set()
    class_busy_g1 = set()
    class_busy_g2 = set()
    class_subject_day = set()

    all_classes = allocations_df["class"].unique()

    # Soft constraint trackers
    class_daily_load = {c: {d: 0 for d in days} for c in all_classes}
    teacher_daily_load = {
        t: {d: 0 for d in days}
        for t in allocations_df["teacher_code"].unique()
        if t != "UNALLOCATED"
    }

    all_timetables = {}
    for class_key in all_classes:
        timetable_df = pd.DataFrame(
            "", index=days, columns=[slot_labels[s] for s in slots]
        )
        for day in days:
            timetable_df.loc[day, slot_labels[lunch_slot]] = "LUNCH"
        all_timetables[class_key] = timetable_df

    unscheduled_lectures = []

    def append_cell(existing, new_val):
        if existing == "" or pd.isna(existing):
            return new_val
        return f"{existing}\n---\n{new_val}"

    def check_gap_penalty(busy_set, entity, day, slot):
        """Returns penalty score if placing here creates a gap."""
        if slot <= 1:
            return 0
        prev_slot = slot - 1
        if prev_slot == lunch_slot:
            prev_slot = slot - 2
        if prev_slot < 1:
            return 0
        if (entity, day, prev_slot) not in busy_set:
            return 50
        return 0

    def find_best_slot(
        class_keys, teacher_codes, duration, room_type,
        is_g1=True, is_g2=True, avoid_subject=None
    ):
        best_score = float("inf")
        best_placement = None
        allow_same_day = False

        for attempt in range(2):
            for day in days:
                if not allow_same_day and avoid_subject:
                    if any(
                        (c, avoid_subject, day) in class_subject_day
                        for c in class_keys
                    ):
                        continue

                for slot in slots:
                    if slot == lunch_slot:
                        continue
                    check_slots = list(range(slot, slot + duration))
                    if any(s > max(slots) or s == lunch_slot for s in check_slots):
                        continue

                    is_feasible = True

                    # Hard: Check class availability
                    for c in class_keys:
                        for s in check_slots:
                            if is_g1 and (c, day, s) in class_busy_g1:
                                is_feasible = False
                                break
                            if is_g2 and (c, day, s) in class_busy_g2:
                                is_feasible = False
                                break
                        if not is_feasible:
                            break
                    if not is_feasible:
                        continue

                    # Hard: Check teacher availability
                    for t in teacher_codes:
                        if any((t, day, s) in teacher_busy for s in check_slots):
                            is_feasible = False
                            break
                    if not is_feasible:
                        continue

                    # Hard: Check room availability
                    req_rooms = len(teacher_codes)
                    avail_rooms = [
                        r for r in
                        rooms_df[rooms_df["room_type"] == room_type]["room_name"].tolist()
                        if all((r, day, s) not in room_busy for s in check_slots)
                    ]
                    if len(avail_rooms) < req_rooms:
                        continue
                    assigned_rooms = avail_rooms[:req_rooms]

                    # Soft: Score calculation
                    score = slot * 5  # Prefer early slots

                    # Soft: Even distribution across week
                    for c in class_keys:
                        score += class_daily_load[c][day] * 10
                        if class_daily_load[c][day] >= 5:
                            score += 100  # Too many in one day
                        score += check_gap_penalty(class_busy_g1, c, day, slot)

                    for t in teacher_codes:
                        if t in teacher_daily_load:
                            score += teacher_daily_load[t][day] * 10
                            if teacher_daily_load[t][day] >= 4:
                                score += 100

                    # Soft: Labs prefer afternoon
                    if room_type == "LAB" and slot < lunch_slot:
                        score += 15
                    # Soft: Theory prefers morning
                    if room_type == "CLASSROOM" and slot > lunch_slot:
                        score += 5

                    if score < best_score:
                        best_score = score
                        best_placement = (day, check_slots, assigned_rooms)

            if best_placement:
                break
            allow_same_day = True

        return best_placement

    def commit_placement(
        class_keys, teacher_codes, day, chosen_slots,
        chosen_rooms, cell_texts, is_g1=True, is_g2=True
    ):
        for s in chosen_slots:
            col = slot_labels[s]
            for i, c in enumerate(class_keys):
                txt = cell_texts[i] if i < len(cell_texts) else cell_texts[0]
                all_timetables[c].loc[day, col] = append_cell(
                    all_timetables[c].loc[day, col], txt
                )
                if is_g1:
                    class_busy_g1.add((c, day, s))
                if is_g2:
                    class_busy_g2.add((c, day, s))

            for i, t in enumerate(teacher_codes):
                teacher_busy.add((t, day, s))
            for i, r in enumerate(chosen_rooms):
                room_busy.add((r, day, s))

        for c in class_keys:
            class_daily_load[c][day] += len(chosen_slots)
        for t in teacher_codes:
            if t in teacher_daily_load:
                teacher_daily_load[t][day] += len(chosen_slots)

    # -----------------------------------------------
    # CROSS-SECTION ELECTIVE SCHEDULING (Goes First)
    # -----------------------------------------------
    def schedule_cross_section_electives(semester, group_name, group_rows):
        classes_inv = group_rows["class"].unique().tolist()
        offerings = group_rows[
            ["subject_code", "teacher_code"]
        ].drop_duplicates().to_dict("records")
        teachers_inv = [o["teacher_code"] for o in offerings]

        if any(t == "UNALLOCATED" for t in teachers_inv):
            unscheduled_lectures.append(
                f"Elective {group_name}: Unallocated teachers."
            )
            return

        for s_type, hrs_col in [("L", "l_hours"), ("T", "t_hours"), ("P", "p_hours")]:
            hrs = int(group_rows.iloc[0][hrs_col])
            if hrs == 0:
                continue

            sub_info_match = subjects_df[
                subjects_df["subject_code"] == offerings[0]["subject_code"]
            ]
            if sub_info_match.empty:
                continue
            sub_info = sub_info_match.iloc[0]
            r_type = "LAB" if sub_info["subject_type"] == "LAB" else "CLASSROOM"
            duration = hrs if s_type == "P" else 1
            to_schedule = 1 if s_type == "P" else hrs

            for _ in range(to_schedule):
                placement = find_best_slot(
                    classes_inv, teachers_inv, duration, r_type,
                    is_g1=True, is_g2=True
                )
                if placement:
                    day, chosen_slots, chosen_rooms = placement
                    block_lines = [
                        f"{o['subject_code']}-{s_type} ({o['teacher_code']}) [{chosen_rooms[i]}]"
                        for i, o in enumerate(offerings)
                    ]
                    block_text = "=== Electives ===\n" + "\n".join(block_lines)

                    cell_texts = [block_text for _ in classes_inv]
                    commit_placement(
                        classes_inv, teachers_inv, day, chosen_slots,
                        chosen_rooms, cell_texts, is_g1=True, is_g2=True
                    )
                    for c in classes_inv:
                        class_subject_day.add((c, f"ELEC_{group_name}", day))
                else:
                    unscheduled_lectures.append(
                        f"Elective {group_name}-{s_type}: Could not schedule."
                    )

    # -----------------------------------------------
    # NORMAL SUBJECT SCHEDULING
    # -----------------------------------------------
    def schedule_normal_subject(row, sub_info):
        c = row["class"]
        sub = row["subject_code"]
        tc = row["teacher_code"]

        if tc == "UNALLOCATED":
            return

        # L (Theory) -> Both G1 and G2
        for _ in range(int(row["l_hours"])):
            placement = find_best_slot(
                [c], [tc], 1, "CLASSROOM",
                is_g1=True, is_g2=True, avoid_subject=sub
            )
            if placement:
                day, chosen_slots, chosen_rooms = placement
                cell_text = f"{sub}-L\n({tc})\n{chosen_rooms[0]}"
                commit_placement(
                    [c], [tc], day, chosen_slots, chosen_rooms,
                    [cell_text], is_g1=True, is_g2=True
                )
                class_subject_day.add((c, sub, day))
            else:
                unscheduled_lectures.append(f"{c}: {sub}-L could not be scheduled.")

        # T (Tutorial) -> Split G1 and G2 separately
        if int(row["t_hours"]) > 0:
            for group, g1_flag, g2_flag in [("G1", True, False), ("G2", False, True)]:
                for _ in range(int(row["t_hours"])):
                    placement = find_best_slot(
                        [c], [tc], 1, "CLASSROOM",
                        is_g1=g1_flag, is_g2=g2_flag
                    )
                    if placement:
                        day, chosen_slots, chosen_rooms = placement
                        cell_text = f"{sub}-T({group})\n({tc})\n{chosen_rooms[0]}"
                        commit_placement(
                            [c], [tc], day, chosen_slots, chosen_rooms,
                            [cell_text], is_g1=g1_flag, is_g2=g2_flag
                        )
                    else:
                        unscheduled_lectures.append(
                            f"{c}: {sub}-T({group}) could not be scheduled."
                        )

        # P (Practical/Lab) -> Split G1 and G2 separately
        if int(row["p_hours"]) > 0:
            r_type = "LAB" if sub_info["subject_type"] == "LAB" else "CLASSROOM"
            duration = int(sub_info["continuous_slots_required"])
            if duration < 1:
                duration = 1

            for group, g1_flag, g2_flag in [("G1", True, False), ("G2", False, True)]:
                placement = find_best_slot(
                    [c], [tc], duration, r_type,
                    is_g1=g1_flag, is_g2=g2_flag
                )
                if placement:
                    day, chosen_slots, chosen_rooms = placement
                    cell_text = f"{sub}-P({group})\n({tc})\n{chosen_rooms[0]}"
                    commit_placement(
                        [c], [tc], day, chosen_slots, chosen_rooms,
                        [cell_text], is_g1=g1_flag, is_g2=g2_flag
                    )
                else:
                    unscheduled_lectures.append(
                        f"{c}: {sub}-P({group}) could not be scheduled."
                    )

    # -----------------------------------------------
    # EXECUTION ORDER
    # -----------------------------------------------
    if not allocations_df.empty:
        allocations_df = allocations_df.sample(frac=1).reset_index(drop=True)

    normal_rows = []
    elective_rows = []

    for _, row in allocations_df.iterrows():
        eg = str(row.get("elective_group", "")).strip()
        if eg != "":
            elective_rows.append(row)
        else:
            normal_rows.append(row)

    # Step 1: Schedule electives first
    elective_df = pd.DataFrame(elective_rows) if elective_rows else pd.DataFrame()
    if not elective_df.empty:
        for (semester, group_name), group_rows in elective_df.groupby(
            ["semester", "elective_group"]
        ):
            schedule_cross_section_electives(semester, group_name, group_rows)

    # Step 2: Schedule normal subjects
    normal_df = pd.DataFrame(normal_rows) if normal_rows else pd.DataFrame()
    for _, row in normal_df.iterrows():
        sub_match = subjects_df[subjects_df["subject_code"] == row["subject_code"]]
        if sub_match.empty:
            unscheduled_lectures.append(
                f"{row['class']}: {row['subject_code']} not in subject master."
            )
            continue
        schedule_normal_subject(row, sub_match.iloc[0])

    return all_timetables, unscheduled_lectures


# ==========================================
# 5. LEAVE MANAGEMENT
# ==========================================
def adjust_for_leave(timetables, absent_teacher, absent_day):
    adjusted_tts = copy.deepcopy(timetables)
    slot_labels_list = [
        "09:00", "09:55", "10:50", "11:45",
        "12:40 (LUNCH)", "13:35", "14:30", "15:25"
    ]

    for class_key, df in adjusted_tts.items():
        daily_schedule = df.loc[absent_day].tolist()

        # Step 1: Clear absent teacher slots
        for i, cell in enumerate(daily_schedule):
            cell_str = str(cell)
            if f"({absent_teacher})" in cell_str:
                if "=== Electives ===" in cell_str:
                    lines = cell_str.split("\n")
                    new_lines = [l for l in lines if f"({absent_teacher})" not in l]
                    daily_schedule[i] = "\n".join(new_lines).strip()
                else:
                    daily_schedule[i] = ""

        # Step 2: Compress schedule (pull later classes forward)
        for empty_idx in range(len(daily_schedule)):
            if slot_labels_list[empty_idx] == "12:40 (LUNCH)":
                continue
            if daily_schedule[empty_idx] == "":
                for later_idx in range(empty_idx + 1, len(daily_schedule)):
                    if slot_labels_list[later_idx] == "12:40 (LUNCH)":
                        continue
                    candidate = daily_schedule[later_idx]
                    if candidate != "" and "=== Electives ===" not in str(candidate):
                        daily_schedule[empty_idx] = candidate
                        daily_schedule[later_idx] = ""
                        break

        adjusted_tts[class_key].loc[absent_day] = daily_schedule

    return adjusted_tts


# ==========================================
# 6. SIDEBAR
# ==========================================
st.sidebar.title("📚 Pro Timetable System")
page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Generator",
        "Timetable Viewer",
        "Teacher Leave Manager",
        "Teachers",
        "Subjects",
        "Classes / Sections",
        "Rooms",
        "Teacher Preferences",
        "Class Subject Mapping"
    ]
)

st.sidebar.markdown("---")
st.sidebar.success("✅ G1/G2 Batching Active")
st.sidebar.success("✅ Strict Parallel Electives")
st.sidebar.success("✅ Smart Gap Avoidance")
st.sidebar.success("✅ Edit & Delete Enabled")


# ==========================================
# 7. DASHBOARD
# ==========================================
if page == "Dashboard":
    st.title("📅 Pro College Timetable Dashboard")
    st.write(
        "Complete timetable engine with G1/G2 batching, "
        "parallel electives, gap avoidance, and leave handling."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Teachers", len(teachers_df))
    col2.metric("Subjects", len(subjects_df))
    col3.metric("Classes / Sections", len(classes_df))

    col4, col5, col6 = st.columns(3)
    col4.metric("Rooms", len(rooms_df))
    col5.metric("Preferences", len(preferences_df))
    col6.metric("Class-Subject Mappings", len(class_subjects_df))

    st.markdown("---")
    st.subheader("✅ Features")
    st.write("""
    - Dynamic sections (A, B, C, D...)
    - L-T-P based subject structure
    - Lab and Tutorial split into G1 / G2 batches
    - Electives scheduled simultaneously for all sections
    - Open Electives scheduled simultaneously for all sections
    - No teacher clash (Hard Constraint)
    - No class double booking (Hard Constraint)
    - No room conflict (Hard Constraint)
    - Weekly hour satisfaction per subject
    - No same subject repeated on same day
    - Smart gap avoidance (Soft Constraint)
    - Even distribution across the week (Soft Constraint)
    - Teacher leave adjustment with schedule compression
    - Full Edit and Delete support for all data
    """)

    if not classes_df.empty:
        st.subheader("📌 Dynamic Section Summary")
        summary = classes_df.groupby(
            ["session_name", "batch_year", "semester"]
        )["section"].apply(list).reset_index()
        st.dataframe(summary, use_container_width=True)

    if not subjects_df.empty:
        st.subheader("📘 Subject Hour Summary")
        temp_df = subjects_df.copy()
        temp_df["total_hours"] = (
            temp_df["l_hours"].fillna(0).astype(int)
            + temp_df["t_hours"].fillna(0).astype(int)
            + temp_df["p_hours"].fillna(0).astype(int)
        )
        st.dataframe(temp_df, use_container_width=True)


# ==========================================
# 8. GENERATOR
# ==========================================
elif page == "Generator":
    st.title("⚙️ Generate Optimized Timetable")

    if class_subjects_df.empty:
        st.warning("Please add Class Subject Mapping data first.")
    elif preferences_df.empty:
        st.warning("Please add Teacher Preferences data first.")
    elif rooms_df.empty:
        st.warning("Please add Rooms data first.")
    elif subjects_df.empty:
        st.warning("Please add Subjects data first.")
    elif teachers_df.empty:
        st.warning("Please add Teachers data first.")
    else:
        session_options = sorted(
            class_subjects_df["session_name"].dropna().unique().tolist()
        )
        if session_options:
            selected_session = st.selectbox("Select Session", session_options)

            if st.button("🚀 Generate Timetable", type="primary"):
                with st.spinner("Running constraint optimizer..."):
                    alloc_df, _ = allocate_teachers(
                        selected_session, class_subjects_df,
                        preferences_df, teachers_df
                    )
                    tt_res, unsch = generate_schedule(alloc_df, subjects_df, rooms_df)

                    st.session_state["allocations"] = alloc_df
                    st.session_state["timetable"] = tt_res
                    st.session_state["base_timetable"] = copy.deepcopy(tt_res)
                    st.session_state["unscheduled"] = unsch

                st.success("Timetable generated successfully.")

            if st.session_state["allocations"] is not None:
                st.subheader("📌 Teacher Allocations")
                st.dataframe(
                    st.session_state["allocations"], use_container_width=True
                )

            if st.session_state["unscheduled"]:
                st.subheader("⚠️ Unscheduled Items")
                for item in st.session_state["unscheduled"]:
                    st.warning(item)
            else:
                if st.session_state["timetable"] is not None:
                    st.info("All sessions scheduled successfully.")


# ==========================================
# 9. TIMETABLE VIEWER
# ==========================================
elif page == "Timetable Viewer":
    st.title("🗓 Timetable Viewer")

    if st.session_state["timetable"] is None:
        st.warning("Please generate the timetable first from the Generator page.")
    else:
        class_options = sorted(list(st.session_state["timetable"].keys()))
        selected_class = st.selectbox("Select Class", class_options)

        if selected_class:
            st.subheader(f"Timetable for {selected_class}")
            display_df = st.session_state["timetable"][selected_class]
            st.dataframe(display_df, use_container_width=True)

            csv_data = display_df.to_csv().encode("utf-8")
            st.download_button(
                label="Download Timetable CSV",
                data=csv_data,
                file_name=f"{selected_class.replace(' ', '_')}_timetable.csv",
                mime="text/csv"
            )


# ==========================================
# 10. TEACHER LEAVE MANAGER
# ==========================================
elif page == "Teacher Leave Manager":
    st.title("🩺 Teacher Leave & Schedule Adjustment")
    st.write(
        "Remove an absent teacher's classes and compress the day schedule "
        "automatically. Elective blocks are preserved."
    )

    if st.session_state["base_timetable"] is None:
        st.warning("Please generate the timetable first from the Generator page.")
    else:
        c1, c2 = st.columns(2)
        absent_teacher = c1.selectbox(
            "Select Teacher on Leave",
            sorted(teachers_df["teacher_code"].dropna().tolist())
        )
        absent_day = c2.selectbox(
            "Select Day of Leave",
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Adjust Timetable for Leave", type="primary"):
                new_tt = adjust_for_leave(
                    st.session_state["base_timetable"],
                    absent_teacher,
                    absent_day
                )
                st.session_state["timetable"] = new_tt
                st.success(
                    f"Schedule adjusted for {absent_teacher} on {absent_day}. "
                    "Later classes have been pulled forward."
                )

        with col2:
            if st.button("Reset to Original Schedule"):
                st.session_state["timetable"] = copy.deepcopy(
                    st.session_state["base_timetable"]
                )
                st.info("Original schedule restored.")


# ==========================================
# 11. TEACHERS PAGE (with Edit & Delete)
# ==========================================
elif page == "Teachers":
    st.title("👨‍🏫 Teachers")

    # Add Form
    with st.form("teacher_form"):
        c1, c2 = st.columns(2)
        teacher_code = c1.text_input("Teacher Code")
        teacher_name = c2.text_input("Teacher Name")

        c3, c4 = st.columns(2)
        short_name = c3.text_input("Short Name")
        department = c4.text_input("Department", value="CSE")

        submitted = st.form_submit_button("Add Teacher")
        if submitted:
            if teacher_code and teacher_name:
                new_row = pd.DataFrame([{
                    "teacher_code": teacher_code.strip(),
                    "teacher_name": teacher_name.strip(),
                    "short_name": short_name.strip(),
                    "department": department.strip()
                }])
                teachers_df = pd.concat(
                    [teachers_df, new_row], ignore_index=True
                )
                save_csv(teachers_df, "teachers.csv")
                st.success("Teacher added successfully.")
                st.rerun()
            else:
                st.error("Teacher code and name are required.")

    st.markdown("---")
    st.subheader("Teacher List")

    if teachers_df.empty:
        st.info("No teachers added yet.")
    else:
        # Edit Form (shown when edit button is clicked)
        if st.session_state["edit_teacher_idx"] is not None:
            idx = st.session_state["edit_teacher_idx"]
            st.subheader(f"✏️ Editing Row {idx}")
            row = teachers_df.loc[idx]

            with st.form("edit_teacher_form"):
                c1, c2 = st.columns(2)
                new_code = c1.text_input("Teacher Code", value=str(row["teacher_code"]))
                new_name = c2.text_input("Teacher Name", value=str(row["teacher_name"]))

                c3, c4 = st.columns(2)
                new_short = c3.text_input("Short Name", value=str(row["short_name"]))
                new_dept = c4.text_input("Department", value=str(row["department"]))

                cs1, cs2 = st.columns(2)
                save_btn = cs1.form_submit_button("💾 Save Changes")
                cancel_btn = cs2.form_submit_button("❌ Cancel")

                if save_btn:
                    teachers_df.at[idx, "teacher_code"] = new_code.strip()
                    teachers_df.at[idx, "teacher_name"] = new_name.strip()
                    teachers_df.at[idx, "short_name"] = new_short.strip()
                    teachers_df.at[idx, "department"] = new_dept.strip()
                    save_csv(teachers_df, "teachers.csv")
                    st.session_state["edit_teacher_idx"] = None
                    st.success("Teacher updated successfully.")
                    st.rerun()

                if cancel_btn:
                    st.session_state["edit_teacher_idx"] = None
                    st.rerun()

        # Table with Edit/Delete buttons
        for idx, row in teachers_df.iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([2, 3, 2, 2, 1, 1])
            col1.write(row["teacher_code"])
            col2.write(row["teacher_name"])
            col3.write(row["short_name"])
            col4.write(row["department"])

            if col5.button("✏️", key=f"edit_t_{idx}"):
                st.session_state["edit_teacher_idx"] = idx
                st.rerun()

            if col6.button("🗑️", key=f"del_t_{idx}"):
                teachers_df = teachers_df.drop(index=idx).reset_index(drop=True)
                save_csv(teachers_df, "teachers.csv")
                st.success("Teacher deleted.")
                st.rerun()


# ==========================================
# 12. SUBJECTS PAGE (with Edit & Delete)
# ==========================================
elif page == "Subjects":
    st.title("📘 Subjects")

    # Add Form
    with st.form("subject_form"):
        c1, c2 = st.columns(2)
        subject_code = c1.text_input("Subject Code")
        subject_name = c2.text_input("Subject Name")

        c3, c4 = st.columns(2)
        subject_type = c3.selectbox(
            "Subject Type", ["THEORY", "LAB", "ELECTIVE", "OPEN_ELECTIVE"]
        )
        requires_lab_room = c4.checkbox("Requires Lab Room", value=False)

        st.subheader("Weekly Hours Distribution (L-T-P)")
        c5, c6, c7, c8 = st.columns(4)
        l_hours = c5.number_input("L (Lecture)", min_value=0, max_value=10, value=3)
        t_hours = c6.number_input("T (Tutorial)", min_value=0, max_value=10, value=0)
        p_hours = c7.number_input("P (Practical)", min_value=0, max_value=10, value=0)
        continuous_slots = c8.number_input(
            "Continuous Slots Required", min_value=1, max_value=4, value=1
        )

        submitted = st.form_submit_button("Add Subject")
        if submitted:
            if subject_code and subject_name:
                new_row = pd.DataFrame([{
                    "subject_code": subject_code.strip(),
                    "subject_name": subject_name.strip(),
                    "subject_type": subject_type,
                    "l_hours": int(l_hours),
                    "t_hours": int(t_hours),
                    "p_hours": int(p_hours),
                    "requires_lab_room": requires_lab_room,
                    "continuous_slots_required": int(continuous_slots)
                }])
                subjects_df = pd.concat(
                    [subjects_df, new_row], ignore_index=True
                )
                save_csv(subjects_df, "subjects.csv")
                st.success("Subject added successfully.")
                st.rerun()
            else:
                st.error("Subject code and name are required.")

    st.markdown("---")
    st.subheader("Subject List")

    if subjects_df.empty:
        st.info("No subjects added yet.")
    else:
        # Edit Form
        if st.session_state["edit_subject_idx"] is not None:
            idx = st.session_state["edit_subject_idx"]
            st.subheader(f"✏️ Editing Row {idx}")
            row = subjects_df.loc[idx]

            with st.form("edit_subject_form"):
                c1, c2 = st.columns(2)
                n_code = c1.text_input("Subject Code", value=str(row["subject_code"]))
                n_name = c2.text_input("Subject Name", value=str(row["subject_name"]))

                c3, c4 = st.columns(2)
                type_options = ["THEORY", "LAB", "ELECTIVE", "OPEN_ELECTIVE"]
                current_type = str(row["subject_type"])
                type_idx = type_options.index(current_type) if current_type in type_options else 0
                n_type = c3.selectbox("Subject Type", type_options, index=type_idx)
                n_req_lab = c4.checkbox(
                    "Requires Lab Room",
                    value=bool(row["requires_lab_room"])
                )

                st.subheader("Weekly Hours (L-T-P)")
                c5, c6, c7, c8 = st.columns(4)
                n_l = c5.number_input("L", 0, 10, int(row["l_hours"]))
                n_t = c6.number_input("T", 0, 10, int(row["t_hours"]))
                n_p = c7.number_input("P", 0, 10, int(row["p_hours"]))
                n_cs = c8.number_input(
                    "Continuous Slots", 1, 4,
                    int(row["continuous_slots_required"])
                )

                cs1, cs2 = st.columns(2)
                save_btn = cs1.form_submit_button("💾 Save Changes")
                cancel_btn = cs2.form_submit_button("❌ Cancel")

                if save_btn:
                    subjects_df.at[idx, "subject_code"] = n_code.strip()
                    subjects_df.at[idx, "subject_name"] = n_name.strip()
                    subjects_df.at[idx, "subject_type"] = n_type
                    subjects_df.at[idx, "l_hours"] = n_l
                    subjects_df.at[idx, "t_hours"] = n_t
                    subjects_df.at[idx, "p_hours"] = n_p
                    subjects_df.at[idx, "requires_lab_room"] = n_req_lab
                    subjects_df.at[idx, "continuous_slots_required"] = n_cs
                    save_csv(subjects_df, "subjects.csv")
                    st.session_state["edit_subject_idx"] = None
                    st.success("Subject updated successfully.")
                    st.rerun()

                if cancel_btn:
                    st.session_state["edit_subject_idx"] = None
                    st.rerun()

        # Table
        header = st.columns([2, 3, 2, 1, 1, 1, 2, 1, 1])
        header[0].markdown("**Code**")
        header[1].markdown("**Name**")
        header[2].markdown("**Type**")
        header[3].markdown("**L**")
        header[4].markdown("**T**")
        header[5].markdown("**P**")
        header[6].markdown("**Slots**")
        header[7].markdown("**Edit**")
        header[8].markdown("**Del**")

        for idx, row in subjects_df.iterrows():
            col = st.columns([2, 3, 2, 1, 1, 1, 2, 1, 1])
            col[0].write(row["subject_code"])
            col[1].write(row["subject_name"])
            col[2].write(row["subject_type"])
            col[3].write(int(row["l_hours"]))
            col[4].write(int(row["t_hours"]))
            col[5].write(int(row["p_hours"]))
            col[6].write(int(row["continuous_slots_required"]))

            if col[7].button("✏️", key=f"edit_s_{idx}"):
                st.session_state["edit_subject_idx"] = idx
                st.rerun()

            if col[8].button("🗑️", key=f"del_s_{idx}"):
                subjects_df = subjects_df.drop(index=idx).reset_index(drop=True)
                save_csv(subjects_df, "subjects.csv")
                st.success("Subject deleted.")
                st.rerun()


# ==========================================
# 13. CLASSES / SECTIONS PAGE (with Edit & Delete)
# ==========================================
elif page == "Classes / Sections":
    st.title("🏫 Classes / Sections")
    st.write(
        "Sections are fully dynamic. Add A, B, C, D as per requirement. "
        "The generator will automatically handle all sections."
    )

    # Add Form
    with st.form("class_form"):
        c1, c2, c3 = st.columns(3)
        session_name = c1.text_input("Session Name", value="2025-26-even")
        batch_year = c2.number_input(
            "Batch Year", min_value=2020, max_value=2035, value=2024
        )
        semester = c3.number_input(
            "Semester", min_value=1, max_value=8, value=4
        )

        c4, c5, c6 = st.columns(3)
        section = c4.text_input("Section", value="A")
        program = c5.text_input("Program", value="CSE")
        strength = c6.number_input(
            "Strength", min_value=1, max_value=200, value=60
        )

        submitted = st.form_submit_button("Add Class Section")
        if submitted:
            if session_name and section:
                new_row = pd.DataFrame([{
                    "session_name": session_name.strip(),
                    "batch_year": int(batch_year),
                    "semester": int(semester),
                    "section": section.strip(),
                    "program": program.strip(),
                    "strength": int(strength)
                }])
                classes_df = pd.concat(
                    [classes_df, new_row], ignore_index=True
                )
                save_csv(classes_df, "classes.csv")
                st.success("Class section added successfully.")
                st.rerun()
            else:
                st.error("Session name and section are required.")

    st.markdown("---")
    st.subheader("Class Sections")

    if classes_df.empty:
        st.info("No class sections added yet.")
    else:
        # Edit Form
        if st.session_state["edit_class_idx"] is not None:
            idx = st.session_state["edit_class_idx"]
            st.subheader(f"✏️ Editing Row {idx}")
            row = classes_df.loc[idx]

            with st.form("edit_class_form"):
                c1, c2, c3 = st.columns(3)
                n_sess = c1.text_input("Session Name", value=str(row["session_name"]))
                n_yr = c2.number_input(
                    "Batch Year", 2020, 2035, int(row["batch_year"])
                )
                n_sem = c3.number_input("Semester", 1, 8, int(row["semester"]))

                c4, c5, c6 = st.columns(3)
                n_sec = c4.text_input("Section", value=str(row["section"]))
                n_prog = c5.text_input("Program", value=str(row["program"]))
                n_str = c6.number_input("Strength", 1, 200, int(row["strength"]))

                cs1, cs2 = st.columns(2)
                save_btn = cs1.form_submit_button("💾 Save Changes")
                cancel_btn = cs2.form_submit_button("❌ Cancel")

                if save_btn:
                    classes_df.at[idx, "session_name"] = n_sess.strip()
                    classes_df.at[idx, "batch_year"] = n_yr
                    classes_df.at[idx, "semester"] = n_sem
                    classes_df.at[idx, "section"] = n_sec.strip()
                    classes_df.at[idx, "program"] = n_prog.strip()
                    classes_df.at[idx, "strength"] = n_str
                    save_csv(classes_df, "classes.csv")
                    st.session_state["edit_class_idx"] = None
                    st.success("Class section updated.")
                    st.rerun()

                if cancel_btn:
                    st.session_state["edit_class_idx"] = None
                    st.rerun()

        # Table
        for idx, row in classes_df.iterrows():
            col = st.columns([2, 2, 1, 1, 2, 1, 1, 1])
            col[0].write(row["session_name"])
            col[1].write(row["program"])
            col[2].write(int(row["batch_year"]))
            col[3].write(f"Sem {int(row['semester'])}")
            col[4].write(f"Section {row['section']}")
            col[5].write(int(row["strength"]))

            if col[6].button("✏️", key=f"edit_c_{idx}"):
                st.session_state["edit_class_idx"] = idx
                st.rerun()

            if col[7].button("🗑️", key=f"del_c_{idx}"):
                classes_df = classes_df.drop(index=idx).reset_index(drop=True)
                save_csv(classes_df, "classes.csv")
                st.success("Class section deleted.")
                st.rerun()

        st.markdown("---")
        st.subheader("Dynamic Section Summary")
        summary = classes_df.groupby(
            ["session_name", "batch_year", "semester"]
        )["section"].apply(list).reset_index()
        st.dataframe(summary, use_container_width=True)


# ==========================================
# 14. ROOMS PAGE (with Edit & Delete)
# ==========================================
elif page == "Rooms":
    st.title("🚪 Rooms")

    # Add Form
    with st.form("room_form"):
        c1, c2, c3 = st.columns(3)
        room_name = c1.text_input("Room Name")
        room_type = c2.selectbox("Room Type", ["CLASSROOM", "LAB"])
        capacity = c3.number_input(
            "Capacity", min_value=1, max_value=300, value=60
        )

        submitted = st.form_submit_button("Add Room")
        if submitted:
            if room_name:
                new_row = pd.DataFrame([{
                    "room_name": room_name.strip(),
                    "room_type": room_type,
                    "capacity": int(capacity)
                }])
                rooms_df = pd.concat([rooms_df, new_row], ignore_index=True)
                save_csv(rooms_df, "rooms.csv")
                st.success("Room added successfully.")
                st.rerun()
            else:
                st.error("Room name is required.")

    st.markdown("---")
    st.subheader("Room List")

    if rooms_df.empty:
        st.info("No rooms added yet.")
    else:
        # Edit Form
        if st.session_state["edit_room_idx"] is not None:
            idx = st.session_state["edit_room_idx"]
            st.subheader(f"✏️ Editing Row {idx}")
            row = rooms_df.loc[idx]

            with st.form("edit_room_form"):
                c1, c2, c3 = st.columns(3)
                n_name = c1.text_input("Room Name", value=str(row["room_name"]))
                type_opts = ["CLASSROOM", "LAB"]
                cur_type = str(row["room_type"])
                t_idx = type_opts.index(cur_type) if cur_type in type_opts else 0
                n_type = c2.selectbox("Room Type", type_opts, index=t_idx)
                n_cap = c3.number_input("Capacity", 1, 300, int(row["capacity"]))

                cs1, cs2 = st.columns(2)
                save_btn = cs1.form_submit_button("💾 Save Changes")
                cancel_btn = cs2.form_submit_button("❌ Cancel")

                if save_btn:
                    rooms_df.at[idx, "room_name"] = n_name.strip()
                    rooms_df.at[idx, "room_type"] = n_type
                    rooms_df.at[idx, "capacity"] = n_cap
                    save_csv(rooms_df, "rooms.csv")
                    st.session_state["edit_room_idx"] = None
                    st.success("Room updated.")
                    st.rerun()

                if cancel_btn:
                    st.session_state["edit_room_idx"] = None
                    st.rerun()

        # Table
        header = st.columns([3, 2, 2, 1, 1])
        header[0].markdown("**Room Name**")
        header[1].markdown("**Type**")
        header[2].markdown("**Capacity**")
        header[3].markdown("**Edit**")
        header[4].markdown("**Delete**")

        for idx, row in rooms_df.iterrows():
            col = st.columns([3, 2, 2, 1, 1])
            col[0].write(row["room_name"])
            col[1].write(row["room_type"])
            col[2].write(int(row["capacity"]))

            if col[3].button("✏️", key=f"edit_r_{idx}"):
                st.session_state["edit_room_idx"] = idx
                st.rerun()

            if col[4].button("🗑️", key=f"del_r_{idx}"):
                rooms_df = rooms_df.drop(index=idx).reset_index(drop=True)
                save_csv(rooms_df, "rooms.csv")
                st.success("Room deleted.")
                st.rerun()


# ==========================================
# 15. TEACHER PREFERENCES PAGE (with Edit & Delete)
# ==========================================
elif page == "Teacher Preferences":
    st.title("⭐ Teacher Preferences")

    if teachers_df.empty or subjects_df.empty:
        st.warning("Please add teachers and subjects first.")
    else:
        # Add Form
        with st.form("preference_form"):
            c1, c2 = st.columns(2)
            session_name = c1.text_input("Session Name", value="2025-26-even")
            teacher_code = c2.selectbox(
                "Teacher", teachers_df["teacher_code"].dropna().tolist()
            )

            c3, c4 = st.columns(2)
            subject_code = c3.selectbox(
                "Subject", subjects_df["subject_code"].dropna().tolist()
            )
            preference_order = c4.number_input(
                "Preference Order (1 = Highest)", min_value=1, max_value=10, value=1
            )

            submitted = st.form_submit_button("Add Preference")
            if submitted:
                new_row = pd.DataFrame([{
                    "session_name": session_name.strip(),
                    "teacher_code": teacher_code,
                    "subject_code": subject_code,
                    "preference_order": int(preference_order)
                }])
                preferences_df = pd.concat(
                    [preferences_df, new_row], ignore_index=True
                )
                save_csv(preferences_df, "preferences.csv")
                st.success("Preference added successfully.")
                st.rerun()

    st.markdown("---")
    st.subheader("Preference List")

    if preferences_df.empty:
        st.info("No preferences added yet.")
    else:
        # Edit Form
        if st.session_state["edit_pref_idx"] is not None:
            idx = st.session_state["edit_pref_idx"]
            st.subheader(f"✏️ Editing Row {idx}")
            row = preferences_df.loc[idx]

            with st.form("edit_pref_form"):
                c1, c2 = st.columns(2)
                n_sess = c1.text_input(
                    "Session Name", value=str(row["session_name"])
                )
                tc_opts = teachers_df["teacher_code"].dropna().tolist()
                cur_tc = str(row["teacher_code"])
                tc_idx = tc_opts.index(cur_tc) if cur_tc in tc_opts else 0
                n_tc = c2.selectbox("Teacher", tc_opts, index=tc_idx)

                c3, c4 = st.columns(2)
                sc_opts = subjects_df["subject_code"].dropna().tolist()
                cur_sc = str(row["subject_code"])
                sc_idx = sc_opts.index(cur_sc) if cur_sc in sc_opts else 0
                n_sc = c3.selectbox("Subject", sc_opts, index=sc_idx)
                n_pref = c4.number_input(
                    "Preference Order", 1, 10, int(row["preference_order"])
                )

                cs1, cs2 = st.columns(2)
                save_btn = cs1.form_submit_button("💾 Save Changes")
                cancel_btn = cs2.form_submit_button("❌ Cancel")

                if save_btn:
                    preferences_df.at[idx, "session_name"] = n_sess.strip()
                    preferences_df.at[idx, "teacher_code"] = n_tc
                    preferences_df.at[idx, "subject_code"] = n_sc
                    preferences_df.at[idx, "preference_order"] = n_pref
                    save_csv(preferences_df, "preferences.csv")
                    st.session_state["edit_pref_idx"] = None
                    st.success("Preference updated.")
                    st.rerun()

                if cancel_btn:
                    st.session_state["edit_pref_idx"] = None
                    st.rerun()

        # Table
        header = st.columns([2, 2, 2, 1, 1, 1])
        header[0].markdown("**Session**")
        header[1].markdown("**Teacher**")
        header[2].markdown("**Subject**")
        header[3].markdown("**Priority**")
        header[4].markdown("**Edit**")
        header[5].markdown("**Delete**")

        for idx, row in preferences_df.iterrows():
            col = st.columns([2, 2, 2, 1, 1, 1])
            col[0].write(row["session_name"])
            col[1].write(row["teacher_code"])
            col[2].write(row["subject_code"])
            col[3].write(int(row["preference_order"]))

            if col[4].button("✏️", key=f"edit_p_{idx}"):
                st.session_state["edit_pref_idx"] = idx
                st.rerun()

            if col[5].button("🗑️", key=f"del_p_{idx}"):
                preferences_df = preferences_df.drop(
                    index=idx
                ).reset_index(drop=True)
                save_csv(preferences_df, "preferences.csv")
                st.success("Preference deleted.")
                st.rerun()


# ==========================================
# 16. CLASS SUBJECT MAPPING PAGE (with Edit & Delete)
# ==========================================
elif page == "Class Subject Mapping":
    st.title("🧩 Class Subject Mapping")

    if classes_df.empty or subjects_df.empty:
        st.warning("Please add classes and subjects first.")
    else:
        # Add Form
        with st.form("class_subject_form"):
            session_name = st.text_input("Session Name", value="2025-26-even")

            c1, c2, c3, c4 = st.columns(4)
            batch_year = c1.selectbox(
                "Batch Year",
                sorted(classes_df["batch_year"].dropna().unique().tolist())
            )
            semester = c2.selectbox(
                "Semester",
                sorted(classes_df["semester"].dropna().unique().tolist())
            )
            section = c3.text_input("Section", value="A")
            subject_code = c4.selectbox(
                "Subject", subjects_df["subject_code"].dropna().tolist()
            )

            st.subheader("Weekly Hours Distribution (L-T-P)")
            c5, c6, c7 = st.columns(3)
            l_hours = c5.number_input(
                "L (Lecture)", min_value=0, max_value=10, value=3
            )
            t_hours = c6.number_input(
                "T (Tutorial)", min_value=0, max_value=10, value=0
            )
            p_hours = c7.number_input(
                "P (Practical)", min_value=0, max_value=10, value=0
            )

            c8, c9 = st.columns(2)
            is_lab = c8.checkbox("Is Lab", value=False)
            lab_continuous_slots = c9.number_input(
                "Lab Continuous Slots", min_value=1, max_value=4, value=2
            )

            elective_group = st.text_input(
                "Elective / Open Elective Group (e.g. E1, OE1 — leave blank for normal subjects)",
                value=""
            )

            submitted = st.form_submit_button("Add Mapping")
            if submitted:
                new_row = pd.DataFrame([{
                    "session_name": session_name.strip(),
                    "batch_year": int(batch_year),
                    "semester": int(semester),
                    "section": section.strip(),
                    "subject_code": subject_code,
                    "l_hours": int(l_hours),
                    "t_hours": int(t_hours),
                    "p_hours": int(p_hours),
                    "is_lab": is_lab,
                    "lab_continuous_slots": int(lab_continuous_slots),
                    "elective_group": elective_group.strip()
                }])
                class_subjects_df = pd.concat(
                    [class_subjects_df, new_row], ignore_index=True
                )
                save_csv(class_subjects_df, "class_subjects.csv")
                st.success("Class-subject mapping added successfully.")
                st.rerun()

    st.markdown("---")
    st.subheader("Class Subject Mappings")

    if class_subjects_df.empty:
        st.info("No mappings added yet.")
    else:
        # Edit Form
        if st.session_state["edit_cs_idx"] is not None:
            idx = st.session_state["edit_cs_idx"]
            st.subheader(f"✏️ Editing Row {idx}")
            row = class_subjects_df.loc[idx]

            with st.form("edit_cs_form"):
                n_sess = st.text_input(
                    "Session Name", value=str(row["session_name"])
                )

                c1, c2, c3, c4 = st.columns(4)
                n_yr = c1.number_input(
                    "Batch Year", 2020, 2035, int(row["batch_year"])
                )
                n_sem = c2.number_input("Semester", 1, 8, int(row["semester"]))
                n_sec = c3.text_input("Section", value=str(row["section"]))
                sc_opts = subjects_df["subject_code"].dropna().tolist()
                cur_sc = str(row["subject_code"])
                sc_i = sc_opts.index(cur_sc) if cur_sc in sc_opts else 0
                n_sc = c4.selectbox("Subject", sc_opts, index=sc_i)

                st.subheader("Weekly Hours (L-T-P)")
                c5, c6, c7 = st.columns(3)
                n_l = c5.number_input("L", 0, 10, int(row["l_hours"]))
                n_t = c6.number_input("T", 0, 10, int(row["t_hours"]))
                n_p = c7.number_input("P", 0, 10, int(row["p_hours"]))

                c8, c9 = st.columns(2)
                n_islab = c8.checkbox("Is Lab", value=bool(row["is_lab"]))
                n_cont = c9.number_input(
                    "Continuous Slots", 1, 4, int(row["lab_continuous_slots"])
                )
                n_eg = st.text_input(
                    "Elective Group", value=str(row["elective_group"])
                    if pd.notna(row["elective_group"]) else ""
                )

                cs1, cs2 = st.columns(2)
                save_btn = cs1.form_submit_button("💾 Save Changes")
                cancel_btn = cs2.form_submit_button("❌ Cancel")

                if save_btn:
                    class_subjects_df.at[idx, "session_name"] = n_sess.strip()
                    class_subjects_df.at[idx, "batch_year"] = n_yr
                    class_subjects_df.at[idx, "semester"] = n_sem
                    class_subjects_df.at[idx, "section"] = n_sec.strip()
                    class_subjects_df.at[idx, "subject_code"] = n_sc
                    class_subjects_df.at[idx, "l_hours"] = n_l
                    class_subjects_df.at[idx, "t_hours"] = n_t
                    class_subjects_df.at[idx, "p_hours"] = n_p
                    class_subjects_df.at[idx, "is_lab"] = n_islab
                    class_subjects_df.at[idx, "lab_continuous_slots"] = n_cont
                    class_subjects_df.at[idx, "elective_group"] = n_eg.strip()
                    save_csv(class_subjects_df, "class_subjects.csv")
                    st.session_state["edit_cs_idx"] = None
                    st.success("Mapping updated.")
                    st.rerun()

                if cancel_btn:
                    st.session_state["edit_cs_idx"] = None
                    st.rerun()

        # Table with total hours
        temp_df = class_subjects_df.copy()
        temp_df["total"] = (
            temp_df["l_hours"].fillna(0).astype(int)
            + temp_df["t_hours"].fillna(0).astype(int)
            + temp_df["p_hours"].fillna(0).astype(int)
        )

        header = st.columns([2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1])
        header[0].markdown("**Session**")
        header[1].markdown("**Sem**")
        header[2].markdown("**Sec**")
        header[3].markdown("**Subject**")
        header[4].markdown("**L-T-P**")
        header[5].markdown("**Total**")
        header[6].markdown("**Lab**")
        header[7].markdown("**Slots**")
        header[8].markdown("**Elective Grp**")
        header[9].markdown("**Edit**")
        header[10].markdown("**Del**")

        for idx, row in temp_df.iterrows():
            col = st.columns([2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 1])
            col[0].write(row["session_name"])
            col[1].write(int(row["semester"]))
            col[2].write(row["section"])
            col[3].write(row["subject_code"])
            col[4].write(
                f"{int(row['l_hours'])}-{int(row['t_hours'])}-{int(row['p_hours'])}"
            )
            col[5].write(int(row["total"]))
            col[6].write("✅" if row["is_lab"] else "❌")
            col[7].write(int(row["lab_continuous_slots"]))
            col[8].write(
                str(row["elective_group"])
                if pd.notna(row["elective_group"]) else "-"
            )

            if col[9].button("✏️", key=f"edit_cs_{idx}"):
                st.session_state["edit_cs_idx"] = idx
                st.rerun()

            if col[10].button("🗑️", key=f"del_cs_{idx}"):
                class_subjects_df = class_subjects_df.drop(
                    index=idx
                ).reset_index(drop=True)
                save_csv(class_subjects_df, "class_subjects.csv")
                st.success("Mapping deleted.")
                st.rerun()