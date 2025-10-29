import hashlib, json, time, random, csv
from datetime import datetime

# Coba import ecdsa untuk tanda tangan digital
try:
    import ecdsa
    USE_ECDSA = True
except ImportError:
    USE_ECDSA = False


# ======================================================
# WALLET
# ======================================================
class Wallet:
    def __init__(self):
        if USE_ECDSA:
            sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
            vk = sk.get_verifying_key()
            self.private_key = sk.to_string().hex()
            self.public_key = vk.to_string().hex()
            self.address = hashlib.sha256(vk.to_string()).hexdigest()[:34]
        else:
            # Fallback sederhana jika ecdsa belum diinstall
            self.private_key = hashlib.sha256(str(random.random()).encode()).hexdigest()
            self.public_key = hashlib.sha256(self.private_key.encode()).hexdigest()
            self.address = "sim" + self.public_key[:32]

    def sign(self, message):
        if USE_ECDSA:
            sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
            return sk.sign(message.encode()).hex()
        else:
            return hashlib.sha256((message + self.private_key).encode()).hexdigest()


# ======================================================
# BLOCKCHAIN
# ======================================================
class Blockchain:
    def __init__(self, difficulty=3):
        self.chain = []
        self.utxos = {}       # UTXO set
        self.difficulty = difficulty
        self.mempool = []

    def genesis(self, wallet, amount=1.5):
        txid = "genesis" + str(len(self.chain) + 1)
        self.utxos[(txid, 0)] = {
            "txid": txid,
            "vout": 0,
            "address": wallet.address,
            "amount": amount
        }

    def add_tx(self, tx):
        if self.verify_tx(tx):
            self.mempool.append(tx)
            return True
        return False

    def verify_tx(self, tx):
        total_in, total_out = 0, 0

        for i in tx["inputs"]:
            key = (i["txid"], i["vout"])
            if key not in self.utxos:
                return False  # input tidak valid (double spend / tidak ada)
            total_in += self.utxos[key]["amount"]

        for o in tx["outputs"]:
            total_out += o["amount"]

        return total_in >= total_out

    def mine_block(self, miner_wallet):
        block = {
            "timestamp": datetime.utcnow().isoformat(),
            "tx": self.mempool.copy(),
            "miner": miner_wallet.address,
            "nonce": 0
        }

        block_json = json.dumps(block, sort_keys=True)

        # Proof of Work sederhana
        while True:
            hash_try = hashlib.sha256((block_json + str(block["nonce"])).encode()).hexdigest()
            if hash_try.startswith("0" * self.difficulty):
                block["hash"] = hash_try
                break
            block["nonce"] += 1

        # Terapkan semua transaksi
        for tx in self.mempool:
            self.apply_tx(tx)

        self.mempool = []
        self.chain.append(block)

        print(f"Mined block #{len(self.chain)} | Hash: {block['hash'][:18]}... | TX: {len(block['tx'])}")

    def apply_tx(self, tx):
        for i in tx["inputs"]:
            key = (i["txid"], i["vout"])
            if key in self.utxos:
                del self.utxos[key]
        for idx, o in enumerate(tx["outputs"]):
            self.utxos[(tx["txid"], idx)] = {
                "txid": tx["txid"],
                "vout": idx,
                "address": o["address"],
                "amount": o["amount"]
            }

    def export_data(self):
        with open("chain.json", "w") as f:
            json.dump(self.chain, f, indent=2)

        with open("utxos.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["txid", "vout", "address", "amount"])
            for (txid, vout), utxo in self.utxos.items():
                writer.writerow([txid, vout, utxo["address"], utxo["amount"]])

        print("✅ Data saved: chain.json & utxos.csv")


# ======================================================
# FUNGSI BANTU BUAT TRANSAKSI
# ======================================================
def create_tx(wallet, blockchain, recipients):
    inputs, total_in = [], 0
    for key, utxo in list(blockchain.utxos.items()):
        if utxo["address"] == wallet.address:
            inputs.append({"txid": utxo["txid"], "vout": utxo["vout"]})
            total_in += utxo["amount"]
            if total_in >= sum(a for _, a in recipients):
                break

    if total_in == 0:
        return None

    tx = {"inputs": inputs, "outputs": [], "timestamp": time.time()}

    for addr, amt in recipients:
        tx["outputs"].append({"address": addr, "amount": amt})

    total_out = sum(a for _, a in recipients)
    change = round(total_in - total_out - 0.0001, 4)
    if change > 0:
        tx["outputs"].append({"address": wallet.address, "amount": change})

    tx["txid"] = hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest()
    tx["signature"] = wallet.sign(tx["txid"])
    return tx


# ======================================================
# SIMULASI
# ======================================================
if __name__ == "__main__":
    print("=== Blockchain Simulation ===\n")

    alice, bob, carol, miner = Wallet(), Wallet(), Wallet(), Wallet()
    chain = Blockchain(difficulty=3)
    chain.genesis(alice, 1.5)

    print("Initial balances:")
    for w in [alice, bob, carol]:
        bal = sum(u["amount"] for u in chain.utxos.values() if u["address"] == w.address)
        print(f"{w.address[:8]}...: {bal} BTC")

    # TX1: Alice → Bob 0.3
    tx1 = create_tx(alice, chain, [(bob.address, 0.3)])
    chain.add_tx(tx1)
    chain.mine_block(miner)

    # TX2: Alice → Bob 0.4, Carol 0.2
    tx2 = create_tx(alice, chain, [(bob.address, 0.4), (carol.address, 0.2)])
    chain.add_tx(tx2)
    chain.mine_block(miner)

    # TX3: Double spend (harus gagal)
    tx3 = create_tx(alice, chain, [(bob.address, 1.0)])
    if not chain.add_tx(tx3):
        print("❌ Double-spend attempt detected.")

    chain.export_data()

    print("\nFinal Balances:")
    for w in [alice, bob, carol]:
        bal = sum(u["amount"] for u in chain.utxos.values() if u["address"] == w.address)
        print(f"{w.address[:8]}...: {bal} BTC")
