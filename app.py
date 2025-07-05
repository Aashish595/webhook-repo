from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient, DESCENDING
from datetime import datetime
import os
import logging
from dotenv import load_dotenv
import hmac
import hashlib

# Initial setup
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# MongoDB connection helper
def get_db():
    """Connect to MongoDB with enhanced settings"""
    try:
        client = MongoClient(
            os.getenv("MONGODB_URI"),
            connectTimeoutMS=10000,
            serverSelectionTimeoutMS=10000,
            maxPoolSize=50,
            retryWrites=True,
            tls=True
        )
        
        # Verify connection
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        
        db = client[os.getenv("MONGO_DB_NAME", "webhook_db")]
        
        # Create indexes
        db.events.create_index([("timestamp", DESCENDING)])
        db.events.create_index("repository")
        db.events.create_index("type")
        
        return db
    except Exception as e:
        logger.critical(f"MongoDB connection failed: {str(e)}")
        raise

db = get_db()

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Process GitHub webhook events with signature verification"""
    try:
        # Verify webhook secret if present
        webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
        if webhook_secret:
            signature = request.headers.get('X-Hub-Signature-256', '').split('=')[1]
            computed_signature = hmac.new(
                webhook_secret.encode(),
                request.data,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, computed_signature):
                logger.warning("Invalid webhook signature")
                return jsonify({"error": "Invalid signature"}), 403

        data = request.get_json()
        if not data:
            logger.warning("Received empty payload")
            return jsonify({"error": "Invalid payload"}), 400

        # Base event structure
        event = {
            "timestamp": datetime.utcnow(),
            "repository": data.get("repository", {}).get("name", "unknown"),
            "received_at": datetime.utcnow()
        }

        # Event type specific processing
        if "commits" in data:  # Push event
            event.update({
                "type": "push",
                "author": data.get("pusher", {}).get("name", "unknown"),
                "branch": data.get("ref", "").split("/")[-1],
                "commit_id": data.get("head_commit", {}).get("id"),
                "commit_message": data.get("head_commit", {}).get("message")
            })
        elif "pull_request" in data:  # PR event
            pr = data["pull_request"]
            event.update({
                "type": "pull_request",
                "author": pr.get("user", {}).get("login"),
                "action": data.get("action"),  # opened, closed, etc.
                "from_branch": pr.get("head", {}).get("ref"),
                "to_branch": pr.get("base", {}).get("ref"),
                "pr_number": pr.get("number"),
                "pr_state": pr.get("state")
            })
        else:
            logger.info(f"Unsupported event type: {data.keys()}")
            return jsonify({"error": "Unsupported event"}), 400

        # Save to database
        result = db.events.insert_one(event)
        logger.info(f"Inserted event with ID: {result.inserted_id}")
        
        return jsonify({
            "status": "success",
            "event_id": str(result.inserted_id)
        }), 200

    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}", exc_info=True)
        return jsonify({"error": "Processing failed"}), 500

@app.route("/events")
def show_events():
    """Display recent events with pagination"""
    try:
        limit = min(int(request.args.get('limit', 50)), 100)
        page = max(int(request.args.get('page', 1)), 1)
        
        skip = (page - 1) * limit
        total_events = db.events.count_documents({})
        
        events = list(db.events.find()
                     .sort("timestamp", DESCENDING)
                     .skip(skip)
                     .limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        processed_events = []
        for event in events:
            event['_id'] = str(event['_id'])
            processed_events.append(event)
        
        return render_template(
            "events.html",
            events=processed_events,
            current_page=page,
            total_pages=(total_events // limit) + 1
        )
    except Exception as e:
        logger.error(f"Failed to retrieve events: {str(e)}")
        return jsonify({"error": "Failed to retrieve events"}), 500

@app.route("/health")
def health_check():
    """Comprehensive health endpoint"""
    try:
        # Check database connection
        db.command('ping')
        
        # Check collection access
        event_count = db.events.count_documents({})
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "event_count": event_count,
            "uptime": str(datetime.utcnow() - app_start_time)
        })
    except Exception as e:
        logger.critical(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route("/")
def home():
    """Root endpoint with API documentation"""
    return jsonify({
        "service": "GitHub Webhook Processor",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "webhook": {
                "path": "/webhook",
                "method": "POST",
                "description": "Accepts GitHub webhook payloads"
            },
            "events": {
                "path": "/events",
                "method": "GET",
                "parameters": {
                    "limit": "Number of events to return (max 100)",
                    "page": "Page number"
                }
            },
            "health": {
                "path": "/health",
                "method": "GET",
                "description": "Service health check"
            }
        },
        "documentation": "https://github.com/your-repo/docs"
    })

# Store application start time
app_start_time = datetime.utcnow()

if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true"
    )