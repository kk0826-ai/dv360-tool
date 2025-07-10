import streamlit as st
import os
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="DV360 Creative Updater",
    page_icon="🔧",
    layout="centered"
)

st.title("DV360 Creative Updater")
st.write("This tool updates a DV360 creative with third-party impression trackers.")

# --- Google Auth ---
SCOPES = ['https://www.googleapis.com/auth/display-video']

# Function to get credentials
def get_creds():
    if 'creds' in st.session_state and st.session_state.creds.valid:
        return st.session_state.creds
    
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        st.session_state.creds = creds
        return creds
        
    # THIS IS THE UPDATED PART - IT NOW USES STREAMLIT SECRETS
    try:
        # Pass the secrets dictionary directly to the flow
        client_config = st.secrets
        flow = InstalledAppFlow.from_client_config(
            client_config, 
            SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
    except Exception as e:
        st.error(f"Failed to load secrets. Make sure you have configured st.secrets correctly. Error: {e}")
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

# --- Main App ---
credentials = get_creds()

if credentials:
    st.header("Creative Details")
    
    advertiser_id = st.text_input("Enter Advertiser ID:")
    creative_id = st.text_input("Enter Creative ID:")
    trackers_str = st.text_area("Enter Impression Tracker URLs (one per line):")

    if st.button("Update Creative"):
        if not all([advertiser_id, creative_id, trackers_str]):
            st.error("Please fill in all fields.")
        else:
            with st.spinner("Updating creative..."):
                try:
                    service = build('displayvideo', 'v3', credentials=credentials)
                    
                    urls = [url.strip() for url in trackers_str.strip().split('\n') if url.strip()]
                    third_party_urls = [{"type": 1, "url": url} for url in urls] # Using number 1 for impression tracker

                    patch_body = {"thirdPartyUrls": third_party_urls}
                    
                    request = service.advertisers().creatives().patch(
                        advertiserId=advertiser_id,
                        creativeId=creative_id,
                        updateMask="thirdPartyUrls",
                        body=patch_body
                    )
                    response = request.execute()
                    
                    st.success("✅ Creative updated successfully!")
                    st.json(response)

                except Exception as e:
                    st.error(f"An error occurred: {e}")
