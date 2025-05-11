from __future__ import print_function
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from dateutil import parser
from mcp.server.fastmcp import FastMCP
import asyncio
import json

from zoneinfo import ZoneInfo  # available in Python 3.9+

# Set your desired timezone (example: Asia/Kolkata)
SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_FILE = '/path/token.json'
CLIENT_SECRET_FILE = '/path/credentials.json'

# MCP server
mcp = FastMCP("Google Calendar")

# Globals for credentials
creds: Credentials | None = None

async def ensure_creds() -> None:
    """Ensure that `creds` is valid, refreshing or running OAuth as needed."""
    global creds
    if creds and creds.valid:
        return

    # Load existing creds if present
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Refresh or run OAuth flow
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists(CLIENT_SECRET_FILE):
            raise FileNotFoundError(f"Missing {CLIENT_SECRET_FILE}")
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRET_FILE, SCOPES
        )
        creds = flow.run_local_server(
            port=5000, access_type='offline', prompt='consent'
        )

    # Save for next time
    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)




def parse_user_datetime(dt_str, timezone_str) :
    """Parses a datetime string and attaches a timezone."""
    naive_dt = parser.parse(dt_str)
    return naive_dt.replace(tzinfo=ZoneInfo(timezone_str))

def to_iso(dt):
        return dt.isoformat() if isinstance(dt, datetime) else dt

@mcp.tool()
async def get_my_events(max_results : int) -> str:
    """Fetches upcoming events from the user's primary Google Calendar with ID and time info."""

    await ensure_creds()

    service = build('calendar', 'v3', credentials=creds)
    now = datetime.utcnow().isoformat() + 'Z'
    print(f"Getting the next {max_results} events starting from {now}")

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    if not events:
        print("No upcoming events found.")
        return json.dumps([])  # Empty JSON list

    out_list = []
    for event in events:
        event_id = event.get('id')
        summary = event.get('summary', 'No Title')
        start_raw = event['start'].get('dateTime', event['start'].get('date'))

        out_list.append({
            "Event ID": event_id,
            "Start Date": start_raw,
            "Summary": summary
        })

    return json.dumps(out_list, indent=4)


@mcp.tool()
async def create_event(
    summary: str,
    description: str,
    user_start: str | datetime,
    user_end: str | datetime,
    timezone: str = "UTC"
) -> str:
    """
    Creates a Google Calendar event.

    Parameters:
    - summary: Event title
    - description: Event description
    - user_start: Start datetime (datetime object or ISO 8601 string)
    - user_end: End datetime (datetime object or ISO 8601 string)
    - timezone: Timezone (default is UTC)
    """
    global creds
    start_time = parse_user_datetime(user_start, timezone)
    end_time = parse_user_datetime(user_end, timezone)

    service = build('calendar', 'v3', credentials=creds)


    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': to_iso(start_time),
            'timeZone': timezone,
        },
        'end': {
            'dateTime': to_iso(end_time),
            'timeZone': timezone,
        },
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print(f"Event created: {event.get('htmlLink')}")
    return event

@mcp.tool()
async def delete_event(event_id: str) -> str:
    """Deletes a specific event by its ID from the user's primary calendar."""

    global creds
    service = build('calendar', 'v3', credentials=creds)

    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        print(f"Event with ID {event_id} deleted successfully.")
        return True
    except Exception as e:
        print(f"Failed to delete event: {e}")
        return False


if __name__ == '__main__':
    mcp.run(transport="stdio")
