"""Locally generated bearer-key identities. Not production authentication."""
import hashlib
from fastapi import Header, HTTPException
from refillops.db import connect, one


def hash_key(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def current_actor(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Supply a local demo bearer key')
    key = authorization[7:].strip()
    if not key:
        raise HTTPException(401, 'Missing bearer key')
    with connect() as conn:
        actor = one(conn, 'SELECT id, station_id, display_name, role FROM users WHERE api_key_hash=? AND active=1', (hash_key(key),))
        if not actor:
            actor = one(conn, """SELECT c.id AS customer_id, c.station_id, c.display_name
                        FROM customer_portal_keys k JOIN customers c
                        ON c.id=k.customer_id AND c.station_id=k.station_id
                        WHERE k.key_hash=? AND c.active=1""", (hash_key(key),))
            if actor:
                actor['id'] = actor['customer_id']
                actor['role'] = 'CUSTOMER'
    if not actor:
        raise HTTPException(401, 'Invalid demo key')
    return actor


def require(actor: dict, *roles: str):
    if actor['role'] not in roles:
        raise HTTPException(403, f'{actor["role"]} is not authorized')
