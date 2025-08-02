import streamlit as st
import os
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json
import pandas as pd
from io import StringIO

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
    "staged_trackers": [],
    "adv_single": "",
    "creative_single": "",
    "urls_single": "",
    "tracker_type_single": "Impression",
    "tracker_map": TRACKER_MAP_CUSTOM
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- Callback to add trackers ---
def add_trackers():
    urls = [url.strip() for url in st.session_state.urls_single.strip().split('\n') if url.strip()]
    tracker_num = st.session_state.tracker_map[st.session_state.tracker_type_single]
    for url in urls:
        st.session_state.staged_trackers.append({"type": tracker_num, "url": url})
    st.session_state.urls_single = ""

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

# --- Update creative ---
def update_creative():
    if not all([st.session_state.adv_single, st.session_state.creative_single, st.session_state.staged_trackers]):
        st.error("Please provide Advertiser ID, Creative ID, and add at least one tracker.")
        return

    try:
        with st.spinner("Fetching, merging, and updating trackers..."):
            service = build('displayvideo', 'v3', credentials=st.session_state.creds)
            adv_id = st.session_state.adv_single
            creative_id = st.session_state.creative_single

            creative_data = service.advertisers().creatives().get(
                advertiserId=adv_id, creativeId=creative_id).execute()

            # Detect tracker map based on creative type
            st.session_state.tracker_map = detect_tracker_map(creative_data)
            tracker_map = st.session_state.tracker_map
            reverse_map = {v: k for k, v in tracker_map.items()}

            existing = creative_data.get('thirdPartyUrls', [])
            staged = st.session_state.staged_trackers

            # --- Group staged trackers by type ---
            staged_by_type = {}
            for tracker in staged:
                staged_by_type.setdefault(tracker['type'], []).append(tracker)

            # --- Filter out all existing trackers that are being replaced ---
            types_to_replace = set(staged_by_type.keys())
            retained_existing = [t for t in existing if t['type'] not in types_to_replace]

            # --- Final merge: retained + all new trackers ---
            merged = retained_existing
            for same_type_trackers in staged_by_type.values():
                merged.extend(same_type_trackers)

            patch_body = {"thirdPartyUrls": merged}
            service.advertisers().creatives().patch(
                advertiserId=adv_id,
                creativeId=creative_id,
                updateMask="thirdPartyUrls",
                body=patch_body
            ).execute()

        st.success("✅ Creative updated successfully!")
        st.session_state.staged_trackers = []
    except Exception as e:
        st.error(f"An error occurred: {e}")

# --- Main UI ---
if st.session_state.creds:
    st.header("Single Creative Update")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Advertiser ID", key="adv_single")
    with col2:
        st.text_input("Creative ID", key="creative_single")

    st.header("Add Trackers")
    col3, col4, col5 = st.columns([2, 3, 1])
    with col3:
        st.selectbox("Select Tracker Type", options=st.session_state.tracker_map.keys(), key="tracker_type_single")
    with col4:
        st.text_area("Enter URLs (one per line)", key="urls_single")
    with col5:
        st.button("Add to List", use_container_width=True, on_click=add_trackers, disabled=(not st.session_state.urls_single))

    if st.session_state.staged_trackers:
        df = pd.DataFrame(st.session_state.staged_trackers)
        df['type'] = df['type'].map({v: k for k, v in st.session_state.tracker_map.items()})
        st.dataframe(df, use_container_width=True)

    col6, col7 = st.columns([1, 3])
    with col6:
        st.button("Update Creative", type="primary", use_container_width=True, on_click=update_creative)
    with col7:
        if st.button("Clear List", use_container_width=True):
            st.session_state.staged_trackers = []
            st.rerun()
