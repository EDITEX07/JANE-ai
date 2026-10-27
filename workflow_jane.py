"""Workflow J.A.N.E. mission and task workspace."""
from datetime import datetime
import uuid
import streamlit as st

def render_workflow_workspace():
    st.markdown("# 🧭 Workflow J.A.N.E.")
    st.caption("Turn a goal into a mission, organize tasks, and track progress.")
    st.info("Workflow v1 stores missions in this active app session. Persistent, account-linked storage will be added after this first version is tested.")

    missions = st.session_state.workflow_missions
    with st.expander("＋ Create a mission", expanded=not bool(missions)):
        # Keep the optional-date toggle outside the form so Streamlit can rerun
        # and show/hide the date picker before the user submits the form.
        set_deadline = st.checkbox("Set a target date (optional)", key="workflow_set_deadline")
        with st.form("workflow_create_mission", clear_on_submit=True):
            mission_title = st.text_input("Mission name", placeholder="e.g. Build J.A.N.E. memory retrieval")
            mission_goal = st.text_area("Mission objective", placeholder="What does success look like?")
            mission_priority = st.selectbox("Priority", ["Low", "Normal", "High", "Critical"], index=1)
            mission_deadline = st.date_input("Target date", value=datetime.now().date()) if set_deadline else None
            create_mission = st.form_submit_button("Create mission", use_container_width=True)
            if create_mission:
                if not mission_title.strip():
                    st.error("Enter a mission name first.")
                else:
                    mission_id = str(uuid.uuid4())
                    missions[mission_id] = {
                        "title": mission_title.strip()[:120],
                        "goal": mission_goal.strip()[:3000],
                        "priority": mission_priority,
                        "deadline": mission_deadline.isoformat() if mission_deadline else "",
                        "status": "Active",
                        "created": datetime.now().isoformat(timespec="minutes"),
                        "tasks": [],
                        "notes": "",
                    }
                    st.session_state.active_workflow_mission = mission_id
                    st.rerun()

    if not missions:
        st.markdown("### Your mission board is ready")
        st.write("Create your first mission above. Each mission can contain tasks, progress, blockers, and a summary.")
    else:
        mission_ids = list(missions.keys())
        current_id = st.session_state.get("active_workflow_mission")
        if current_id not in missions:
            current_id = mission_ids[-1]
            st.session_state.active_workflow_mission = current_id
        labels = {mid: f"{missions[mid]['title']} · {missions[mid]['status']}" for mid in mission_ids}
        chosen_id = st.selectbox(
            "Select mission", mission_ids,
            index=mission_ids.index(current_id),
            format_func=lambda mid: labels.get(mid, mid),
            key="workflow_mission_picker",
        )
        st.session_state.active_workflow_mission = chosen_id
        mission = missions[chosen_id]
        tasks = mission.setdefault("tasks", [])
        completed = sum(1 for task in tasks if task.get("status") == "Completed")
        total = len(tasks)
        progress = int((completed / total) * 100) if total else 0
        blocked = sum(1 for task in tasks if task.get("status") == "Blocked")

        top = st.columns(4)
        top[0].metric("Progress", f"{progress}%")
        top[1].metric("Tasks", total)
        top[2].metric("Completed", completed)
        top[3].metric("Blocked", blocked)
        st.progress(progress / 100 if total else 0.0, text=f"{completed} of {total} tasks completed" if total else "Add tasks to begin tracking progress")

        left, right = st.columns([3, 2])
        with left:
            st.markdown("### Mission overview")
            st.markdown(f"**{mission['title']}**")
            st.write(mission.get("goal") or "No objective added yet.")
            meta = [f"Priority: {mission.get('priority', 'Normal')}", f"Status: {mission.get('status', 'Active')}"]
            if mission.get("deadline"):
                meta.append(f"Target date: {mission['deadline']}")
            st.caption(" · ".join(meta))
            with st.expander("Edit mission details"):
                with st.form(f"workflow_edit_{chosen_id}"):
                    edit_title = st.text_input("Mission name", value=mission.get("title", ""), max_chars=120)
                    edit_goal = st.text_area("Mission objective", value=mission.get("goal", ""), max_chars=3000)
                    edit_priority = st.selectbox("Priority", ["Low", "Normal", "High", "Critical"], index=["Low", "Normal", "High", "Critical"].index(mission.get("priority", "Normal")))
                    edit_status = st.selectbox("Mission status", ["Active", "Paused", "Completed", "Archived"], index=["Active", "Paused", "Completed", "Archived"].index(mission.get("status", "Active")))
                    edit_notes = st.text_area("Mission notes / blockers", value=mission.get("notes", ""), max_chars=5000)
                    save_details = st.form_submit_button("Save mission details")
                    if save_details:
                        if not edit_title.strip():
                            st.error("Mission name cannot be empty.")
                        else:
                            mission.update({"title": edit_title.strip(), "goal": edit_goal.strip(), "priority": edit_priority, "status": edit_status, "notes": edit_notes.strip()})
                            st.rerun()
        with right:
            st.markdown("### Mission summary")
            remaining = total - completed
            st.write(f"**{completed}** completed · **{remaining}** remaining · **{blocked}** blocked")
            if total == 0:
                st.write("No tasks yet. Add the first task to turn this mission into an actionable plan.")
            elif progress == 100:
                st.success("All tasks are complete. Review the mission notes before archiving it.")
            elif blocked:
                st.warning("There are blocked tasks. Review the task list and mission notes for the next action.")
            else:
                next_task = next((task for task in tasks if task.get("status") != "Completed"), None)
                if next_task:
                    st.write("**Next task:** " + next_task.get("title", "Untitled task"))
            if mission.get("notes", "").strip():
                st.markdown("**Notes / blockers**")
                st.write(mission["notes"])

        st.divider()
        st.markdown("### Task list")
        with st.form(f"workflow_add_task_{chosen_id}", clear_on_submit=True):
            task_title = st.text_input("New task", placeholder="Describe one concrete action")
            task_details = st.text_input("Task details (optional)", placeholder="Notes, dependencies, or definition of done")
            add_task = st.form_submit_button("＋ Add task", use_container_width=True)
            if add_task:
                if not task_title.strip():
                    st.error("Enter a task name.")
                else:
                    tasks.append({"id": str(uuid.uuid4()), "title": task_title.strip()[:180], "details": task_details.strip()[:1000], "status": "Not Started"})
                    st.rerun()

        if tasks:
            for index, task in enumerate(tasks):
                with st.container(border=True):
                    task_cols = st.columns([4, 2, 1])
                    with task_cols[0]:
                        st.markdown(f"**{index + 1}. {task.get('title', 'Untitled task')}**")
                        if task.get("details"):
                            st.caption(task["details"])
                    with task_cols[1]:
                        statuses = ["Not Started", "In Progress", "Blocked", "Completed"]
                        old_status = task.get("status", "Not Started")
                        if old_status not in statuses:
                            old_status = "Not Started"
                        new_status = st.selectbox("Status", statuses, index=statuses.index(old_status), key=f"workflow_status_{chosen_id}_{task['id']}", label_visibility="collapsed")
                        if new_status != task.get("status"):
                            task["status"] = new_status
                            st.rerun()
                    with task_cols[2]:
                        if st.button("✕", key=f"workflow_delete_{chosen_id}_{task['id']}", help="Delete task"):
                            mission["tasks"] = [item for item in tasks if item.get("id") != task.get("id")]
                            st.rerun()

        st.divider()
        summary_text = (
            f"MISSION: {mission.get('title', '')}\n"
            f"OBJECTIVE: {mission.get('goal', '')}\n"
            f"STATUS: {mission.get('status', 'Active')} | PRIORITY: {mission.get('priority', 'Normal')}\n"
            f"PROGRESS: {progress}% ({completed}/{total} tasks completed)\n"
            f"BLOCKED TASKS: {blocked}\n"
            f"NOTES: {mission.get('notes', '')}\n"
            "TASKS:\n" + "\n".join(f"- [{task.get('status', 'Not Started')}] {task.get('title', '')}" + (f" — {task.get('details', '')}" if task.get('details') else "") for task in tasks)
        )
        export_col, delete_col = st.columns(2)
        with export_col:
            st.download_button("⬇ Export mission summary", data=summary_text, file_name="jane_workflow_mission.txt", mime="text/plain", use_container_width=True)
        with delete_col:
            if st.button("Delete this mission", key=f"workflow_delete_mission_{chosen_id}", use_container_width=True):
                del missions[chosen_id]
                st.session_state.active_workflow_mission = next(iter(missions), None)
                st.rerun()

    st.caption("Workflow J.A.N.E. v1 · Mission data is session-only in this first implementation.")
    st.stop()
