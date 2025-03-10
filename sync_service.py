from flask import Flask, jsonify
import requests
import logging
import os
import json
import time
import hashlib

app = Flask(__name__)

# Load API keys from environment variables
REGAL_IO_API_KEY = os.environ["REGAL_IO_API_KEY"]
MAILCHIMP_API_KEY = os.environ["MAILCHIMP_API_KEY"]
MAILCHIMP_LIST_ID = os.environ["MAILCHIMP_LIST_ID"]
MAILCHIMP_DC = os.environ["MAILCHIMP_DC"]

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
    """Manually trigger updating contacts."""
    result = update_contacts_in_regal()
    return jsonify(result)


def fetch_mailchimp_contacts():
    """Fetch the first 5 contacts from the specified Mailchimp audience list."""
    url = f"{MAILCHIMP_API_BASE}/lists/{MAILCHIMP_LIST_ID}/members"
    params = {"count": 5, "offset": 0}  # Limit to first 5 contacts
    contacts = []

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER, params=params)

        if response.status_code != 200:
            logging.error(f"Failed to fetch contacts: {response.status_code} - {response.text}")
            return []

        data = response.json()
        contacts = data.get("members", [])

        if not contacts:
            logging.info("No contacts found in the audience list.")
            return []

        logging.info(f"Fetched {len(contacts)} contacts from Mailchimp: {json.dumps(contacts, indent=2)}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching Mailchimp contacts: {e}")
        return []

    return contacts
    ''' """Fetch all contacts from the specified Mailchimp audience list with pagination support."""
    url = f"{MAILCHIMP_API_BASE}/lists/{MAILCHIMP_LIST_ID}/members"
    contacts = []

    try:
        while url:
            response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
            response.raise_for_status()
            data = response.json()

            contacts.extend(data.get("members", []))
            url = data.get("links", [{}])[-1].get("href") if data.get("total_items", 0) > len(contacts) else None

            time.sleep(1)  # Prevent hitting Mailchimp rate limits

        # LOGGING: Print contacts fetched from Mailchimp
        logging.info(f"Fetched {len(contacts)} contacts from Mailchimp: {json.dumps(contacts[:3], indent=2)}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching Mailchimp contacts: {e}")

    return contacts'''




def get_campaign_reports():
    """Fetches all campaign reports and aggregates engagement metrics."""
    url = f"{MAILCHIMP_API_BASE}/reports"
    campaign_reports = {}

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        campaigns = response.json().get("reports", [])

        for campaign in campaigns:
            campaign_id = campaign.get("id", "")
            campaign_reports[campaign_id] = {
                "subject": campaign.get("subject_line", ""),
                "open_rate": campaign.get("opens", {}).get("open_rate", 0),
                "click_rate": campaign.get("clicks", {}).get("click_rate", 0),
                "bounce_rate": campaign.get("bounces", {}).get("hard_bounces", 0),
                "total_opens": campaign.get("opens", {}).get("opens_total", 0),
                "total_clicks": campaign.get("clicks", {}).get("clicks_total", 0),
            }

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign reports: {e}")

    return campaign_reports


def fetch_user_engagement(email):
    """Fetch engagement data for a specific user based on their email hash."""
    email_hash = hashlib.md5(email.lower().encode()).hexdigest()
    url = f"{MAILCHIMP_API_BASE}/lists/{MAILCHIMP_LIST_ID}/members/{email_hash}/activity"
    
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        activities = response.json().get("activity", [])

        engagement_data = {
            "opens": sum(1 for a in activities if a["action"] == "open"),
            "clicks": sum(1 for a in activities if a["action"] == "click"),
            "bounces": sum(1 for a in activities if a["action"] == "bounce"),
        }

        # LOGGING: Print engagement data
        logging.info(f"Engagement for {email}: {json.dumps(engagement_data, indent=2)}")

        return engagement_data

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching engagement for {email}: {e}")
        return {"opens": 0, "clicks": 0, "bounces": 0}



def update_contacts_in_regal():
    """Fetch contacts from Mailchimp, gather engagement data, and update them in Regal.io."""
    contacts = fetch_mailchimp_contacts()
    campaign_reports = get_campaign_reports()

    for contact in contacts:
        email = contact.get("email_address", "")
        first_name = contact.get("merge_fields", {}).get("FNAME", "")
        last_name = contact.get("merge_fields", {}).get("LNAME", "")
        phone = contact.get("merge_fields", {}).get("PHONE", "")
        zip_code = contact.get("merge_fields", {}).get("MMERGE12", "")
        state = contact.get("merge_fields", {}).get("MMERGE21", "")

        # Fetch user-specific engagement data
        engagement_data = fetch_user_engagement(email)

        # Construct Regal.io payload
        latest_campaign_id = list(campaign_reports.keys())[-1] if campaign_reports else None
        latest_campaign = campaign_reports.get(latest_campaign_id, {}) if latest_campaign_id else {}

        regal_payload = {
            "traits": {
                "email": email,
                "phone": phone,
                "firstName": first_name,
                "lastName": last_name,
                "zip": zip_code,
                "state": state,
                "total_opens": engagement_data["opens"],
                "total_clicks": engagement_data["clicks"],
                "bounced_email": engagement_data["bounces"],
                "latest_campaign": latest_campaign.get("subject", ""),
                "open_rate": latest_campaign.get("open_rate", 0),
                "click_rate": latest_campaign.get("click_rate", 0),
                "bounce_rate": latest_campaign.get("bounce_rate", 0),
            },
            "name": "User Engagement Update",
            "properties": {
                "total_opens": engagement_data["opens"],
                "total_clicks": engagement_data["clicks"],
                "bounced_email": engagement_data["bounces"],
            },
            "eventSource": "MailChimp",
        }

        send_to_regal(regal_payload)
        time.sleep(1)  # Avoid hitting rate limits

    return {"status": "success", "message": "Contacts updated in Regal.io"}


def send_to_regal(payload):
    """Send formatted data to Regal.io."""
    headers = {"Authorization": REGAL_IO_API_KEY, "Content-Type": "application/json"}
    
    try:
        # LOGGING: Print payload before sending
        logging.info(f"Sending data to Regal.io: {json.dumps(payload, indent=2)}")

        response = requests.post("https://events.regalvoice.com/events", json=payload, headers=headers)
        response.raise_for_status()
        logging.info(f"Successfully sent data to Regal.io: {response.text}")
        return response

    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending data to Regal.io: {e}")
        return None



if __name__ == "__main__":
    logging.info("Starting Flask server and syncing first 5 contacts...")
    update_contacts_in_regal()  # Call sync function automatically when the server starts
    app.run(host="0.0.0.0", port=10000, debug=True)

