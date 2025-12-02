import requests

def format_message(title, subtitle, text, url):
    """Format an adaptive card message for Teams."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": title,
                            "weight": "Bolder",
                            "size": "Large",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": subtitle,
                            "wrap": True,
                            "weight": "Lighter",
                            "size": "Medium",
                            "isSubtle": True
                        },
                        {
                            "type": "TextBlock",
                            "text": text,
                            "wrap": True
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "Open link",
                            "url": url
                        }
                    ]
                }
            }
        ]
    }

def send_message(webhook_url, title, subtitle, text, url):
    """Send an adaptive card message to Teams."""
    message = format_message(title, subtitle, text, url)
    response = requests.post(webhook_url, json=message)

    if response.status_code in [200, 202]:
        print("Message sent successfully.")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")