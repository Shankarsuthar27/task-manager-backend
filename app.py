from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv
import os

from services.gmail_service import send_email

load_dotenv()

app = Flask(__name__)
CORS(app)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

@app.route("/")
def home():
    return {"message": "API Running"}

@app.route("/tasks", methods=["POST"])
def create_task():
    data = request.json

    task = {
        "title": data["title"],
        "description": data["description"],
        "created_by": data["created_by"],
        "assigned_to": data["assigned_to"]
    }

    response = supabase.table("tasks").insert(task).execute()

    assigned_user = supabase.table("users") \
        .select("*") \
        .eq("id", data["assigned_to"]) \
        .single() \
        .execute()

    email = assigned_user.data["email"]

    send_email(
        email,
        "New Task Assigned",
        f"You have been assigned task: {data['title']}"
    )

    return jsonify(response.data)

@app.route("/tasks", methods=["GET"])
def get_tasks():
    response = supabase.table("tasks").select("*").execute()
    return jsonify(response.data)

@app.route("/tasks/<task_id>/complete", methods=["PUT"])
def complete_task(task_id):

    response = supabase.table("tasks") \
        .update({"status": "completed"}) \
        .eq("id", task_id) \
        .execute()

    task = response.data[0]

    creator = supabase.table("users") \
        .select("*") \
        .eq("id", task["created_by"]) \
        .single() \
        .execute()

    send_email(
        creator.data["email"],
        "Task Completed",
        f"Task '{task['title']}' has been completed."
    )

    return jsonify(response.data)

if __name__ == "__main__":
    app.run(debug=True)