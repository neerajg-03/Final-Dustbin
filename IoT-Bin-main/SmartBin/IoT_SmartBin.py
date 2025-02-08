import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import folium_static
import plotly.express as px
import time
import random
from PIL import Image
from fpdf import FPDF
from twilio.rest import Client
import googlemaps
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Securely retrieve API keys from .env file
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
GMAPS_API_KEY = os.getenv("GMAPS_API_KEY")

# Initialize Twilio & Google Maps clients (Ensure API keys are stored securely)
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    st.warning("Twilio credentials missing. SMS notifications won't work.")

if GMAPS_API_KEY:
    gmaps = googlemaps.Client(key=GMAPS_API_KEY)
else:
    st.warning("Google Maps API Key missing. Route optimization won't work.")

# Load UI assets
logo = Image.open("assets/dustbin_logo.jpg")  # Ensure 'assets' folder exists
header_img = Image.open("assets/header.jpg")

# Streamlit UI Configuration
st.title("IoT SmartBin Dashboard")
st.image(header_img, use_container_width=True)
st.sidebar.image(logo, width=200)
st.sidebar.title("MCD Admin Panel")

# Role selection
user_role = st.sidebar.radio("Select Role", ["Admin", "Field Worker"])


# Function to generate mock bin data
def generate_bin_data():
    bins = []
    for i in range(10):
        bins.append({
            "Bin ID": f"Bin-{i + 1}",
            "Latitude": random.uniform(28.5, 28.9),
            "Longitude": random.uniform(77.0, 77.5),
            "Fill Level (%)": random.randint(20, 100),
            "Temperature (°C)": random.uniform(20, 40),
            "Humidity (%)": random.uniform(30, 80),
            "Tilt": random.choice([0, 1]),
            "Tilt Alert": random.choice([True, False]),
            "Last Updated": time.strftime('%Y-%m-%d %H:%M:%S')
        })
    return pd.DataFrame(bins)


# Compute priority for bin collection
def calculate_priority(df):
    df["Priority"] = (
            (df["Fill Level (%)"] / 100) * 2 +
            (df["Tilt"] * 3) +
            (df["Temperature (°C)"] / 50) +
            (df["Humidity (%)"] / 100)
    )
    df.sort_values(by="Priority", ascending=False, inplace=True)
    return df


# Generate and process bin data
bin_data = generate_bin_data()
bin_data = calculate_priority(bin_data)


# Generate mock van data
def generate_van_data():
    return pd.DataFrame({
        "Van ID": [f"Van-{i + 1}" for i in range(4)],
        "Latitude": [random.uniform(28.5, 28.9) for _ in range(4)],
        "Longitude": [random.uniform(77.0, 77.5) for _ in range(4)]
    })


vans = generate_van_data()


# Assign bins dynamically to closest available vans
def assign_bins_to_vans(bin_data, vans):
    assignments = []
    for _, bin in bin_data.iterrows():
        min_distance = float('inf')
        assigned_van = None

        for _, van in vans.iterrows():
            distance = np.sqrt((bin["Latitude"] - van["Latitude"]) ** 2 + (bin["Longitude"] - van["Longitude"]) ** 2)
            if distance < min_distance:
                min_distance = distance
                assigned_van = van["Van ID"]

        assignments.append(assigned_van)

    bin_data["Assigned Van"] = assignments
    return bin_data


bin_data = assign_bins_to_vans(bin_data, vans)

# Display bin data
st.subheader("📍 Live Bin Status")
st.dataframe(
    bin_data.style.format({"Fill Level (%)": "{:.2f}", "Temperature (°C)": "{:.2f}", "Humidity (%)": "{:.2f}"})
)

# Display bins on a map
st.subheader("🗺️ Bin Locations & Routes")
map = folium.Map(location=[28.7, 77.2], zoom_start=12)

# Add markers for bins
for _, bin in bin_data.iterrows():
    folium.Marker(
        location=[bin["Latitude"], bin["Longitude"]],
        popup=f"Bin ID: {bin['Bin ID']}<br>Fill Level: {bin['Fill Level (%)']}%",
        icon=folium.Icon(icon="trash", prefix="fa", color="black")
    ).add_to(map)


# Assign optimized routes using Google Maps API
def get_routes(bin_data, vans, map_obj):
    if not GMAPS_API_KEY:
        st.error("Google Maps API Key missing. Cannot generate optimized routes.")
        return map_obj

    colors = ["blue", "red", "green", "purple"]

    for i, van in vans.iterrows():
        assigned_bins = bin_data[bin_data["Assigned Van"] == van["Van ID"]]
        coordinates = [(row["Latitude"], row["Longitude"]) for _, row in assigned_bins.iterrows()]

        if coordinates:
            coordinates.insert(0, (van["Latitude"], van["Longitude"]))
            try:
                directions = gmaps.directions(
                    origin=coordinates[0],
                    destination=coordinates[-1],
                    waypoints=coordinates[1:-1],
                    mode="driving"
                )

                route_coords = [(step['start_location']['lat'], step['start_location']['lng']) for leg in
                                directions[0]['legs'] for step in leg['steps']]

                path_color = colors[i % len(colors)]
                folium.PolyLine(route_coords, color=path_color, weight=5, opacity=0.8).add_to(map_obj)

                folium.Marker(
                    [van["Latitude"], van["Longitude"]],
                    popup=f"Van: {van['Van ID']}",
                    icon=folium.Icon(color=path_color, icon="truck", prefix="fa")
                ).add_to(map_obj)

            except Exception as e:
                st.error(f"Error generating route for {van['Van ID']}: {e}")
    return map_obj


map = get_routes(bin_data, vans, map)
folium_static(map)


# Function to send real-time updates via Twilio
def send_update_message(worker_phone, message):
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=worker_phone
        )
    else:
        st.error("Twilio credentials missing. Cannot send SMS.")


# Admin Panel for Worker Management
if user_role == "Admin":
    st.sidebar.subheader("👷 Field Workers Management")
    workers = pd.DataFrame({
        "Worker ID": [101, 102, 103, 104],
        "Name": ["Rajesh", "Amit", "Pooja", "Suresh"],
        "Assigned Zone": ["North", "South", "East", "West"],
        "Phone": ["+91XXXXXXXXXX"] * 4  # Masked phone numbers
    })
    st.sidebar.dataframe(workers)

    st.success("✅ Dashboard Updated Successfully!")
