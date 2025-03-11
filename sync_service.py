from flask import Flask, jsonify
import requests
import logging
import os
import json
import time
from datetime import datetime, timedelta

app = Flask(__name__)

# Load API keys securely from environment variables
REGAL_IO_API_KEY = os.environ["REGAL_IO_API_KEY"]
MAILCHIMP_API_KEY = os.environ["MAILCHIMP_API_KEY"]
MAILCHIMP_LIST_ID = "2960f1c6f4"
MAILCHIMP_DC = os.environ["MAILCHIMP_DC"]
MAILCHIMP_CAMPAIGN_ID = "61e6ff8c14"

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
    """Trigger updating contacts based on campaign reports."""
    campaign_id = MAILCHIMP_CAMPAIGN_ID  # Use predefined campaign ID

    if not campaign_id:
        return jsonify({"status": "error", "message": "Missing campaign_id"}), 400

    result = update_contacts_in_regal(campaign_id)
    return jsonify(result)


def fetch_campaign_performance(campaign_id):
    """Fetch campaign title and performance metrics from Mailchimp."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}"
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()

        return {
            "title": data.get("campaign_title", data.get("campaign_name", "Unknown Campaign")),
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign performance: {e}")
        return {}


def fetch_campaign_open_details(campaign_id):
    """Fetch open details for the campaign from Mailchimp."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/open-details"
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()
        return {entry["email_address"]: 1 for entry in data.get("members", [])}  # Map emails to count 1
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign open details: {e}")
        return {}


def fetch_campaign_click_details(campaign_id):
    """Fetch click details for the campaign from Mailchimp."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/click-details"
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()
        return {entry["email_address"]: 1 for entry in data.get("members", [])}  # Map emails to count 1
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign click details: {e}")
        return {}


def fetch_email_activity(campaign_id):
    """Fetch email activity for a campaign (bounces and recipients)."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/email-activity"
    contacts = []
    offset = 0
    count = 100  # Fetch 100 records per API call

    try:
        while True:
            paginated_url = f"{url}?count={count}&offset={offset}"
            response = requests.get(paginated_url, headers=MAILCHIMP_AUTH_HEADER)
            response.raise_for_status()
            data = response.json()

            emails = data.get("emails", [])
            if not emails:
                break  # Stop fetching if there are no more contacts

            for entry in emails:
                email_address = entry.get("email_address", "")
                actions = entry.get("activity", [])

                if email_address:
                    contacts.append({
                        "email": email_address,
                        "bounces": sum(1 for act in actions if act["action"] == "bounce"),
                    })

            offset += count  # Move to the next batch

        logging.info(f"Fetched {len(contacts)} contacts from campaign {campaign_id}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching email activity: {e}")

    return contacts


def update_contacts_in_regal(campaign_id):
    """Update contacts in Regal.io based on Mailchimp campaign reports."""
    logging.info(f"Updating contacts for campaign: {campaign_id}")

    campaign_performance = fetch_campaign_performance(campaign_id)
    opens = fetch_campaign_open_details(campaign_id)
    clicks = fetch_campaign_click_details(campaign_id)
    contacts = fetch_email_activity(campaign_id)

    if not contacts:
        logging.info("No contacts found for this campaign.")
        return {"status": "error", "message": "No contacts found for the campaign"}

    campaign_title = campaign_performance.get("title", "Unknown Campaign")

    payloads = []
    for contact in contacts:
        email = contact.get("email", "")

        regal_payload = {
            "traits": {
                "email": email,
            },
            "name": "Campaign Engagement Update",
            "properties": {
                "campaign_title": campaign_title,
                "total_opens": opens.get(email, 0),
                "total_clicks": clicks.get(email, 0),
                "bounced_email": contact.get("bounces", 0),
                "campaign_id": campaign_id,
            },
            "eventSource": "MailChimp",
        }

        payloads.append(regal_payload)

    # Send each contact individually
    send_to_regal_individually(payloads)

    return {"status": "success", "message": f"Contacts updated for campaign {campaign_id}"}


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

            time.sleep(1)  # Add a delay to prevent hitting rate limits

        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending data to Regal.io: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
