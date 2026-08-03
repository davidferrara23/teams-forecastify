import hashlib
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from teams import send_message

# Load environment variables from .env file
load_dotenv()

# Configure the NWS product to scrape.
site = os.getenv("nws_office", "ILN")
statement_page_url = os.getenv(
	"statements_url",
	f"https://forecast.weather.gov/product.php?site={site}&issuedby={site}&product=PNS",
)


# Support dedicated and fallback webhooks.
teams_webhook_url = os.getenv("statements_teams_webhook")

if not teams_webhook_url:
	raise ValueError(
		"No Teams webhook URL configured. Set 'statements_teams_webhook', 'forecast_teams_webhook', or 'alerts_teams_webhook' in .env"
	)


# Cache file to track which statements have already been sent.
CACHE_FILE = ".statements_cache.json"
CACHE_EXPIRATION_DAYS = 30


def load_cache():
	"""Load the cached statement fingerprints from disk."""
	if Path(CACHE_FILE).exists():
		try:
			with open(CACHE_FILE, "r", encoding="utf-8") as file_handle:
				return json.load(file_handle)
		except (json.JSONDecodeError, OSError):
			return {}
	return {}


def save_cache(cache):
	"""Save the statement fingerprint cache to disk."""
	with open(CACHE_FILE, "w", encoding="utf-8") as file_handle:
		json.dump(cache, file_handle, indent=2)


def clean_expired_cache(cache):
	"""Remove cached statements older than CACHE_EXPIRATION_DAYS."""
	now = datetime.now()
	expired_keys = []

	for statement_id, data in cache.items():
		try:
			timestamp_str = data.get("timestamp") if isinstance(data, dict) else None
			if timestamp_str:
				cached_time = datetime.fromisoformat(timestamp_str)
				if (now - cached_time).days >= CACHE_EXPIRATION_DAYS:
					expired_keys.append(statement_id)
		except (ValueError, AttributeError):
			expired_keys.append(statement_id)

	for key in expired_keys:
		del cache[key]

	if expired_keys:
		print(f"Removed {len(expired_keys)} expired statement(s) from cache.")

	return cache


def fetch_statement_page(url):
	"""Fetch the HTML for the NWS product page."""
	response = requests.get(
		url,
		headers={"User-Agent": "Forecastify/1.0 (+https://forecast.weather.gov/)"},
		timeout=20,
	)
	response.raise_for_status()
	return response.text


def extract_statement_text(page_html):
	"""Extract the latest statement text from the product page."""
	match = re.search(
		r'<pre[^>]*class="glossaryProduct"[^>]*>(.*?)</pre>',
		page_html,
		flags=re.IGNORECASE | re.DOTALL,
	)

	if not match:
		raise ValueError("Unable to locate the statement text on the NWS product page")

	statement_text = html.unescape(match.group(1)).replace("\r\n", "\n").strip()
	return statement_text


def fingerprint_statement(statement_text):
	"""Create a stable fingerprint for deduplicating statements."""
	normalized_text = re.sub(r"\s+", " ", statement_text).strip().lower()
	return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def find_headline(lines):
	"""Return the first headline-like line from the statement body."""
	for line in lines:
		stripped = line.strip()
		if stripped.startswith("...") and stripped.endswith("...") and len(stripped) > 6:
			return stripped.strip(".")
	return "Public Information Statement"


def find_issue_line(lines):
	"""Return the statement issue time line if present."""
	time_pattern = re.compile(r"\b\d{1,2}\s?[AP]M\s[A-Z]{3}\s[a-zA-Z]{3}\s[a-zA-Z]{3}\s\d{1,2}\s\d{4}\b")

	for line in lines:
		if time_pattern.search(line):
			return line.strip()

	return ""


def format_statement(statement_text):
	"""Format the scraped statement for Teams."""
	lines = [line.rstrip() for line in statement_text.splitlines()]
	lines = [line for line in lines if line.strip()]

	headline = find_headline(lines)
	issue_line = find_issue_line(lines)

	body_lines = lines
	body_start = 0
	for index, line in enumerate(lines):
		if line.strip() == headline:
			body_start = index + 1
			break

	body_lines = lines[body_start:]
	formatted_text = []

	if issue_line:
		formatted_text.append(f"**Issued:** {issue_line}")

	formatted_text.append("")
	formatted_text.extend(body_lines)

	return headline, "\n".join(formatted_text).strip()


def get_latest_statement(page_url):
	"""Fetch and parse the latest Public Information Statement."""
	page_html = fetch_statement_page(page_url)
	statement_text = extract_statement_text(page_html)
	statement_id = fingerprint_statement(statement_text)
	headline, formatted_text = format_statement(statement_text)
	return {
		"id": statement_id,
		"headline": headline,
		"text": formatted_text,
		"url": page_url,
		"raw_text": statement_text,
	}


def get_new_statements(current_statement, cache):
	"""Return the statement if it has not already been sent."""
	if current_statement["id"] in cache:
		return []

	cache[current_statement["id"]] = {
		"headline": current_statement["headline"],
		"timestamp": datetime.now().isoformat(),
	}
	return [current_statement]


def main():
	"""Fetch the latest statement and send it to Teams if it is new."""
	try:
		cache = load_cache()
		cache = clean_expired_cache(cache)

		current_statement = get_latest_statement(statement_page_url)
		new_statements = get_new_statements(current_statement, cache)

		if new_statements:
			timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")

			for statement in new_statements:
				try:
					send_message(
						webhook_url=teams_webhook_url,
						title=statement["headline"],
						subtitle=timestamp,
						text=statement["text"],
						url=statement["url"],
					)
					print(f"Statement sent: {statement['headline']}")
				except Exception as e:
					print(f"Error sending statement to Teams: {e}")

			save_cache(cache)
			print(f"{len(new_statements)} new statement(s) sent to Teams.")
		else:
			print("No new statements.")
	except Exception as e:
		print(f"Error: {e}")


if __name__ == "__main__":
	main()
