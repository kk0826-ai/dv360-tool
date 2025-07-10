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

TRACKER_TYPE_MAP = {
    "Impression": 1, "Click tracking": 14, "Start": 2, "First quartile": 3,
    "Midpoint": 4, "Third quartile": 5, "Complete": 6, "Mute": 7,
    "Pause": 8, "Rewind": 9, "Fullscreen": 10, "Stop": 11,
    "Custom": 12, "Skip": 13, "Progress": 15
}
REVERSE_TRACKER_TYPE_MAP = {v: k for k, v in TRACKER_TYPE_MAP.items()}

SCOPES = ['https://www.googleapis.com/auth/display-video']

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

credentials = get_creds()

if credentials:
    single_tab, bulk_tab = st.tabs(["Single Creative Update", "Bulk Update via CSV"])

    with single_tab:
        st.header("1. Enter Creative Details")
        col1, col2 = st.columns(2)
        with col1:
            adv_id_single = st.text_input("Advertiser ID", key="adv_single")
        with col2:
            creative_id_single = st.text_input("Creative ID", key="creative_single")

        st.header("2. Add Trackers to Your List")
        if 'staged_trackers' not in st.session_state:
            st.session_state.staged_trackers = []

        col3, col4, col5 = st.columns([2,3,1])
        with col3:
            tracker_type_single = st.selectbox("Select Tracker Type", options=TRACKER_TYPE_MAP.keys())
        with col4:
            urls_single = st.text_area("Enter URLs (one per line)")
        with col5:
            if st.button("Add to List", use_container_width=True):
                urls = [url.strip() for url in urls_single.strip().split('\n') if url.strip()]
                tracker_num = TRACKER_TYPE_MAP[tracker_type_single]
                for url in urls:
                    st.session_state.staged_trackers.append({"type": tracker_num, "url": url})
        
        st.subheader("Trackers Ready for Update")
        if st.session_state.staged_trackers:
            df_staged = pd.DataFrame(st.session_state.staged_trackers)
            df_staged['type'] = df_staged['type'].map(REVERSE_TRACKER_TYPE_MAP)
            st.dataframe(df_staged, use_container_width=True)
        else:
            st.info("No trackers have been added yet.")

        st.header("3. Update Creative")
        col6, col7 = st.columns([1,3])
        with col6:
            if st.button("Update Creative", type="primary", use_container_width=True):
                if not all([adv_id_single, creative_id_single, st.session_state.staged_trackers]):
                    st.error("Please provide IDs and add at least one tracker.")
                else:
                    with st.spinner("Updating creative..."):
                        try:
                            service = build('displayvideo', 'v3', credentials=credentials)
                            patch_body = {"thirdPartyUrls": st.session_state.staged_trackers}
                            request = service.advertisers().creatives().patch(
                                advertiserId=adv_id_single, creativeId=creative_id_single,
                                updateMask="thirdPartyUrls", body=patch_body)
                            response = request.execute()
                            st.success("✅ Creative updated successfully!")
                            st.session_state.staged_trackers = []
                        except Exception as e:
                            st.error(f"An error occurred: {e}")
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
                        service = build('displayvideo', 'v3', credentials=credentials)
                        grouped = df.groupby(['advertiser_id', 'creative_id'])
                        
                        results = []
                        progress_bar = st.progress(0)
                        total_creatives = len(grouped)

                        for i, (ids, group) in enumerate(grouped):
                            adv_id, creative_id = ids
                            try:
                                with st.status(f"Processing Creative ID: {creative_id}", expanded=False) as status:
                                    try:
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
                                        
                                        st.write("✅ Update successful.")
                                        results.append({'Creative ID': creative_id, 'Status': 'Success', 'Details': ''})
                                        status.update(label=f"✅ Creative ID: {creative_id} updated successfully.", state="complete")

                                    except Exception as e:
                                        st.write(f"❌ Update failed: {e}")
                                        results.append({'Creative ID': creative_id, 'Status': 'Failed', 'Details': str(e)})
                                        status.update(label=f"❌ Creative ID: {creative_id} failed.", state="error")
                            except Exception as e:
                                 st.error(f"A critical error occurred processing creative {creative_id}: {e}")
                                 results.append({'Creative ID': creative_id, 'Status': 'Critical Failure', 'Details': str(e)})

                            progress_bar.progress((i + 1) / total_creatives)
                        
                        st.header("Bulk Update Results")
                        st.dataframe(pd.DataFrame(results), use_container_width=True)
                except Exception as e:
                    st.error(f"An error occurred while processing the file: {e}")
            else:
                st.error("Please upload a CSV file first.")
