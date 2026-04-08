import requests
import json
import os
import re
from pathlib import Path
from datetime import datetime
from teams import send_message
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve values from environment variables
latitude = float(os.getenv("latitude"))
longitude = float(os.getenv("longitude"))
city = os.getenv("city")

# Support both alert-specific and fallback webhooks
alerts_teams_webhook = os.getenv("alerts_teams_webhook")
forecast_teams_webhook = os.getenv("forecast_teams_webhook")
teams_webhook_url = alerts_teams_webhook or forecast_teams_webhook

if not teams_webhook_url:
    raise ValueError("No Teams webhook URL configured. Set either 'alerts_teams_webhook' or 'forecast_teams_webhook' in .env")

county_zones_raw = os.getenv("county_zones", "").split(",")
county_zones_raw = [zone.strip() for zone in county_zones_raw if zone.strip()]

# Parse county codes and names from environment variable
# Format: "OHC061:Hamilton,OHC025:Clermont,..."
COUNTY_NAME_MAP = {}
county_zones = []
for item in county_zones_raw:
    if ":" in item:
        code, name = item.split(":", 1)
        code = code.strip()
        name = name.strip()
        COUNTY_NAME_MAP[code] = name
        county_zones.append(code)
    else:
        # Fallback if no name provided
        code = item.strip()
        COUNTY_NAME_MAP[code] = code
        county_zones.append(code)

# Get interested county names from configured zones
INTERESTED_COUNTIES = set(COUNTY_NAME_MAP.get(zone, "") for zone in county_zones if zone in COUNTY_NAME_MAP)

# Cache file to track which alerts have been sent
CACHE_FILE = ".cache.json"
CACHE_EXPIRATION_DAYS = 30


def load_cache():
    """
    Load the cached alerts from the cache file.
    Returns a dictionary with alert IDs as keys.
    """
    if Path(CACHE_FILE).exists():
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache):
    """
    Save the cache of alerts to the cache file.
    """
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def clean_expired_cache(cache):
    """
    Remove cache entries older than CACHE_EXPIRATION_DAYS.
    Returns the cleaned cache dictionary.
    """
    now = datetime.now()
    expired_keys = []
    
    for alert_id, data in cache.items():
        try:
            # Parse the timestamp from the cache entry
            timestamp_str = data.get("timestamp") if isinstance(data, dict) else None
            if timestamp_str:
                cached_time = datetime.fromisoformat(timestamp_str)
                age_days = (now - cached_time).days
                
                if age_days >= CACHE_EXPIRATION_DAYS:
                    expired_keys.append(alert_id)
        except (ValueError, AttributeError):
            # If we can't parse the timestamp, remove it to be safe
            expired_keys.append(alert_id)
    
    # Remove expired entries
    for key in expired_keys:
        del cache[key]
    
    if expired_keys:
        print(f"Removed {len(expired_keys)} expired alert(s) from cache.")
    
    return cache


def get_active_alerts(county_zones):
    """
    Fetches active alerts from the NWS API for the given county zones.
    Returns a list of alert dictionaries deduplicated by alert ID.
    """
    all_alerts = []
    seen_ids = set()
    
    for zone in county_zones:
        try:
            # Fetch alerts for each county zone
            alerts_url = f"https://api.weather.gov/alerts/active?zone={zone}"
            alerts_response = requests.get(alerts_url)
            if alerts_response.status_code != 200:
                print(f"Warning: Error fetching alerts for {zone}: {alerts_response.status_code}")
                continue
            
            alerts_data = alerts_response.json()
            features = alerts_data.get("features", [])
            
            # Add alerts, deduplicating by ID
            for feature in features:
                alert_id = feature.get("id")
                if alert_id and alert_id not in seen_ids:
                    all_alerts.append(feature)
                    seen_ids.add(alert_id)
        except Exception as e:
            print(f"Warning: Error fetching alerts for {zone}: {e}")
            continue
    
    return all_alerts


def highlight_interested_counties(area_desc):
    """
    Bolds county names in area description if they are in the interested counties list.
    Returns the formatted area description with bolded interested counties.
    """
    if not area_desc or not INTERESTED_COUNTIES:
        return area_desc
    
    formatted_desc = area_desc
    for county in INTERESTED_COUNTIES:
        # Bold the county name if it appears (case-insensitive)
        formatted_desc = re.sub(
            rf'\b{re.escape(county)}\b',
            f'**{county}**',
            formatted_desc,
            flags=re.IGNORECASE
        )
    
    return formatted_desc


def format_alert(alert):
    """
    Formats an alert for display in Teams.
    Returns a tuple of (title, text, url, area_desc).
    """
    properties = alert.get("properties", {})
    
    event = properties.get("event", "Unknown Alert")
    headline = properties.get("headline", "No headline available")
    description = properties.get("description", "No description available")
    severity = properties.get("severity", "Unknown")
    # Use @id which links directly to the specific alert
    url = properties.get("@id", "https://weather.gov")
    area_desc = properties.get("areaDesc", "")
    
    # Format the time
    effective = properties.get("effective", "")
    expires = properties.get("expires", "")
    
    # Parse and format timestamps
    try:
        effective_dt = datetime.fromisoformat(effective.replace("Z", "+00:00"))
        effective_str = effective_dt.strftime("%I:%M %p %Z")
    except:
        effective_str = "Unknown"
    
    try:
        expires_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        expires_str = expires_dt.strftime("%I:%M %p %Z")
    except:
        expires_str = "Unknown"
    
    # Build the alert text
    alert_text = f"**Event:** {event}\n\n"
    if area_desc:
        highlighted_areas = highlight_interested_counties(area_desc)
        alert_text += f"**Areas:** {highlighted_areas}\n\n"
    alert_text += f"**Severity:** {severity}\n\n"
    alert_text += f"**Effective:** {effective_str}\n\n"
    alert_text += f"**Expires:** {expires_str}\n\n"
    alert_text += f"**Details:**\n\n{description}"
    
    return headline, alert_text, url, area_desc


def get_new_alerts(current_alerts, cache):
    """
    Compares current alerts against the cache and returns only new alerts.
    Updates the cache with the new alert IDs.
    Returns a list of new alert dictionaries.
    """
    new_alerts = []
    
    for alert in current_alerts:
        alert_id = alert.get("id")
        
        if alert_id and alert_id not in cache:
            new_alerts.append(alert)
            # Add to cache as processed
            cache[alert_id] = {
                "event": alert.get("properties", {}).get("event", "Unknown"),
                "timestamp": datetime.now().isoformat()
            }
    
    return new_alerts


def main():
    """
    Main function to fetch new alerts and send them to Teams.
    """
    try:
        # Validate that county zones are configured
        if not county_zones:
            raise Exception("No county zones configured in .env file (county_zones variable)")
        
        # Load the cache of previously sent alerts
        cache = load_cache()
        
        # Clean expired entries from cache
        cache = clean_expired_cache(cache)
        
        # Fetch current active alerts
        current_alerts = get_active_alerts(county_zones)
        
        # Identify new alerts
        new_alerts = get_new_alerts(current_alerts, cache)
        
        # Send new alerts to Teams
        if new_alerts:
            for alert in new_alerts:
                try:
                    headline, alert_text, url, area_desc = format_alert(alert)
                    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
                    
                    send_message(
                        webhook_url=teams_webhook_url,
                        title=f"⚠️ Weather alert",
                        subtitle=timestamp,
                        text=alert_text,
                        url=url
                    )
                    print(f"Alert sent: {headline}")
                except Exception as e:
                    print(f"Error sending alert to Teams: {e}")
            
            # Save the updated cache
            save_cache(cache)
            print(f"{len(new_alerts)} new alert(s) sent to Teams.")
        else:
            print("No new alerts.")
    
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
