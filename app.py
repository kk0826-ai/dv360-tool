import streamlit as st
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pandas as pd

st.set_page_config(page_title="DV360 Creative Updater", page_icon="🔧", layout="wide")
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

# --- Session State Defaults ---
for k, v in {
    "staged_trackers": [],
    "adv_single": "",
    "creative_single": "",
    "urls_single": "",
    "tracker_type_single": "Impression",
    "existing_trackers": []
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- Authentication ---
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
            st.warning(f"Couldn't load saved credentials: {e}")

    try:
        client_config = st.secrets
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
    except Exception as e:
        st.error(f"Failed to load client secrets. Error: {e}")
        return None

    auth_url, _ = flow.authorization_url(prompt='consent')
    st.warning("Authorize the app by visiting this URL:")
    st.code(auth_url)
    auth_code = st.text_input("Paste the authorization code here:")
    if st.button("Complete Authentication"):
        try:
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            with open('token.json', 'w') as token_file:
                token_file.write(creds.to_json())
            st.session_state.creds = creds
            st.success("Authentication successful. Please refresh.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to complete auth: {e}")
    return None

st.session_state.creds = get_creds()

# --- Merge trackers preserving keys except replacing URL ---
def merge_trackers(existing, staged):
    staged_map = {}
    for t in staged:
        staged_map.setdefault(t["type"], []).append(t)

    final = []
    processed_types = set()

    for tracker in existing:
        ttype = tracker['type']
        if ttype in staged_map:
            # Replace URL only, keep other keys intact
            for new_tracker in staged_map[ttype]:
                new_tracker_full = tracker.copy()
                new_tracker_full['url'] = new_tracker['url']
                final.append(new_tracker_full)
            processed_types.add(ttype)
        else:
            final.append(tracker)

    # Add completely new types that don't exist yet
    for ttype, trackers in staged_map.items():
        if ttype not in processed_types:
            final.extend(trackers)

    return final

# --- Add trackers to staged list ---
def add_trackers():
    urls = [url.strip() for url in st.session_state.urls_single.strip().split('\n') if url.strip()]
    tracker_label = st.session_state.tracker_type_single
    tracker_num = TRACKER_TYPE_MAP[tracker_label]

    for url in urls:
        st.session_state.staged_trackers.append({"type": tracker_num, "url": url})
    st.session_state.urls_single = ""

    st.write("🧪 You just added:", [{"type": tracker_num, "label": tracker_label, "url": url} for url in urls])
    st.write("🧪 All staged trackers so far:", st.session_state.staged_trackers)

# --- Load existing trackers from DV360 API ---
def load_existing_trackers():
    if not (st.session_state.adv_single and st.session_state.creative_single):
        st.error("Enter Advertiser ID and Creative ID first.")
        return
    try:
        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        creative = service.advertisers().creatives().get(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single
        ).execute()
        st.session_state.existing_trackers = creative.get('thirdPartyUrls', [])
        st.success(f"Loaded {len(st.session_state.existing_trackers)} existing trackers.")
        st.write("Existing trackers from API:", st.session_state.existing_trackers)
    except Exception as e:
        st.error(f"Failed to fetch existing trackers: {e}")

# --- Update creative with merged trackers ---
def update_creative():
    if not (st.session_state.adv_single and st.session_state.creative_single and st.session_state.staged_trackers):
        st.error("Advertiser ID, Creative ID, and at least one tracker are required.")
        return

    try:
        service = build('displayvideo', 'v3', credentials=st.session_state.creds)
        creative = service.advertisers().creatives().get(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single
        ).execute()

        merged = merge_trackers(creative.get("thirdPartyUrls", []), st.session_state.staged_trackers)

        # Optional: sort for consistent ordering
        merged.sort(key=lambda x: x['type'])

        st.write("🔎 Final payload being sent:", merged)

        service.advertisers().creatives().patch(
            advertiserId=st.session_state.adv_single,
            creativeId=st.session_state.creative_single,
            updateMask="thirdPartyUrls",
            body={"thirdPartyUrls": merged}
        ).execute()

        st.success("✅ Creative updated successfully!")
        st.session_state.staged_trackers = []
        st.session_state.adv_single = ""
        st.session_state.creative_single = ""
    except Exception as e:
        st.error(f"Error updating creative: {e}")

# --- UI ---
if st.session_state.creds:
    single_tab, bulk_tab = st.tabs(["Single Creative Update", "Bulk Update via CSV"])

    with single_tab:
        st.header("1. Enter Creative Info")
        col1, col2 = st.columns(2)
        col1.text_input("Advertiser ID", key="adv_single")
        col2.text_input("Creative ID", key="creative_single")

        if st.button("Load Existing Trackers"):
            load_existing_trackers()

        st.header("2. Add Third-Party Trackers")
        c1, c2, c3 = st.columns([2, 3, 1])
        c1.selectbox("Select Tracker Type", TRACKER_TYPE_MAP.keys(), key="tracker_type_single")
        c2.text_area("Tracker URLs (one per line)", key="urls_single")
        c3.button("Add to List", on_click=add_trackers, disabled=not st.session_state.urls_single)

        if st.session_state.staged_trackers:
            st.subheader("Trackers to Be Added")
            df = pd.DataFrame(st.session_state.staged_trackers)
            df["type_label"] = df["type"].map(REVERSE_TRACKER_TYPE_MAP)
            st.dataframe(df[["type_label", "url"]], use_container_width=True)
        else:
            st.info("No trackers staged yet.")

        st.header("3. Update Creative")
        col6, col7 = st.columns([1, 3])
        col6.button("Update Creative", type="primary", on_click=update_creative)
        if col7.button("Clear"):
            st.session_state.staged_trackers = []
            st.rerun()
