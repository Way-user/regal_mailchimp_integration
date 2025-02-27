from flask import Flask, request, jsonify
import requests
import datetime
import logging
import os
import json

app = Flask(__name__)

# Load API keys securely from environment variables
REGAL_IO_API_KEY = os.environ["REGAL_IO_API_KEY"]
MAILCHIMP_API_KEY = os.environ["MAILCHIMP_API_KEY"]
MAILCHIMP_LIST_ID = os.environ["MAILCHIMP_LIST_ID"]
MAILCHIMP_DC = os.environ["MAILCHIMP_DC"]

# Configure logging
logging.basicConfig(level=logging.INFO)


MAILCHIMP_API_BASE = f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0"
MAILCHIMP_AUTH_HEADER = {"Authorization": f"Bearer {MAILCHIMP_API_KEY}"}


# --- Mailchimp to Regal.io Sync ---
@app.route("/", methods=["GET","POST"])
def home():
    """Handles incoming webhooks from Mailchimp."""
    logging.info(f"Incoming Request: {request.method} {request.path} - Headers: {dict(request.headers)}")

    if request.method == "GET":
        return jsonify({"message": "GET request received, Mailchimp verification success."}), 200
   
    # Handle different content types (JSON & Form)
    if request.content_type == "application/json":
        data = request.get_json()
    elif request.content_type == "application/x-www-form-urlencoded":
        data = request.form.to_dict()
    else:
        logging.error(f"Unsupported Media Type: {request.content_type}")
        return jsonify({"status": "error", "message": "Unsupported Media Type"}), 415

    # Log request data for debugging
    logging.info(f"Received Mailchimp webhook: {json.dumps(data, indent=4)}")
    
    ''' 
    data = request.get_json()

    # Logging request for debugging
    logging.info(f"Received Mailchimp webhook: {data}")
    '''
    # Extract event type from Mailchimp data
    event_type = data.get("type", "unknown")
    mailchimp_list_info = get_mailchimp_list_info()

    # Extract data inside "data[]" fields from Mailchimp
    email = data.get("data[email]", "")
    first_name = data.get("data[merges][FNAME]", "")
    last_name = data.get("data[merges][LNAME]", "")
    phone = data.get("data[merges][PHONE]", "")
    zip_code = data.get("data[merges][MMERGE12]", "")
    state = data.get("data[merges][MMERGE21]", "")
    clicked_link = int(data.get("data[merges][MMERGE9]", "0"))
    opened_email = (data.get("data[merges][MMERGE8]", "0"))
    bounced_email = (data.get("data[merges][MMERGE10]", "0"))
    marked_as_spam = (data.get("data[merges][MMERGE11]", "0"))
    
    #  Handle Subscription Events
    if event_type == "subscribe":
        event_name = "User Subscribed"
        email_opt_in = True

    elif event_type == "unsubscribe":
        event_name = "User Unsubscribed"
        email_opt_in = False

    elif event_type == "profile":
        event_name = "Profile Updated"
        email_opt_in = True

    # Handle Email Activity Events
    elif event_type == "open":
        event_name = "Email Opened"

    elif event_type == "click":
        event_name = "Link Clicked"

    elif event_type == "bounce":
        event_name = "Email Bounced"

    #  Handle Campaign Sent Events
    elif event_type == "campaign":
        event_name = "Campaign Sent"
        campaign_id = data.get("data[id]", "")
        campaign_subject = data.get("data[subject]", "")
        # Fetch Campaign Recipients (since Mailchimp does NOT send recipients in the webhook)
        recipients = get_campaign_recipients(campaign_id)
         #  Send each recipient event to Regal.io
        for recipient in recipients:
            recipient_email = recipient.get("email_address", "")
            activity = recipient.get("activity", [])

            clicks = sum(1 for action in activity if action["action"] == "click")
            opens = sum(1 for action in activity if action["action"] == "open")
            bounces = sum(1 for action in activity if action["action"] == "bounce")

            regal_payload = {
                "traits": {
                    "email": recipient_email,
                    "emailOptIn": {"subscribed": True},
                    "campaign_subject": campaign_subject,
                    "from_name": mailchimp_list_info.get("from_name", ""),
                    "from_email": mailchimp_list_info.get("from_email", ""),
                    "language": mailchimp_list_info.get("language", ""),
                    "open_rate": mailchimp_list_info.get("open_rate", 0),
                    "click_rate": mailchimp_list_info.get("click_rate", 0),
                    "clicked_link": clicks,
                    "opened_email": opens,
                    "bounced_email": bounces,
                },
                "name": event_name,
                "properties": {
                    "email_subject": campaign_subject,
                    "clicked_link": clicks,
                    "opened_email": opens,
                    "bounced_email": bounces,
                    "campaign_id": campaign_id,
                    "open_rate": mailchimp_list_info.get("open_rate", 0),
                    "click_rate": mailchimp_list_info.get("click_rate", 0),
                },
                "eventSource": "MailChimp"
            }
            send_to_regal(regal_payload)

        return jsonify({"status": "success", "message": "Campaign processed"}), 200



     # Format the Regal.io payload
    regal_payload = {
        #"userId": "MailChimp_"+data.get("data[id]", ""),
        "traits": {
            "phone": phone,
            "emails": {
                email: {
                    "emailOptIn": {
                        "subscribed": email_opt_in # Default value (change if needed)
                    }
                }
            },
            "firstName": first_name,
            "lastName": last_name,
            "zip": zip_code,
            "state": state,
            "clicked_link": clicked_link,
            "opened_email": opened_email,
            "bounced_email": bounced_email,
            "marked_as_spam": marked_as_spam,
        },
        "name": event_name,
        "properties": {
            "clicked_link": clicked_link,
            "opened_email": opened_email,
            "bounced_email": bounced_email,
            "marked_as_spam": marked_as_spam,
        },
        "eventSource": "MailChimp"
    }
    # Log payload before sending to Regal.io
    logging.info(f"Payload Sent to Regal.io: {json.dumps(regal_payload, indent=4)}")
     # ✅ Send Non-Campaign Events to Regal.io
    send_to_regal(regal_payload)
    return jsonify({"status": "success", "regal_response": response.json()}), response.status_code
    
    
def get_mailchimp_list_info():
    """Fetch list info (campaign defaults & stats) from Mailchimp."""
    url = f"{MAILCHIMP_API_BASE}/lists/{MAILCHIMP_LIST_ID}"
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()
        data = response.json()
        return {
            "from_name": data.get("campaign_defaults", {}).get("from_name", ""),
            "from_email": data.get("campaign_defaults", {}).get("from_email", ""),
            "subject": data.get("campaign_defaults", {}).get("subject", ""),
            "language": data.get("campaign_defaults", {}).get("language", ""),
            "open_rate": data.get("stats", {}).get("open_rate", 0),
            "click_rate": data.get("stats", {}).get("click_rate", 0)
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching Mailchimp list info: {e}")
        return {}

def get_campaign_recipients(campaign_id):
    """Fetch campaign recipients from Mailchimp API."""
    
    url = f"{MAILCHIMP_API_BASE}/reports/{campaign_id}/email-activity"
    
    try:
        response = requests.get(url, headers=MAILCHIMP_AUTH_HEADER)
        response.raise_for_status()  # Raise error if request fails
        data = response.json()
        return data.get("emails", [])  # Extract the list of recipients
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching campaign recipients: {e}")
        return []

def send_to_regal(payload):
    """Send formatted data to Regal.io (one contact at a time)."""
    headers = {"Authorization": REGAL_IO_API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(
            "https://events.regalvoice.com/events",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        logging.info(f"Successfully sent data to Regal.io: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending data to Regal.io: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

'''
# --- Regal.io to Mailchimp Sync (Only if `source` is "INSURANCE") ---
@app.route("/regal-webhook", methods=["POST"])
def regal_webhook():
    data = request.json
    traits = data.get("traits", {})
    custom_properties = data.get("customProperties", {}).get("autoFinance", {})

    email = traits.get("email", "")
    first_name = traits.get("firstName", "")
    last_name = traits.get("lastName", "")
    source = custom_properties.get("source", "")

    # Only sync if source is "INSURANCE"
    if source != "INSURANCE":
        return jsonify({"status": "skipped", "reason": "Source does not match"}), 200

    if not email:
        return jsonify({"status": "error", "message": "Email missing"}), 400

    # Mailchimp API requires email hash (MD5)
    email_hash = hashlib.md5(email.lower().encode()).hexdigest()
    mailchimp_url = f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/lists/{MAILCHIMP_LIST_ID}/members/{email_hash}"

    headers = {
        "Authorization": f"Bearer {MAILCHIMP_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "email_address": email,
        "status_if_new": "subscribed",
        "merge_fields": {
            "FNAME": first_name,
            "LNAME": last_name
        }
    }

    response = requests.put(mailchimp_url, json=payload, headers=headers)

    return jsonify({"status": "success", "mailchimp_response": response.json()}), response.status_code
'''
# Run the Flask app on all addresses (for Render)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
