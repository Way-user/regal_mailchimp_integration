from flask import Flask, request, jsonify
import requests
import datetime
import logging

app = Flask(__name__)

# Regal.io API Details
REGAL_IO_ENDPOINT = "https://events.regalvoice.com/events"
REGAL_IO_API_KEY = "mg0Fk9ZtRI_tu6Vvntg1Ekrt3HU9dI-_GTNmzyaOYcNjgcAtJxeCGQ"

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)


# Mailchimp API Details
MAILCHIMP_API_KEY = "c2560ec52e254104f08b39a4515a12cf-us1"
MAILCHIMP_LIST_ID = "2960f1c6f4"
MAILCHIMP_DC = "us1"  # Example: 'us19' (found in your API key)

EVENT_MAPPING = {
    "subscribe": "User Subscribed",
    "unsubscribe": "User Unsubscribed",
    "profile": "Profile Updated",
    "cleaned": "Email Bounced",
    "upemail": "Email Address Updated",
    "campaign": "Campaign Sent"
}

# Home route to check if API is running
#@app.route("/", methods=["GET"])
#def home():
#    return "Flask API is running!", 200


# --- Mailchimp to Regal.io Sync ---
@app.route("/mailchimp-webhook", methods=["POST"])
def mailchimp_webhook():
    data = request.json

    # Logging request for debugging
    logging.info(f"Received Mailchimp webhook: {data}")

    # Extract event type from Mailchimp data
    event_type = data.get("type", "unknown")
    event_name = EVENT_MAPPING.get(event_type, "Unknown Event")

    # Extract event source
    event_source = data.get("source", "Unknown Source")

   # Extract relevant fields from Mailchimp event
    email = data.get("email", "")
    first_name = data.get("merges", {}).get("FNAME", "")
    last_name = data.get("merges", {}).get("LNAME", "")
    phone = data.get("merges", {}).get("PHONE", "")
    zip_code = data.get("merges", {}).get("MMERGE12", "")
    state = data.get("merges", {}).get("MMERGE21", "")

    # Convert numeric values
    def convert_to_number(value):
        """Convert string numbers to int or float, else return as-is."""
        try:
            if "." in value:
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            return value

    # Engagement metrics
    clicked_link = convert_to_number(data.get("merges", {}).get("MMERGE8", "0"))
    opened_email = convert_to_number(data.get("merges", {}).get("MMERGE13", "0"))
    bounced_email = convert_to_number(data.get("merges", {}).get("MMERGE19", "0"))
    marked_as_spam = convert_to_number(data.get("merges", {}).get("MMERGE17", "0"))

    # Generate unique userId (e.g., use email hash or Mailchimp ID)
    user_id = data.get("id", "")


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

    # Send formatted data to Regal.io
    headers = {"Authorization": REGAL_IO_API_KEY, "Content-Type": "application/json"}
    print("Sending Request to Regal.io with Headers:", headers)

    response = requests.post(REGAL_IO_ENDPOINT, json=regal_payload, headers=headers)
    #print("Payload sent to Regal.io:", json.dumps(regal_payload, indent=4))

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
