
# GitHub Webhook Receiver and Viewer

This Flask app receives webhooks from a GitHub repository (push/pull request events), stores them in MongoDB, and displays them live on a UI.

## How to Run Locally

1. Clone this repo
2. Install dependencies:
3. Start the Flask server:
4. Use ngrok to get a public URL:
5. Register your ngrok URL as a webhook in your `action-repo` under GitHub > Settings > Webhooks.

6. Open `http://localhost:5000` to see your events updating live every 15 seconds.

## Environment
- Python 3.8+
- Flask
- MongoDB (Atlas recommended)
