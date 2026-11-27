"""Print the chat id and sender id of the latest private message to your bot.

Setup: put TELEGRAM_BOT_TOKEN in your environment or in a local .env
file, send any message to your bot from the account you will use as the
reviewer, then run:  python get_telegram_ids.py

Optional: if Telegram is blocked on your network, set TELEGRAM_PROXY
(environment or .env) to an HTTP(S) proxy, e.g. http://127.0.0.1:8080
The standard HTTPS_PROXY / HTTP_PROXY variables are also honoured.

It makes one getUpdates call (read only: it sends nothing and does not
mark updates as read). It prints only the chat id, the sender user id
and the sender first name. It never prints the token, and errors are
reported by class name, network reason or HTTP status only.
"""

import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request


def read_setting(key: str) -> str | None:
    value = os.environ.get(key)
    if value:
        return value.strip()
    try:
        with open(".env", encoding="utf-8") as handle:
            for line in handle:
                name, sep, val = line.strip().partition("=")
                if sep and name.strip() == key:
                    return val.strip().strip("'\"") or None
    except OSError:
        return None
    return None


def latest_private_message(updates: list) -> dict | None:
    for update in reversed(updates):
        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict):
            continue
        chat, sender = message.get("chat"), message.get("from")
        if (isinstance(chat, dict) and chat.get("type") == "private"
                and isinstance(sender, dict)):
            return {
                "chat_id": chat.get("id"),
                "user_id": sender.get("id"),
                "first_name": sender.get("first_name", ""),
            }
    return None


def explain_network_error(reason: object) -> str:
    """Turn a URLError reason into a short, token-free hint."""
    text = str(reason)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (f"{text}\n  Hint: an antivirus or proxy is intercepting HTTPS."
                " Disable HTTPS scanning or fix your certificate store.")
    if isinstance(reason, (socket.timeout, TimeoutError)) or "10060" in text:
        return (f"{text}\n  Hint: connection timed out. Telegram is probably"
                " blocked on this network. Try a VPN, a mobile hotspot, or"
                " set TELEGRAM_PROXY.")
    if isinstance(reason, ConnectionRefusedError) or "10061" in text:
        return (f"{text}\n  Hint: connection refused. Check your proxy"
                " address/port, or try a VPN.")
    if isinstance(reason, socket.gaierror) or "getaddrinfo" in text:
        return (f"{text}\n  Hint: DNS cannot resolve api.telegram.org."
                " Check your internet, or switch DNS to 1.1.1.1 / 8.8.8.8.")
    return text


def build_opener() -> urllib.request.OpenerDirector:
    proxy = read_setting("TELEGRAM_PROXY")
    if proxy:
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
        return urllib.request.build_opener(handler)
    # Default opener also picks up HTTPS_PROXY / system proxy settings.
    return urllib.request.build_opener()


def main() -> int:
    token = read_setting("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set (environment or .env).")
        return 1
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getUpdates",
        data=json.dumps({"timeout": 0, "limit": 100,
                         "allowed_updates": ["message"]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    opener = build_opener()
    try:
        with opener.open(request, timeout=20) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        # Must come before URLError: HTTPError is a subclass of it.
        print(f"Telegram answered HTTP {exc.code}."
              " (401 = wrong token, 409 = a webhook or another poller"
              " is active)")
        return 1
    except urllib.error.URLError as exc:
        # exc.reason describes the network problem and never holds the token.
        print(f"Request failed: URLError: {explain_network_error(exc.reason)}")
        return 1
    except (socket.timeout, TimeoutError):
        print("Request failed: timed out. Telegram may be blocked on this"
              " network (try a VPN or TELEGRAM_PROXY).")
        return 1
    except Exception as exc:
        print(f"Request failed: {type(exc).__name__}")
        return 1
    result = body.get("result") if isinstance(body, dict) else None
    found = latest_private_message(result) if isinstance(result, list) else None
    if found is None:
        print("No private message found. Send your bot a message from"
              " your own account, then run this again.")
        return 1
    print(f"chat id (TELEGRAM_CHAT_ID):            {found['chat_id']}")
    print(f"sender id (TELEGRAM_REVIEWER_USER_ID): {found['user_id']}")
    print(f"first name: {found['first_name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())