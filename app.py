# PRO TIP: Click the 'copy' icon in the top-right of this code block to copy it without errors.
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

# --- Constants ---
TRACKER_TYPE_MAP = {
    "Impression": 1, "Click tracking": 14, "Start": 2, "First quartile": 3,
    "Midpoint": 4, "Third quartile": 5, "Complete": 6, "Mute": 7,
    "Pause": 8, "Rewind": 9, "Fullscreen": 10, "Stop": 11,
    "Custom": 12, "Skip": 13, "Progress": 15
}
REVERSE_TRACKER_TYPE_MAP = {v: k for k, v in TRACKER_TYPE_MAP.items()}
SCOPES = ['https://www.googleapis.com/auth/display-video']

# --- Session State Initialization ---
if "staged_trackers" not in st.session_state:
    st.session_state.staged_trackers = []
if "adv_single" not in st.session_state:
    st.session_state.adv_single = ""
if "creative_single" not in st.session_state:
    st.session_state.creative_single = ""
if "urls_single" not in st.session_state:
    st.session_state.urls_single = ""
if "tracker_type_single" not in st.session_state:
    st.session_state.tracker_type_single = "Impression"

# --- Callback Functions ---
def add_trackers():
    urls = [url.strip() for url in st.session_state.urls_single.strip().split('\n') if url.strip()]
    tracker_num = TRACKER_TYPE_MAP[st.session_state.tracker_type_single]
    for url in urls:
        st.session_state.staged_trackers.append({"type": tracker_num, "url": url})
    st.session_state.urls_single = ""

def update_creative():
    if not all([st.session_state.adv_single, st.session_state.creative_single, st.session_state.staged_trackers]):
        st.error("Please provide Advertiser ID, Creative ID, and add at least one tracker.")
        return

    try:
        with st.spinner("Fetching existing trackers and updating creative..."):
            service = build('displayvideo', 'v3', credentials=st.session_state.creds)

            # 1. FETCH the existing creative data
            get_request = service.advertisers().creatives().get(
                advertiserId=st.session_state.adv_single,
                creativeId=st.session_state.creative_single
            )
            creative_data = get_request.execute()
            existing_trackers = creative_data.get('thirdPartyUrls', [])

            # 2. MODIFY the list by combining existing and new trackers
            combined_trackers = existing_trackers + st.session_state.staged_trackers
            
            # 3. PATCH the creative with the full, combined list
            patch_body = {"thirdPartyUrls": combined_trackers}
            patch_request = service.advertisers().creatives().patch(
                advertiserId=st.session_state.adv_single,
                creativeId=st.session_state.creative_single,
                updateMask="thirdPartyUrls",
                body=patch_body
            )
            patch_request.execute()

        st.success("✅ Creative updated successfully!")
        st.session_state.staged_trackers = []
        st.session_state.adv_single = ""
        st.session_state.creative_single = ""
    except Exception as e:
        st.error(f"An error occurred: {e}")

# --- Main App Logic ---
def get_creds():
    if 'creds' in st.session_state and st.session_state.creds.valid:
        return st.session_state.creds
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        st.session_state.creds = creds
        return creds
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

if st.session_state.creds:
    single_tab, bulk_tab = st.tabs(["Single Creative Update", "Bulk Update via CSV"])

    with single_tab:
        st.header("1. Enter Creative Details")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Advertiser ID", key="adv_single")
        with col2:
            st.text_input("Creative ID", key="creative_single")

        st.header("2. Add Trackers to Your List")
        col3, col4, col5 = st.columns([2, 3, 1])
        with col3:
            st.selectbox("Select Tracker Type", options=TRACKER_TYPE_MAP.keys(), key="tracker_type_single")
        with col4:
            st.text_area("Enter URLs (one per line)", key="urls_single", help="Enter one URL per line.")
        with col5:
            st.button(
                "Add to List",
                use_container_width=True,
                on_click=add_trackers,
                disabled=(not st.session_state.urls_single)
            )

        st.subheader("Trackers Ready for Update")
        if st.session_state.staged_trackers:
            df_staged = pd.DataFrame(st.session_state.staged_trackers)
            df_staged['type'] = df_staged['type'].map(REVERSE_TRACKER_TYPE_MAP)
            st.dataframe(df_staged, use_container_width=True)
        else:
            st.info("No trackers have been added yet.")

        st.header("3. Update Creative")
        col6, col7 = st.columns([1, 3])
        with col6:
            st.button("Update Creative", type="primary", use_container_width=True, on_click=update_creative)
        with col7:
            if st.button("Clear List", use_container_width=True):
                st.session_state.staged_trackers = []
                st.rerun()

    with bulk_tab:
        st.header("Upload CSV for Bulk Updates")
        st.info(
            "Your CSV must have these exact column headers: `advertiser_id`, `creative_id`, `tracker_type`, `tracker_url`"
        )
        st.write("For `tracker_type`, use the official name (e.g., Impression, Start, Complete). Separate multiple URLs in the `tracker_url` cell with a comma.")

        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

        if st.button("Process Bulk Update", type="primary"):
            if uploaded_file is not None:
                try:
                    df = pd.read_csv(uploaded_file, dtype=str).fillna('')
                    required_cols = {'advertiser_id', 'creative_id', 'tracker_type', 'tracker_url'}
                    if not required_cols.issubset(df.columns):
                        st.error(f"CSV is missing required columns. It must contain: {', '.join(required_cols)}")
                    else:
                        st.success("CSV loaded successfully. Starting updates...")
                        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
                        grouped = df.groupby(['advertiser_id', 'creative_id'])

                        results = []
                        progress_bar = st.progress(0)
                        total_creatives = len(grouped)

                        for i, (ids, group) in enumerate(grouped):
                            adv_id, creative_id = ids
                            try:
                                with st.status(f"Processing Creative ID: {creative_id}", expanded=False) as status:
                                    try:
                                        # In bulk mode, we assume full replacement is intended per the CSV group.
                                        third_party_urls = []
                                        for _, row in group.iterrows():
                                            tracker_name = row['tracker_type']
                                            if tracker_name in TRACKER_TYPE_MAP:
                                                tracker_num = TRACKER_TYPE_MAP[tracker_name]
                                                urls_string = row['tracker_url']
                                                individual_urls = [url.strip() for url in urls_string.split(',') if url.strip()]
                                                for url in individual_urls:
                                                    third_party_urls.append({
                                                        "type": tracker_num,
                                                        "url": url
                                                    })
                                            else:
                                                st.warning(f"Skipping unknown tracker type '{tracker_name}'")

                                        patch_body = {"thirdPartyUrls": third_party_urls}
                                        request = service.advertisers().creatives().patch(
                                            advertiserId=adv_id, creativeId=creative_id,
                                            updateMask="thirdPartyUrls", body=patch_body)
                                        request.execute()

                                        results.append({'Creative ID': creative_id, 'Status': 'Success', 'Details': ''})
                                        status.update(label=f"✅ Creative ID: {creative_id} updated successfully.", state="complete")

                                    except Exception as e:
                                        results.append({'Creative ID': creative_id, 'Status': 'Failed', 'Details': str(e)})
                                        status.update(label=f"❌ Creative ID: {creative_id} failed.", state="error")
                            except Exception as e:
                                results.append({'Creative ID': creative_id, 'Status': 'Critical Failure', 'Details': str(e)})
                            
                            progress_bar.progress((i + 1) / total_creatives)

                        st.header("Bulk Update Results")
                        st.dataframe(pd.DataFrame(results), use_container_width=True)
                except Exception as e:
                    st.error(f"An error occurred while processing the file: {e}")
            else:
                st.error("Please upload a CSV file first.")
