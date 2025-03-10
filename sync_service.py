from flask import Flask, request, jsonify
import requests
import logging
import os
import json
import time

app = Flask(__name__)

# Load API keys from environment variables
REGAL_IO_API_KEY = os.getenv("REGAL_IO_API_KEY")
MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY")
MAILCHIMP_LIST_ID = os.getenv("MAILCHIMP_LIST_ID")
MAILCHIMP_DC = os.getenv("MAILCHIMP_DC")
CAMPAIGN_ID = os.getenv("MAILCHIMP_CAMPAIGN_ID")
RENDER_APP_URL = os.getenv("RENDER_APP_URL")

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
    """Trigger update for a specific campaign."""
    campaign_id = request.args.get("campaign_id")

    if not campaign_id:
        return jsonify({"status": "error", "message": "Please provide a campaign_id"}), 400

    result = update_contacts_in_regal(campaign_id)
    return jsonify(result)


def fetch_mailchimp_campaign_contacts(campaign_id):
    """Fetch contacts who received a specific Mailchimp campaign."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/email-activity"
    contacts = []

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        if response.status_code != 200:
            logging.error(f"Failed to fetch campaign recipients: {response.status_code} - {response.text}")
            return []

        data = response.json()
        emails = data.get("emails", [])

        for entry in emails:
            email_address = entry.get("email_address", "")
            actions = entry.get("activity", [])

            if email_address:
                contacts.append({
                    "email": email_address,
                    "opens": sum(1 for act in actions if act["action"] == "open"),
                    "clicks": sum(1 for act in actions if act["action"] == "click"),
                    "bounces": sum(1 for act in actions if act["action"] == "bounce"),
                })

        logging.info(f"Fetched {len(contacts)} contacts from campaign {campaign_id}: {json.dumps(contacts[:3], indent=2)}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign contacts: {e}")

    return contacts


def fetch_campaign_details(campaign_id):
    """Fetch campaign metadata like subject and click rate."""
    url = f"{MAILCHIMP_API_BASE}/campaigns/{campaign_id}"
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        if response.status_code != 200:
            logging.error(f"Failed to fetch campaign details: {response.status_code} - {response.text}")
            return {}

        data = response.json()
        return {
            "subject": data.get("settings", {}).get("subject_line", ""),
            "open_rate": data.get("report_summary", {}).get("open_rate", 0),
            "click_rate": data.get("report_summary", {}).get("click_rate", 0),
            "bounce_rate": data.get("report_summary", {}).get("hard_bounces", 0),
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign details: {e}")
        return {}


def update_contacts_in_regal(campaign_id):
    """Fetch contacts from a specific campaign and update them in Regal.io."""
    logging.info(f"Updating contacts for campaign: {campaign_id}")

    contacts = fetch_mailchimp_campaign_contacts(campaign_id)
    campaign_details = fetch_campaign_details(campaign_id)

    if not contacts:
        logging.info("No contacts found for this campaign.")
        return {"status": "error", "message": "No contacts found for the campaign"}

    for contact in contacts:
        email = contact.get("email", "")
        opens = contact.get("opens", 0)
        clicks = contact.get("clicks", 0)
        bounces = contact.get("bounces", 0)

        regal_payload = {
            "traits": {
                "email": email,
                "total_opens": opens,
                "total_clicks": clicks,
                "bounced_email": bounces,
                "campaign_subject": campaign_details.get("subject", ""),
                "open_rate": campaign_details.get("open_rate", 0),
                "click_rate": campaign_details.get("click_rate", 0),
                "bounce_rate": campaign_details.get("bounce_rate", 0),
            },
            "name": "Campaign Engagement Update",
            "properties": {
                "total_opens": opens,
                "total_clicks": clicks,
                "bounced_email": bounces,
                "campaign_subject": campaign_details.get("subject", ""),
                "open_rate": campaign_details.get("open_rate", 0),
                "click_rate": campaign_details.get("click_rate", 0),
                "bounce_rate": campaign_details.get("bounce_rate", 0),
            },
            "eventSource": "MailChimp",
        }

        send_to_regal(regal_payload)
        time.sleep(1)  # Avoid hitting rate limits

    return {"status": "success", "message": f"Contacts updated for campaign {campaign_id}"}


def send_to_regal(payload):
    """Send formatted data to Regal.io."""
    headers = {"Authorization": f"Bearer {REGAL_IO_API_KEY}", "Content-Type": "application/json"}
    
    try:
        logging.info(f"Sending data to Regal.io: {json.dumps(payload, indent=2)}")

        response = requests.post("https://events.regalvoice.com/events", json=payload, headers=headers)
        
        if response.status_code != 200:
            logging.error(f"Failed to send data to Regal.io: {response.status_code} - {response.text}")
            return None

        logging.info(f"Successfully sent data to Regal.io: {response.text}")
        return response

    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending data to Regal.io: {e}")
        return None


def trigger_update():
    """Trigger update on Render startup once and then exit."""
    if CAMPAIGN_ID and RENDER_APP_URL:
        response = requests.get(f"{RENDER_APP_URL}/update-contacts?campaign_id={CAMPAIGN_ID}")
        logging.info(f"Update Triggered: {response.status_code} - {response.text}")
    else:
        logging.error("CAMPAIGN_ID or RENDER_APP_URL is not set!")


if __name__ == "__main__":
    if os.getenv("RUN_UPDATE_ON_STARTUP") == "true":  # ✅ Only run on startup if enabled
        trigger_update()  # ✅ Runs once on Render startup

    app.run(host="0.0.0.0", port=10000, debug=True)
