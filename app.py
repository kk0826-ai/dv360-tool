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

# --- Maps (will be corrected after getting debug data) ---
TRACKER_MAP_STANDARD = {
    "Impression": "THIRD_PARTY_URL_TYPE_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_CLICK_TRACKING",
}
TRACKER_MAP_VIDEO = {
    "Impression": "THIRD_PARTY_URL_TYPE_VAST_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_VAST_CLICK_TRACKING",
    "Start": "THIRD_PARTY_URL_TYPE_VAST_START",
}

# --- Functions ---
def detect_tracker_map(creative_data):
    creative_type = creative_data.get("creativeType", "")
    if creative_type == "CREATIVE_TYPE_VIDEO":
        return TRACKER_MAP_VIDEO
    return TRACKER_MAP_STANDARD

def get_creds():
    # This function is assumed to be working correctly.
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
        client_config = { "web": st.secrets }
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

def load_existing_trackers():
    if not all([st.session_state.adv_single, st.session_state.creative_single]):
        st.error("Please enter both Advertiser and Creative ID.")
        return
    try:
        with st.spinner("Loading creative trackers..."):
            service = build('displayvideo', 'v3', credentials=st.session_state.creds)
            creative = service.advertisers().creatives().get(
                advertiserId=st.session_state.adv_single,
                creativeId=st.session_state.creative_single
            ).execute()

            # --- DIAGNOSTIC STEP ---
            # This will print the raw data to the screen.
            st.subheader("Raw Creative Data from API")
            st.info("Please copy the text in the box below and provide it for analysis.")
            st.json(creative)
            # --- END DIAGNOSTIC STEP ---

            # The rest of the function will run as before.
            st.session_state.tracker_map = detect_tracker_map(creative)
            reverse_map = {v: k for k, v in st.session_state.tracker_map.items()}
            trackers = creative.get("thirdPartyUrls", [])
            
            processed_trackers = []
            if trackers:
                for tracker in trackers:
                    api_type = tracker.get('type')
                    event_type = reverse_map.get(api_type, api_type)
                    processed_trackers.append({
                        'event_type': event_type,
                        'existing_url': tracker.get('url', '')
                    })
            
            df = pd.DataFrame(processed_trackers)
            if df.empty:
                df = pd.DataFrame(columns=['event_type', 'existing_url'])

            df['new_url'] = ""
            st.session_state.editable_tracker_df = df[['event_type', 'existing_url', 'new_url']]

    except Exception as e:
        st.error(f"Error loading creative: {e}")

def update_creative():
    # This function is disabled until we fix the loading issue.
    st.error("Update function is disabled during diagnostics. Please provide the raw data first.")

# --- Main App ---
SCOPES = ['https://www.googleapis.com/auth/display-video']

for key, default in {"editable_tracker_df": None, "adv_single": "", "creative_single": ""}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.session_state.creds = get_creds()

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
        all_event_options = list(TRACKER_MAP_STANDARD.keys()) + list(TRACKER_MAP_VIDEO.keys())
        st.data_editor(
            st.session_state.editable_tracker_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "event_type": st.column_config.SelectboxColumn(
                    "Event Type",
                    options=sorted(list(set(all_event_options))),
                    required=True,
                ),
                 "existing_url": st.column_config.TextColumn("Existing URL", disabled=True,),
                "new_url": st.column_config.TextColumn("New or Updated URL",),
            },
            key="tracker_table"
        )
        st.button("Update Creative", on_click=update_creative, type="primary")
