import os

import httpx
from dotenv import load_dotenv

load_dotenv()
page_id = os.getenv("FACEBOOK_PAGE_ID")
token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
print("FACEBOOK_PAGE_ID =", page_id)
print("TELEGRAM_REVIEW_PAGE_ID =", os.getenv("TELEGRAM_REVIEW_PAGE_ID"))
if not page_id or not token:
    raise SystemExit("page id or token missing")
response = httpx.get(
    f"https://graph.facebook.com/v22.0/{page_id}",
    params={"fields": "name,id", "access_token": token},
    timeout=20,
)
if response.status_code == 200:
    data = response.json()
    print("page name =", data.get("name"), "| id =", data.get("id"))
else:
    print("facebook answered HTTP", response.status_code)