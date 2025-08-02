import streamlit as st
import os
import re
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

st.title("DV360 Bulk Creative Updater")

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

ALL_TRACKER_MAPS = {**TRACKER_MAP_STANDARD, **TRACKER_MAP_VAST_VIDEO, **TRACKER_MAP_HOSTED_VIDEO}

# --- Functions ---
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

def parse_raw_tracker_block(text_block, tracker_map):
    """
    Intelligently parses a block of text to find URLs and their associated event types.
    """
    parsed_trackers = []
    # Regex to find all URLs
    urls = re.findall(r'https?://[^\s]+', text_block)
    
    # Reverse map for finding friendly names
    reverse_map = {v: k for k, v in tracker_map.items()}

    for url in urls:
        # Check for keywords within the URL itself
        for friendly_name, api_name in tracker_map.items():
            # Use a simple keyword check in the URL
            if friendly_name.lower() in url.lower():
                parsed_trackers.append({"type": api_name, "url": url})
                break # Move to next URL once a match is found
    
    # This is a simplified parser. A more advanced version could use surrounding text.
    return parsed_trackers


def process_bulk_update():
    if st.session_state.uploaded_file is None:
        st.error("Please upload a CSV file first.")
        return
    
    try:
        df = pd.read_csv(st.session_state.uploaded_file)
        if not {'creative_id', 'raw_tracker_block'}.issubset(df.columns):
            st.error("CSV must contain 'creative_id' and 'raw_tracker_block' columns.")
            return
            
        st.success("File validated. Starting bulk update process...")
        
        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        results = []
        progress_bar = st.progress(0)

        for i, row in df.iterrows():
            creative_id = str(row['creative_id'])
            raw_block = str(row['raw_tracker_block'])
            
            try:
                # 1. Fetch the creative to determine its type
                creative = service.advertisers().creatives().get(
                    advertiserId=st.session_state.adv_id,
                    creativeId=creative_id
                ).execute()
                
                existing_trackers = creative.get("thirdPartyUrls", [])
                
                # 2. Parse the new trackers from the raw block
                tracker_map_for_creative = ALL_TRACKER_MAPS # Use a combined map for parsing
                parsed_new_trackers = parse_raw_tracker_block(raw_block, tracker_map_for_creative)

                # 3. Intelligently merge existing and new trackers
                final_trackers_map = {t['type']: t for t in existing_trackers}
                for new_tracker in parsed_new_trackers:
                    final_trackers_map[new_tracker['type']] = new_tracker
                
                final_trackers = list(final_trackers_map.values())
                
                # 4. Patch the creative
                service.advertisers().creatives().patch(
                    advertiserId=st.session_state.adv_id,
                    creativeId=creative_id,
                    updateMask="thirdPartyUrls",
                    body={"thirdPartyUrls": final_trackers}
                ).execute()
                
                results.append({"Creative ID": creative_id, "Status": "✅ Success", "Details": ""})

            except Exception as e:
                results.append({"Creative ID": creative_id, "Status": "❌ Failed", "Details": str(e)})

            progress_bar.progress((i + 1) / len(df))
            
        st.subheader("Bulk Update Results")
        st.dataframe(pd.DataFrame(results), use_container_width=True)

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")


# --- Main UI ---
SCOPES = ['https://www.googleapis.com/auth/display-video']

st.session_state.creds = get_creds()

if st.session_state.creds:
    st.header("1. Enter Advertiser ID")
    st.text_input("Advertiser ID", key="adv_id")
    
    st.header("2. Upload Your Bulk File")
    st.info("Please upload a CSV file with two columns: `creative_id` and `raw_tracker_block`.")
    st.file_uploader("Upload CSV", type="csv", key="uploaded_file")

    st.header("3. Run the Update")
    st.button("Process Bulk Update", on_click=process_bulk_update, type="primary")
