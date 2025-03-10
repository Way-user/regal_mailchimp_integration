import requests
import os
import logging

# Load environment variables
CAMPAIGN_ID = os.getenv("MAILCHIMP_CAMPAIGN_ID")
RENDER_APP_URL = os.getenv("RENDER_APP_URL")

# Configure logging
logging.basicConfig(level=logging.INFO)
'''
def trigger_update():
    """Trigger /update-contacts when Render starts."""
    if CAMPAIGN_ID and RENDER_APP_URL:
        update_url = f"{RENDER_APP_URL}/update-contacts?campaign_id={CAMPAIGN_ID}"
        logging.info(f"Triggering update: {update_url}")

        try:
            response = requests.get(update_url)
            logging.info(f"Update Triggered: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            logging.error(f"Error triggering update: {e}")
    else:
        logging.error("CAMPAIGN_ID or RENDER_APP_URL is not set!")

# Run update once on startup
trigger_update()
'''
