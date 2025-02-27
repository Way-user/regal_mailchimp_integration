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


EVENT_MAPPING = {
    "subscribe": "User Subscribed",
    "unsubscribe": "User Unsubscribed",
    "profile": "Profile Updated",
    "cleaned": "Email Bounced",
    "upemail": "Email Address Updated",
    "campaign": "Campaign Sent"
}
'''
@app.route("/", methods=["GET", "POST"])
def home():
    """Health check endpoint."""
    if request.method == "POST":
        logging.info("Received POST request at /")
        return jsonify({"message": "POST request received, but no action taken."}), 200
    return jsonify({"message": "Flask API is running!"}), 200
'''

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
    event_name = EVENT_MAPPING.get(event_type, "Unknown Event")

    # Extract event source
    event_source = data.get("source", "Unknown Source")

      # Extract data inside "data[]" fields from Mailchimp
    email = data.get("data[email]", "")
    first_name = data.get("data[merges][FNAME]", "")
    last_name = data.get("data[merges][LNAME]", "")
    phone = data.get("data[merges][PHONE]", "")
    zip_code = data.get("data[merges][MMERGE12]", "")
    state = data.get("data[merges][MMERGE21]", "")

    # Engagement metrics
    def convert_to_number(value):
        try:
            if "." in value:
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            return value

    clicked_link = convert_to_number(data.get("data[merges][MMERGE8]", "0"))
    opened_email = convert_to_number(data.get("data[merges][MMERGE13]", "0"))
    bounced_email = convert_to_number(data.get("data[merges][MMERGE19]", "0"))
    marked_as_spam = convert_to_number(data.get("data[merges][MMERGE17]", "0"))

    user_id = data.get("data[id]", "")

     # Format the Regal.io payload
    regal_payload = {
        "userId": "MailChimp_"+user_id,
        "traits": {
            "phone": phone,
            "emails": {
                email: {
                    "emailOptIn": {
                        "subscribed": True # Default value (change if needed)
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
            "marked_as_spam": marked_as_spam
        },
        "name": event_name,
        "properties": {
            "clicked_link": clicked_link,
            "opened_email": opened_email,
            "bounced_email": bounced_email,
            "marked_as_spam": marked_as_spam
        },
        "eventSource": "MailChimp"
    }
    # Log payload before sending to Regal.io
    logging.info(f"Payload Sent to Regal.io: {json.dumps(regal_payload, indent=4)}")

    headers = {"Authorization": REGAL_IO_API_KEY, "Content-Type": "application/json"}
    
    try:
        response = requests.post(
        "https://events.regalvoice.com/events",
        data=json.dumps(regal_payload),  # Convert dictionary to JSON
        headers=headers
    )
    
        logging.info(f"Response from Regal.io: {response.status_code} - {response.text}")
    
        response.raise_for_status()  # Raise an error for bad responses
        return jsonify({"status": "success", "regal_response": response.json()}), response.status_code

    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending to Regal.io: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", "regal_response": response.json()}), response.status_code

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
