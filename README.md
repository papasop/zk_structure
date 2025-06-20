# zk_structure

🛡️ A prototype zero-knowledge structure verification system using Circom + Groth16.

## Files
- `phi_commit.circom` – core circuit definition
- `phi_input.json` – input signals
- `proof.json` – ZK proof
- `public.json` – public signals
- `verification_key.json` – key to verify proof

## To verify:
```bash
snarkjs groth16 verify verification_key.json public.json proof.json
