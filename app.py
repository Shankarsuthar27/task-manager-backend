from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv
from postgrest.exceptions import APIError
import os

from services.gmail_service import send_email

load_dotenv()

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL")

# ── Anon client  (used for tasks — respects RLS) ──────────────────────────────
supabase = create_client(SUPABASE_URL, os.getenv("SUPABASE_KEY"))

# ── Admin client (uses service_role key — bypasses RLS for user sync) ─────────
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else None

# ──────────────────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/users/sync", methods=["POST"])
def sync_user():
    """
    Upsert the user into public.users.
    Tries service_role client first (bypasses RLS), falls back to anon.
    Body: { id, email, name? }
    """
    data = request.json
    if not data or not data.get("id") or not data.get("email"):
        return jsonify({"error": "id and email are required"}), 400

    user_record_full_name = {"id": data["id"], "email": data["email"]}
    user_record_name      = {"id": data["id"], "email": data["email"]}
    user_record_minimal   = {"id": data["id"], "email": data["email"]}

    if data.get("name"):
        user_record_full_name["full_name"] = data["name"]
        user_record_name["name"] = data["name"]

    clients_to_try = [c for c in [supabase_admin, supabase] if c is not None]

    for client in clients_to_try:
        # Try with full_name first, then name, then fallback to minimal
        for record in [user_record_full_name, user_record_name, user_record_minimal]:
            try:
                response = client.table("users") \
                    .upsert(record, on_conflict="id") \
                    .execute()
                return jsonify(response.data), 200
            except APIError as e:
                print(f"User sync attempt failed ({list(record.keys())}): {e}")
                continue

    return jsonify({"warning": "User sync failed — tasks will be created without user tracking"}), 503

@app.route("/users", methods=["GET"])
def get_users():
    """Return all users. Tries different column sets gracefully."""
    # Try most complete set first, progressively fall back
    column_sets = [
        "id, email, full_name, is_admin",
        "id, email, name, is_admin",
        "id, email, full_name",
        "id, email, name",
        "id, email, is_admin",
        "id, email",
    ]
    # Prefer service_role for reading users, but fall back to anon
    clients_to_try = [c for c in [supabase_admin, supabase] if c is not None]

    for client in clients_to_try:
        for cols in column_sets:
            try:
                response = client.table("users").select(cols).execute()
                data = response.data or []
                # Normalize: ensure is_admin and name always exist
                result = []
                for u in data:
                    name_val = u.get("full_name") or u.get("name") or u.get("email", "")
                    result.append({
                        "id":       u.get("id", ""),
                        "email":    u.get("email", ""),
                        "name":     name_val,
                        "is_admin": u.get("is_admin", False),
                    })
                return jsonify(result)
            except Exception:
                continue

    return jsonify([])


# ──────────────────────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/tasks", methods=["POST"])
def create_task():
    """
    Create a task and send email notification to the assigned user.

    Expected body:
      title          str  (required)
      description    str
      created_by     uuid  (auth user ID)
      created_by_email str  (passed directly — no users table query needed)
      created_by_name  str
      assigned_to    uuid
      assigned_email str  (passed directly — no users table query needed)
      assigned_name  str
    """
    data = request.json
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Task title is required"}), 400

    task = {
        "title":       title,
        "description": data.get("description", ""),
        "status":      "pending",
    }

    # Only attach FK fields when service_role key is configured
    if supabase_admin and data.get("created_by"):
        task["created_by"] = data["created_by"]
    if supabase_admin and data.get("assigned_to"):
        task["assigned_to"] = data["assigned_to"]

    # ── Insert with FK-safe retry ──────────────────────────────────────────────
    try:
        response = supabase.table("tasks").insert(task).execute()
    except APIError as e:
        error_msg = str(e)
        if "foreign key constraint" in error_msg or "23503" in error_msg:
            print("FK constraint hit — retrying without created_by/assigned_to")
            task_safe = {
                "title":       task["title"],
                "description": task["description"],
                "status":      task["status"],
            }
            try:
                response = supabase.table("tasks").insert(task_safe).execute()
            except APIError as e2:
                return jsonify({"error": e2.message or str(e2)}), 500
        else:
            return jsonify({"error": e.message or str(e)}), 500

    # ── Email notification (uses emails passed directly in the request) ────────
    assigned_email = data.get("assigned_email", "").strip()
    assigned_name  = data.get("assigned_name",  "there")
    creator_name   = data.get("created_by_name", "A teammate")
    description    = data.get("description", "(none)")

    if assigned_email:
        send_email(
            to=assigned_email,
            subject=f"[TaskFlow] New Task Assigned: {title}",
            body=(
                f"Hi {assigned_name},\n\n"
                f"{creator_name} has assigned you a new task:\n\n"
                f"  📌 Title:       {title}\n"
                f"  📝 Description: {description}\n\n"
                f"Please log in to TaskFlow to view and manage this task.\n\n"
                f"— TaskFlow"
            )
        )

    return jsonify(response.data), 201


@app.route("/tasks", methods=["GET"])
def get_tasks():
    """
    Return tasks. Supports optional ?assigned_to=<uuid> filter
    so users can fetch only tasks assigned to them.
    """
    assigned_to = request.args.get("assigned_to", "").strip()
    try:
        query = supabase.table("tasks").select("*")
        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        response = query.order("created_at", desc=True).execute()
        return jsonify(response.data)
    except APIError as e:
        return jsonify({"error": e.message or str(e)}), 500


@app.route("/tasks/<task_id>/complete", methods=["PUT"])
def complete_task(task_id):
    """
    Mark task complete and email both creator and assignee.

    Expected body (optional):
      creator_email  str
      creator_name   str
      assigned_email str
      assigned_name  str
    """
    data = request.json or {}

    try:
        response = supabase.table("tasks") \
            .update({"status": "completed"}) \
            .eq("id", task_id) \
            .execute()
    except APIError as e:
        return jsonify({"error": e.message or str(e)}), 500

    if not response.data:
        return jsonify({"error": "Task not found"}), 404

    task       = response.data[0]
    task_title = task.get("title", "")

    # ── Build list of recipients from request body ─────────────────────────────
    recipients = []

    creator_email = data.get("creator_email", "").strip()
    creator_name  = data.get("creator_name",  "there")
    if creator_email:
        recipients.append({"email": creator_email, "name": creator_name, "role": "creator"})

    assigned_email = data.get("assigned_email", "").strip()
    assigned_name  = data.get("assigned_name",  "there")
    # Avoid duplicate email if creator == assignee
    if assigned_email and assigned_email != creator_email:
        recipients.append({"email": assigned_email, "name": assigned_name, "role": "assignee"})

    # ── Send completion emails ─────────────────────────────────────────────────
    for r in recipients:
        send_email(
            to=r["email"],
            subject=f"[TaskFlow] ✅ Task Completed: {task_title}",
            body=(
                f"Hi {r['name']},\n\n"
                f"Great news! The following task has been marked as completed:\n\n"
                f"  ✅ Title: {task_title}\n\n"
                f"You are receiving this notification as the {r['role']} of this task.\n\n"
                f"Keep up the great work!\n\n"
                f"— TaskFlow"
            )
        )

    return jsonify(response.data)


@app.route("/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """
    Delete a task by ID. Admin-only action (enforced on the frontend).
    """
    try:
        response = supabase.table("tasks") \
            .delete() \
            .eq("id", task_id) \
            .execute()
    except APIError as e:
        return jsonify({"error": e.message or str(e)}), 500

    return jsonify({"success": True, "deleted_id": task_id}), 200


if __name__ == "__main__":
    app.run(debug=True)