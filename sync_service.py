from flask import Flask, jsonify
import requests
import logging
import os
import json
import time
from datetime import datetime, timedelta

app = Flask(__name__)

# Load API keys securely from environment variables
REGAL_IO_API_KEY = "mg0Fk9ZtRI_tu6Vvntg1Ekrt3HU9dI-_GTNmzyaOYcNjgcAtJxeCGQ"#os.environ["REGAL_IO_API_KEY"]
MAILCHIMP_API_KEY = "c2560ec52e254104f08b39a4515a12cf-us1"#os.environ["MAILCHIMP_API_KEY"]
MAILCHIMP_LIST_ID = "51b4b25ac8"
MAILCHIMP_DC = "us1"#os.environ["MAILCHIMP_DC"]

# Configure logging
logging.basicConfig(level=logging.INFO)

MAILCHIMP_API_BASE = f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0"
MAILCHIMP_AUTH_HEADER = {"Authorization": f"Bearer {MAILCHIMP_API_KEY}"}

@app.route("/", methods=["GET"])
def home():
    """Root route to verify the API is running."""
    return jsonify({"message": "Flask API is running."}), 200

@app.route("/update-contacts", methods=["GET"])
def update_contacts():
    """Trigger updating contacts based on the last 24 hours activity for all campaigns in the audience list."""
    campaigns = fetch_campaigns_for_list()
    if not campaigns:
        return jsonify({"status": "error", "message": "No campaigns found for the audience list"}), 400

    for campaign in campaigns:
        update_contacts_in_regal(campaign["id"], campaign["title"])

    return jsonify({"status": "success", "message": "Contacts updated for all campaigns in the audience list"})


def fetch_campaigns_for_list():
    """Fetch all campaigns related to the given audience list."""
    url = f"{MAILCHIMP_API_BASE}/campaigns?list_id={MAILCHIMP_LIST_ID}&count=100"
    campaigns = []

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()

        for campaign in data.get("campaigns", []):
            campaigns.append({
                "id": campaign["id"],
                "title": campaign["settings"]["title"]
            })

        logging.info(f"Fetched {len(campaigns)} campaigns for audience list {MAILCHIMP_LIST_ID}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaigns: {e}")

    return campaigns


def fetch_open_counts(campaign_id):
    """Fetch the number of opens per email in the last 24 hours."""
    last_24_hours = (datetime.utcnow() - timedelta(days=1)).isoformat()
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/open-details?since={last_24_hours}&count=100"
    open_counts = {}

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()

        for member in data.get("members", []):
            email_address = member.get("email_address", "")
            open_events = member.get("opens", [])
            open_count = len(open_events)

            if email_address:
                open_counts[email_address] = open_count

        logging.info(f"Fetched open counts for {len(open_counts)} emails in campaign {campaign_id}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching open counts: {e}")

    return open_counts


def fetch_click_counts(campaign_id):
    """Fetch the number of clicks per email in the last 24 hours."""
    last_24_hours = (datetime.utcnow() - timedelta(days=1)).isoformat()
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/click-details?since={last_24_hours}&count=100"
    click_counts = {}

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()

        for link in data.get("urls_clicked", []):
            link_id = link.get("id")
            if not link_id:
                continue

            link_url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/click-details/{link_id}/members"
            response = requests.get(link_url, headers=MAILCHIMP_AUTH_HEADER)
            response.raise_for_status()
            click_data = response.json()

            for member in click_data.get("members", []):
                email_address = member.get("email_address", "")
                if email_address:
                    click_counts[email_address] = click_counts.get(email_address, 0) + 1

        logging.info(f"Fetched click counts for {len(click_counts)} emails in campaign {campaign_id}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching click counts: {e}")

    return click_counts


def update_contacts_in_regal(campaign_id, campaign_title):
    """Update contacts in Regal.io based on Mailchimp campaign reports for the last 24 hours."""
    logging.info(f"Updating contacts for campaign: {campaign_id} ({campaign_title})")

    open_counts = fetch_open_counts(campaign_id)
    click_counts = fetch_click_counts(campaign_id)

    if not open_counts and not click_counts:
        logging.info(f"No engagement data found for campaign {campaign_id} in the last 24 hours.")
        return

    payloads = []
    all_emails = set(open_counts.keys()).union(set(click_counts.keys()))

    for email in all_emails:
        regal_payload = {
            "traits": {
                "email": email,
            },
            "name": "Mailchimp Campaign Activity Update",
            "properties": {
                "campaign_title": campaign_title,
                "total_opens": open_counts.get(email, 0),
                "total_clicks": click_counts.get(email, 0),
                "campaign_id": campaign_id,
            },
            "eventSource": "MailChimp",
        }

        payloads.append(regal_payload)

    send_to_regal_individually(payloads)


def send_to_regal_individually(payloads):
    """Send each contact to Regal.io individually."""
    headers = {"Authorization": REGAL_IO_API_KEY, "Content-Type": "application/json"}

    for payload in payloads:
        try:
            logging.info(f"Sending data to Regal.io: {json.dumps(payload, indent=2)}")
            response = requests.post("https://events.regalvoice.com/events", json=payload, headers=headers)

            if response.status_code != 200:
                logging.error(f"Failed to send data to Regal.io: {response.status_code} - {response.text}")
            else:
                logging.info(f"Successfully sent data to Regal.io: {response.text}")

            time.sleep(1)  # Prevent rate limiting

        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending data to Regal.io: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
