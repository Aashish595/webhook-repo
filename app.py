# app.py
# --------------------------
# Flask webhook listener for GitHub events
# Stores webhook data into MongoDB
# Renders event list via HTML template
# --------------------------

from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
import certifi

# Load environment variables from .env file
load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Database connection helper function
def get_db():
    try:
        # Use certifi to provide trusted CA certificates for TLS
        client = MongoClient(
            os.getenv("MONGODB_URI"),
            tlsCAFile=certifi.where()
        )
        # Ping the MongoDB server to confirm connection
        client.admin.command('ping')
        # Get the target database
        db = client[os.getenv("MONGO_DB_NAME", "webhook_db")]
        # Ensure index on timestamp for efficient sorting
        db.events.create_index("timestamp")
        return db
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise e

# Initialize database connection
db = get_db()

# Webhook endpoint for GitHub
@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Handles incoming GitHub webhook events"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid payload"}), 400

        # Common event data
        event = {
            "timestamp": datetime.utcnow(),
            "repository": data.get("repository", {}).get("name", "unknown")
        }

        # Identify event type and extract relevant data
        if "commits" in data:  # Push event
            event.update({
                "type": "push",
                "author": data["pusher"]["name"],
                "branch": data["ref"].split("/")[-1],
                "commit_id": data["head_commit"]["id"]
            })
        elif "pull_request" in data:  # Pull request event
            pr = data["pull_request"]
            event.update({
                "type": "pull_request",
                "author": pr["user"]["login"],
                "from_branch": pr["head"]["ref"],
                "to_branch": pr["base"]["ref"]
            })
        else:
            return jsonify({"error": "Unsupported event"}), 400

        logger.info(f"Received event: {event}")

        # Save event to MongoDB
        db.events.insert_one(event)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return jsonify({"error": "Processing failed"}), 500

# Home route to display stored events
@app.route("/")
def home():
    events = list(db.events.find().sort("timestamp", -1).limit(50))
    return render_template("index.html", events=events)

# Health check endpoint for monitoring
@app.route("/health")
def health_check():
    try:
        db.command('ping')
        return jsonify({"status": "healthy", "db": "connected"})
    except Exception as e:
        logger.error(f"DB health check failed: {str(e)}")
        return jsonify({
            "status": "down",
            "error": str(e),
            "solution": "Check MongoDB URI and network connectivity"
        }), 500

# Run Flask server via Waitress in production
if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_HOST", "0.0.0.0"), port=int(os.getenv("FLASK_PORT", 5000)))
