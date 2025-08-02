import streamlit as st
import os
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json
import pandas as pd

st.set_page_config(
    page_title="DV360 Creative Updater",
    page_icon="🔧",
    layout="wide"
)

st.title("DV360 Creative Updater")

# --- Corrected Tracker Type Maps ---
# Map for Standard Display, Audio, etc.
TRACKER_MAP_STANDARD = {
    "Impression": "THIRD_PARTY_URL_TYPE_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_CLICK_TRACKING",
}

# New, separate map specifically for Video creatives
TRACKER_MAP_VIDEO = {
    "Impression": "THIRD_PARTY_URL_TYPE_VAST_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_VAST_CLICK_TRACKING",
    "Start": "THIRD_PARTY_URL_TYPE_VAST_START",
    "First quartile": "THIRD_PARTY_URL_TYPE_VAST_FIRST_QUARTILE",
    "Midpoint": "THIRD_PARTY_URL_TYPE_VAST_MIDPOINT",
    "Third quartile": "THIRD_PARTY_URL_TYPE_VAST_THIRD_QUARTILE",
    "Complete": "THIRD_PARTY_URL_TYPE_VAST_COMPLETE",
    "Mute": "THIRD_PARTY_URL_TYPE_VAST_MUTE",
    "Pause": "THIRD_PARTY_URL_TYPE_VAST_PAUSE",
    "Rewind": "THIRD_PARTY_URL_TYPE_VAST_REWIND",
    "Fullscreen": "THIRD_PARTY_URL_TYPE_VAST_FULLSCREEN",
    "Stop": "THIRD_PARTY_URL_TYPE_VAST_STOP",
    "Custom": "THIRD_PARTY_URL_TYPE_VAST_CUSTOM_CLICK", # Note: VAST Custom is for clicks
    "Skip": "THIRD_PARTY_URL_TYPE_VAST_SKIP",
    "Progress": "THIRD_PARTY_URL_TYPE_VAST_PROGRESS"
}

# --- Updated function to detect creative type and assign the correct map ---
def detect_tracker_map(creative_data):
    creative_type = creative_data.get("creativeType", "")
    if creative_type == "CREATIVE_TYPE_VIDEO":
        return TRACKER_MAP_VIDEO
    # Default to the standard map for all other types
    return TRACKER_MAP_STANDARD

# --- Session State Initialization ---
for key, default in {
    "editable_tracker_df": None,
    "adv_single": "",
    "creative_single": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- Auth ---
SCOPES = ['https://www.googleapis.com/auth/display-video']

def get_creds():
    if 'creds' in st.session_state and st.session_state.creds and st.session_state.creds.valid:
        return st.session_state.creds
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if creds and creds.valid:
                st.session_state.creds = creds
                return creds
        except Exception as e:
            st.warning(f"Could not load token.json: {e}. Please re-authenticate.")

    try:
        # Assumes secrets are in st.secrets for Streamlit Cloud deployment
        client_config = {
            "web": {
                "client_id": st.secrets["client_id"],
                "project_id": st.secrets["project_id"],
                "auth_uri": st.secrets["auth_uri"],
                "token_uri": st.secrets["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
                "client_secret": st.secrets["client_secret"],
                "redirect_uris": st.secrets["redirect_uris"]
            }
        }
        flow = InstalledAppFlow.from_client_config(
            client_config, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
    except Exception as e:
        st.error(f"Failed to load secrets. Error: {e}")
        return None

    auth_url, _ = flow.authorization_url(prompt='consent')
    st.warning("Please authorize this application by visiting the URL below:")
    st.code(auth_url)
    auth_code = st.text_input("Enter the authorization code here:")
    if st.button("Complete Authentication"):
        try:
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
            st.session_state.creds = creds
            st.success("Authentication successful! Please refresh the page.")
            st.rerun()
        except Exception as e:
            st.error(f"Error fetching token: {e}")
    return None

st.session_state.creds = get_creds()

# --- Load existing creative trackers ---
def load_existing_trackers():
    if not all([st.session_state.adv_single, st.session_state.creative_single]):
        st.error("Please enter both Advertiser and Creative ID.")
        return
    try:
        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        creative = service.advertisers().creatives().get(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single
        ).execute()

        # Dynamically get the correct tracker map and create its reverse
        st.session_state.tracker_map = detect_tracker_map(creative)
        reverse_map = {v: k for k, v in st.session_state.tracker_map.items()}

        trackers = creative.get("thirdPartyUrls", [])
        
        # Build the DataFrame
        if trackers:
            df = pd.DataFrame(trackers)
            df['event_type'] = df['type'].map(reverse_map)
            df['existing_url'] = df['url']
        else:
            # Create an empty DataFrame if no trackers exist
            df = pd.DataFrame(columns=['event_type', 'existing_url', 'type', 'url'])

        # Add the editable 'new_url' column
        df['new_url'] = ""
        st.session_state.editable_tracker_df = df[['event_type', 'existing_url', 'new_url']]
        st.success("Trackers loaded. You can now edit the 'new_url' column or add new rows.")

    except Exception as e:
        st.error(f"Error loading creative: {e}")

# --- Update creative ---
def update_creative():
    if st.session_state.editable_tracker_df is None:
        st.error("No tracker data to update. Please load trackers first.")
        return
    try:
        # Get the latest state from the data_editor
        edited_df = st.session_state.tracker_table

        # Prepare the final list of trackers
        final_trackers = []
        tracker_map = st.session_state.tracker_map

        for _, row in edited_df.iterrows():
            event_type = row['event_type']
            # Prioritize new URL, but fall back to existing if new is empty
            url_to_use = row['new_url'].strip() if pd.notna(row['new_url']) and row['new_url'].strip() else row['existing_url']
            
            # Only include trackers that have a valid event type and a URL
            if pd.notna(event_type) and event_type in tracker_map and pd.notna(url_to_use):
                final_trackers.append({
                    "type": tracker_map[event_type],
                    "url": str(url_to_use).strip()
                })

        # Send the update to the API
        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        service.advertisers().creatives().patch(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single,
            updateMask="thirdPartyUrls",
            body={"thirdPartyUrls": final_trackers}
        ).execute()

        st.success("✅ Creative updated successfully!")
        # Reload the trackers to show the updated state
        load_existing_trackers()

    except Exception as e:
        st.error(f"An error occurred while updating: {e}")

# --- Main UI ---
if st.session_state.creds:
    st.header("Single Creative Update")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Advertiser ID", key="adv_single")
    with col2:
        st.text_input("Creative ID", key="creative_single")

    st.button("Load Existing Trackers", on_click=load_existing_trackers)

    if st.session_state.editable_tracker_df is not None:
        st.subheader("Edit Trackers")
        st.info("Edit the 'new_url' column to update a tracker. Add a new row to add a tracker. Delete a row to remove one.")
        
        # The key for the data_editor must be persistent
        st.data_editor(
            st.session_state.editable_tracker_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "event_type": st.column_config.SelectboxColumn(
                    "Event Type",
                    help="Select the tracker's event type",
                    options=list(TRACKER_MAP_STANDARD.keys()) + list(TRACKER_MAP_VIDEO.keys()),
                    required=True,
                ),
                 "existing_url": st.column_config.TextColumn(
                    "Existing URL",
                    disabled=True,
                ),
                "new_url": st.column_config.TextColumn(
                    "New or Updated URL",
                    help="Enter the new URL here. Leave blank to keep the existing URL.",
                ),
            },
            key="tracker_table" # This key links the editor's state to session_state
        )

        st.button("Update Creative", on_click=update_creative, type="primary")
