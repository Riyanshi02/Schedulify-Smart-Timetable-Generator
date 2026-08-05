# 📅 Pro Timetable Engine

**An automated, constraint-based college timetable generator built with Streamlit.**

Pro Timetable Engine takes department data — teachers, subjects, sections, rooms, and teacher preferences — and generates conflict-free weekly timetables for every class, with automated teacher allocation, elective handling, lab batching, and leave adjustment.

---

## ✨ Features

| Category | Capability |
|---|---|
| 🧠 Scheduling Engine | Constraint-based optimizer with hard & soft constraint scoring |
| 👥 Teacher Allocation | Preference-ranked assignment with a max weekly hour cap per teacher |
| 🧪 Lab/Tutorial Batching | Automatic G1 / G2 group splitting |
| 🔀 Electives | Cross-section electives & open electives scheduled in parallel |
| 🚫 Hard Constraints | Zero teacher clashes, room conflicts, or class double-booking |
| ⚖️ Soft Constraints | Even weekly load distribution, gap avoidance, time-of-day preference (labs → afternoon, theory → morning) |
| 🩺 Leave Manager | Adjusts a teacher's absence day and auto-compresses the schedule |
| ✏️ Full CRUD | Add / edit / delete for all data entities via the UI |
| 📤 Export | Per-class timetable download as CSV |
| 📊 Dashboard | Live summary metrics and subject-hour breakdown |

---

## 🏗️ How It Works

The engine runs in two stages:

1. **Teacher Allocation** — For every class–subject combination, teachers are assigned from a ranked preference list, subject to a maximum weekly teaching load (default: 24 hours). Unmatched combinations are flagged as `UNALLOCATED`.

2. **Timetable Generation** — Each Lecture / Tutorial / Practical block is placed into a Monday–Friday, 8-slot grid using a best-slot search that:
   - **Hard-enforces:** no teacher, room, or class conflicts
   - **Soft-optimizes:** load balancing across the week, gap minimization, subject repetition avoidance, and time-of-day preference

---

## 📁 Data Model

All data is stored as local CSV files under a `data/` directory (auto-created on first run).

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+

### Installation

```bash
git clone https://github.com/<your-username>/Pro-Timetable-Engine.git
cd Pro-Timetable-Engine
pip install -r requirements.txt
```

### Run the app

```bash
streamlit run main.py
```

The app will open in your browser at `http://localhost:8501`.

---

## 🖥️ Usage

1. Go to **Teachers / Subjects / Classes / Rooms** and add your department's data.
2. Set teacher subject preferences under **Teacher Preferences**.
3. Map subjects to class sections under **Class Subject Mapping**.
4. Head to **Generator**, select the session, and click **🚀 Generate Timetable**.
5. View and export each class's schedule from **Timetable Viewer**.
6. Use **Teacher Leave Manager** to auto-adjust a schedule when a teacher is absent for a day.

---

## 🛠️ Tech Stack

- **[Streamlit](https://streamlit.io/)** — UI framework
- **[Pandas](https://pandas.pydata.org/)** — data handling
- **CSV files** — lightweight, database-free persistence

---


## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
