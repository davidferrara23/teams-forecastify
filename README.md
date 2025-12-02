# Teams Forecastify

A simple script to pull the latest National Weather Service forecast for a specified location and send it to Microsoft Teams. You can create a Windows Task Scheduler job to run this script at regular intervals.

## Requirements

- Python 3.x
- `requests` library
- `python-dotenv` library

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   ```

2. Navigate to the project directory:
   ```bash
   cd TeamsForecastify
   ```

3. Install the required Python libraries:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project directory and add the following environment variables:
   ```env
   latitude=<your-latitude>
   longitude=<your-longitude>
   city=<your-city>
   nws_office_city=<nearest-NWS-office-city>
   nws_office_state=<nearest-NWS-office-state>
   teams_webhook_url=<your-teams-webhook-url>
   ```

## Usage

Run the script using the following command:
```bash
python forecastify.py
```

The script will fetch the 7-day forecast for the specified location and send it to the configured Microsoft Teams channel.

## Files

- `forecastify.py`: Main script to fetch the forecast and send it to Teams.
- `teams.py`: Helper functions to format and send messages to Teams.

## Notes

- Ensure that the latitude and longitude correspond to the desired location.
- The Teams webhook URL must be valid and configured to accept messages.

## License

This project is licensed under the MIT License.