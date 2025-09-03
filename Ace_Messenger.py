from flask import Flask, request, jsonify, render_template, redirect, url_for, Response, g
from flask_socketio import SocketIO
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from pyngrok import ngrok
from datetime import datetime, timezone, timedelta
from dateutil import parser, tz

from sms_sender_core import send_sms_batch
import threading
import os, sqlite3, threading, webbrowser, time, csv

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


import sqlite3

# ── CONFIG ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "messages.db")
LEADS_CSV_PATH = os.path.join(BASE_DIR, "Leads.csv")
PORT = int(os.environ.get("PORT", 5000))

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBERS = os.environ.get("TWILIO_NUMBERS", "").split(",")
YOUR_PHONE = os.environ.get("YOUR_PHONE")


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
batch_status = {"sent": 0, "total": 0, "running": False}
BASE_DIR = os.path.dirname(__file__)
BATCH_CSV = os.path.join(BASE_DIR, 'Batch.csv')

# --- MIGRATION: Ensure contact_drip_assignments table exists ---
def ensure_drip_assignment_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS contact_drip_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_phone TEXT,
            drip_id INTEGER,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

ensure_drip_assignment_table()


import threading
import time
# Stop flag for batch control
stop_batch = False

TAGS = [
    "Hot", "Nurture", "Drip", "Qualified", "Wrong Number", "Not interested", "DNC"
]
TAG_ICONS = {
    "Hot": "🔥",
    "Nurture": "🌱",
    "Drip": "💧",
    "Qualified": "✅",
    "Wrong Number": "❗",
    "Not interested": "❌",
    "DNC": "📵",
    "No tag": "🏷️"
}

ngrok_public_url = ngrok.connect(PORT).public_url
print(f"[ngrok] Public URL: {ngrok_public_url}")
# ── HELPERS ────────────────────────────────────────────────────────
def normalize_e164(num):
    s = ''.join(filter(str.isdigit, str(num)))
    if s.startswith('1') and len(s) == 11:
        return '+' + s
    elif len(s) == 10:
        return '+1' + s
    elif num.startswith('+'):
        return num
    return num
def normalize_timestamp(ts_str):
    if not ts_str:
        return ""
    try:
        if "T" in ts_str:
            date_part, time_part = ts_str.split("T")
        elif " " in ts_str:
            date_part, time_part = ts_str.split(" ")
        else:
            # fallback if timestamp is not standard
            return ts_str

        time_part = time_part.split(".")[0]  # remove microseconds
        return f"{date_part} {time_part}"
    except Exception as e:
        print(f"Error normalizing timestamp: {ts_str} -> {e}")
        return ts_str


        # Example before inserting into DB
        raw_ts = message["timestamp"]  # from Twilio API
        normalized_ts = normalize_timestamp(raw_ts)
        message["timestamp"] = normalized_ts

        # Now insert message dict into DB
        db_cursor.execute("""
            INSERT INTO messages (phone, body, timestamp, ...)
            VALUES (?, ?, ?, ...)
        """, (message["phone"], message["body"], message["timestamp"], ...))

def get_caller_id_for_phone(phone):
    phone = normalize_e164(phone)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 1) Latest INBOUND
    c.execute("""
        SELECT twilio_number FROM messages
        WHERE phone=? AND direction='inbound'
              AND twilio_number IS NOT NULL AND twilio_number != ''
        ORDER BY timestamp DESC LIMIT 1
    """, (phone,))
    row = c.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]
    # 2) Latest OUTBOUND
    c.execute("""
        SELECT twilio_number FROM messages
        WHERE phone=? AND direction LIKE 'outbound%%'
              AND twilio_number IS NOT NULL AND twilio_number != ''
        ORDER BY timestamp DESC LIMIT 1
    """, (phone,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    # 3) Default fallback
    return TWILIO_NUMBERS[0]

def remove_drip_assignment(phone):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM contact_drip_assignments WHERE contact_phone=?", (phone,))
    conn.commit()
    conn.close()

def log_message(phone, direction, body, status=None, timestamp=None, twilio_number=None):
    phone = normalize_e164(phone)

    # Ensure timestamp
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    timestamp = normalize_timestamp(timestamp)

    # Fallback Twilio number logic
    if not twilio_number:
        try:
            if request:  # Only valid inside a request context
                if direction == 'inbound':
                    twilio_number = request.form.get("To")
                else:
                    twilio_number = request.form.get("From")
        except RuntimeError:
            # No request context (e.g. background import)
            pass
        if not twilio_number:
            twilio_number = TWILIO_NUMBERS[0]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Duplicate check (ignore timestamp to avoid mismatch problems)
    c.execute("SELECT 1 FROM messages WHERE phone=? AND direction=? AND body=?",
              (phone, direction, body))
    if not c.fetchone():
        c.execute(
            "INSERT INTO messages (phone, direction, body, timestamp, status, twilio_number) VALUES (?, ?, ?, ?, ?, ?)",
            (phone, direction, body, timestamp, status, twilio_number)
        )
        conn.commit()
        print(f"[DB] Inserted message: {phone=} {direction=} {body[:50]!r} {timestamp=} {status=} {twilio_number=}")
    else:
        print(f"[DB] Skipped duplicate: {phone=} {direction=} {body[:50]!r}")

    conn.close()

    # Emit to frontend
    socketio.emit("new_message", {
        "phone": phone,
        "body": body,
        "direction": direction,
        "timestamp": timestamp
    })

    # ---------------------------
    # Tagging hook (added)
    # ---------------------------
    if direction == "inbound":
        # Remove drip assignment if contact replies
        remove_drip_assignment(phone)
        tag = get_tag_for_message(body)
        if tag:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE contacts SET tag=? WHERE phone=?", (tag, phone))
            conn.commit()
            conn.close()
            print(f"[Tagging] {phone} tagged as {tag} (msg: {body[:50]!r})")
# === DRIP SCHEDULER ===
def process_drip_assignments():
    now = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Get all active assignments
    c.execute("SELECT id, contact_phone, drip_id, assigned_at FROM contact_drip_assignments WHERE completed=0")
    assignments = c.fetchall()
    for assign_id, phone, drip_id, assigned_at in assignments:
        # Get all drip messages for this drip
        c2 = conn.cursor()
        c2.execute("SELECT day_offset, message_template FROM drip_messages WHERE drip_id=? ORDER BY day_offset ASC", (drip_id,))
        drip_msgs = c2.fetchall()
        # Parse assigned_at
        assigned_dt = parser.parse(assigned_at)
        days_since = (now - assigned_dt).days
        # For each message, check if it should be sent
        for day_offset, msg_template in drip_msgs:
            # Only send if day_offset matches days_since and not already sent
            # Check if a message with this template has already been sent to this phone after assigned_at
            c2.execute("SELECT 1 FROM messages WHERE phone=? AND body=? AND timestamp>=?", (phone, msg_template, assigned_at))
            already_sent = c2.fetchone()
            if not already_sent and days_since >= int(day_offset):
                # Send at the same time of day as assigned_at
                send_time = assigned_dt + timedelta(days=int(day_offset))
                if now >= send_time and now < send_time + timedelta(minutes=10):  # 10 min window
                    # Use the most recent twilio_number for this thread, or fallback
                    c2.execute("SELECT twilio_number FROM messages WHERE phone=? AND twilio_number IS NOT NULL AND twilio_number != '' ORDER BY timestamp DESC LIMIT 1", (phone,))
                    row = c2.fetchone()
                    from_number = row[0] if row and row[0] else TWILIO_NUMBERS[0]
                    try:
                        client.messages.create(to=phone, from_=from_number, body=msg_template)
                        log_message(phone=phone, direction="outbound", body=msg_template, twilio_number=from_number)
                        print(f"[Drip] Sent drip message to {phone} for drip {drip_id} (day {day_offset})")
                    except Exception as e:
                        print(f"[Drip] Failed to send drip message to {phone}: {e}")
    conn.close()

def drip_scheduler_loop():
    while True:
        try:
            process_drip_assignments()
        except Exception as e:
            print(f"[Drip Scheduler] Error: {e}")
        time.sleep(600)  # Run every 10 minutes

# Start the scheduler in a background thread
drip_thread = threading.Thread(target=drip_scheduler_loop, daemon=True)
drip_thread.start()



def get_conversation(phone):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE phone=? ORDER BY timestamp ASC", (phone,))
    convo = c.fetchall()
    conn.close()
    return convo

def get_threads(search=None, tag_filters=None, box=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_phone ON messages(phone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)")

    if not box:
        box = 'all'

    c.execute("SELECT phone, MAX(timestamp) as latest_time FROM messages GROUP BY phone ORDER BY latest_time DESC")
    phones = c.fetchall()
    threads = []

    for contact_phone, latest_time in phones:
        # Get last 2 inbound messages for preview
        c.execute("""
            SELECT body, timestamp FROM messages
            WHERE phone=? AND direction='inbound'
            ORDER BY timestamp DESC LIMIT 2
        """, (contact_phone,))
        inbound_rows = c.fetchall()

        if inbound_rows:
            latest_body = "\n".join([(row[0] or "") for row in inbound_rows[::-1]])
            latest_timestamp = inbound_rows[0][1]  # timestamp of most recent inbound
            latest_direction = "inbound"
            twilio_number = ""  # not needed for preview
        else:
            # Fallback → latest message of any type
            c.execute("""
                SELECT body, direction, timestamp, twilio_number 
                FROM messages 
                WHERE phone=? ORDER BY timestamp DESC LIMIT 1
            """, (contact_phone,))
            latest_row = c.fetchone()
            latest_body = latest_row[0] if latest_row else ""
            latest_direction = latest_row[1] if latest_row else ""
            latest_timestamp = latest_row[2] if latest_row else latest_time
            twilio_number = latest_row[3] if latest_row else ""

        # Fetch contact info
        c.execute("SELECT Name, Address, tag, notes FROM contacts WHERE phone=?", (contact_phone,))
        contact_row = c.fetchone()
        name = contact_row[0] if contact_row else ""
        address = contact_row[1] if contact_row else ""
        tag = contact_row[2] if contact_row and len(contact_row) > 2 else ""
        notes = contact_row[3] if contact_row and len(contact_row) > 3 else ""

        # Filter by box type
        if box == 'inbox' and latest_direction != 'inbound':
            continue
        if box == 'sent' and not str(latest_direction).startswith('outbound'):
            continue

        # Filter by tag
        if tag_filters:
            tag_val = (tag or "").strip().lower()
            match = False
            for tf in tag_filters:
                if tf == "__no_tag__" and not tag_val:
                    match = True
                elif tag_val == tf:
                    match = True
            if not match:
                continue

        # Filter by search
        if search and search.strip() and search.lower() not in (str(contact_phone) + str(name) + str(address)).lower():
            continue

        # Format timestamp
        dt = parser.parse(str(latest_timestamp)) if latest_timestamp else datetime.now()
        ts_formatted = dt.strftime('%Y-%m-%d %I:%M:%S %p CST')

        # Build thread entry
        threads.append({
            "phone": contact_phone,
            "name": name,
            "address": address,
            "tag": tag,
            "notes": notes,
            "latest": latest_body,
            "latest_direction": latest_direction,  # add this line
            "timestamp": ts_formatted,
            "twilio_number": twilio_number,
            "unread": False
        })


    conn.close()
    return threads


from dateutil import parser, tz
import sqlite3

def deduplicate_and_import(preview_only=False, lookback_days=1):
    """
    Import recent messages from Twilio into the local DB.
    Uses a sliding window to ensure no outbound-api messages are skipped.
    """
    from_zone = tz.gettz('UTC')
    to_zone = tz.gettz('America/Chicago')

    # Step 1: Prepare deduplication set from DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone, direction, body, timestamp FROM messages")
    db_msgs = set((row[0], row[1], row[2], str(row[3])) for row in c.fetchall())
    conn.close()

    # Step 2: Sliding window - fetch last N days
    since_dt = datetime.utcnow() - timedelta(days=lookback_days)
    fetch_kwargs = {"limit": 1000, "date_sent_after": since_dt.isoformat() + "Z"}

    twilio_msgs = []
    total_msgs = 0

    for msg in client.messages.list(**fetch_kwargs):
        direction = msg.direction  # Twilio gives 'inbound', 'outbound-api', 'outbound-reply'
        phone = msg.from_ if direction == "inbound" else msg.to
        twilio_number = msg.to if direction == "inbound" else msg.from_
        body = msg.body
        ts = parser.parse(msg.date_sent.isoformat()).astimezone(to_zone).strftime('%Y-%m-%d %H:%M:%S') if msg.date_sent else ""
        status = msg.status
        sid = msg.sid  # unique Twilio message ID

        # Dedup check: use sid if available, else fallback on (phone, direction, body, ts)
        key = (phone, direction, body, ts)
        if key not in db_msgs:
            twilio_msgs.append((phone, direction, body, ts, status, twilio_number))
        total_msgs += 1

    if preview_only:
        print(f"[Preview] Found {len(twilio_msgs)} new of {total_msgs} fetched.")
        return

    # Step 3: Insert new messages
    for phone, direction, body, timestamp, status, twilio_number in twilio_msgs:
        log_message(
            phone=phone,
            direction=direction,
            body=body,
            status=status,
            timestamp=timestamp,
            twilio_number=twilio_number
        )

    print(f"[Sync] Imported {len(twilio_msgs)} new messages from Twilio (checked {total_msgs}).")

def update_webhooks(public_url):
    for number in TWILIO_NUMBERS:
        incoming = client.incoming_phone_numbers.list(phone_number=number)
        if incoming: incoming[0].update(sms_url=f"{public_url}/sms-webhook", sms_method="POST")
        
def get_tag_for_message(body: str):
    body = body.lower().strip()
    if "stop" in body:
        return "DNC"       # Stop always wins
    elif "wrong" in body:
        return "Wrong number"
    return None

def process_message(phone, direction, body, timestamp):
    if direction != "inbound":
        return

    tag = get_tag_for_message(body)
    if tag:
        print(f"Tagging {phone} with {tag} (msg: {body})")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # assumes your contacts table has phone + tag fields
        c.execute("UPDATE contacts SET tag=? WHERE phone=?", (tag, phone))
        conn.commit()
        conn.close()


# ── ROUTES ────────────────────────────────────────────────────────


# 📩 Inbox (main page)
from flask import Flask, request, render_template
from datetime import datetime

app = Flask(__name__)

@app.route("/")
@app.route("/inbox")
def inbox():
    search = request.args.get("search", "")
    box = request.args.get("box", "inbox")
    tags_filter = request.args.getlist("tags")
    selected_phone = request.args.get("selected")

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    # fetch all threads
    all_threads = get_threads(search=search, box=box)

    if box == 'unread':
        all_threads = [
            t for t in all_threads
            if not t.get("tag") and t.get("latest") and t.get("latest").strip() and "inbound" in t.get("latest_direction", "inbound")
        ]

    # --- Tag filtering ---
    if tags_filter:
        if "__ALL__" not in tags_filter:
            if "__NO_tag__" in tags_filter:
                all_threads = [t for t in all_threads if not t.get("tag")]
            else:
                all_threads = [t for t in all_threads if t.get("tag") in tags_filter]
        else:
            excluded = {"DNC", "No tag", "Wrong Number", "Unverified", "Not interested"}
            all_threads = [t for t in all_threads if t.get("tag") not in excluded]

    # --- Date filtering ---
    def parse_date(ts):
        try:
            return datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    if from_date:
        from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
        all_threads = [
            t for t in all_threads
            if parse_date(t.get("timestamp")) and parse_date(t["timestamp"]) >= from_d
        ]

    if to_date:
        to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
        all_threads = [
            t for t in all_threads
            if parse_date(t.get("timestamp")) and parse_date(t["timestamp"]) <= to_d
        ]

    threads = all_threads  

    unread_count = len([t for t in all_threads if t.get("latest_direction") == "inbound" and not t.get("read")])
    unanswered_count = len([t for t in all_threads if t.get("latest_direction") == "inbound" and not t.get("responded")])
    reminders_count = 0  # later query reminders table
    no_tags_count = len([t for t in all_threads if not t.get("tag")])

    return render_template(
        "dashboard.html",
        threads=threads,
        search=search,
        box=box,
        selected_phone=selected_phone,
        total_threads=len(all_threads),
        tags=TAGS,
        tag_icons=TAG_ICONS,
        TWILIO_NUMBERS=TWILIO_NUMBERS,
        unread_count=unread_count,
        unanswered_count=unanswered_count,
        reminders_count=reminders_count,
        no_tags_count=no_tags_count
    )

# === Drip Automations ===
@app.route("/assign-drip", methods=["POST"])
def assign_drip():
    data = request.get_json(force=True)
    phone = data.get("phone")
    drip_id = data.get("drip_id")
    if not phone or not drip_id:
        return jsonify({"success": False, "error": "Missing phone or drip_id"}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Get drip name
    c.execute("SELECT name FROM drip_automations WHERE id=?", (drip_id,))
    drip_row = c.fetchone()
    drip_name = drip_row[0] if drip_row else ""
    # Remove any previous assignment for this contact (optional, only one drip at a time)
    c.execute("DELETE FROM contact_drip_assignments WHERE contact_phone=?", (phone,))
    c.execute("INSERT INTO contact_drip_assignments (contact_phone, drip_id) VALUES (?, ?)", (phone, drip_id))
    # Set tag as 'Drip - [Drip Name]'
    if drip_name:
        tag_val = f"Drip - {drip_name}"
        c.execute("UPDATE contacts SET tag=? WHERE phone=?", (tag_val, phone))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# === Drip Messages Popup ===
@app.route("/drip-messages/<int:drip_id>")
def drip_messages_popup(drip_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM drip_automations WHERE id=?", (drip_id,))
    drip_row = c.fetchone()
    drip_name = drip_row[0] if drip_row else ""
    c.execute("SELECT day_offset, message_template FROM drip_messages WHERE drip_id=? ORDER BY day_offset ASC", (drip_id,))
    messages = [
        {"day_offset": row[0], "message_template": row[1]} for row in c.fetchall()
    ]
    conn.close()
    return render_template("drip_messages_popup.html", drip={"name": drip_name}, messages=messages)

# 📊 Placeholder Dashboard page (real KPIs later)
@app.route("/dashboard")
def dashboard():
    return render_template("placeholder_dashboard.html")

@app.route("/reminders/new", methods=["POST"])
def new_reminder():
    thread_phone = request.form.get("thread_phone")
    remind_at = request.form.get("remind_at")
    note = request.form.get("note")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO reminders (thread_phone, remind_at, note)
        VALUES (?, ?, ?)
    """, (thread_phone, remind_at, note))
    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/thread/<phone>")
def thread_view(phone):
    # === Get messages ===
    convo = get_conversation(phone)
    convo_out = []
    for row in convo:
        is_outbound = str(row[2]).startswith("outbound")
        convo_out.append({
            "row": row,
            "body": row[3],
            "timestamp": row[4],
            "twilio_number": row[5],
            "is_outbound": is_outbound
        })

    # === Get contact ===
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(contacts)")
    col_names = [desc[1] for desc in c.fetchall()]

    c.execute("SELECT * FROM contacts WHERE phone=?", (phone,))
    row = c.fetchone()
    contact = {col: str(val) if val is not None else "" for col, val in zip(col_names, row)} if row else {}

    # === Normalize name ===
    csv_name = contact.get("Name", "").strip()
    db_name = contact.get("db_name", "").strip() if "db_name" in contact else ""
    fallback_name = contact.get("name", "").strip() if "name" in contact else ""

    # Choose best available
    name = csv_name or db_name or fallback_name
    if not name and "name" in contact:  # catch-all for lowercase
        name = contact["name"].strip()

    # === Pick main fields ===
    main_fields = [
        "Name", "Address", "County", "Mailing Address", "Phone", "notes",
        "Last Sale Amount", "Last Sale Recording Date", "Effective Year Built",
        "Bd/Ba", "Owner 2", "Building Sqft", "Alt Phone 1", "Alt Phone 2"
    ]
    contact_main = {k: contact.get(k, "") for k in main_fields} if contact else {}

    # === Build response ===
    return jsonify(dict(
        messages=convo_out,
        contact=contact_main,
        contact_all=contact,
        contact_headers=col_names,
        csv_name=csv_name,
        db_name=db_name,
        name=name,              # 🔑 Always return a top-level "name"
        tag=contact.get("tag", ""),
        notes=contact.get("notes", "")
    ))


@app.route("/send", methods=["POST"])
def send_sms():
    data = request.json
    to, body = data["to"], data["body"]

    # Pick the most recent Twilio number for this thread
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT twilio_number FROM messages
        WHERE phone=? AND twilio_number IS NOT NULL AND twilio_number != ''
        ORDER BY timestamp DESC LIMIT 1
    """, (to,))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return jsonify(success=False, error="No previous Twilio number found for this thread.")

    from_number = row[0]

    try:
        # Send via Twilio
        message = client.messages.create(to=to, from_=from_number, body=body)

        # Poll a few times for a status update (optional)
        status = None
        for _ in range(5):
            msg = client.messages(message.sid).fetch()
            if msg.status not in ("queued", "sending", "accepted"):
                break
            time.sleep(1)
        status = msg.status

        # Log it explicitly with from_number
        log_message(
            phone=to,
            direction="outbound",
            body=body,
            status=status,
            twilio_number=from_number
        )

        return jsonify(success=True, status=status)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/call", methods=["POST"])
def call_contact():
    data = request.get_json(force=True)
    phone = data.get("phone")
    custom_from = data.get("from")  # Caller ID selected in the dialer (optional)

    if not phone:
        return jsonify(success=False, error="No phone provided"), 400

    to_number = normalize_e164(phone)

    # If user picked one from dropdown, use it
    if custom_from and custom_from in TWILIO_NUMBERS:
        from_number = custom_from
    else:
        # fallback → use last used or default
        from_number = get_caller_id_for_phone(to_number)

    twiml_url = f"{ngrok_public_url}/twiml?lead={to_number}"
    try:
        call = client.calls.create(to=YOUR_PHONE, from_=from_number, url=twiml_url)
        return jsonify(success=True, sid=call.sid, from_number=from_number, lead=to_number)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route("/create_thread", methods=["POST"])
def create_thread():
    data = request.get_json(force=True)
    to = data.get("to")
    from_number = data.get("from")
    body = data.get("body")

    if not to or not body:
        return jsonify({"success": False, "error": "Missing to/body"}), 400

    try:
        # Send SMS via Twilio
        message = client.messages.create(to=to, from_=from_number, body=body)

        # Log in messages table so the new thread shows up
        log_message(phone=to, direction="outbound", body=body, twilio_number=from_number)

        # Ensure a contact row exists for this number
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM contacts WHERE phone=?", (to,))
        if not c.fetchone():
            c.execute("INSERT INTO contacts (phone, tag, notes) VALUES (?, ?, ?)", (to, "No tag", ""))
            conn.commit()
        conn.close()

        return jsonify({"success": True, "thread_id": to})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/update-meta", methods=["POST"])
def update_meta():
    data = request.get_json(force=True)
    phone, tag, notes = data.get("phone"), data.get("tag", ""), data.get("notes", "")

    # Default to "No tag" if empty
    if not tag:
        tag = "No tag"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if contact exists
    c.execute("SELECT 1 FROM contacts WHERE phone=?", (phone,))
    if c.fetchone():
        c.execute("UPDATE contacts SET tag=?, notes=? WHERE phone=?", (tag, notes, phone))
    else:
        # Insert new row with default "No tag"
        c.execute("INSERT INTO contacts (phone, tag, notes) VALUES (?, ?, ?)", (phone, tag, notes))

    conn.commit()
    conn.close()

    socketio.emit("meta_updated", {"phone": phone, "tag": tag, "notes": notes})
    return jsonify({"success": True})


@app.route("/sms-webhook", methods=["POST"])
def sms_webhook():
    data = request.form.to_dict()
    phone, body = data.get('From'), data.get('Body')
    timestamp = datetime.utcnow().isoformat()
    log_message(phone, 'inbound', body, timestamp=timestamp)
    return 'OK', 200

@app.route("/twiml", methods=['GET','POST'])
def serve_twiml():
    lead_number = request.args.get('lead')
    if not lead_number: return "Missing 'lead' number", 400
    vr = VoiceResponse()
    vr.dial(lead_number)
    return Response(str(vr), mimetype='text/xml')

# === Drip Automations ===
@app.route("/drip-automations")
def drip_automations():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT d.id, d.name, m.day_offset, m.message_template
        FROM drip_automations d
        LEFT JOIN drip_messages m ON d.id = m.drip_id
        ORDER BY d.id ASC, m.day_offset ASC
    """)
    automations = [
        {"id": row[0], "name": row[1], "day_offset": row[2], "message_template": row[3]}
        for row in c.fetchall()
    ]
    # Get contacts table columns for merge field dropdown
    c.execute("PRAGMA table_info(contacts)")
    contact_columns = [row[1] for row in c.fetchall()]
    conn.close()
    # If AJAX (popup), render only the popup partial
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('popup') == '1':
        return render_template("drip_select_popup.html", automations=automations)
    return render_template("drip_automations.html", automations=automations, contact_columns=contact_columns)


@app.route("/drip-automations/new", methods=["GET", "POST"])
def new_drip_automation():
    if request.method == "POST":
        name = request.form.get("name")
        messages = request.form.getlist("messages[]")  # multiple textarea values
        days = request.form.getlist("days[]")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Insert parent drip
        c.execute("INSERT INTO drip_automations (name) VALUES (?)", (name,))
        drip_id = c.lastrowid

        # Insert messages
        for day, msg in zip(days, messages):
            c.execute("""
                INSERT INTO drip_messages (drip_id, day_offset, message_template)
                VALUES (?, ?, ?)
            """, (drip_id, day, msg))

        conn.commit()
        conn.close()
        return redirect("/drip-automations")
    else:
        # GET: render new drip form with contact columns
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(contacts)")
        contact_columns = [row[1] for row in c.fetchall()]
        conn.close()
        return render_template("new_drip.html", contact_columns=contact_columns)



@app.route("/drip-automations/edit/<int:drip_id>", methods=["GET", "POST"])
def edit_drip_automation(drip_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        messages = request.form.getlist("messages[]")
        days = request.form.getlist("days[]")

        # update name
        c.execute("UPDATE drip_automations SET name=? WHERE id=?", (name, drip_id))

        # delete old messages and reinsert
        c.execute("DELETE FROM drip_messages WHERE drip_id=?", (drip_id,))
        for day, msg in zip(days, messages):
            c.execute("""
                INSERT INTO drip_messages (drip_id, day_offset, message_template)
                VALUES (?, ?, ?)
            """, (drip_id, day, msg))

        conn.commit()
        conn.close()
        return redirect("/drip-automations")
    else:
        # fetch automation + messages
        c.execute("SELECT id, name FROM drip_automations WHERE id=?", (drip_id,))
        drip = c.fetchone()
        c.execute("SELECT id, day_offset, message_template FROM drip_messages WHERE drip_id=? ORDER BY day_offset ASC", (drip_id,))
        messages = [{"id": row[0], "day_offset": row[1], "message_template": row[2]} for row in c.fetchall()]
        # fetch contact columns
        c.execute("PRAGMA table_info(contacts)")
        contact_columns = [row[1] for row in c.fetchall()]
        conn.close()
        if not drip:
            return "Drip automation not found", 404
        return render_template("edit_drip.html", drip={"id": drip[0], "name": drip[1]}, messages=messages, contact_columns=contact_columns)


@app.route("/drip-automations/delete/<int:drip_id>", methods=["POST"])
def delete_drip_automation(drip_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM drip_automations WHERE id=?", (drip_id,))
    conn.commit()
    conn.close()
    return redirect("/drip-automations")


@app.route("/export-contacts", methods=["POST"])
def export_contacts():
    data = request.get_json(force=True)
    phones = data.get("phones")
    if not phones: return jsonify({"error":"No phones provided"}),400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(contacts)")
    col_names = [row[1] for row in c.fetchall()]
    rows=[]
    for phone in phones:
        c.execute(f"SELECT {', '.join(col_names)} FROM contacts WHERE phone=?", (phone,))
        contact_row = c.fetchone()
        if contact_row: rows.append(contact_row)
    conn.close()
    def generate():
        with open('/tmp/selected_contacts.csv','w',newline='',encoding='utf-8') as f:
            writer=csv.writer(f)
            writer.writerow(col_names)
            for row in rows: writer.writerow(row)
        with open('/tmp/selected_contacts.csv','r',encoding='utf-8') as f: yield f.read()
    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition":"attachment;filename=selected_contacts.csv"})

@app.route("/add-to-leads", methods=["POST"])
def add_to_leads():
    data = request.get_json(force=True)
    phone = data.get("phone")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, address, tag, notes FROM contacts WHERE phone=?", (phone,))
    contact_row = c.fetchone()
    name = contact_row[0] if contact_row else ""
    address = contact_row[1] if contact_row else ""
    tag = contact_row[2] if contact_row and len(contact_row) > 2 else ""
    notes = contact_row[3] if contact_row and len(contact_row) > 3 else ""
    c.execute("SELECT body, twilio_number FROM messages WHERE phone=? ORDER BY timestamp DESC LIMIT 1", (phone,))
    msg_row = c.fetchone()
    body = msg_row[0] if msg_row else ""
    twilio_number = msg_row[1] if msg_row else ""
    conn.close()
    fields = ["phone","name","address","body","tag","notes","twilio_number"]
    row_data = [phone,name,address,body,tag,notes,twilio_number]
    file_exists = os.path.isfile(LEADS_CSV_PATH)
    with open(LEADS_CSV_PATH,"a",newline='',encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists: writer.writerow(fields)
        writer.writerow(row_data)
    return jsonify({"success": True})

# --- SEARCH Feature --- Database connection helper ---
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row  # Access columns by name
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# --- Fetch threads with optional contact info ---
def get_all_threads():
    conn = get_db()
    cursor = conn.cursor()
    # Left join contacts table to get name/address if available
    cursor.execute("""
        SELECT 
            m.phone, m.body, m.timestamp,
            c.name AS contact_name, 
            c.address AS contact_address
        FROM messages m
        LEFT JOIN contacts c ON m.phone = c.phone
        ORDER BY m.timestamp DESC
    """)
    rows = cursor.fetchall()
    return [
        {
            "phone": r["phone"],
            "body": r["body"],
            "timestamp": r["timestamp"],
            "contact_name": r["contact_name"],      # can be None
            "contact_address": r["contact_address"] # can be None
        }
        for r in rows
    ]

# --- Search endpoint ---
@app.route("/search_threads")
def search_threads():
    query = request.args.get("q", "").lower()

    all_threads = get_all_threads()

    if query:
        filtered = [
            t for t in all_threads
            if query in (t["phone"] or "").lower()
               or query in (t["body"] or "").lower()
        ]
    else:
        filtered = all_threads

    # No pagination → return all
    return jsonify({
        "threads": filtered,
        "page": 1,
        "total_pages": 1
    })



# ── SUPPORT /threads REDIRECT TO INDEX ───────────────────────────────
@app.route("/threads")
def threads_redirect():
    search = request.args.get("search", "")
    box = request.args.get("box", "inbox")
    tag = request.args.get("tags", "").strip()
    selected_phone = request.args.get("selected")

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    # fetch all threads
    all_threads = get_threads(search=search, box=box)

    if box == 'unread':
        all_threads = [
            t for t in all_threads
            if not t.get("tag") and t.get("latest_direction") == "inbound"
        ]

    elif box == "reminders":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT thread_phone FROM reminders")
        phones_with_reminders = {row[0] for row in c.fetchall()}
        conn.close()
        all_threads = [t for t in all_threads if t.get("phone") in phones_with_reminders]

    elif box == "no-tags":
        all_threads = [t for t in all_threads if not t.get("tag")]

    # --- Tag filtering ---
    if tag:
        if tag == "__NO_tag__":
            all_threads = [t for t in all_threads if not t.get("tag")]
        elif tag != "__ALL__":  # specific tag filter
            all_threads = [t for t in all_threads if t.get("tag") == tag]

    # --- Date filtering ---
    def parse_date(ts):
        try:
            return datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    if from_date:
        from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
        all_threads = [
            t for t in all_threads
            if parse_date(t.get("timestamp")) and parse_date(t["timestamp"]) >= from_d
        ]

    if to_date:
        to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
        all_threads = [
            t for t in all_threads
            if parse_date(t.get("timestamp")) and parse_date(t["timestamp"]) <= to_d
        ]

    # no slicing → return all
    threads = all_threads  

    # Render only the thread list (AJAX expects this)
    return render_template("_threads_list.html", threads=threads, selected_phone=selected_phone)

@app.route("/batch-logs")
def batch_logs():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    rows = []
    if os.path.exists(BATCH_CSV):
        with open(BATCH_CSV, newline='', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
            total = len(all_rows)
            start = (page - 1) * per_page
            end = start + per_page
            # newest first
            rows = list(reversed(all_rows))[start:end]
    else:
        total = 0

    return jsonify({
        "rows": rows,
        "page": page,
        "per_page": per_page,
        "total": total
    })


@app.route("/batch-sender", methods=["GET", "POST"])
def batch_sender():
    global batch_status, stop_batch
    if request.method == "POST":
        max_texts = int(request.form.get("max_texts", 200))
        min_interval = float(request.form.get("min_interval", 5.01))
        max_interval = float(request.form.get("max_interval", 9.99))

        # reset batch status and stop flag
        batch_status = {"sent": 0, "total": 0, "running": True}
        stop_batch = False

        def progress_cb(sent, total):
            batch_status["sent"] = sent
            batch_status["total"] = total

        def worker():
            from sms_sender_core import send_sms_batch
            send_sms_batch(
                max_texts,
                min_interval,
                max_interval,
                progress_cb,
                stop_flag=lambda: stop_batch
            )
            batch_status["running"] = False

        threading.Thread(target=worker, daemon=True).start()
        return redirect("/batch-sender")

    return render_template("batch_sender.html", status=batch_status)


@app.route("/batch-progress")
def batch_progress():
    return jsonify(batch_status)

@app.route("/stop-batch", methods=["POST"])
def stop_batch_route():
    global stop_batch
    stop_batch = True
    return jsonify({"stopped": True})

# ── SERVER LAUNCH ─────────────────────────────────────────────────
def run_flask(): socketio.run(app, port=PORT, debug=False)

def launch_dashboard():
    print("[Progress] Deduplicating and importing messages...")
    deduplicate_and_import()
    print("[Progress] Updating Twilio webhooks...")
    update_webhooks(ngrok_public_url)
    print("[Progress] Launching dashboard in browser...")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

if __name__ == "__main__":
    launch_dashboard()
