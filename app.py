import streamlit as st
import os
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
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

# --- Session State ---
for key in ["staged_trackers", "adv_single", "creative_single", "urls_single", "tracker_type_single"]:
    if key not in st.session_state:
        st.session_state[key] = "" if "single" in key else []

if st.session_state.tracker_type_single == "":
    st.session_state.tracker_type_single = "Impression"

# --- Helper: Add Trackers ---
def add_trackers():
    urls = [url.strip() for url in st.session_state.urls_single.strip().split('\n') if url.strip()]
    tracker_num = TRACKER_TYPE_MAP[st.session_state.tracker_type_single]
    for url in urls:
        st.session_state.staged_trackers.append({"type": tracker_num, "url": url})
    st.session_state.urls_single = ""

# --- Helper: Update Single Creative ---
def update_creative():
    if not all([st.session_state.adv_single, st.session_state.creative_single, st.session_state.staged_trackers]):
        st.error("Please provide Advertiser ID, Creative ID, and add at least one tracker.")
        return

    try:
        with st.spinner("Fetching, merging, and updating trackers..."):
            service = build('displayvideo', 'v3', credentials=st.session_state.creds)
            get_request = service.advertisers().creatives().get(
                advertiserId=st.session_state.adv_single,
                creativeId=st.session_state.creative_single
            )
            creative_data = get_request.execute()
            existing_trackers = creative_data.get('thirdPartyUrls', [])
            staged_map = {tracker['type']: tracker for tracker in st.session_state.staged_trackers}
            final_trackers = []
            processed_types = set()

            for existing in existing_trackers:
                t_type = existing['type']
                if t_type in staged_map:
                    final_trackers.append(staged_map[t_type])
                else:
                    final_trackers.append(existing)
                processed_types.add(t_type)

            for tracker in st.session_state.staged_trackers:
                if tracker['type'] not in processed_types:
                    final_trackers.append(tracker)

            patch_body = {"thirdPartyUrls": final_trackers}
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

# --- Auth Handling ---
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

# --- Main UI ---
if st.session_state.creds:
    single_tab, bulk_tab = st.tabs(["Single Creative Update", "Bulk Update via CSV"])

    # --- Single Creative ---
    with single_tab:
        st.header("1. Enter Creative Details")
        col1, col2 = st.columns(2)
        col1.text_input("Advertiser ID", key="adv_single")
        col2.text_input("Creative ID", key="creative_single")

        st.header("2. Add Trackers to Your List")
        col3, col4, col5 = st.columns([2, 3, 1])
        col3.selectbox("Select Tracker Type", options=TRACKER_TYPE_MAP.keys(), key="tracker_type_single")
        col4.text_area("Enter URLs (one per line)", key="urls_single", help="Enter one URL per line.")
        col5.button("Add to List", use_container_width=True, on_click=add_trackers, disabled=(not st.session_state.urls_single))

        st.subheader("Trackers Ready for Update")
        if st.session_state.staged_trackers:
            df_staged = pd.DataFrame(st.session_state.staged_trackers)
            df_staged['type'] = df_staged['type'].map(REVERSE_TRACKER_TYPE_MAP)
            st.dataframe(df_staged, use_container_width=True)
        else:
            st.info("No trackers have been added yet.")

        st.header("3. Update Creative")
        col6, col7 = st.columns([1, 3])
        col6.button("Update Creative", type="primary", use_container_width=True, on_click=update_creative)
        if col7.button("Clear List", use_container_width=True):
            st.session_state.staged_trackers = []
            st.rerun()

    # --- Bulk Creative ---
    with bulk_tab:
        st.header("Upload CSV for Bulk Updates")
        st.info("CSV must contain: `advertiser_id`, `creative_id`, `tracker_type`, `tracker_url`")
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

        if st.button("Process Bulk Update", type="primary"):
            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file, dtype=str).fillna('')
                    required_cols = {'advertiser_id', 'creative_id', 'tracker_type', 'tracker_url'}
                    if not required_cols.issubset(df.columns):
                        st.error(f"CSV missing required columns: {', '.join(required_cols)}")
                    else:
                        st.success("CSV loaded successfully. Starting updates...")
                        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
                        grouped = df.groupby(['advertiser_id', 'creative_id'])

                        results = []
                        progress_bar = st.progress(0)
                        total = len(grouped)

                        for i, (ids, group) in enumerate(grouped):
                            adv_id, creative_id = ids
                            try:
                                with st.status(f"Processing Creative ID: {creative_id}", expanded=False) as status:
                                    try:
                                        get_request = service.advertisers().creatives().get(
                                            advertiserId=adv_id, creativeId=creative_id)
                                        creative_data = get_request.execute()
                                        existing_trackers = creative_data.get('thirdPartyUrls', [])

                                        staged_trackers = []
                                        for _, row in group.iterrows():
                                            tracker_name = row['tracker_type'].strip()
                                            if tracker_name in TRACKER_TYPE_MAP:
                                                t_type = TRACKER_TYPE_MAP[tracker_name]
                                                urls = [u.strip() for u in row['tracker_url'].split(',') if u.strip()]
                                                for url in urls:
                                                    staged_trackers.append({"type": t_type, "url": url})
                                            else:
                                                st.warning(f"Unknown tracker type '{tracker_name}' in Creative ID {creative_id}")

                                        staged_map = {t['type']: t for t in staged_trackers}
                                        final_trackers = []
                                        processed = set()

                                        for t in existing_trackers:
                                            t_type = t['type']
                                            if t_type in staged_map:
                                                final_trackers.append(staged_map[t_type])
                                            else:
                                                final_trackers.append(t)
                                            processed.add(t_type)

                                        for t in staged_trackers:
                                            if t['type'] not in processed:
                                                final_trackers.append(t)

                                        patch_body = {"thirdPartyUrls": final_trackers}
                                        request = service.advertisers().creatives().patch(
                                            advertiserId=adv_id, creativeId=creative_id,
                                            updateMask="thirdPartyUrls", body=patch_body)
                                        request.execute()

                                        results.append({'Creative ID': creative_id, 'Status': 'Success', 'Details': ''})
                                        status.update(label=f"✅ Creative ID: {creative_id} updated.", state="complete")
                                    except Exception as e:
                                        results.append({'Creative ID': creative_id, 'Status': 'Failed', 'Details': str(e)})
                                        status.update(label=f"❌ Creative ID: {creative_id} failed.", state="error")
                            except Exception as e:
                                results.append({'Creative ID': creative_id, 'Status': 'Critical Failure', 'Details': str(e)})
                            progress_bar.progress((i + 1) / total)

                        st.header("Bulk Update Results")
                        st.dataframe(pd.DataFrame(results), use_container_width=True)
                except Exception as e:
                    st.error(f"Error processing CSV: {e}")
            else:
                st.error("Please upload a CSV file first.")
