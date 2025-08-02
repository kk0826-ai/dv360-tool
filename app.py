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
    "Impression": "THIRD_PARTY_URL_TYPE_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_CLICK_TRACKING",
}

TRACKER_MAP_VAST_VIDEO = {
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
    "Custom": "THIRD_PARTY_URL_TYPE_VAST_CUSTOM_CLICK",
    "Skip": "THIRD_PARTY_URL_TYPE_VAST_SKIP",
    "Progress": "THIRD_PARTY_URL_TYPE_VAST_PROGRESS"
}

TRACKER_MAP_HOSTED_VIDEO = {
    "Impression": "THIRD_PARTY_URL_TYPE_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_CLICK_TRACKING",
    "Start": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_START",
    "First quartile": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_FIRST_QUARTILE",
    "Midpoint": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_MIDPOINT",
    "Third quartile": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_THIRD_QUARTILE",
    "Complete": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_COMPLETE",
}

# --- Functions ---
def detect_tracker_map(creative_data):
    creative_type = creative_data.get("creativeType")
    hosting_source = creative_data.get("hostingSource")

    if creative_type == "CREATIVE_TYPE_VIDEO":
        if hosting_source == "HOSTING_SOURCE_HOSTED":
            return TRACKER_MAP_HOSTED_VIDEO
        else:
            return TRACKER_MAP_VAST_VIDEO
            
    return TRACKER_MAP_STANDARD

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
            # Initialize the state for the data editor
            st.session_state.tracker_df = df[['event_type', 'existing_url', 'new_url']]
            st.success("Trackers loaded successfully.")

    except Exception as e:
        st.error(f"Error loading creative: {e}")

def update_creative():
    # The update function now reads the final state from the editor key
    if "tracker_table" not in st.session_state:
        st.error("No tracker data to update. Please load trackers first.")
        return
    try:
        with st.spinner("Updating creative..."):
            # Convert the final state of the editor to a DataFrame
            edited_df = pd.DataFrame(st.session_state.tracker_table)
            
            final_trackers = []
            tracker_map = st.session_state.tracker_map

            for _, row in edited_df.iterrows():
                event_type_val = row['event_type']
                url_to_use = row['new_url'].strip() if pd.notna(row['new_url']) and row['new_url'].strip() else row['existing_url']
                
                if pd.notna(event_type_val) and pd.notna(url_to_use) and url_to_use:
                    api_type = tracker_map.get(event_type_val, event_type_val)
                    final_trackers.append({"type": api_type, "url": str(url_to_use).strip()})

            service = build('displayvideo', 'v3', credentials=st.session_state.creds)
            service.advertisers().creatives().patch(
                advertiserId=st.session_state.adv_single,
                creativeId=st.session_state.creative_single,
                updateMask="thirdPartyUrls",
                body={"thirdPartyUrls": final_trackers}
            ).execute()

            st.success("✅ Creative updated successfully!")
            load_existing_trackers()

    except Exception as e:
        st.error(f"An error occurred while updating: {e}")


# --- Main UI ---
SCOPES = ['https://www.googleapis.com/auth/display-video']

# Initialize session state keys
if "tracker_df" not in st.session_state:
    st.session_state.tracker_df = None
if "adv_single" not in st.session_state:
    st.session_state.adv_single = ""
if "creative_single" not in st.session_state:
    st.session_state.creative_single = ""

st.session_state.creds = get_creds()

if st.session_state.creds:
    st.header("Single Creative Update")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Advertiser ID", key="adv_single")
    with col2:
        st.text_input("Creative ID", key="creative_single")

    st.button("Load Existing Trackers", on_click=load_existing_trackers)

    # Only show the editor if the DataFrame has been loaded into session state
    if st.session_state.tracker_df is not None:
        st.subheader("Edit Trackers")
        st.info("Edit the 'new_url' column, add/delete rows, then click Update.")
        
        current_map = st.session_state.get("tracker_map", TRACKER_MAP_STANDARD)
        event_options = list(current_map.keys())
        
        # The data editor's state is stored in st.session_state.tracker_table
        st.data_editor(
            st.session_state.tracker_df, # Initialize with the loaded data
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "event_type": st.column_config.SelectboxColumn(
                    "Event Type",
                    options=event_options,
                    required=True,
                ),
                 "existing_url": st.column_config.TextColumn(
                    "Existing URL",
                    disabled=True,
                ),
                "new_url": st.column_config.TextColumn(
                    "New or Updated URL",
                ),
            },
            key="tracker_table"
        )
        st.button("Update Creative", on_click=update_creative, type="primary")
