import streamlit as st
import pandas as pd
from io import BytesIO
import os

# Import Google libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

st.set_page_config(
    page_title="Bulk Creative Updater",
    layout="wide"
)

st.title("Bulk Creative Updater Workflow")

# --- Tracker Type Maps (from our successful single-updater) ---
TRACKER_MAP_HOSTED_VIDEO = {
    "Impression": "THIRD_PARTY_URL_TYPE_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_CLICK_TRACKING",
    "Start": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_START",
    "First quartile": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_FIRST_QUARTILE",
    "Midpoint": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_MIDPOINT",
    "Third quartile": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_THIRD_QUARTILE",
    "Complete": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_COMPLETE",
}
# Add other maps if needed and a detection function

# --- Authentication (from app.py) ---
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
            st.warning(f"Could not load token.json: {e}. Please re-authenticate on the main page.")
            return None
    st.error("You are not logged in. Please go to the main 'app.py' page to authenticate.")
    return None


def fetch_creative_details(service, advertiser_id, creative_id):
    """
    Makes a live API call to fetch creative details.
    """
    try:
        request = service.advertisers().creatives().get(
            advertiserId=advertiser_id,
            creativeId=creative_id
        )
        return request.execute()
    except Exception as e:
        st.error(f"Failed to fetch Creative ID {creative_id}: {e}")
        return None

# --- Main UI ---
creds = get_creds()

if creds:
    st.header("Phase 1: Upload Creative IDs")

    # This requires an Advertiser ID to make the API calls
    advertiser_id = st.text_input("Enter the Advertiser ID for all creatives in your list")
    
    uploaded_ids_file = st.file_uploader("Upload a one-column CSV with your Creative IDs", type="csv")

    if uploaded_ids_file and advertiser_id:
        if st.button("Process IDs and Show Results"):
            try:
                # Use robust method to read IDs
                raw_text = uploaded_ids_file.getvalue().decode('utf-8')
                lines = raw_text.splitlines()
                creative_ids = [line.strip() for line in lines if line.strip() and line.strip().lower() != 'creative_id']

                if not creative_ids:
                    st.error("The uploaded file contains no valid Creative IDs.")
                else:
                    st.session_state.results_to_display = [] # Reset results
                    service = build('displayvideo', 'v3', credentials=creds)
                    
                    with st.spinner(f"Fetching data for {len(creative_ids)} creatives..."):
                        progress_bar = st.progress(0)
                        for i, creative_id in enumerate(creative_ids):
                            details = fetch_creative_details(service, advertiser_id, creative_id)
                            st.session_state.results_to_display.append(details)
                            progress_bar.progress((i + 1) / len(creative_ids))
                    
                    st.success("Data extraction complete. Results are shown below.")

            except Exception as e:
                st.error(f"An error occurred while processing the file: {e}")

    # --- Display Folded Results ---
    if 'results_to_display' in st.session_state and st.session_state.results_to_display:
        st.header("Extracted Creative Details")
        st.info("Click on each creative to view its trackers and download its data.")

        for creative_data in st.session_state.results_to_display:
            if creative_data:
                creative_name = creative_data.get('displayName', 'No Name Found')
                creative_id_short = creative_data.get('creativeId', 'N/A')
                
                with st.expander(f"Creative: {creative_name} (ID: {creative_id_short})"):
                    trackers = creative_data.get("thirdPartyUrls", [])
                    
                    # For now, we use the hosted video map. A full implementation would detect this.
                    reverse_map = {v: k for k, v in TRACKER_MAP_HOSTED_VIDEO.items()}

                    processed_trackers = []
                    if trackers:
                        for tracker in trackers:
                            api_type = tracker.get('type')
                            processed_trackers.append({
                                'event_type': reverse_map.get(api_type, api_type), # Show raw name if unknown
                                'url': tracker.get('url', '')
                            })
                    
                    df_display = pd.DataFrame(processed_trackers)
                    if df_display.empty:
                        st.write("This creative has no third-party trackers.")
                    else:
                        st.dataframe(df_display, use_container_width=True)
                        
                        # Add a download button inside each expander
                        csv = df_display.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label=f"📥 Download CSV for {creative_id_short}",
                            data=csv,
                            file_name=f"{creative_id_short}_trackers.csv",
                            mime='text/csv',
                        )

    # --- Placeholder for Phase 2 and 3 ---
    st.header("Phase 2: Upload Your Edited Excel File")
    edited_file = st.file_uploader("Upload the Excel file you edited", type=["xlsx", "csv"], key="edited_uploader")

    if edited_file:
        if st.button("Validate and Review Changes"):
            st.info("Validation and review step would be implemented here.")
