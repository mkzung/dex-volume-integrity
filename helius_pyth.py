"""PYTH (Solana) on-chain full-day check via Helius Enhanced Transactions API, for symmetry
with the EVM pools. For each PYTH-fleet wallet, paginate its SWAP transactions over the last
24h and sum the PYTH-token leg (mint HZ1Jov...) in USD. Compare the fleet total to the pool's
independent daily volume (DexScreener). Writes data/pyth_onchain.json.
Note: these wallets also trade other tokens, so we count only their PYTH-pool volume."""
import json, os, subprocess, time
from lib_secrets import HELIUS_KEY
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
MINT = "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"
PRICE = 0.0390089107499520
FLEET = ["HYe4vSaEGqQKnDrxWDrk3o5H2gznv7qtij5G6NNG8WHd", "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa",
         "JD6rVaerbyz6wjQ433nrw6bFTgFrp46MiYmi8EtUAfsG", "R32xAccFis3YzBzGwZ1C4QkGiehLxSao7gDmErA3kjk"]
CUTOFF = int(time.time()) - 86400

def page(wallet, before=None):
    u = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions/?api-key={HELIUS_KEY}&type=SWAP&limit=100"
    if before: u += f"&before={before}"
    try:
        out = subprocess.run(["curl","-sS","--max-time","25",u],capture_output=True,text=True,timeout=30).stdout
        d = json.loads(out)
        return d if isinstance(d, list) else []
    except Exception:
        return []

def pyth_usd_24h(wallet):
    tot_tokens = 0.0; n_sw = 0; before = None
    for _ in range(15):                    # cap pages
        batch = page(wallet, before); time.sleep(0.5)
        if not batch: break
        stop = False
        for t in batch:
            if (t.get("timestamp") or 0) < CUTOFF: stop = True; break
            legs = [tt for tt in t.get("tokenTransfers", []) if tt.get("mint") == MINT
                    and (tt.get("fromUserAccount") == wallet or tt.get("toUserAccount") == wallet)]
            if legs:
                n_sw += 1
                tot_tokens += sum(abs(float(l.get("tokenAmount") or 0)) for l in legs)
        before = batch[-1].get("signature")
        if stop or len(batch) < 100: break
    return tot_tokens * PRICE, n_sw

ds = json.loads(subprocess.run(["curl","-sS","--max-time","15",
    "https://api.dexscreener.com/latest/dex/pairs/solana/8erNF5u3CHrqZJXtkfY8CjSxFYF1yqHmN8uDbAhk6tWM"],
    capture_output=True,text=True).stdout or "{}")
pool_daily = float(((ds.get("pairs") or [{}])[0].get("volume") or {}).get("h24") or 0)

fleet_usd = 0.0; rows = []
for w in FLEET:
    usd, nsw = pyth_usd_24h(w); fleet_usd += usd; rows.append([w, round(usd), nsw])
    print(f"  {w} PYTH-swaps24h={nsw} vol=${usd:,.0f}")
share = fleet_usd / pool_daily if pool_daily else None
out = {"pool_daily_usd": round(pool_daily), "fleet_pyth_usd_24h": round(fleet_usd),
       "fleet_share_24h": round(share, 3) if share is not None else None, "wallets": rows}
json.dump(out, open(os.path.join(DATA, "pyth_onchain.json"), "w"), indent=1)
print(f"\nPYTH fleet on-chain 24h PYTH volume: ${fleet_usd:,.0f} vs pool daily ${pool_daily:,.0f} -> share {share if share is None else round(share,3)}")
print("wrote data/pyth_onchain.json")
