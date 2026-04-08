import requests
from datetime import datetime
import re
from teams import send_message
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Retrieve values from environment variables
latitude = float(os.getenv("latitude"))
longitude = float(os.getenv("longitude"))
city = os.getenv("city")
nws_office_city = os.getenv("nws_office_city")
nws_office_state = os.getenv("nws_office_state")

# Support both forecast-specific and fallback webhooks
forecast_teams_webhook = os.getenv("forecast_teams_webhook")
alerts_teams_webhook = os.getenv("alerts_teams_webhook")
teams_webhook_url = forecast_teams_webhook or alerts_teams_webhook

if not teams_webhook_url:
    raise ValueError("No Teams webhook URL configured. Set either 'forecast_teams_webhook' or 'alerts_teams_webhook' in .env")

def format_time(text):
    """
    Formats time strings in the forecast text from '1am' to '1 a.m.', '3 pm' to '3 p.m.', etc.
    Ensures no double periods are added.
    """
    # Regular expression to match times like '1am', '7pm', '12 am', etc.
    time_pattern = r'(\d{1,2})(\s?[ap]m)(\.)?'
    formatted_text = re.sub(
        time_pattern,
        lambda m: f"{m.group(1)} {m.group(2).replace(' ', '').lower().replace('am', 'a.m.').replace('pm', 'p.m.')}".rstrip('.') + ('.' if m.group(3) else ''),
        text
    )
    return formatted_text

def format_day_name(name):
    """
    Ensures that 'Night' in day names is converted to lowercase 'night'.
    """
    if "Night" in name:
        name = name.replace("Night", "night")
    return name

def get_forecast(latitude, longitude, source_city, source_state, city):
    """
    Fetches the 7-day forecast from the NWS API for the given latitude and longitude.
    Formats the forecast for easy copy-pasting into a story.
    """
    # Step 1: Get the gridpoint for the location
    points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
    points_response = requests.get(points_url)
    if points_response.status_code != 200:
        raise Exception(f"Error fetching gridpoint: {points_response.status_code}")
    
    points_data = points_response.json()

    # Step 2: Fetch the 7-day forecast
    forecast_url = points_data["properties"]["forecast"]
    forecast_response = requests.get(forecast_url)
    if forecast_response.status_code != 200:
        raise Exception(f"Error fetching forecast: {forecast_response.status_code}")
    
    forecast_data = forecast_response.json()
    periods = forecast_data["properties"]["periods"]

    # Step 3: Format the forecast
    formatted_forecast = ""
    current_day = datetime.now().strftime("%A")  # Get the current day of the week

    for period in periods:
        name = period["name"]
        detailed_forecast = period["detailedForecast"]

        # Replace "Today," "Tonight," etc. with the current day of the week
        if name.lower() == "today":
            name = current_day
        elif name.lower() == "tonight":
            name = f"{current_day} night"
        elif name.lower() == "This Afternoon":
            name = f"{current_day} afternoon"

        # Ensure all "Night" in day names is lowercase
        name = format_day_name(name)

        # Format the time in the detailed forecast
        detailed_forecast = format_time(detailed_forecast)

        # Format the forecast with bold day names and add an extra line break
        formatted_forecast += f"**{name}**: {detailed_forecast}\n\n"

    # Step 4: Add the source line with the dynamically constructed forecast URL
    forecast_page_url = f"https://forecast.weather.gov/MapClick.php?lon={longitude}&lat={latitude}"
    formatted_forecast += f"*Source: [National Weather Service in {source_city}"

    if source_state:
       formatted_forecast += f", {source_state}"

    formatted_forecast += f"]({forecast_page_url})*"

    return formatted_forecast.strip()

if __name__ == "__main__":
    try:
        # Get the forecast
        forecast = get_forecast(latitude, longitude, nws_office_city, nws_office_state, city)
        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")

        # Send the forecast to Teams
        send_message(
            webhook_url=teams_webhook_url,
            title=f"{city} forecast",
            subtitle=f"{timestamp}",
            text=forecast,
            url=f"https://forecast.weather.gov/MapClick.php?lon={longitude}&lat={latitude}"
        )
        print("Forecast sent to Teams successfully.")
    except Exception as e:
        print(f"Error: {e}")
