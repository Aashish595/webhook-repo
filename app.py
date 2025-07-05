from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# Initial setup
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# MongoDB connection helper
def get_db():
    """Connect to MongoDB and return database object"""
    client = MongoClient(
        os.getenv("MONGODB_URI"),
        connectTimeoutMS=5000,
        serverSelectionTimeoutMS=5000
    )
    client.admin.command('ping')  # Test connection
    db = client[os.getenv("MONGO_DB_NAME", "webhook_db")]
    db.events.create_index("timestamp")  # Create index for faster queries
    return db

db = get_db()

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Process GitHub webhook events"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid payload"}), 400

        # Common event data
        event = {
            "timestamp": datetime.utcnow(),
            "repository": data.get("repository", {}).get("name", "unknown")
        }

        # Handle different event types
        if "commits" in data:  # Push event
            event.update({
                "type": "push",
                "author": data["pusher"]["name"],
                "branch": data["ref"].split("/")[-1],
                "commit_id": data["head_commit"]["id"]
            })
        elif "pull_request" in data:  # PR event
            pr = data["pull_request"]
            event.update({
                "type": "pull_request",
                "author": pr["user"]["login"],
                "from_branch": pr["head"]["ref"],
                "to_branch": pr["base"]["ref"]
            })
        else:
            return jsonify({"error": "Unsupported event"}), 400
        
        print(request.json)  # Add this to your route

        # Save to database
        db.events.insert_one(event)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"error": "Processing failed"}), 500
    
@app.route("/")
def home():
    events = list(db.events.find().sort("timestamp", -1).limit(50))
    return render_template("index.html", events=events)  # Point to index.html



@app.route("/health")
def health_check():
    """Simple health endpoint"""
    try:
        db.command('ping')
        return jsonify({"status": "healthy"})
    except Exception as e:
        return jsonify({"status": "down", "error": str(e)}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)