from flask import Flask, jsonify
import requests
import logging
import os
import json
import time

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


def fetch_campaign_title(campaign_id):
    """Fetch the campaign title from Mailchimp."""
    url = f"{MAILCHIMP_API_BASE}/campaigns/{campaign_id}"
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()
        return data.get("settings", {}).get("title", "Unknown Campaign")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign title: {e}")
        return "Unknown Campaign"


def fetch_email_addresses(campaign_id):
    """Fetch all email addresses associated with a campaign."""
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
                if email_address:
                    contacts.append(email_address)

            offset += count  # Move to the next batch

        logging.info(f"Fetched {len(contacts)} email addresses from campaign {campaign_id}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching email addresses: {e}")

    return contacts


def fetch_open_counts(campaign_id):
    """Fetch the total number of opens per email from the campaign."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/open-details"
    open_counts = {}
    offset = 0
    count = 100  # Fetch 100 records per API call

    try:
        while True:
            paginated_url = f"{url}?count={count}&offset={offset}"
            response = requests.get(paginated_url, headers=MAILCHIMP_AUTH_HEADER)
            response.raise_for_status()
            data = response.json()

            members = data.get("members", [])
            if not members:
                break

            for member in members:
                email_address = member.get("email_address", "")
                open_events = member.get("opens", [])  # List of open events
                
                # Convert open events to just a count
                open_count = len(open_events)  

                if email_address:
                    open_counts[email_address] = open_count

            offset += count

        logging.info(f"Fetched open counts for {len(open_counts)} emails from campaign {campaign_id}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching open counts: {e}")

    return open_counts  # Returns { "email1@example.com": 2, "email2@example.com": 0, ... }



def fetch_click_counts(campaign_id):
    """Fetch click counts for each email in the campaign."""
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/click-details"
    click_counts = {}
    offset = 0
    count = 100  # Fetch 100 records per API call

    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()

        links = data.get("urls_clicked", [])
        for link in links:
            link_id = link.get("id")
            if not link_id:
                continue  # Skip if link ID is missing

            link_url = f"{url}/{link_id}/members"
            offset = 0

            while True:
                paginated_url = f"{link_url}?count={count}&offset={offset}"
                response = requests.get(paginated_url, headers=MAILCHIMP_AUTH_HEADER)
                response.raise_for_status()
                click_data = response.json()

                members = click_data.get("members", [])
                if not members:
                    break

                for member in members:
                    email_address = member.get("email_address", "")
                    if email_address:
                        click_counts[email_address] = click_counts.get(email_address, 0) + 1  # Count each click

                offset += count

        logging.info(f"Fetched click counts for {len(click_counts)} emails from campaign {campaign_id}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching click counts: {e}")

    return click_counts


def update_contacts_in_regal(campaign_id):
    """Update contacts in Regal.io based on Mailchimp campaign reports."""
    logging.info(f"Updating contacts for campaign: {campaign_id}")

    campaign_title = fetch_campaign_title(campaign_id)
    email_addresses = fetch_email_addresses(campaign_id)
    open_counts = fetch_open_counts(campaign_id)
    click_counts = fetch_click_counts(campaign_id)

    if not email_addresses:
        logging.info("No contacts found for this campaign.")
        return {"status": "error", "message": "No contacts found for the campaign"}

    payloads = []
    for email in email_addresses:
        regal_payload = {
            "traits": {
                "email": email,
            },
            "name": "Campaign Engagement Update",
            "properties": {
                "campaign_title": campaign_title,
                "total_opens": open_counts.get(email, 0),
                "total_clicks": click_counts.get(email, 0),
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
