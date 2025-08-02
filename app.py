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

# --- Tracker Type Maps ---
TRACKER_MAP_STANDARD = {
    "Impression": 1,
    "Start": 2,
    "First quartile": 3,
    "Midpoint": 4,
    "Third quartile": 5,
    "Complete": 6,
    "Mute": 7,
    "Pause": 8,
    "Rewind": 9,
    "Fullscreen": 10,
    "Stop": 11,
    "Custom": 12,
    "Skip": 13,
    "Click tracking": 14,
    "Progress": 15
}

TRACKER_MAP_CUSTOM = {
    "Impression": 1,
    "Click tracking": 2,
    "Start": 3,
    "First quartile": 4,
    "Midpoint": 5,
    "Third quartile": 6,
    "Complete": 7,
    "Mute": 8,
    "Pause": 9,
    "Rewind": 10,
    "Fullscreen": 11,
    "Stop": 12,
    "Custom": 13,
    "Skip": 14,
    "Progress": 15
}

# --- Detect creative type and assign appropriate tracker map ---
def detect_tracker_map(creative_data):
    creative_type = creative_data.get("creativeType", "").lower()
    if "video" in creative_type:
        return TRACKER_MAP_CUSTOM
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
        client_config = st.secrets
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
    try:
        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        creative = service.advertisers().creatives().get(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single
        ).execute()

        st.session_state.tracker_map = detect_tracker_map(creative)
        reverse_map = {v: k for k, v in st.session_state.tracker_map.items()}

        trackers = creative.get("thirdPartyUrls", [])
        df = pd.DataFrame(trackers)
        if not df.empty:
            df['event_type'] = df['type'].map(reverse_map)
            df['existing_url'] = df['url']
        else:
            df = pd.DataFrame(columns=['event_type', 'existing_url'])

        df['new_url'] = ""  # editable
        st.session_state.editable_tracker_df = df[['event_type', 'existing_url', 'new_url']]
        st.success("Trackers loaded. You can now edit or add new ones.")
    except Exception as e:
        st.error(f"Error loading creative: {e}")

# --- Update creative ---
def update_creative():
    try:
        df = st.session_state.editable_tracker_df.copy()
        df = df[df['new_url'].str.strip() != ""]  # Only new/edited rows

        tracker_map = st.session_state.tracker_map
        third_party_urls = [
            {"type": tracker_map[row['event_type']], "url": row['new_url'].strip()}
            for _, row in df.iterrows()
        ]

        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        service.advertisers().creatives().patch(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single,
            updateMask="thirdPartyUrls",
            body={"thirdPartyUrls": third_party_urls}
        ).execute()

        st.success("✅ Creative updated successfully!")
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

    if st.button("Load Existing Trackers"):
        load_existing_trackers()

    if st.session_state.editable_tracker_df is not None:
        st.subheader("Edit Trackers")
        edited_df = st.data_editor(
            st.session_state.editable_tracker_df,
            num_rows="dynamic",
            use_container_width=True,
            key="tracker_table"
        )
        st.session_state.editable_tracker_df = edited_df

        st.button("Update Creative", on_click=update_creative, type="primary")
