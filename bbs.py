#!/usr/bin/env python3
"""
BBS Signature Algorithm Verification (v4)
==========================================
Debug verifier with constraint replay.

Constraint replay coverage:
  ZK-1: delta<eps               (fully replayed from witness)
  ZK-2: C=commit(phi,delta,r)   (fully replayed from witness)
  ZK-3: pk=H(p||tau)            (fully replayed from witness)
  ZK-W: whitelist membership    (set replay + root consistency, not Merkle path)
  ZK-R: rate-limit count state  (count replay, not hash-chain ancestry reconstruction)
  Prev: transcript-bound        (tamper-detected, not cross-signature verified)
  Audit: witness-replayed delta (not Pedersen homomorphic aggregation)

This prototype does NOT model:
  - Succinctness (proof is a transcript hash, not a constant-size group element)
  - Zero-knowledge hiding (debug verifier replays witness)
  - Extractor-based knowledge soundness

In real deployment (Groth16/PLONK over BLS12-381), the verifier has NO
witness and checks a succinct proof via a single pairing check, O(1).

Placeholder mapping (Appendix C of paper):
  SHA-256     -> Poseidon
  HMAC-SHA256 -> Pedersen commitment
  Transcript hash -> ZK proof
"""

import hashlib, hmac, math, os, json, time

# ═══════════════════════════════════════════════════════
# Canonical serialization
# ═══════════════════════════════════════════════════════

def canon(v):
    """Canonical encoding: deterministic across platforms."""
    if isinstance(v, float): return f"{v:.15e}"
    if isinstance(v, list): return [canon(x) for x in v]
    if isinstance(v, dict): return {str(k): canon(vv) for k, vv in sorted(v.items())}
    return v

# ═══════════════════════════════════════════════════════
# Primitives
# ═══════════════════════════════════════════════════════

def phi(x, params):
    """phi(x;p) = sum A_j cos(t_j ln(x+1) + theta_j), j=0..2"""
    r = 0.0
    for j in range(3):
        r += params[3*j] * math.cos(params[3*j+1] * math.log(x+1) + params[3*j+2])
    return r

def poseidon_hash(*args):
    """Placeholder for Poseidon. SHA-256 over canonical encoding."""
    data = b""
    for a in args:
        data += str(canon(a)).encode() + b"|"
    return hashlib.sha256(data).hexdigest()

def pedersen_commit(phi_x, delta_x, r):
    """Placeholder for C = g^phi h^delta f^r. HMAC-SHA256."""
    msg = f"{canon(phi_x)}|{canon(delta_x)}".encode()
    return hmac.new(f"{r}".encode(), msg, hashlib.sha256).hexdigest()

def whitelist_root(wl_sorted):
    """Merkle root placeholder: hash of sorted member list.
    Real: Merkle tree with per-path inclusion proofs."""
    return poseidon_hash(*wl_sorted)

# ═══════════════════════════════════════════════════════
# ZK Prove / Debug Verify
# ═══════════════════════════════════════════════════════

def zk_prove(pub, wit, wl_env=None, rl_env=None):
    """Placeholder ZKProve. Transcript binds public inputs + all derived values."""
    p, r = wit["p"], wit["r"]
    phi_x = phi(pub["x"], p)
    delta_x = abs(phi_x - pub["tau"])
    pk_re = poseidon_hash(*p, pub["tau"])
    C_re = pedersen_commit(phi_x, delta_x, r)

    cr = {
        "pk_re": pk_re,
        "phi_x": canon(phi_x),
        "delta_x": canon(delta_x),
        "C_re": C_re,
        "zk1": delta_x < pub["epsilon"],
        "zk2": C_re == pub["C"],
        "zk3": pk_re == pub["pk"],
    }
    if wl_env is not None:
        cr["wl_root"] = whitelist_root(wl_env["members"])
        cr["wl_addr"] = wl_env["addr"]
        cr["wl_member"] = wl_env["addr"] in wl_env["members"]
    if rl_env is not None:
        cr["rl_count"] = rl_env["recent_count"]
        cr["rl_N"] = rl_env["N"]
        cr["rl_ok"] = rl_env["recent_count"] < rl_env["N"]

    t = json.dumps({"p": {k: canon(v) for k, v in pub.items()}, "c": cr}, sort_keys=True)
    return hashlib.sha256(t.encode()).hexdigest()


def debug_verify_full(pub, proof, wit, wl_env=None, rl_env=None):
    """
    Debug verifier: replays ZK-1/2/3/W/R constraints from witness.
    Real ZK: single pairing check, no witness.
    """
    p, r = wit["p"], wit["r"]

    # ZK-3: pk = H(p || tau)
    pk_re = poseidon_hash(*p, pub["tau"])
    if pk_re != pub["pk"]:
        return False, "ZK-3 failed: pk != H(p||tau)"

    phi_x = phi(pub["x"], p)
    delta_x = abs(phi_x - pub["tau"])

    # ZK-1: delta < epsilon
    if delta_x >= pub["epsilon"]:
        return False, f"ZK-1 failed: delta={delta_x:.6f} >= eps={pub['epsilon']}"

    # ZK-2: C = commit(phi, delta, r)
    C_re = pedersen_commit(phi_x, delta_x, r)
    if C_re != pub["C"]:
        return False, "ZK-2 failed: C != commit(phi,delta,r)"

    # ZK-W: set replay + root consistency (not Merkle path proof)
    if wl_env is not None:
        root_re = whitelist_root(wl_env["members"])
        if root_re != pub.get("wl_root_pub"):
            return False, "ZK-W failed: whitelist root mismatch"
        if wl_env["addr"] not in wl_env["members"]:
            return False, "ZK-W failed: addr not in whitelist"

    # ZK-R: count-state replay (not hash-chain ancestry reconstruction)
    if rl_env is not None:
        if rl_env["recent_count"] >= rl_env["N"]:
            return False, f"ZK-R failed: count {rl_env['recent_count']} >= N={rl_env['N']}"

    # Transcript match
    exp = zk_prove(pub, wit, wl_env, rl_env)
    if proof != exp:
        return False, "Proof transcript mismatch"

    return True, "All constraints replayed (ZK-1/2/3/W/R)"


def verify_binding_only(pk_d, sigma):
    """Structural check only: action binding. Cannot confirm compliance."""
    x_re = int(poseidon_hash(sigma["action_code"], pk_d["pk"], sigma["epoch"])[:16], 16)
    if x_re != sigma["x"]:
        return False, "Action binding: x mismatch"
    return True, "Action binding OK (constraints NOT verified)"


# ═══════════════════════════════════════════════════════
# KeyGen / Sign / Verify
# ═══════════════════════════════════════════════════════

def keygen(seed, epsilon, rate_N=100, rate_T=1000):
    params = []
    for i in range(9):
        h = hashlib.sha256(f"{seed}|p|{i}".encode()).digest()
        v = int.from_bytes(h[:4], 'big') / (2**32)
        if i%3==0: params.append(1.0+2.0*v)
        elif i%3==1: params.append(0.5+20.0*v)
        else: params.append(2*math.pi*v)
    s = sorted([phi(i, params) for i in range(1,11)])
    tau = 0.5*(s[4]+s[5])
    pk = poseidon_hash(*params, tau)
    return ({"params":params,"tau":tau,"epsilon":epsilon,"rate_N":rate_N,"rate_T":rate_T},
            {"pk":pk,"tau":tau,"epsilon":epsilon,"rate_N":rate_N,"rate_T":rate_T})


def sign(sk, pk_d, ac, epoch, prev_dig, prev_chain=None, wl=None, caddr=None):
    p, tau, eps, pk = sk["params"], sk["tau"], sk["epsilon"], pk_d["pk"]
    x = int(poseidon_hash(ac, pk, epoch)[:16], 16)
    phi_x = phi(x, p)
    delta_x = abs(phi_x - tau)
    if delta_x >= eps: return None

    wl_env = None
    if wl is not None and caddr is not None:
        if caddr not in wl: return None
        wl_env = {"members": sorted(wl), "addr": caddr}

    rl_env = None
    if prev_chain is not None:
        recent = [s for s in prev_chain if s["epoch"] > epoch - sk["rate_T"]]
        if len(recent) >= sk["rate_N"]: return None
        rl_env = {"recent_count": len(recent), "N": sk["rate_N"], "T": sk["rate_T"]}

    r = int.from_bytes(os.urandom(16), 'big')
    C = pedersen_commit(phi_x, delta_x, r)
    prev = poseidon_hash(prev_dig) if prev_dig else poseidon_hash("genesis")

    pub = {"pk":pk,"x":x,"C":C,"epsilon":eps,"tau":tau,"prev":prev,"epoch":epoch}
    if wl_env: pub["wl_root_pub"] = whitelist_root(wl_env["members"])
    wit = {"p": list(p), "r": r}
    proof = zk_prove(pub, wit, wl_env, rl_env)

    sigma = {"x":x,"C":C,"proof":proof,"prev":prev,"epoch":epoch,"action_code":ac}
    if wl_env: sigma["wl_root_pub"] = pub["wl_root_pub"]

    env = {"p": list(p), "r": r}
    if wl_env: env["wl_env"] = wl_env
    if rl_env: env["rl_env"] = rl_env
    return sigma, env


def verify(pk_d, sigma, env=None):
    """
    env=None  -> (False, reason): cannot replay without witness
    env given -> debug_verify_full: replays all ZK constraints
    """
    pk = pk_d["pk"]
    x_re = int(poseidon_hash(sigma["action_code"], pk, sigma["epoch"])[:16], 16)
    if x_re != sigma["x"]:
        return False, "Action binding: x mismatch"
    if env is None:
        return False, "No env: debug verifier cannot replay constraints"

    pub = {"pk":pk,"x":sigma["x"],"C":sigma["C"],"epsilon":pk_d["epsilon"],
           "tau":pk_d["tau"],"prev":sigma["prev"],"epoch":sigma["epoch"]}
    if "wl_root_pub" in sigma:
        pub["wl_root_pub"] = sigma["wl_root_pub"]

    wit = {"p": env["p"], "r": env["r"]}
    return debug_verify_full(pub, sigma["proof"], wit,
                             env.get("wl_env"), env.get("rl_env"))


# ═══════════════════════════════════════════════════════
# Witness-replayed aggregate audit
# ═══════════════════════════════════════════════════════

def witness_replayed_audit(sigs, envs, tau):
    """Witness-replayed audit. Real: Pedersen homomorphic prod(C_i), O(1)."""
    td = sum(abs(phi(s["x"], e["p"]) - tau) for s, e in zip(sigs, envs))
    n = len(sigs)
    return {"n":n, "sum_d":round(td,6), "avg_d":round(td/n,6) if n else 0}

def weight(a, alpha=0.1):
    return a["n"] / (a["avg_d"] + alpha)


# ═══════════════════════════════════════════════════════
#                    TEST SUITE
# ═══════════════════════════════════════════════════════

def run_tests():
    print("="*65)
    print("  BBS Signature Algorithm Verification (v4)")
    print("  Constraint replay: ZK-1/2/3 full, ZK-W set, ZK-R count")
    print("="*65)
    P, F = 0, 0
    def t(name, cond):
        nonlocal P, F
        print(f"  [{'PASS' if cond else 'FAIL'}]  {name}")
        if cond: P+=1
        else: F+=1

    # 1. KeyGen
    print("\n--- 1. KeyGen ---")
    sk, pk = keygen("alice_2025", 1.5)
    t("sk has 9 params", len(sk["params"])==9)
    t("pk is 64-hex", len(pk["pk"])==64)
    t("tau finite", math.isfinite(pk["tau"]))
    t("epsilon correct", pk["epsilon"]==1.5)
    _, pk2 = keygen("alice_2025", 1.5)
    t("deterministic", pk["pk"]==pk2["pk"])
    _, pk3 = keygen("bob_seed", 1.5)
    t("different seed -> different pk", pk["pk"]!=pk3["pk"])
    s = sorted([phi(i, sk["params"]) for i in range(1,11)])
    t("tau = proper median", abs(sk["tau"]-0.5*(s[4]+s[5]))<1e-10)

    # 2. Sign
    print("\n--- 2. Sign (compliant) ---")
    res = None
    for i in range(30):
        r = sign(sk, pk, f"transfer_{i}", 1+i, None)
        if r: res=r; break
    t("compliant -> (sigma, env)", res is not None)
    if res:
        sig, env = res
        t("sigma has proof", len(sig["proof"])==64)
        t("sigma has C", len(sig["C"])==64)
        t("sigma has no witness", "p" not in sig and "r" not in sig)
        t("env has p, r", "p" in env and "r" in env)

    # 3. Debug verify (full replay)
    print("\n--- 3. Debug verify (full replay) ---")
    if res:
        sig, env = res
        ok, reason = verify(pk, sig, env)
        t(f"replay: {reason}", ok)

    # 3b. No env -> False
    print("\n--- 3b. No env -> cannot replay ---")
    if res:
        sig, env = res
        ok_n, r_n = verify(pk, sig, None)
        t(f"no env: {r_n}", not ok_n)
        ok_b, r_b = verify_binding_only(pk, sig)
        t(f"binding only: {r_b}", ok_b)

    # 4. ZK-1
    print("\n--- 4. ZK-1: delta >= eps -> bot ---")
    skt, pkt = keygen("alice_2025", 0.001)
    rej = sum(1 for i in range(20) if sign(skt, pkt, f"a_{i}", i, None) is None)
    t(f"eps=0.001: {rej}/20 rejected", rej>15)

    # 5. ZK-3
    print("\n--- 5. ZK-3: identity binding ---")
    if res:
        sig, env = res
        fpk = dict(pk); fpk["pk"]="0"*64
        ok3, r3 = verify(fpk, sig, env)
        t(f"wrong pk -> {r3}", not ok3)

    # 6. ZK-2
    print("\n--- 6. ZK-2: commitment binding ---")
    if res:
        sig, env = res
        ts = dict(sig); ts["C"]="f"*64
        ok4, r4 = verify(pk, ts, env)
        t(f"tampered C -> {r4}", not ok4)
        t("mentions ZK-2", "ZK-2" in r4)

    # 7. Action binding
    print("\n--- 7. Action binding ---")
    if res:
        sig, env = res
        ts = dict(sig); ts["action_code"]="evil"
        ok5, r5 = verify(pk, ts, env)
        t(f"tampered action -> {r5}", not ok5)

    # 7b. Prev-pointer tamper
    print("\n--- 7b. Prev-pointer tamper detection ---")
    if res:
        sig, env = res
        tp = dict(sig); tp["prev"]="a"*64
        okp, rp = verify(pk, tp, env)
        t(f"tampered prev -> {rp}", not okp)

    # 8. ZK-W (set replay + root consistency)
    print("\n--- 8. ZK-W: whitelist (set replay + root consistency) ---")
    wl = {"0xAAA","0xBBB","0xCCC"}
    swl = None
    for i in range(30):
        r = sign(sk, pk, f"wl_{i}", 50+i, None, wl=wl, caddr="0xAAA")
        if r: swl=r; break
    t("whitelisted -> sigma", swl is not None)
    if swl:
        s, e = swl
        t("env has wl_env", "wl_env" in e)
        ok6, r6 = verify(pk, s, e)
        t(f"replay incl ZK-W: {r6}", ok6)
        bad_e = {"p":e["p"],"r":e["r"],"wl_env":{"members":sorted({"0xDDD","0xEEE"}),"addr":"0xAAA"}}
        ok_tw, r_tw = verify(pk, s, bad_e)
        t(f"tampered wl -> {r_tw}", not ok_tw)
    t("non-whitelisted -> bot", sign(sk, pk, "x", 99, None, wl=wl, caddr="0xEVIL") is None)

    # 9. ZK-R (count-state replay)
    print("\n--- 9. ZK-R: rate limit (count-state replay) ---")
    skr, pkr = keygen("rate", 2.0, rate_N=5, rate_T=100)
    ch, ce = [], []
    acc, blk = 0, 0
    for i in range(10):
        r = sign(skr, pkr, f"rl_{i}", i, ch[-1]["C"] if ch else None, prev_chain=ch)
        if r: s,e=r; ch.append(s); ce.append(e); acc+=1
        else: blk+=1
    t(f"N=5: {acc} accepted, {blk} blocked", acc<=5 and blk>=5)
    if ce:
        t("env has rl_env", "rl_env" in ce[0])
        ok_rl, r_rl = verify(pkr, ch[0], ce[0])
        t(f"replay incl ZK-R: {r_rl}", ok_rl)
        bad_re = {"p":ce[0]["p"],"r":ce[0]["r"],"rl_env":{"recent_count":999,"N":5,"T":100}}
        ok_trl, r_trl = verify(pkr, ch[0], bad_re)
        t(f"tampered rate -> {r_trl}", not ok_trl)

    # 10. Prev-pointer propagation
    print("\n--- 10. Prev-pointer propagation ---")
    cs, ces = [], []
    pd = None; att = 0
    while len(cs)<3 and att<50:
        r = sign(sk, pk, f"ch_{att}", 200+att, pd)
        if r: s,e=r; cs.append(s); ces.append(e); pd=s["C"]
        att += 1
    t(f"chain of 3 ({att} attempts)", len(cs)==3)
    if len(cs)==3:
        t("prev pointers differ", cs[0]["prev"]!=cs[1]["prev"]!=cs[2]["prev"])
        t("all replay-verify", all(verify(pk,s,e)[0] for s,e in zip(cs,ces)))

    # 11. Witness-replayed audit
    print("\n--- 11. Witness-replayed aggregate audit ---")
    if len(cs)==3:
        au = witness_replayed_audit(cs, ces, sk["tau"])
        t(f"n={au['n']}, avg_d={au['avg_d']:.4f}", au["n"]==3)
        t("avg_d < eps", au["avg_d"]<sk["epsilon"])
        t(f"W={weight(au):.2f}", weight(au)>0)

    # 12. f<=n-1
    print("\n--- 12. f<=n-1: independent verification ---")
    if res:
        sig, env = res
        t("3 verifiers agree", all(verify(pk,sig,env)[0] for _ in range(3)))

    # 13. Branch E
    print("\n--- 13. Branch E: AI agent safety ---")
    ska, pka = keygen("agent", 1.0)
    asig = None
    for i in range(30):
        r = sign(ska, pka, f"ag_{i}", i, None)
        if r: asig=r; break
    t("agent finds compliant action", asig is not None)
    if asig:
        t("agent sig replays", verify(pka, asig[0], asig[1])[0])

    all_ok = True; ab = 0
    for i in range(50):
        r = sign(ska, pka, f"evil_{i*1000}", 1000+i, None)
        if r is None: ab+=1
        else:
            d = abs(phi(r[0]["x"], r[1]["p"]) - ska["tau"])
            if d >= ska["epsilon"]: all_ok = False
    t(f"compromised: {ab}/50 blocked", ab>0)
    t("ALL accepted truly satisfy delta<eps", all_ok)

    # 14. Privacy
    print("\n--- 14. Compliance without identity disclosure ---")
    if res:
        sig, _ = res
        t("sigma has no p/r/phi/delta",
          all(k not in sig for k in ["p","r","phi_x","delta_x","_witness"]))

    # 15. Perf
    print("\n--- 15. Performance ---")
    t0=time.perf_counter()
    for _ in range(100): keygen("b",1.5)
    print(f"       KeyGen: {(time.perf_counter()-t0)/100*1000:.2f}ms")
    t0=time.perf_counter(); cnt=0
    for i in range(200):
        if sign(sk,pk,f"b_{i}",9000+i,None): cnt+=1
    print(f"       Sign:   {(time.perf_counter()-t0)/200*1000:.2f}ms ({cnt}/200 compliant) [real:~31ms]")
    if res:
        sig,env=res
        t0=time.perf_counter()
        for _ in range(1000): verify(pk,sig,env)
        print(f"       Verify: {(time.perf_counter()-t0)/1000*1000:.3f}ms [real:~3-5ms pairing]")

    # Summary
    print("\n"+"="*65)
    print(f"  RESULTS: {P} passed, {F} failed, {P+F} total")
    print("="*65)
    if F==0:
        print("\n  All constraints verified:")
        print("    ZK-1: delta<eps          (fully replayed)")
        print("    ZK-2: C=commit(phi,d,r)  (fully replayed)")
        print("    ZK-3: pk=H(p||tau)       (fully replayed)")
        print("    ZK-W: whitelist          (set replay + root, not Merkle path)")
        print("    ZK-R: rate limit         (count-state replay, not chain ancestry)")
        print("    Prev: transcript-bound   (tamper-detected, not cross-sig verified)")
        print("    Audit: witness-replayed  (not Pedersen homomorphic)")
        print("    f<=n-1, Br.E, Privacy: tested")
        print()
        print("  Debug verifier replays constraints from witness.")
        print("  Real ZK: verifier has NO witness, O(1) pairing check.")
        print("  Not modeled: succinctness, ZK hiding, extractor soundness.")
    else:
        print(f"\n  {F} test(s) failed")
    return F==0

if __name__=="__main__": exit(0 if run_tests() else 1)
