"""Load secrets from .secrets.env (gitignored). Never hard-code keys; never print them."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(HERE, ".secrets.env")

def load():
    s = {}
    if os.path.exists(_PATH):
        for ln in open(_PATH):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                s[k.strip()] = v.strip()
    return s

SECRETS = load()
ETHERSCAN_KEY = SECRETS.get("ETHERSCAN_KEY", "")
HELIUS_KEY = SECRETS.get("HELIUS_KEY", "")
BITQUERY_TOKEN = SECRETS.get("BITQUERY_TOKEN", "")
