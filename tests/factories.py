# tests/factories.py
import uuid
from datetime import datetime, timezone

def uid():
    return str(uuid.uuid4())

def make_actor():
    return uid()

def make_org():
    return uid()

def now():
    return datetime.now(timezone.utc)
