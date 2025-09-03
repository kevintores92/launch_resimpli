import os, csv, time, random
from datetime import datetime
from twilio.rest import Client

# --- Configuration ---

import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
SENDER_NUMBERS = ['+16153144957', '+16158824237', '+16154549166', '+16158806389', '+16158824633']

# CSV Paths
BASE_DIR = os.path.dirname(__file__)
CONTACTS_CSV = os.path.join(BASE_DIR, 'Batch-Contacts.csv')
TEMPLATES_CSV = os.path.join(BASE_DIR, 'Ace Holdings - Templates - Text Blast.csv')
BATCH_CSV = os.path.join(BASE_DIR, 'Batch.csv')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# --- Utility Functions ---
def fill_template(template, values):
    for key, val in values.items():
        template = template.replace(f'{{{key}}}', val or '')
    return template


def load_contacts(filepath):
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        return list(csv.DictReader(csvfile))


def load_templates(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        return list(csv.DictReader(csvfile))


def write_contacts(filepath, contacts, fieldnames):
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(contacts)


def append_batch(filepath, batch_rows, fieldnames):
    file_exists = os.path.isfile(filepath)
    with open(filepath, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(batch_rows)


# --- Core Sending Logic ---
def send_sms_batch(max_texts, min_interval, max_interval, progress_callback=None, stop_flag=lambda: False):
    contacts = load_contacts(CONTACTS_CSV)
    templates = load_templates(TEMPLATES_CSV)

    main_templates = [t for t in templates if t.get('Type', '').lower() == 'main']
    alt_templates = [t for t in templates if t.get('Type', '').lower() == 'alt']
    if not main_templates and templates:
        main_templates = templates

    sender_idx = 0
    sent_count = 0
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    batch_id = f"BATCH-{random.randint(100000, 999999)}"
    batch_rows = []
    processed_indices = []

    total_contacts = len(contacts)
    contact_fieldnames = contacts[0].keys() if contacts else ['Phone', 'Name', 'Address', 'Status', 'Message Used']
    batch_fieldnames = list(contact_fieldnames) + ['Batch', 'timestamp']

    for idx, contact in enumerate(contacts):
        if sent_count >= max_texts or stop_flag():
            break

        name = contact.get('Name', '')
        address = contact.get('Address', '')
        phone = contact.get('Phone', '')

        if not phone:
            contact['Status'] = 'error'
            contact['Message Used'] = ''
            continue

        template_row = random.choice(main_templates) if name and address and main_templates else (
            random.choice(alt_templates) if alt_templates else None)

        template = template_row['Message'] if template_row else "Hello {Name}, your address is {Address}."
        message = fill_template(template, {'Name': name, 'Address': address, 'Phone': phone})
        sender_number = SENDER_NUMBERS[sender_idx % len(SENDER_NUMBERS)]
        sender_idx += 1

        try:
            client.messages.create(
                body=message,
                from_=sender_number,
                to=phone if phone.startswith('+') else f'+1{phone}'
            )
            contact['Status'] = now_str
            contact['Message Used'] = template
            sent_count += 1

            batch_row = dict(contact)
            batch_row['Batch'] = batch_id
            batch_row['timestamp'] = now_str
            batch_rows.append(batch_row)
            processed_indices.append(idx)
        except Exception:
            contact['Status'] = 'error'
            contact['Message Used'] = template

        if progress_callback:
            progress_callback(sent_count, total_contacts)

        if stop_flag():
            break

        time.sleep(random.uniform(min_interval, max_interval))

    # Save updated contacts & batch
    unprocessed = [c for i, c in enumerate(contacts) if i not in processed_indices]
    write_contacts(CONTACTS_CSV, unprocessed, contact_fieldnames)

    if batch_rows:
        append_batch(BATCH_CSV, batch_rows, batch_fieldnames)

    return sent_count, total_contacts
