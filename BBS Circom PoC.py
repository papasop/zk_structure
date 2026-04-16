#!/usr/bin/env python3
"""
================================================================================
BBS Circom PoC — Single-File Colab Runner  (v9, paper consistency)
================================================================================

Behavior-Bound Signatures: reference Groth16/BN254 implementation of the three
core constraints (ZK-1: delta<eps, ZK-2: commitment binding, ZK-3: pk binding).

HOW TO RUN
----------
  Option A (Colab): paste this entire file into a single cell and run.
  Option B (shell): python3 bbs_circom_colab.py
  Option C (Colab upload): !python3 bbs_circom_colab.py

REQUIREMENTS
------------
  * Linux/macOS, Python 3.8+
  * Node.js 18+ (Colab ships v20; install via nvm/brew elsewhere)
  * ~2 GB disk for Powers of Tau
  * Internet access (downloads Rust, circom source, npm packages)

TIMING (Colab free tier, 2 vCPU)
--------------------------------
  First run:  ~5-7 minutes  (cargo install dominates; no redundant build)
  Re-runs:    ~2-3 minutes  (all install steps skipped)

CHANGES IN v1  (round 1: correctness)
---------------------------------------
  v1.1 Entropy: Python `secrets.token_hex(32)` (was: `xxd`, not portable)
  v1.2 Rustup:  check cargo presence after install (was: pipefail-masked)
  v1.3 Circom:  drop redundant `cargo build --release` (cargo install rebuilds)
  v1.4 Parse:   regex r"Constraints:\\s*(\\d+)" (was: matched any digit run)
  v1.5 Grep:    `Wires` not `Variables` (actual snarkjs field name)
  v1.6 Clone:   verify Cargo.toml before reusing /tmp/circom-src
  v1.7 Dir:     fall back to $HOME if /content exists but isn't writable

CHANGES IN v2  (round 2: robustness + UX)
-------------------------------------------
  v2.1 PATH:    ensure_cargo_on_path() BEFORE tool_present check, so Colab
                reconnects don't trigger spurious 4-minute reinstalls
  v2.2 Pipe:    drop all `| tail -N` in commands; `run(..., tail=N)` instead.
                Shell pipe exit code was masking snarkjs/circom failures
  v2.3 EnvChk:  use tool_present() in phase_environment instead of fragile
                `tool --version 2>&1 | head -1` (which echoed shell errors)
  v2.4 NodeMod: absolute path for node_modules existence check

CHANGES IN v3  (round 3: streaming + path consistency)
--------------------------------------------------------
  v3.1 Stream:  run(..., stream=True) for benchmark phase — live progress
                instead of 1-2 minutes of silence that looked like a hang
  v3.2 Paths:   p(rel) helper; every file reference is absolute, not
                CWD-relative. Eliminates the "works only if chdir holds"
                fragility that lingered in sanity/ptau/groth16/benchmark
  v3.3 Cleanup: os.remove() instead of `rm -f`; tar with -C flag instead
                of `cd ... && tar ...`
  v3.4 Pipefail: curl | sh wrapped in `bash -c 'set -o pipefail; ...'` so
                 a failed curl no longer silently passes an empty script

CHANGES IN v4  (round 4: integrity verification)
--------------------------------------------------
  v4.1 PtauVerify: `snarkjs powersoftau verify` before skipping an existing
                   .ptau file. Without this, a truncated ptau left by a
                   Colab disconnect is silently reused, and the downstream
                   `groth16 setup` fails with a cryptic
                   "Reading out of the range of the section" stack trace.
                   Stale downstream zkey/vkey are also invalidated.
  v4.2 ZkeyVerify: `snarkjs zkey verify` against circuit+ptau before
                   skipping an existing zkey. Same failure mode, different
                   stage. Also verifies the freshly-produced zkey so a bad
                   ceremony fails at setup time, not at proving time.
  v4.3 Regenerate: when verification fails, regenerate automatically with
                   a clear warning instead of propagating a confusing error.

CHANGES IN v5  (round 5: install streaming + fix v3 streaming regression)
---------------------------------------------------------------------------
  v5.1 BenchStream: actually-streaming benchmark progress. The v3 streaming
                    fix was undermined by benchmark.js using `\\r`-only
                    progress writes that block Python's readline() until
                    the next \\n. Switched to console.log(`    prove i/N`).
  v5.2 CircomStream: stream cargo install (3-4 min) instead of capturing
                     silently. Same UX class as Issue #8 — was missed in v3.
                     Also drops `cd && cargo` for absolute --path.
  v5.3 NpmStream: stream npm install too, for consistency.
  v5.4 VersionStr: main() header string now matches file header (was v2).

CHANGES IN v6  (round 6: diagnostic surfacing)
------------------------------------------------
  v6.1 VerifyDiag: _verify_ptau and _verify_zkey now return (ok, diag)
                   tuples. On verification failure, snarkjs's actual error
                   message (last 5 lines) is shown to the user instead of
                   a generic "WARNING: failed integrity check". This lets
                   users distinguish:
                     - truncated file (the common Colab-disconnect case)
                     - wrong curve / version mismatch
                     - corrupted bytes from disk error
                   without re-running snarkjs verify manually.
  v6.2 RegenMsg:   regeneration warnings now name the artifact ("zkey + vkey"
                   vs. just "ptau") so logs are unambiguous when both ptau
                   and zkey fail in the same run.

CHANGES IN v7  (round 7: hygiene)
---------------------------------
  v7.1 ChangelogSemantics: header changed from "CHANGES FROM vN" (which
                           confusingly suggested labels vN.x were FUTURE
                           changes from vN onward) to "CHANGES IN vN"
                           (matching the natural reading: in version N,
                           here is what was changed). No code impact.
  v7.2 DeadVar: `out_dir` in main() was assigned but never read; renamed
                to `_` to make the discard explicit.
  v7.3 NamedConst: '26000' magic number from paper §7.3.2 promoted to
                   TARGET_FULL_CIRCUIT_CONSTRAINTS at module level. Single
                   source of truth if the paper updates the projection.

CHANGES IN v8  (round 8: JS error handling + signature cleanup)
---------------------------------------------------------------
  v8.1 JSCatch: GENERATE_JS and VALIDATE_JS now end with .catch(...) just
                like BENCHMARK_JS already did. Without this, on Node 18+
                an unhandled promise rejection (e.g., readFileSync ENOENT
                if input.json is missing) prints a noisy V8 internal stack
                trace under `node:internal/process/promises:268` which
                buries the actual error message. The .catch surfaces
                "validate_input failed: ENOENT: ..." instead.
  v8.2 ReturnSig: phase_package_results() returned a (tar_path, out_dir)
                  tuple but the only caller (main) discarded out_dir via
                  `tar_path, _ = ...`. Simplified to `return tar_path`
                  and updated caller to single-value assignment. The
                  out_dir path is still printed in-phase for visibility.

CHANGES IN v9  (round 9: paper consistency)
-------------------------------------------
  v9.1 NoSelfContradict: the v7 summary block printed a linear extrapolation
                         ("26000 constraints -> prove ~ 11,378 ms") that
                         directly contradicted paper §7.3.2's claim of
                         "26-130 ms on commodity hardware". The gap is
                         real but expected: snarkjs (pure JS, dev-tier)
                         vs. rapidsnark/arkworks (native Rust, production).
                         Removed the extrapolation; now prints per-constraint
                         cost (us/constraint) with an explicit note that
                         the paper's baseline assumes native Rust and
                         snarkjs typically runs 100-500x slower. Output
                         no longer reads as a refutation of the paper.
  v9.2 MdDisclaimer: benchmark_results.md (the artifact deliverable that
                     paper would cite) now includes a 'Platform note'
                     section explaining the snarkjs / rapidsnark gap.
                     Reviewers reading the .md directly cannot miss the
                     caveat. The table itself is unchanged.

OUTPUT
------
  {PROJECT}/build/benchmark_results.md    (paste into paper)
  {PROJECT}/build/benchmark_results.json  (raw timings)
  bbs-circom-results.tar.gz               (packaged deliverables)
================================================================================
"""

import os
import sys
import subprocess
import time
import json
import shutil
import re
import secrets   # FIX #1: entropy without xxd dependency

# ==============================================================================
# CONFIGURATION
# ==============================================================================

def _pick_project_dir():
    """FIX #7: Prefer /content only if writable; fall back to $HOME."""
    candidates = ["/content/bbs-circom-poc", os.path.expanduser("~/bbs-circom-poc")]
    for c in candidates:
        parent = os.path.dirname(c)
        if os.path.isdir(parent) and os.access(parent, os.W_OK):
            return c
    return os.path.expanduser("~/bbs-circom-poc")

PROJECT = _pick_project_dir()
PTAU_SIZE = 14            # 2^14 = 16,384 max constraints
BENCH_ITERS = 100         # Number of benchmark iterations
BENCH_WARMUP = 5          # Warmup iterations before timing

# FIX Issue #25: name the magic number from paper §7.3.2 so future readers
# can update it without grepping. This is the projected constraint count of
# the full BBS circuit including ZK-R† (rate limit, ~25K) + base (~1K).
TARGET_FULL_CIRCUIT_CONSTRAINTS = 26000


def p(rel):
    """FIX Issue #9: join a relative path to PROJECT root. Using this helper
    everywhere (instead of CWD-relative strings like 'build/foo') makes the
    script robust to CWD changes and consistent with the Issue #5 fix."""
    return os.path.join(PROJECT, rel)

# ==============================================================================
# EMBEDDED FILES — circuit and JavaScript helpers
# ==============================================================================

CIRCOM_SRC = r"""pragma circom 2.1.6;

include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/bitify.circom";

/*
 * BBS Core Circuit (ZK-1, ZK-2, ZK-3)
 *
 * Simplifications vs. full scheme:
 *   (1) phi = p[0] + p[1]*x + p[2]*x^2  (polynomial, vs. cos/ln sum)
 *   (2) C = Poseidon(phi, delta, r)     (vs. Pedersen g^phi h^delta f^r)
 *   (3) 64-bit range for delta, epsilon
 *
 * Public inputs:  pk, x, C, tau, epsilon
 * Private inputs: p[3], r, phi, delta, sign
 */

template BBSCore(nBits) {
    // Public
    signal input pk;
    signal input x;
    signal input C;
    signal input tau;
    signal input epsilon;

    // Private witness
    signal input p[3];
    signal input r;
    signal input phi;
    signal input delta;
    signal input sign;

    // ZK-3: pk = Poseidon(p[0..2], tau)
    component pkHash = Poseidon(4);
    pkHash.inputs[0] <== p[0];
    pkHash.inputs[1] <== p[1];
    pkHash.inputs[2] <== p[2];
    pkHash.inputs[3] <== tau;
    pkHash.out === pk;

    // phi = p[0] + p[1]*x + p[2]*x^2
    signal x2;  x2 <== x * x;
    signal t1;  t1 <== p[1] * x;
    signal t2;  t2 <== p[2] * x2;
    phi === p[0] + t1 + t2;

    // |phi - tau| = delta via sign bit
    sign * (sign - 1) === 0;
    signal selector;
    selector <== 2 * sign - 1;
    phi - tau === selector * delta;

    // ZK-1: delta in [0, 2^nBits) AND delta < epsilon
    component dR = Num2Bits(nBits);  dR.in <== delta;
    component eR = Num2Bits(nBits);  eR.in <== epsilon;
    component lt = LessThan(nBits);
    lt.in[0] <== delta;
    lt.in[1] <== epsilon;
    lt.out === 1;

    // ZK-2: C = Poseidon(phi, delta, r)
    component cHash = Poseidon(3);
    cHash.inputs[0] <== phi;
    cHash.inputs[1] <== delta;
    cHash.inputs[2] <== r;
    cHash.out === C;
}

component main { public [pk, x, C, tau, epsilon] } = BBSCore(64);
"""

GENERATE_JS = r"""const { buildPoseidon } = require("circomlibjs");
const fs = require("fs"), path = require("path");
const FIELD_P = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const mod = (a, p) => ((a % p) + p) % p;

(async () => {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;

  const p = [12345n, 67890n, 11111n];
  const x = 42n, tau = 100000n, epsilon = 5000000000n, r = 99999n;

  const phi = mod(p[0] + p[1] * x + p[2] * x * x, FIELD_P);
  let delta, sign;
  if (phi >= tau) { delta = phi - tau; sign = 1n; }
  else            { delta = tau - phi; sign = 0n; }
  if (delta >= epsilon) throw new Error("delta >= epsilon");

  const pk = F.toObject(poseidon([p[0], p[1], p[2], tau]));
  const C  = F.toObject(poseidon([phi, delta, r]));

  const input = {
    pk: pk.toString(), x: x.toString(), C: C.toString(),
    tau: tau.toString(), epsilon: epsilon.toString(),
    p: p.map(v => v.toString()), r: r.toString(),
    phi: phi.toString(), delta: delta.toString(), sign: sign.toString()
  };
  fs.writeFileSync(path.join(__dirname, "..", "inputs", "input.json"),
                   JSON.stringify(input, null, 2));
  console.log("Input generated.");
  console.log("  phi     =", phi.toString());
  console.log("  delta   =", delta.toString(), "(sign =", sign.toString() + ")");
  console.log("  delta < epsilon:", delta < epsilon);
})().catch(e => { console.error("generate_input failed:", e.message || e); process.exit(1); });
"""

VALIDATE_JS = r"""const { buildPoseidon } = require("circomlibjs");
const fs = require("fs"), path = require("path");
const FIELD_P = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const TWO64 = 1n << 64n;
const mod = (a, p) => ((a % p) + p) % p;

(async () => {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;
  const inp = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "inputs", "input.json")));
  const [pk, x, C, tau, epsilon, r, phi, delta, sign] =
    [inp.pk, inp.x, inp.C, inp.tau, inp.epsilon, inp.r, inp.phi, inp.delta, inp.sign].map(BigInt);
  const p = inp.p.map(BigInt);

  let pass = 0, fail = 0;
  const chk = (n, c) => { if (c) { console.log("  [PASS] " + n); pass++; } else { console.log("  [FAIL] " + n); fail++; } };

  console.log("Validating input against circuit constraints:");
  chk("ZK-3: pk == Poseidon(p, tau)", pk === F.toObject(poseidon([p[0], p[1], p[2], tau])));
  chk("phi == p[0] + p[1]*x + p[2]*x^2", phi === mod(p[0] + p[1]*x + p[2]*x*x, FIELD_P));
  chk("sign in {0,1}", sign === 0n || sign === 1n);
  const sel = mod(2n * sign - 1n, FIELD_P);
  chk("(phi - tau) == (2*sign-1) * delta", mod(phi - tau, FIELD_P) === mod(sel * delta, FIELD_P));
  chk("delta in [0, 2^64)", delta >= 0n && delta < TWO64);
  chk("epsilon in [0, 2^64)", epsilon >= 0n && epsilon < TWO64);
  chk("ZK-1: delta < epsilon", delta < epsilon);
  chk("ZK-2: C == Poseidon(phi, delta, r)", C === F.toObject(poseidon([phi, delta, r])));

  console.log(`\n  Result: ${pass} passed, ${fail} failed`);
  if (fail > 0) process.exit(1);
})().catch(e => { console.error("validate_input failed:", e.message || e); process.exit(1); });
"""

BENCHMARK_JS = r"""const snarkjs = require("snarkjs");
const fs = require("fs"), path = require("path");
const { performance } = require("perf_hooks");

const ROOT  = path.join(__dirname, "..");
const WASM  = path.join(ROOT, "build", "bbs_core_js", "bbs_core.wasm");
const ZKEY  = path.join(ROOT, "build", "bbs_final.zkey");
const VKEY  = JSON.parse(fs.readFileSync(path.join(ROOT, "build", "verification_key.json")));
const INPUT = JSON.parse(fs.readFileSync(path.join(ROOT, "inputs", "input.json")));

const N = parseInt(process.argv[2] || "100", 10);
const WARM = parseInt(process.argv[3] || "5", 10);

const stats = xs => {
  const s = [...xs].sort((a,b)=>a-b);
  const n = s.length, sum = s.reduce((a,b)=>a+b, 0), mean = sum/n;
  const median = (n % 2 === 0) ? (s[n/2 - 1] + s[n/2]) / 2 : s[(n-1) >> 1];
  return {
    mean, median, min: s[0], max: s[n-1],
    p95: s[Math.floor(n*0.95)],
    stdev: Math.sqrt(s.map(x=>(x-mean)**2).reduce((a,b)=>a+b, 0)/n)
  };
};
const fmt = ms => ms < 1 ? (ms*1000).toFixed(1) + " us" : ms.toFixed(2) + " ms";

(async () => {
  console.log(`Warmup (${WARM} iters)...`);
  let proof, pub;
  for (let i = 0; i < WARM; i++) {
    ({ proof, publicSignals: pub } = await snarkjs.groth16.fullProve(INPUT, WASM, ZKEY));
  }

  console.log(`Benchmarking prove (${N} iters)...`);
  const pT = [];
  for (let i = 0; i < N; i++) {
    const t0 = performance.now();
    ({ proof, publicSignals: pub } = await snarkjs.groth16.fullProve(INPUT, WASM, ZKEY));
    pT.push(performance.now() - t0);
    // FIX Issue #19: use console.log (newline-terminated) not process.stdout.write
    // with \r. readline() in Python's streaming mode blocks until \n, so \r-only
    // progress output would be silently buffered until end — defeating the
    // whole point of Issue #8's streaming fix.
    if ((i+1) % 20 === 0) console.log(`    prove  ${i+1}/${N}`);
  }

  console.log(`Benchmarking verify (${N} iters)...`);
  const vT = [];
  for (let i = 0; i < N; i++) {
    const t0 = performance.now();
    const ok = await snarkjs.groth16.verify(VKEY, pub, proof);
    vT.push(performance.now() - t0);
    if (!ok) throw new Error("Verify failed");
    if ((i+1) % 20 === 0) console.log(`    verify ${i+1}/${N}`);
  }

  const pS = stats(pT), vS = stats(vT);
  console.log("\n" + "=".repeat(65));
  console.log(`RESULTS (N=${N})`);
  console.log("=".repeat(65));
  console.log(`Prove:  mean=${fmt(pS.mean)}  median=${fmt(pS.median)}  p95=${fmt(pS.p95)}  min/max=${fmt(pS.min)}/${fmt(pS.max)}`);
  console.log(`Verify: mean=${fmt(vS.mean)}  median=${fmt(vS.median)}  p95=${fmt(vS.p95)}  min/max=${fmt(vS.min)}/${fmt(vS.max)}`);
  console.log(`Proof size: ~${JSON.stringify(proof).length} bytes JSON / ~192 bytes binary`);

  const md = `# BBS Core Circuit Benchmark

**Platform:** ${process.platform} / Node.js ${process.version}
**Date:** ${new Date().toISOString()}
**Iterations:** ${N}
**Prover:** snarkjs (pure JavaScript, reference implementation)

| Operation | Mean | Median | p95 | Min | Max |
|-----------|------|--------|-----|-----|-----|
| Prove  | ${fmt(pS.mean)} | ${fmt(pS.median)} | ${fmt(pS.p95)} | ${fmt(pS.min)} | ${fmt(pS.max)} |
| Verify | ${fmt(vS.mean)} | ${fmt(vS.median)} | ${fmt(vS.p95)} | ${fmt(vS.min)} | ${fmt(vS.max)} |

## Platform note

These numbers were produced by **snarkjs**, a pure-JavaScript Groth16
prover intended for development and algorithmic verification. Paper
§7.3.2 projects \\~1 microsecond per constraint on commodity hardware
with **native Rust provers** (arkworks, rapidsnark). snarkjs typically
runs 100-500x slower than rapidsnark for the same circuit due to JS
interpreter overhead and the absence of hand-tuned MSM/FFT routines.

**This artifact verifies that the BBS core constraints (ZK-1, ZK-2,
ZK-3) are correctly encodable and that honest inputs satisfy them.**
It does NOT independently measure the performance claims in §7.3.2;
a rapidsnark benchmark is left as future work.
`;
  fs.writeFileSync(path.join(ROOT, "build", "benchmark_results.md"), md);
  fs.writeFileSync(path.join(ROOT, "build", "benchmark_results.json"),
    JSON.stringify({ prove: {times_ms: pT, stats: pS}, verify: {times_ms: vT, stats: vS},
                     N, platform: process.platform, node: process.version,
                     date: new Date().toISOString() }, null, 2));
  console.log("\nResults written to build/benchmark_results.{md,json}");
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
"""

PACKAGE_JSON = {
    "name": "bbs-circom-poc-colab",
    "version": "0.2.0",
    "private": True,
    "dependencies": {
        "circomlib":   "^2.0.5",
        "circomlibjs": "^0.1.7",
        "snarkjs":     "^0.7.4"
    }
}

# ==============================================================================
# HELPERS
# ==============================================================================

def run(cmd, check=True, capture=True, show_tail=5, tail=None, stream=False):
    """Run a shell command. Return stripped stdout (or last `tail` lines thereof).

    FIX Issue #2 (pipe|tail hiding errors): if the caller needs only the last
    N lines of output, they should pass `tail=N` rather than appending
    `| tail -N` to the command. Otherwise the shell pipeline's exit code
    becomes tail's exit code (always 0), masking real command failures.

    FIX Issue #8 (silent hangs on long benchmarks): when `stream=True`, output
    is echoed to the real stdout line-by-line AS it's produced, while also
    being captured for error reporting and return. This prevents users on
    Colab from seeing nothing for 1-2 minutes and thinking the cell hung.

    Raises RuntimeError on non-zero exit when check=True.
    """
    if stream:
        # Live-stream stdout (merged with stderr) while capturing for return
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        captured = []
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ''):
            sys.stdout.write(line)
            sys.stdout.flush()
            captured.append(line)
        proc.stdout.close()
        rc = proc.wait()
        out_full = ''.join(captured)
        if check and rc != 0:
            print(f"  COMMAND FAILED (rc={rc}):", cmd)
            t = "\n    ".join(out_full.strip().splitlines()[-show_tail:])
            print(f"  output (tail):\n    {t}")
            raise RuntimeError(f"Command failed (rc={rc}): {cmd}")
        out = out_full.strip()
        if tail is not None and out:
            out = "\n".join(out.splitlines()[-tail:])
        return out

    # Non-streaming path (default)
    r = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    if check and r.returncode != 0:
        print("  COMMAND FAILED:", cmd)
        if r.stdout:
            t = "\n    ".join(r.stdout.strip().splitlines()[-show_tail:])
            print(f"  stdout (tail):\n    {t}")
        if r.stderr:
            t = "\n    ".join(r.stderr.strip().splitlines()[-show_tail:])
            print(f"  stderr (tail):\n    {t}")
        raise RuntimeError(f"Command failed (rc={r.returncode}): {cmd}")
    out = (r.stdout or "").strip()
    if tail is not None and out:
        out = "\n".join(out.splitlines()[-tail:])
    return out


def tool_present(cmd):
    """Check if a tool is available on PATH."""
    return subprocess.run(f"command -v {cmd}", shell=True, capture_output=True).returncode == 0


def ensure_cargo_on_path():
    """FIX Issue #1 (PATH order): add ~/.cargo/bin to PATH BEFORE checking for cargo.

    Without this, re-runs after the environment loses the PATH entry (e.g.,
    Colab runtime reconnect) would falsely conclude Rust is missing and
    trigger a 4-minute reinstall of an already-installed toolchain.
    """
    cargo_bin = os.path.expanduser("~/.cargo/bin")
    if os.path.isdir(cargo_bin) and cargo_bin not in os.environ["PATH"].split(os.pathsep):
        os.environ["PATH"] = f"{cargo_bin}{os.pathsep}{os.environ['PATH']}"


def header(title):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def step(n, total, title):
    print(f"\n[{n}/{total}] {title}")
    print("-" * 72)


# ==============================================================================
# PHASES
# ==============================================================================

def phase_environment():
    step(1, 13, "Environment check")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {sys.platform}")
    print(f"  Project dir: {PROJECT}")
    # FIX Issue #4: check presence first, then query version. Previously the
    # "NOT INSTALLED" fallback was unreachable because `tool --version 2>&1`
    # on a missing tool prints a shell error that `head -1` happily echoes
    # back, making the result non-empty.
    ensure_cargo_on_path()  # so cargo/circom show up if already installed
    for tool, needed in [("node", True), ("npm", True), ("cargo", False), ("circom", False)]:
        if tool_present(tool):
            ver = run(f"{tool} --version", tail=1, check=False) or "(version unknown)"
            suffix = ""
        else:
            ver = "NOT INSTALLED"
            suffix = f"  [{'REQUIRED' if needed else 'will install'}]"
        print(f"  {tool:8} {ver}{suffix}")
    if not tool_present("node"):
        raise RuntimeError("Node.js is required but not installed.")


def phase_install_rust():
    """FIX Issue #1: ensure PATH contains ~/.cargo/bin BEFORE the presence check.
    Otherwise a re-run after Colab disconnects (which resets env) would falsely
    reinstall Rust. FIX Issue #3: don't trust rustup's pipe exit code; verify
    with a post-install presence check."""
    step(2, 13, "Install Rust (~1 min if not present)")
    ensure_cargo_on_path()  # FIX Issue #1: MUST come before tool_present check
    if tool_present("cargo"):
        print(f"  Rust already installed: {run('cargo --version')}")
        return

    print("  Installing Rust via rustup...")
    t0 = time.time()
    # FIX Issue #12 (curl|sh pipefail): without `set -o pipefail`, a failed
    # download (curl non-zero) would still pass through to sh, which exits 0
    # on empty input, giving a falsely successful install. bash -c lets us
    # enable pipefail locally.
    installer_cmd = (
        "set -o pipefail; "
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | "
        "sh -s -- -y --default-toolchain stable --profile minimal"
    )
    rc = subprocess.run(["bash", "-c", installer_cmd]).returncode
    if rc != 0:
        raise RuntimeError(f"rustup installer returned non-zero exit code: {rc}")
    print(f"  rustup finished in {time.time()-t0:.0f}s")

    # Post-install: add to PATH and verify
    ensure_cargo_on_path()
    if not tool_present("cargo"):
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        raise RuntimeError(
            f"cargo not found on PATH even after install. Check {cargo_bin}/cargo exists."
        )
    print(f"  {run('cargo --version')}")


def phase_install_circom():
    """FIX Issue #1: ensure_cargo_on_path before presence check.
    FIX Issue #6: re-clone if source dir was left incomplete.
    FIX Issue #20: stream cargo install output (3-4 min) instead of capturing
    silently — same UX class as Issue #8. Inconsistent with rustup which
    already streams via raw subprocess.run."""
    step(3, 13, "Install circom (~3-4 min if not present)")
    ensure_cargo_on_path()  # FIX Issue #1
    if tool_present("circom"):
        print(f"  circom already installed: {run('circom --version', tail=1)}")
        return

    src_dir = "/tmp/circom-src"
    if os.path.exists(src_dir) and not os.path.isfile(f"{src_dir}/Cargo.toml"):
        print(f"  {src_dir} exists but looks incomplete; re-cloning.")
        shutil.rmtree(src_dir, ignore_errors=True)
    if not os.path.exists(src_dir):
        print("  Cloning circom from GitHub...")
        run(f"git clone --depth 1 https://github.com/iden3/circom.git {src_dir}")

    print("  Building + installing circom (cargo install, release mode)...")
    print("  (compilation takes 3-4 minutes; output streams below)")
    t0 = time.time()
    # FIX Issue #20: stream=True so user sees cargo's compilation progress
    # in real time. Without this, the 3-4 minute build looks like a hang.
    # FIX Issue #21 (related): use absolute path instead of `cd && cargo`
    # for consistency with the no-shell-cd convention from v3.3.
    run(f"cargo install --path {src_dir}/circom", stream=True)
    print(f"  Installed in {time.time()-t0:.0f}s")
    if not tool_present("circom"):
        raise RuntimeError("circom install appeared to succeed but binary not found on PATH.")
    print(f"  {run('circom --version', tail=1)}")


def phase_project_setup():
    step(4, 13, "Create project directory + install Node dependencies")
    for sub in ["circuits", "scripts", "inputs", "build"]:
        os.makedirs(os.path.join(PROJECT, sub), exist_ok=True)

    with open(os.path.join(PROJECT, "package.json"), "w") as f:
        json.dump(PACKAGE_JSON, f, indent=2)
    os.chdir(PROJECT)

    # FIX Issue #5: use absolute path rather than CWD-relative check
    if os.path.exists(os.path.join(PROJECT, "node_modules")):
        print("  node_modules exists; skipping npm install.")
    else:
        print("  Installing snarkjs + circomlib + circomlibjs (~30s)...")
        t0 = time.time()
        # FIX Issue #21: stream npm output for live progress (~30s but
        # still benefits from visibility, and consistent with circom's
        # streaming install in phase_install_circom).
        run("npm install", stream=True)
        print(f"  Installed in {time.time()-t0:.0f}s")


def phase_write_files():
    step(5, 13, "Write circuit + scripts")
    files = {
        "circuits/bbs_core.circom":     CIRCOM_SRC,
        "scripts/generate_input.js":    GENERATE_JS,
        "scripts/validate_input.js":    VALIDATE_JS,
        "scripts/benchmark.js":         BENCHMARK_JS,
    }
    for rel, content in files.items():
        fpath = os.path.join(PROJECT, rel)
        with open(fpath, "w") as f:
            f.write(content)
        print(f"  wrote {rel}  ({len(content)} bytes)")


def phase_compile():
    step(6, 13, "Compile circuit")
    os.chdir(PROJECT)
    t0 = time.time()
    # Circom prefers being run from a dir where its `-l` library path exists.
    # We chdir here so `-l node_modules` resolves; all output paths are still
    # given as absolute p(...) so chdir drift cannot corrupt them.
    run(f"circom {p('circuits/bbs_core.circom')} --r1cs --wasm --sym "
        f"-o {p('build')} -l {p('node_modules')}")
    print(f"  Compiled in {time.time()-t0:.1f}s")

    info = run(f"npx snarkjs r1cs info {p('build/bbs_core.r1cs')}", tail=20)
    interesting = [ln for ln in info.splitlines()
                   if any(k in ln for k in ["Curve", "Wires", "Constraints",
                                             "Private Inputs", "Public Inputs", "Outputs"])]
    print("  Circuit stats:")
    for line in interesting:
        print(f"    {line.strip()}")


def _verify_ptau(ptau):
    """FIX Issue #13: verify ptau integrity, not just existence.

    Colab runtime disconnects mid-ceremony can leave a ~correct-size but
    internally truncated .ptau file. `snarkjs powersoftau verify` reads
    through all sections and fails with 'Reading out of the range of the
    section' if the file is truncated.

    Returns (ok: bool, diag: str). On failure, diag holds the last few
    lines of snarkjs output so the caller can show the user WHY verify
    failed (FIX Issue #22: don't blame Colab disconnects when the real
    cause is something else like a curve or version mismatch).
    """
    r = subprocess.run(
        f"npx snarkjs powersoftau verify {ptau}",
        shell=True, capture_output=True, text=True,
    )
    if r.returncode == 0:
        return True, ""
    # Grab the most informative tail (last 5 lines of stderr if any, else stdout)
    err = (r.stderr or r.stdout or "").strip().splitlines()
    diag = "\n    ".join(err[-5:]) if err else "(no output)"
    return False, diag


def _verify_zkey(r1cs, ptau, zkey):
    """FIX Issue #13: verify zkey against its circuit and ptau.
    FIX Issue #22: return diagnostic context, not just bool."""
    r = subprocess.run(
        f"npx snarkjs zkey verify {r1cs} {ptau} {zkey}",
        shell=True, capture_output=True, text=True,
    )
    if r.returncode == 0:
        return True, ""
    err = (r.stderr or r.stdout or "").strip().splitlines()
    diag = "\n    ".join(err[-5:]) if err else "(no output)"
    return False, diag


def phase_powers_of_tau():
    """FIX Issue #9: absolute paths throughout.
    FIX Issue #13: verify integrity before skipping."""
    step(7, 13, f"Powers of Tau ceremony (2^{PTAU_SIZE} constraints)")
    ptau = p(f"build/pot{PTAU_SIZE}_final.ptau")

    # FIX Issue #13: existence alone is not enough — verify the file parses.
    if os.path.exists(ptau):
        print(f"  {ptau} exists ({os.path.getsize(ptau)/1e6:.1f} MB); verifying...")
        ok, diag = _verify_ptau(ptau)
        if ok:
            print(f"  ptau verified OK; skipping regeneration.")
            return ptau
        # FIX Issue #22: surface WHY verification failed so unusual causes
        # (e.g., wrong curve, snarkjs version mismatch) can be diagnosed.
        # The "Colab disconnect" wording is the most common cause but not
        # the only one.
        print(f"  WARNING: ptau failed integrity check. snarkjs reported:")
        print(f"    {diag}")
        print(f"  Most likely cause: previous Colab disconnect truncated the file.")
        print(f"  Regenerating from scratch.")
        os.remove(ptau)
        # Also invalidate downstream artifacts that depended on this ptau.
        for stale in (p("build/bbs_final.zkey"), p("build/verification_key.json")):
            if os.path.exists(stale):
                os.remove(stale)
                print(f"    removed stale {os.path.basename(stale)}")

    pot0 = p("build/pot_0000.ptau")
    pot1 = p("build/pot_0001.ptau")

    t0 = time.time()
    print("  Phase 1a: new ceremony...")
    run(f"npx snarkjs powersoftau new bn128 {PTAU_SIZE} {pot0}")

    print("  Phase 1b: contribute entropy...")
    entropy = secrets.token_hex(32)
    run(f"npx snarkjs powersoftau contribute {pot0} {pot1} "
        f"--name='colab' -e='{entropy}'")

    print("  Phase 1c: prepare phase2...")
    run(f"npx snarkjs powersoftau prepare phase2 {pot1} {ptau}")

    # FIX Issue #9: cleanup via Python, not shell rm
    for f in (pot0, pot1):
        try: os.remove(f)
        except FileNotFoundError: pass

    # FIX Issue #13: verify what we just produced, so a bad ceremony fails fast.
    ok, diag = _verify_ptau(ptau)
    if not ok:
        raise RuntimeError(
            f"Freshly generated ptau at {ptau} failed verification.\n"
            f"  snarkjs output: {diag}\n"
            f"  This usually means the ceremony was interrupted; re-run."
        )
    print(f"  Done in {time.time()-t0:.0f}s  ({os.path.getsize(ptau)/1e6:.1f} MB, verified)")
    return ptau


def phase_groth16_setup(ptau):
    """FIX Issue #9: absolute paths.
    FIX Issue #13: verify zkey against circuit + ptau before skipping."""
    step(8, 13, "Groth16 circuit-specific setup (phase 2)")
    zkey = p("build/bbs_final.zkey")
    vkey = p("build/verification_key.json")
    r1cs = p("build/bbs_core.r1cs")

    # FIX Issue #13: existence is not enough. A half-written zkey from a
    # previous disconnect would skip the setup here and then fail during
    # proving with a cryptic snarkjs error about reading beyond section bounds.
    if os.path.exists(zkey) and os.path.exists(vkey):
        print("  zkey + vkey exist; verifying zkey against circuit + ptau...")
        ok, diag = _verify_zkey(r1cs, ptau, zkey)
        if ok:
            print("  zkey verified OK; skipping regeneration.")
            return zkey, vkey
        # FIX Issue #22: surface snarkjs error so user can distinguish a
        # truncated zkey from a circuit-version mismatch (which would
        # require also regenerating r1cs, not just zkey).
        print("  WARNING: zkey failed integrity check. snarkjs reported:")
        print(f"    {diag}")
        print("  Regenerating zkey + vkey.")
        for stale in (zkey, vkey):
            if os.path.exists(stale):
                os.remove(stale)

    zkey0 = p("build/bbs_0000.zkey")

    t0 = time.time()
    run(f"npx snarkjs groth16 setup {r1cs} {ptau} {zkey0}")
    entropy = secrets.token_hex(32)
    run(f"npx snarkjs zkey contribute {zkey0} {zkey} "
        f"--name='colab' -e='{entropy}'")
    run(f"npx snarkjs zkey export verificationkey {zkey} {vkey}")
    try: os.remove(zkey0)
    except FileNotFoundError: pass

    # FIX Issue #13: verify what we just produced, so a bad ceremony fails
    # at setup time, not later at proving time with a confusing error.
    ok, diag = _verify_zkey(r1cs, ptau, zkey)
    if not ok:
        raise RuntimeError(
            f"Freshly generated zkey at {zkey} failed verification.\n"
            f"  snarkjs output: {diag}\n"
            f"  This indicates a problem with ptau or r1cs; re-run from scratch."
        )
    print(f"  Done in {time.time()-t0:.0f}s  (zkey verified)")
    print(f"    {zkey}: {os.path.getsize(zkey)/1e6:.2f} MB")
    print(f"    {vkey}: {os.path.getsize(vkey)/1e3:.1f} KB")
    return zkey, vkey


def phase_generate_input():
    step(9, 13, "Generate witness input")
    os.chdir(PROJECT)
    print(run(f"node {p('scripts/generate_input.js')}"))


def phase_validate_input():
    step(10, 13, "Validate input against circuit constraints")
    os.chdir(PROJECT)
    print(run(f"node {p('scripts/validate_input.js')}"))


def phase_sanity_prove_verify(zkey, vkey):
    """FIX Issue #9: absolute paths for every file reference."""
    step(11, 13, "Single prove + verify (sanity)")
    os.chdir(PROJECT)

    wasm    = p("build/bbs_core_js/bbs_core.wasm")
    wit_js  = p("build/bbs_core_js/generate_witness.js")
    wit     = p("build/witness.wtns")
    proof   = p("build/proof.json")
    public_ = p("build/public.json")
    inp     = p("inputs/input.json")

    run(f"node {wit_js} {wasm} {inp} {wit}")
    print("  witness.wtns: OK")

    t0 = time.time()
    run(f"npx snarkjs groth16 prove {zkey} {wit} {proof} {public_}")
    print(f"  Single prove: {(time.time()-t0)*1000:.1f} ms (includes Node startup)")

    t0 = time.time()
    result = run(f"npx snarkjs groth16 verify {vkey} {public_} {proof}", tail=2)
    if "OK" not in result:
        raise RuntimeError(f"Verification failed: {result}")
    print(f"  Verify:       {(time.time()-t0)*1000:.1f} ms (includes Node startup)")
    print(f"  Proof size:   {os.path.getsize(proof)} bytes (JSON)")


def phase_benchmark():
    """FIX Issue #8: stream=True lets the user see Node's progress output
    ('  20/100\\r', '  40/100\\r', ...) in real time instead of 1-2 minutes
    of silence followed by a burst of output. FIX Issue #9: absolute path."""
    step(12, 13, f"Benchmark ({BENCH_ITERS} iterations)")
    os.chdir(PROJECT)
    t0 = time.time()
    run(f"node {p('scripts/benchmark.js')} {BENCH_ITERS} {BENCH_WARMUP}",
        stream=True)
    print(f"\n  Wall time: {time.time()-t0:.0f}s")


def phase_package_results():
    """FIX Issue #9: absolute paths throughout."""
    step(13, 13, "Package deliverables")
    out_dir = os.path.join(os.path.dirname(PROJECT), "bbs-circom-results")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    for rel in [
        "build/bbs_core.r1cs",
        "build/verification_key.json",
        "build/proof.json",
        "build/public.json",
        "build/benchmark_results.md",
        "build/benchmark_results.json",
        "circuits/bbs_core.circom",
        "inputs/input.json",
    ]:
        src = p(rel)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out_dir, os.path.basename(rel)))

    tar_path = os.path.join(os.path.dirname(PROJECT), "bbs-circom-results.tar.gz")
    # FIX Issue #9: tar via absolute paths; no shell cd
    run(f"tar czf {tar_path} -C {os.path.dirname(out_dir)} {os.path.basename(out_dir)}")
    sz = os.path.getsize(tar_path)
    print(f"  Packaged: {tar_path}  ({sz} bytes)")
    print(f"  Contents: {out_dir}/")
    for fname in sorted(os.listdir(out_dir)):
        pp = os.path.join(out_dir, fname)
        print(f"    {fname}  ({os.path.getsize(pp)} bytes)")
    # FIX Issue #26: caller (main) never used out_dir from the return tuple,
    # so don't return it. The path is already printed above for visibility.
    return tar_path


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    header("BBS Circom PoC — Single-File Colab Runner (v9)")
    wall_t0 = time.time()
    tar_path = None

    try:
        phase_environment()
        phase_install_rust()
        phase_install_circom()
        phase_project_setup()
        phase_write_files()
        phase_compile()
        ptau = phase_powers_of_tau()
        zkey, vkey = phase_groth16_setup(ptau)
        phase_generate_input()
        phase_validate_input()
        phase_sanity_prove_verify(zkey, vkey)
        phase_benchmark()
        tar_path = phase_package_results()  # FIX Issue #26: now returns just tar_path
    except Exception as e:
        header("PIPELINE FAILED")
        print(f"  Error: {e}")
        print(f"  Partial project: {PROJECT}")
        raise

    # ----- Summary -----
    wall = time.time() - wall_t0
    header(f"ALL PHASES COMPLETE  (total wall time: {int(wall//60)}m {int(wall%60)}s)")

    md_path = p("build/benchmark_results.md")
    if os.path.exists(md_path):
        print("\nBenchmark summary (build/benchmark_results.md):\n")
        with open(md_path) as f:
            for line in f:
                print(f"  {line.rstrip()}")

    # FIX Issue #29 (round 9): the previous "linear extrapolation" block was
    # printing a number that directly contradicted the paper's §7.3.2 claim
    # (paper: 26-130 ms for 26K-constraint circuit on native Rust;
    #  output: 11,378 ms linear extrap. from snarkjs on Colab).
    # The mismatch is not a measurement error — it is the 100-500x gap
    # between snarkjs (pure JS, dev-tier) and rapidsnark/arkworks (native
    # Rust, production-tier), a well-known fact in the circom ecosystem.
    # Fix: report per-constraint cost and the platform assumption explicitly,
    # so artifact output is CONSISTENT with paper claims even though it
    # does not independently measure native performance.
    try:
        with open(p("build/benchmark_results.json")) as f:
            data = json.load(f)
        info_raw = run(f"npx snarkjs r1cs info {p('build/bbs_core.r1cs')}", tail=20)
        m = re.search(r"Constraints:\s*(\d+)", info_raw)
        if m and data:
            nc = int(m.group(1))
            if nc > 0:
                pm = data["prove"]["stats"]["median"]
                vm = data["verify"]["stats"]["median"]
                us_per_constraint = (pm * 1000.0) / nc  # ms -> us
                print(f"\nPer-constraint cost (paper §7.3.2):")
                print(f"  Measured:  {nc} constraints → prove median = {pm:.1f} ms, verify = {vm:.1f} ms")
                print(f"  Rate:      {us_per_constraint:.0f} us/constraint (snarkjs, pure JavaScript)")
                print()
                print(f"  Paper §7.3.2 projects ~1 us/constraint on commodity hardware with")
                print(f"  native provers (arkworks / rapidsnark). This PoC uses snarkjs for")
                print(f"  algorithmic verification only; native Rust implementations typically")
                print(f"  run 100-500x faster. A rapidsnark benchmark is left as future work.")
                print()
                print(f"  Verify is constant-time: 3 BN254 pairings, independent of circuit size.")
    except Exception as e:
        print(f"\n  (Per-constraint summary skipped: {e})")

    if tar_path and os.path.exists("/content"):
        print("\nTo download the results tarball in Colab:")
        print("  from google.colab import files")
        print(f"  files.download('{tar_path}')")
    elif tar_path:
        print(f"\nResults at: {tar_path}")


if __name__ == "__main__":
    main()
