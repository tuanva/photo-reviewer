import os
import cv2
import numpy as np
from PIL import Image
import streamlit as st
import face_recognition
from io import BytesIO

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

@st.cache_resource
def authenticate_gdrive():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def download_images_from_drive(service, folder_id, local_dir='photos'):
    os.makedirs(local_dir, exist_ok=True)
    query = f"'{folder_id}' in parents and mimeType contains 'image/'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    for item in items:
        file_id = item['id']
        file_name = item['name']
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        with open(os.path.join(local_dir, file_name), 'wb') as f:
            f.write(fh.getbuffer())
        st.write(f"✅ Downloaded: {file_name}")
    return local_dir

# Image evaluation
def evaluate_image(filepath):
    img = cv2.imread(filepath)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    score = {}

    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = np.mean(gray)
    contrast = np.std(gray)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = np.mean(hsv[:, :, 1])
    overexposed = np.mean(img > 240) > 0.05
    underexposed = np.mean(img < 15) > 0.05

    score['sharpness'] = round(sharpness, 2)
    score['brightness'] = round(brightness, 2)
    score['contrast'] = round(contrast, 2)
    score['saturation'] = round(saturation, 2)
    score['overexposed'] = overexposed
    score['underexposed'] = underexposed

    try:
        face_image = face_recognition.load_image_file(filepath)
        face_locations = face_recognition.face_locations(face_image)
        score['faces'] = len(face_locations)
    except:
        score['faces'] = 0

    return score

def analyze_folder(folder):
    results = []
    for fname in os.listdir(folder):
        if fname.lower().endswith(('jpg', 'jpeg', 'png')):
            path = os.path.join(folder, fname)
            score = evaluate_image(path)
            score['filename'] = fname
            score['path'] = path
            results.append(score)
    return results

# Streamlit UI
def main():
    st.title("📸 Google Drive Photo Quality Reviewer")

    with st.sidebar:
        st.header("Google Drive Setup")
        folder_id = st.text_input("Enter Google Drive folder ID:")
        if folder_id:
            service = authenticate_gdrive()
            st.write("🔄 Downloading images...")
            download_images_from_drive(service, folder_id)

    if os.path.exists('photos'):
        photos = analyze_folder('photos')

        st.sidebar.header("Filter")
        min_faces = st.sidebar.slider("Minimum Faces", 0, 5, 1)
        max_brightness = st.sidebar.slider("Max Brightness", 0, 255, 255)
        min_sharpness = st.sidebar.slider("Min Sharpness", 0, 1000, 100)

        filtered = [
            p for p in photos
            if p['faces'] >= min_faces and p['brightness'] <= max_brightness and p['sharpness'] >= min_sharpness
        ]

        st.markdown(f"### ✅ Showing {len(filtered)} photos")
        for photo in filtered:
            col1, col2 = st.columns([1, 3])
            with col1:
                st.image(photo['path'], width=150)
            with col2:
                st.markdown(f"**{photo['filename']}**")
                st.markdown(
                    f"""
                    - Faces Detected: `{photo['faces']}`
                    - Sharpness: `{photo['sharpness']}`
                    - Brightness: `{photo['brightness']}`
                    - Contrast: `{photo['contrast']}`
                    - Saturation: `{photo['saturation']}`
                    - Overexposed: `{photo['overexposed']}`
                    - Underexposed: `{photo['underexposed']}`
                    """
                )
                st.markdown("---")
    else:
        st.info("📁 Waiting for photo download...")

if __name__ == "__main__":
    main()
