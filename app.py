from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)

# Connect to your MongoDB. Replace with your own connection string:
client = MongoClient("mongodb+srv://<username>:<password>@<cluster-url>/webhook_db?retryWrites=true&w=majority")
db = client["webhook_db"]
events = db["events"]

@app.route("/webhook", methods=["POST"])
def github_webhook():
    data = request.json

    # Handle PUSH event
    if "commits" in data:
        author = data["pusher"]["name"]
        branch = data["ref"].split("/")[-1]
        timestamp = datetime.utcnow().isoformat()
        events.insert_one({
            "type": "push",
            "author": author,
            "branch": branch,
            "timestamp": timestamp
        })
    # Handle PULL REQUEST event
    elif "pull_request" in data:
        pr = data["pull_request"]
        author = pr["user"]["login"]
        from_branch = pr["head"]["ref"]
        to_branch = pr["base"]["ref"]
        timestamp = datetime.utcnow().isoformat()
        events.insert_one({
            "type": "pull_request",
            "author": author,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "timestamp": timestamp
        })

    return jsonify({"status": "ok"}), 200

@app.route("/events", methods=["GET"])
def get_events():
    latest_events = list(events.find().sort("timestamp", -1).limit(10))
    for e in latest_events:
        e["_id"] = str(e["_id"])  # Convert ObjectId to string
    return jsonify(latest_events)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
