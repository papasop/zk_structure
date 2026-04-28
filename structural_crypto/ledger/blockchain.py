"""A minimal policy-enforced UTXO blockchain."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from dataclasses import asdict
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Tuple

from structural_crypto.consensus import ColdStartEngine, ColdStartState
from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.crypto.signature import StructurePrivateKey, StructureSignature
from structural_crypto.identity import (
    IdentityAction,
    IdentityActionValidator,
    IdentityState,
    IdentityStateStore,
    IdentityTransitionEngine,
    RecoveryPolicyState,
)
from .models import (
    Block,
    FinalityCertificate,
    FinalityCheckpoint,
    FinalityCommitteeMember,
    FinalityVote,
    SenderTrajectoryState,
    Transaction,
    TxInput,
    TxOutput,
)


class ValidationError(ValueError):
    """Raised when a transaction or block is invalid."""


class Blockchain:
    SCHEMA_VERSION = 5

    def __init__(
        self,
        difficulty: int = 3,
        producer_reward: int = 25,
        emission_schedule: Optional[List[dict]] = None,
        tail_reward_floor: Optional[float] = None,
        rate_limit_window: int = 60,
        max_txs_per_window: int = 3,
        min_tx_gap: int = 1,
        allow_probationary_producers: bool = False,
        allow_new_producers: bool = False,
        confirmation_threshold: float = 1.5,
    ):
        self.difficulty = difficulty
        self.producer_reward = producer_reward
        self.emission_schedule = self._normalize_emission_schedule(
            emission_schedule or [{"start_block": 1, "reward": float(producer_reward)}]
        )
        self.tail_reward_floor = (
            float(tail_reward_floor) if tail_reward_floor is not None else float(producer_reward)
        )
        self.rate_limit_window = rate_limit_window
        self.max_txs_per_window = max_txs_per_window
        self.min_tx_gap = min_tx_gap
        self.allow_probationary_producers = allow_probationary_producers
        self.allow_new_producers = allow_new_producers
        self.confirmation_threshold = confirmation_threshold
        self.blocks: List[Block] = []
        self.block_by_hash: Dict[str, Block] = {}
        self.frontier: List[str] = []
        self.children_by_hash: Dict[str, List[str]] = {}
        self.mempool: List[Transaction] = []
        self.utxos: Dict[Tuple[str, int], TxOutput] = {}
        self.sender_states: Dict[str, SenderTrajectoryState] = {}
        self.identity_states: Dict[str, ColdStartState] = {}
        self.identity_store = IdentityStateStore()
        self.identity_action_validator = IdentityActionValidator()
        self.identity_transition_engine = IdentityTransitionEngine(
            state_store=self.identity_store,
            validator=self.identity_action_validator,
        )
        self.cold_start = ColdStartEngine()
        self._finality_state_cache: dict = {
            "cache_key": None,
            "committee": [],
            "checkpoints": [],
            "summary": {},
        }
        self._create_genesis_block()

    @classmethod
    def from_state(cls, state: dict) -> "Blockchain":
        schema_version = state.get("schema_version")
        if schema_version not in {2, 3, 4, cls.SCHEMA_VERSION}:
            raise ValidationError(
                f"unsupported state schema version: {schema_version!r}, expected {cls.SCHEMA_VERSION}"
            )
        chain = cls(
            difficulty=state["config"]["difficulty"],
            producer_reward=state["config"]["producer_reward"],
            emission_schedule=state["config"].get("emission_schedule"),
            tail_reward_floor=state["config"].get("tail_reward_floor"),
            rate_limit_window=state["config"]["rate_limit_window"],
            max_txs_per_window=state["config"]["max_txs_per_window"],
            min_tx_gap=state["config"]["min_tx_gap"],
            allow_probationary_producers=state["config"]["allow_probationary_producers"],
            allow_new_producers=state["config"]["allow_new_producers"],
            confirmation_threshold=state["config"]["confirmation_threshold"],
        )
        chain.blocks = [chain._block_from_dict(item) for item in state["blocks"]]
        chain.block_by_hash = {block.block_hash: block for block in chain.blocks}
        chain.children_by_hash = {
            block.block_hash: [] for block in chain.blocks
        }
        for block in chain.blocks:
            for parent in block.parents:
                chain.children_by_hash.setdefault(parent, []).append(block.block_hash)
        chain.frontier = list(state["frontier"])
        chain.mempool = [chain._transaction_from_dict(item) for item in state["mempool"]]
        chain.utxos = {
            (entry["txid"], entry["output_index"]): TxOutput(
                amount=entry["output"]["amount"],
                recipient=entry["output"]["recipient"],
            )
            for entry in state["utxos"]
        }
        chain.sender_states = {
            sender: SenderTrajectoryState(**sender_state)
            for sender, sender_state in state["sender_states"].items()
        }
        chain.identity_states = {
            sender: ColdStartState(**identity_state)
            for sender, identity_state in state["identity_states"].items()
        }
        identity_store_state = state.get("identity_store_state")
        if identity_store_state is not None:
            chain.identity_store = IdentityStateStore(
                IdentityState(**identity_state)
                for identity_state in identity_store_state.get("states", [])
            )
        else:
            chain.identity_store = IdentityStateStore()
            chain._rebuild_identity_store()
        chain.identity_action_validator = IdentityActionValidator()
        chain.identity_transition_engine = IdentityTransitionEngine(
            state_store=chain.identity_store,
            validator=chain.identity_action_validator,
        )
        finality_state = state.get("finality_state")
        if finality_state is not None:
            chain._restore_finality_state(finality_state)
        else:
            chain._refresh_finality_state()
        return chain

    def export_state(self) -> dict:
        self._ensure_finality_state()
        return {
            "schema_version": self.SCHEMA_VERSION,
            "config": self._config_view(),
            "blocks": [self._block_to_dict(block) for block in self.blocks],
            "frontier": list(self.frontier),
            "mempool": [self._transaction_to_dict(tx) for tx in self.mempool],
            "utxos": [
                {
                    "txid": txid,
                    "output_index": output_index,
                    "output": {
                        "amount": output.amount,
                        "recipient": output.recipient,
                    },
                }
                for (txid, output_index), output in self.utxos.items()
            ],
            "sender_states": {
                sender: asdict(state)
                for sender, state in self.sender_states.items()
            },
            "identity_states": {
                sender: asdict(state)
                for sender, state in self.identity_states.items()
            },
            "identity_store_state": self.identity_store.export_state(),
            "finality_state": self._export_finality_state_cache(),
        }

    def export_state_json(self) -> str:
        return json.dumps(self.export_state(), sort_keys=True, separators=(",", ":"))

    def state_digest(self) -> str:
        return hashlib.sha256(self.export_state_json().encode("utf-8")).hexdigest()

    def config_digest(self) -> str:
        config_json = json.dumps(self._config_view(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(config_json.encode("utf-8")).hexdigest()

    def consensus_digest(self) -> str:
        consensus_view = {
            "block_hashes": sorted(self.block_by_hash.keys()),
            "frontier": sorted(self.frontier),
            "virtual_order": self.virtual_order(),
            "confirmed_order": self.confirmed_order(),
            "finalized_order": self.finalized_order(),
            "latest_finalized_checkpoint": self.finality_summary()["latest_finalized_checkpoint"],
        }
        encoded = json.dumps(consensus_view, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def save_state(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_name(f"{target.name}.tmp")
        temp_target.write_text(self.export_state_json(), encoding="utf-8")
        os.replace(temp_target, target)
        return target

    @classmethod
    def load_state(cls, path: str | Path) -> "Blockchain":
        source = Path(path)
        state = json.loads(source.read_text(encoding="utf-8"))
        return cls.from_state(state)

    @staticmethod
    def default_state_path(base_dir: str | Path = ".poct") -> Path:
        return Path(base_dir) / "chain_state.json"

    def _create_genesis_block(self) -> None:
        block = Block(
            index=0,
            parents=[],
            timestamp=int(time.time()),
            nonce=0,
            difficulty=self.difficulty,
            producer_id="GENESIS",
            producer_phase="mature",
            producer_ordering_score=1.0,
            producer_weight_snapshot=1.0,
            dynamic_k_snapshot=0.0,
            aggregate_delta=0.0,
            trajectory_commitment=self._head_commitment("GENESIS", None, 0),
            virtual_order_hint="genesis",
            transactions=[],
            merkle_root=self._merkle_root([]),
            block_hash="0" * 64,
        )
        self.blocks.append(block)
        self.block_by_hash[block.block_hash] = block
        self.children_by_hash[block.block_hash] = []
        self.frontier = [block.block_hash]

    def faucet(self, recipient: str, amount: int) -> Transaction:
        genesis_policy = PolicyCommitment.from_values(epsilon=10.0)
        genesis_key = StructurePrivateKey("genesis", "genesis-seed")
        timestamp = int(time.time())
        policy_hash = self._policy_hash(genesis_policy)
        tx = Transaction(
            txid=self._hash_json({"type": "faucet", "recipient": recipient, "amount": amount, "at": len(self.blocks)}),
            sender="GENESIS",
            trajectory_id=None,
            prev=None,
            sequence=0,
            epoch=timestamp,
            policy_hash=policy_hash,
            delta=0.0,
            sender_head_commitment=self._head_commitment("GENESIS", None, 0),
            inputs=[],
            outputs=[TxOutput(amount=amount, recipient=recipient)],
            message=self._tx_message(
                sender="GENESIS",
                identity_id="GENESIS",
                action_type="mint",
                action_key="GENESIS",
                inputs=[],
                outputs=[TxOutput(amount=amount, recipient=recipient)],
                trajectory_id=None,
                prev=None,
                sequence=0,
                epoch=timestamp,
                policy_hash=policy_hash,
                sender_head_commitment=self._head_commitment("GENESIS", None, 0),
                pending_recovery_id=None,
                recovery_policy_version=None,
            ),
            policy=genesis_policy,
            signature=genesis_key.sign(
                message=self._tx_message(
                    sender="GENESIS",
                    identity_id="GENESIS",
                    action_type="mint",
                    action_key="GENESIS",
                    inputs=[],
                    outputs=[TxOutput(amount=amount, recipient=recipient)],
                    trajectory_id=None,
                    prev=None,
                    sequence=0,
                    epoch=timestamp,
                    policy_hash=policy_hash,
                    sender_head_commitment=self._head_commitment("GENESIS", None, 0),
                    pending_recovery_id=None,
                    recovery_policy_version=None,
                ),
                policy=genesis_policy,
                amount=amount,
                recipients=[recipient],
            ),
            timestamp=timestamp,
            identity_id="GENESIS",
            action_type="mint",
            action_key="GENESIS",
        )
        self._apply_transaction(tx)
        genesis = self.blocks[0]
        genesis_transactions = [*genesis.transactions, tx]
        self.blocks[0] = replace(
            genesis,
            transactions=genesis_transactions,
            merkle_root=self._merkle_root(genesis_transactions),
        )
        self.block_by_hash[self.blocks[0].block_hash] = self.blocks[0]
        return tx

    def register_identity(
        self,
        identity_id: str,
        action_keys: List[str],
        guardian_keys: Optional[List[str]] = None,
        recovery_threshold: int = 0,
        recovery_delay_epochs: int = 0,
    ) -> IdentityState:
        existing = self.identity_store.get(identity_id)
        if existing is not None:
            return existing
        state = self.identity_transition_engine.register_identity(
            identity_id=identity_id,
            action_keys=action_keys,
            guardian_keys=guardian_keys,
            recovery_threshold=recovery_threshold,
            recovery_delay_epochs=recovery_delay_epochs,
        )
        self._identity_state(identity_id)
        self._sync_identity_legitimacy(identity_id)
        return state

    def build_identity_action(
        self,
        key: StructurePrivateKey,
        action_type: str,
        payload: Optional[dict] = None,
        identity_id: Optional[str] = None,
        approvals: Optional[List[dict]] = None,
        timestamp: Optional[int] = None,
    ) -> Transaction:
        identity_id = identity_id or key.public_key
        self._ensure_identity_registration(identity_id, key.public_key)
        identity_state, pending_txs = self._sender_context(identity_id)
        trajectory_id = identity_state.trajectory_id or self._trajectory_id_for(identity_id)
        prev = pending_txs[-1].txid if pending_txs else identity_state.head_txid
        sequence = (pending_txs[-1].sequence if pending_txs else identity_state.sequence) + 1
        timestamp = timestamp or int(time.time())
        policy = PolicyCommitment.from_values(epsilon=10.0)
        policy_hash = self._policy_hash(policy)
        head_commitment = self._head_commitment(identity_id, prev, sequence)
        action_payload = dict(payload or {})
        recovery_policy_version = self.identity_store.require(identity_id).recovery_policy.policy_version
        pending_recovery_id = action_payload.get("pending_recovery_id")
        message = self._tx_message(
            sender=key.public_key,
            identity_id=identity_id,
            action_type=action_type,
            action_key=key.public_key,
            inputs=[],
            outputs=[],
            trajectory_id=trajectory_id,
            prev=prev,
            sequence=sequence,
            epoch=timestamp,
            policy_hash=policy_hash,
            sender_head_commitment=head_commitment,
            pending_recovery_id=pending_recovery_id,
            recovery_policy_version=recovery_policy_version,
        )
        signature = key.sign(
            message=message,
            policy=policy,
            amount=0,
            recipients=[],
        )
        tx = Transaction(
            txid=self._hash_json(
                {
                    "sender": key.public_key,
                    "identity_id": identity_id,
                    "action_type": action_type,
                    "action_key": key.public_key,
                    "trajectory_id": trajectory_id,
                    "prev": prev,
                    "sequence": sequence,
                    "epoch": timestamp,
                    "policy_hash": policy_hash,
                    "delta": signature.delta,
                    "sender_head_commitment": head_commitment,
                    "approvals": approvals or [],
                    "action_payload": action_payload,
                    "pending_recovery_id": pending_recovery_id,
                    "recovery_policy_version": recovery_policy_version,
                    "inputs": [],
                    "outputs": [],
                    "message": message,
                }
            ),
            sender=key.public_key,
            trajectory_id=trajectory_id,
            prev=prev,
            sequence=sequence,
            epoch=timestamp,
            policy_hash=policy_hash,
            delta=signature.delta,
            sender_head_commitment=head_commitment,
            inputs=[],
            outputs=[],
            message=message,
            policy=policy,
            signature=signature,
            timestamp=timestamp,
            identity_id=identity_id,
            action_type=action_type,
            action_key=key.public_key,
            approvals=list(approvals or []),
            action_payload=action_payload,
            recovery_policy_version=recovery_policy_version,
            pending_recovery_id=pending_recovery_id,
        )
        self.validate_transaction(tx, signer_seed=key.seed)
        return tx

    def build_transaction(
        self,
        key: StructurePrivateKey,
        recipients: List[Tuple[str, int]],
        policy: PolicyCommitment,
        timestamp: Optional[int] = None,
    ) -> Transaction:
        total_amount = sum(amount for _, amount in recipients)
        selected_inputs, input_total = self._select_utxos(key.public_key, total_amount)
        outputs = [TxOutput(amount=amount, recipient=recipient) for recipient, amount in recipients]
        if input_total > total_amount:
            outputs.append(TxOutput(amount=input_total - total_amount, recipient=key.public_key))
        identity_id = key.public_key
        self._ensure_identity_registration(identity_id, key.public_key)
        sender_state, pending_txs = self._sender_context(identity_id)
        trajectory_id = sender_state.trajectory_id or self._trajectory_id_for(identity_id)
        prev = pending_txs[-1].txid if pending_txs else sender_state.head_txid
        sequence = (pending_txs[-1].sequence if pending_txs else sender_state.sequence) + 1
        timestamp = timestamp or int(time.time())
        policy_hash = self._policy_hash(policy)
        head_commitment = self._head_commitment(identity_id, prev, sequence)
        message = self._tx_message(
            sender=key.public_key,
            identity_id=identity_id,
            action_type="transfer",
            action_key=key.public_key,
            inputs=selected_inputs,
            outputs=outputs,
            trajectory_id=trajectory_id,
            prev=prev,
            sequence=sequence,
            epoch=timestamp,
            policy_hash=policy_hash,
            sender_head_commitment=head_commitment,
            pending_recovery_id=None,
            recovery_policy_version=self.identity_store.require(identity_id).recovery_policy.policy_version,
        )
        signature = key.sign(
            message=message,
            policy=policy,
            amount=total_amount,
            recipients=[recipient for recipient, _ in recipients],
        )
        tx = Transaction(
            txid=self._hash_json(
                {
                    "sender": key.public_key,
                    "identity_id": identity_id,
                    "action_type": "transfer",
                    "action_key": key.public_key,
                    "trajectory_id": trajectory_id,
                    "prev": prev,
                    "sequence": sequence,
                    "epoch": timestamp,
                    "policy_hash": policy_hash,
                    "delta": signature.delta,
                    "sender_head_commitment": head_commitment,
                    "approvals": [],
                    "action_payload": {},
                    "recovery_policy_version": self.identity_store.require(identity_id).recovery_policy.policy_version,
                    "pending_recovery_id": None,
                    "inputs": [(i.prev_txid, i.output_index) for i in selected_inputs],
                    "outputs": [(o.recipient, o.amount) for o in outputs],
                    "message": message,
                }
            ),
            sender=key.public_key,
            trajectory_id=trajectory_id,
            prev=prev,
            sequence=sequence,
            epoch=timestamp,
            policy_hash=policy_hash,
            delta=signature.delta,
            sender_head_commitment=head_commitment,
            inputs=selected_inputs,
            outputs=outputs,
            message=message,
            policy=policy,
            signature=signature,
            timestamp=timestamp,
            identity_id=identity_id,
            action_type="transfer",
            action_key=key.public_key,
            recovery_policy_version=self.identity_store.require(identity_id).recovery_policy.policy_version,
        )
        self.validate_transaction(tx, signer_seed=key.seed)
        return tx

    def add_transaction(self, tx: Transaction, signer_seed: str) -> None:
        try:
            self.validate_transaction(tx, signer_seed=signer_seed)
        except ValidationError:
            if tx.sender != "GENESIS":
                identity_id = self._tx_identity_id(tx)
                self._identity_state(identity_id)
                self.cold_start.record_rejected_tx(
                    self.identity_states[identity_id],
                    branch_conflict=self._looks_like_branch_conflict(tx),
                )
                self._sync_sender_phase(identity_id)
            raise
        self.mempool.append(tx)

    def validate_transaction(self, tx: Transaction, signer_seed: str) -> None:
        if tx.message != self._tx_message(
            sender=tx.sender,
            identity_id=self._tx_identity_id(tx),
            action_type=tx.action_type,
            action_key=self._tx_action_key(tx),
            inputs=tx.inputs,
            outputs=tx.outputs,
            trajectory_id=tx.trajectory_id,
            prev=tx.prev,
            sequence=tx.sequence,
            epoch=tx.epoch,
            policy_hash=tx.policy_hash,
            sender_head_commitment=tx.sender_head_commitment,
            pending_recovery_id=tx.pending_recovery_id,
            recovery_policy_version=tx.recovery_policy_version,
        ):
            raise ValidationError("transaction message does not match trajectory metadata")
        if tx.policy_hash != self._policy_hash(tx.policy):
            raise ValidationError("policy hash does not match transaction policy")
        expected_txid = self._txid_for(tx)
        if tx.txid != expected_txid:
            raise ValidationError("transaction id does not match transaction contents")
        input_total = 0
        pending_inputs = {
            (tx_input.prev_txid, tx_input.output_index)
            for pending_tx in self.mempool
            for tx_input in pending_tx.inputs
        }
        for tx_input in tx.inputs:
            key = (tx_input.prev_txid, tx_input.output_index)
            if key not in self.utxos:
                raise ValidationError(f"missing UTXO {key}")
            if key in pending_inputs:
                raise ValidationError("transaction input is already reserved by another pending transaction")
            utxo = self.utxos[key]
            if utxo.recipient != tx.sender:
                raise ValidationError("transaction tries to spend an output it does not own")
            input_total += utxo.amount
        output_total = tx.total_output()
        if tx.inputs and input_total < output_total:
            raise ValidationError("transaction creates value from nothing")
        if not tx.inputs and tx.sender != "GENESIS" and tx.action_type == "transfer":
            raise ValidationError("only GENESIS can create transactions without inputs")
        signer_public_key = tx.sender
        if tx.sender == "GENESIS":
            signer_public_key = StructurePrivateKey("genesis", "genesis-seed").public_key
        if not StructurePrivateKey.verify(
            message=tx.message,
            policy=tx.policy,
            amount=sum(output.amount for output in self._policy_outputs(tx)),
            recipients=[output.recipient for output in self._policy_outputs(tx)],
            public_key=signer_public_key,
            seed=signer_seed,
            signature=tx.signature,
        ):
            raise ValidationError("invalid structure signature or policy proof")
        if tx.sender != "GENESIS":
            self._validate_identity_action(tx)
            self._validate_trajectory(tx)

    def produce_block(self, producer_id: str) -> Block:
        if not self.producer_is_eligible(producer_id):
            raise ValidationError("producer is not eligible to produce blocks")
        reward_tx = self._build_reward_transaction(producer_id)
        transactions = [*self.mempool, reward_tx]
        block = self._build_block(transactions, producer_id)
        self._apply_block(block)
        self.mempool.clear()
        return block

    def mine_block(self, miner_address: str) -> Block:
        """Backward-compatible alias for the old PoW-flavored name."""
        return self.produce_block(miner_address)

    def build_candidate_block(
        self,
        producer_id: str,
        transactions: Optional[List[Transaction]] = None,
        parents: Optional[List[str]] = None,
    ) -> Block:
        if not self.producer_is_eligible(producer_id):
            raise ValidationError("producer is not eligible to build blocks")
        block_txs = list(transactions) if transactions is not None else []
        return self._build_block(block_txs, producer_id, parents=parents)

    def accept_block(self, block: Block) -> None:
        self._validate_block_structure(block)
        self.blocks.append(block)
        self.block_by_hash[block.block_hash] = block
        self.children_by_hash.setdefault(block.block_hash, [])
        for parent in block.parents:
            self.children_by_hash.setdefault(parent, []).append(block.block_hash)
            if parent in self.frontier:
                self.frontier.remove(parent)
        if block.block_hash not in self.frontier:
            self.frontier.append(block.block_hash)

    def validate_chain(self) -> bool:
        temp_utxos: Dict[Tuple[str, int], TxOutput] = {}
        temp_sender_states: Dict[str, SenderTrajectoryState] = {}
        previous_hash = "0" * 64
        for index, block in enumerate(self.blocks):
            if index == 0:
                if block.parents:
                    return False
                for tx in block.transactions:
                    for output_index, output in enumerate(tx.outputs):
                        temp_utxos[(tx.txid, output_index)] = output
                previous_hash = block.block_hash
                continue
            if not block.parents:
                return False
            if block.prev_hash != previous_hash:
                return False
            for parent in block.parents:
                if parent not in self.block_by_hash and parent != previous_hash:
                    return False
            if not block.block_hash.startswith("0" * block.difficulty):
                return False
            if self._hash_block_payload(
                block.index,
                block.parents,
                block.timestamp,
                block.nonce,
                block.producer_id,
                block.producer_phase,
                block.producer_ordering_score,
                block.producer_weight_snapshot,
                block.dynamic_k_snapshot,
                block.aggregate_delta,
                block.trajectory_commitment,
                block.virtual_order_hint,
                block.transactions,
                block.merkle_root,
            ) != block.block_hash:
                return False
            for tx in block.transactions:
                if tx.sender != "GENESIS":
                    identity_id = self._tx_identity_id(tx)
                    temp_state = temp_sender_states.get(
                        identity_id,
                        SenderTrajectoryState(sender=identity_id),
                    )
                    expected_trajectory_id = temp_state.trajectory_id or tx.trajectory_id
                    expected_prev = temp_state.head_txid
                    expected_sequence = temp_state.sequence + 1
                    if tx.trajectory_id != expected_trajectory_id:
                        return False
                    if tx.prev != expected_prev:
                        return False
                    if tx.sequence != expected_sequence:
                        return False
                    for tx_input in tx.inputs:
                        key = (tx_input.prev_txid, tx_input.output_index)
                        if key not in temp_utxos:
                            return False
                        del temp_utxos[key]
                    temp_state.trajectory_id = tx.trajectory_id
                    temp_state.head_txid = tx.txid
                    temp_state.sequence = tx.sequence
                    temp_sender_states[identity_id] = temp_state
                for output_index, output in enumerate(tx.outputs):
                    temp_utxos[(tx.txid, output_index)] = output
            previous_hash = block.block_hash
        return True

    def balances(self) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for output in self.utxos.values():
            totals[output.recipient] = totals.get(output.recipient, 0) + output.amount
        return totals

    def chain_summary(self) -> List[dict]:
        return [
            {
                "index": block.index,
                "hash": block.block_hash,
                "parents": block.parents,
                "prev_hash": block.prev_hash,
                "producer_id": block.producer_id,
                "transactions": [tx.txid for tx in block.transactions],
            }
            for block in self.blocks
        ]

    def dag_summary(self) -> List[dict]:
        return [
            {
                "hash": block.block_hash,
                "parents": block.parents,
                "producer_id": block.producer_id,
                "producer_phase": block.producer_phase,
                "producer_ordering_score": block.producer_ordering_score,
                "confirmation_score": self.confirmation_score(block.block_hash),
                "confirmed": self.is_confirmed(block.block_hash),
                "confirmed_reward": self.confirmed_reward_for_block(block.block_hash),
            }
            for block in self.blocks
        ]

    def trajectory_summary(self) -> Dict[str, dict]:
        return {
            sender: {
                "trajectory_id": state.trajectory_id,
                "head_txid": state.head_txid,
                "sequence": state.sequence,
                "phase": state.phase,
                "branch_conflicts": state.branch_conflicts,
                "ordering_score": self.cold_start.ordering_score(self._identity_state(sender)),
                "identity_store_head": self.identity_store.get(sender).trajectory_head if self.identity_store.get(sender) else None,
                "identity_store_sequence": self.identity_store.get(sender).sequence if self.identity_store.get(sender) else None,
            }
            for sender, state in self.sender_states.items()
        }

    def identity_store_summary(self) -> dict:
        return {
            "identity_count": self.identity_store.export_state()["identity_count"],
            "state_root": self.identity_store.state_root(),
            "states": [
                {
                    "identity_id": state.identity_id,
                    "trajectory_head": state.trajectory_head,
                    "sequence": state.sequence,
                    "phase": state.phase,
                    "ordering_score": state.ordering_score,
                    "active_action_keys": list(state.active_action_keys),
                    "active_producer_keys": list(state.active_producer_keys),
                    "recovery_guardians": list(state.recovery_policy.guardians),
                    "recovery_threshold": state.recovery_policy.threshold,
                    "pending_recovery": dict(state.pending_recovery) if state.pending_recovery else None,
                    "equivocation_count": state.equivocation_count,
                    "delegated_producer": state.delegated_producer,
                }
                for state in self.identity_store.values()
            ],
        }

    def weighted_anticone_view(self) -> List[dict]:
        dagknight = self._dagknight_state()
        return [
            {
                "block_hash": block_hash,
                "anticone": list(dagknight["anticone_members"][block_hash]),
                "anticone_weight": dagknight["anticone_weight"][block_hash],
            }
            for block_hash in dagknight["topological_order"]
        ]

    def dynamic_k(self) -> float:
        return self._dagknight_state()["dynamic_k"]

    def dagknight_summary(self) -> dict:
        dagknight = self._dagknight_state()
        return {
            "dynamic_k": dagknight["dynamic_k"],
            "blue_set": list(dagknight["blue_set"]),
            "topological_order": list(dagknight["topological_order"]),
            "virtual_order": list(dagknight["virtual_order"]),
            "weighted_anticone": self.weighted_anticone_view(),
        }

    def virtual_order(self) -> List[str]:
        return list(self._dagknight_state()["virtual_order"])

    def confirmation_score(self, block_hash: str) -> float:
        if block_hash not in self.block_by_hash:
            raise ValidationError("unknown block for confirmation score")
        dagknight = self._dagknight_state()
        blue_set = dagknight["blue_set"]
        descendants = dagknight["descendants"][block_hash]
        return sum(
            dagknight["weights"][descendant]
            for descendant in descendants
            if descendant in blue_set
        )

    def is_confirmed(self, block_hash: str) -> bool:
        if block_hash == self.blocks[0].block_hash:
            return True
        adaptive_threshold = max(self.confirmation_threshold, self.dynamic_k() / 2.0)
        return self.confirmation_score(block_hash) >= adaptive_threshold

    def confirmed_order(self) -> List[str]:
        return [block_hash for block_hash in self.virtual_order() if self.is_confirmed(block_hash)]

    def finality_epoch(self) -> int:
        return 0

    def finality_committee(self) -> List[FinalityCommitteeMember]:
        self._ensure_finality_state()
        return list(self._finality_state_cache["committee"])

    def committee_digest(self) -> str:
        self._ensure_finality_state()
        return self._finality_state_cache["summary"]["committee_digest"]

    def finality_checkpoints(self) -> List[FinalityCheckpoint]:
        self._ensure_finality_state()
        return list(self._finality_state_cache["checkpoints"])

    def finality_checkpoint_by_id(self, checkpoint_id: str) -> Optional[FinalityCheckpoint]:
        for checkpoint in self.finality_checkpoints():
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None

    def finality_quorum_threshold(self) -> float:
        return 2.0 / 3.0

    def finality_weight_map(self) -> Dict[str, float]:
        return {
            member.identity_id: member.finality_weight
            for member in self.finality_committee()
        }

    def latest_locked_checkpoint(self) -> Optional[FinalityCheckpoint]:
        checkpoints = self.finality_checkpoints()
        return checkpoints[-1] if checkpoints else None

    def latest_finalized_checkpoint(self) -> Optional[FinalityCheckpoint]:
        checkpoints = self.finality_checkpoints()
        if not checkpoints:
            return None
        finalized = [item for item in checkpoints if item.finalize_certificate is not None]
        return finalized[-1] if finalized else None

    def finalized_order(self) -> List[str]:
        checkpoint = self.latest_finalized_checkpoint()
        if checkpoint is None:
            return []
        confirmed_blocks = self.confirmed_order()
        return confirmed_blocks[: checkpoint.ordered_prefix_end + 1]

    def finalized_l1_batch(self) -> dict:
        finalized_blocks = self.finalized_order()
        resolved_map = {item["block_hash"]: item for item in self.resolved_virtual_blocks()}
        transactions: List[dict] = []
        blocks: List[dict] = []
        for block_hash in finalized_blocks:
            block = self.block_by_hash[block_hash]
            resolved = resolved_map.get(block_hash, {"accepted_txids": [], "rejected_txids": []})
            blocks.append(
                {
                    "block_hash": block.block_hash,
                    "index": block.index,
                    "parents": list(block.parents),
                    "producer_id": block.producer_id,
                    "producer_phase": block.producer_phase,
                    "producer_ordering_score": block.producer_ordering_score,
                    "producer_weight_snapshot": block.producer_weight_snapshot,
                    "dynamic_k_snapshot": block.dynamic_k_snapshot,
                    "aggregate_delta": block.aggregate_delta,
                    "timestamp": block.timestamp,
                    "accepted_txids": list(resolved["accepted_txids"]),
                    "rejected_txids": list(resolved["rejected_txids"]),
                    "confirmed_reward": self.confirmed_reward_for_block(block_hash),
                    "finalized": True,
                }
            )
            accepted_txids = set(resolved["accepted_txids"])
            for tx in block.transactions:
                if tx.txid not in accepted_txids:
                    continue
                tx_record = self._l1_transaction_record(tx, block)
                tx_record["finalized"] = True
                transactions.append(tx_record)
        latest_checkpoint = self.latest_finalized_checkpoint()
        return {
            "mode": "finalized",
            "feed_scope": "finalized",
            "block_hashes": finalized_blocks,
            "blocks": blocks,
            "transactions": transactions,
            "checkpoint_id": latest_checkpoint.checkpoint_id if latest_checkpoint is not None else None,
            "checkpoint_digest": latest_checkpoint.ordered_prefix_digest if latest_checkpoint is not None else None,
        }

    def finality_summary(self) -> dict:
        self._ensure_finality_state()
        return dict(self._finality_state_cache["summary"])

    def confirmed_l1_batch(self) -> dict:
        confirmed_blocks = self.confirmed_order()
        resolved_map = {
            item["block_hash"]: item for item in self.resolved_virtual_blocks()
        }
        blocks: List[dict] = []
        transactions: List[dict] = []
        for block_hash in confirmed_blocks:
            block = self.block_by_hash[block_hash]
            resolved = resolved_map.get(
                block_hash,
                {"accepted_txids": [], "rejected_txids": []},
            )
            blocks.append(
                {
                    "block_hash": block.block_hash,
                    "index": block.index,
                    "parents": list(block.parents),
                    "producer_id": block.producer_id,
                    "producer_phase": block.producer_phase,
                    "producer_ordering_score": block.producer_ordering_score,
                    "producer_weight_snapshot": block.producer_weight_snapshot,
                    "dynamic_k_snapshot": block.dynamic_k_snapshot,
                    "aggregate_delta": block.aggregate_delta,
                    "timestamp": block.timestamp,
                    "accepted_txids": list(resolved["accepted_txids"]),
                    "rejected_txids": list(resolved["rejected_txids"]),
                    "confirmed_reward": self.confirmed_reward_for_block(block_hash),
                }
            )
            accepted_txids = set(resolved["accepted_txids"])
            for tx in block.transactions:
                if tx.txid not in accepted_txids:
                    continue
                transactions.append(self._l1_transaction_record(tx, block))
        return {
            "mode": "confirmed",
            "block_hashes": confirmed_blocks,
            "blocks": blocks,
            "transactions": transactions,
        }

    def export_l1_feed(self, confirmed_only: bool = True) -> dict:
        if confirmed_only:
            batch = self.confirmed_l1_batch()
            batch["feed_scope"] = "confirmed"
            return batch

        resolved_blocks = self.resolved_virtual_blocks()
        resolved_map = {item["block_hash"]: item for item in resolved_blocks}
        transactions: List[dict] = []
        blocks: List[dict] = []
        for block_hash in self.virtual_order():
            block = self.block_by_hash[block_hash]
            resolved = resolved_map.get(
                block_hash,
                {"accepted_txids": [], "rejected_txids": []},
            )
            blocks.append(
                {
                    "block_hash": block.block_hash,
                    "index": block.index,
                    "parents": list(block.parents),
                    "producer_id": block.producer_id,
                    "producer_phase": block.producer_phase,
                    "producer_ordering_score": block.producer_ordering_score,
                    "aggregate_delta": block.aggregate_delta,
                    "timestamp": block.timestamp,
                    "confirmed": self.is_confirmed(block_hash),
                    "accepted_txids": list(resolved["accepted_txids"]),
                    "rejected_txids": list(resolved["rejected_txids"]),
                }
            )
            accepted_txids = set(resolved["accepted_txids"])
            for tx in block.transactions:
                if tx.txid not in accepted_txids:
                    continue
                tx_record = self._l1_transaction_record(tx, block)
                tx_record["confirmed"] = self.is_confirmed(block_hash)
                transactions.append(tx_record)
        return {
            "mode": "virtual",
            "feed_scope": "resolved_virtual",
            "block_hashes": self.virtual_order(),
            "blocks": blocks,
            "transactions": transactions,
        }

    def export_l1_handoff(self, prefer_finalized: bool = True) -> dict:
        finalized_batch = self.finalized_l1_batch()
        use_finalized = prefer_finalized and finalized_batch.get("checkpoint_id") is not None
        batch = finalized_batch if use_finalized else self.confirmed_l1_batch()
        finality_status = "finalized" if use_finalized else "confirmed"
        txids = [tx["txid"] for tx in batch.get("transactions", [])]
        handoff_digest = self._hash_json(
            {
                "scope": "l1-handoff",
                "finality_status": finality_status,
                "block_hashes": batch.get("block_hashes", []),
                "txids": txids,
                "checkpoint_id": batch.get("checkpoint_id"),
            }
        )
        return {
            "handoff_version": 1,
            "finality_status": finality_status,
            "handoff_scope": finality_status,
            "batch_digest": handoff_digest,
            "checkpoint_id": batch.get("checkpoint_id"),
            "checkpoint_digest": batch.get("checkpoint_digest"),
            "block_count": len(batch.get("blocks", [])),
            "transaction_count": len(batch.get("transactions", [])),
            "batch": batch,
        }

    def export_finality_state(self) -> dict:
        self._ensure_finality_state()
        return self._export_finality_state_cache()

    def verify_finality_checkpoint(self, checkpoint_data: dict) -> bool:
        checkpoint_id = checkpoint_data.get("checkpoint_id")
        ordered_prefix_end = checkpoint_data.get("ordered_prefix_end")
        anchor_block_hash = checkpoint_data.get("anchor_block_hash")
        committee_digest = checkpoint_data.get("committee_digest")
        config_digest = checkpoint_data.get("config_digest")
        if checkpoint_id is None or ordered_prefix_end is None or anchor_block_hash is None:
            return False
        if committee_digest != self.committee_digest():
            return False
        if config_digest != self.config_digest():
            return False
        local_order = self.virtual_order()
        if ordered_prefix_end < 0 or ordered_prefix_end >= len(local_order):
            return False
        local_prefix = local_order[: ordered_prefix_end + 1]
        if not local_prefix or local_prefix[-1] != anchor_block_hash:
            return False
        expected_ordered_prefix_digest = self._hash_json(
            {
                "scope": "finalized-prefix",
                "block_hashes": local_prefix,
            }
        )
        expected_confirmed_batch_digest = self._hash_json(
            {
                "scope": "finalized-batch",
                "block_hashes": local_prefix,
                "txids": self._accepted_txids_for_blocks(local_prefix),
            }
        )
        return (
            checkpoint_data.get("ordered_prefix_digest") == expected_ordered_prefix_digest
            and checkpoint_data.get("confirmed_batch_digest") == expected_confirmed_batch_digest
        )

    def verify_finality_certificate(self, checkpoint_id: str, certificate_data: dict) -> bool:
        self._ensure_finality_state()
        checkpoint_map = {
            item.checkpoint_id: item
            for item in self._finality_state_cache["checkpoints"]
        }
        checkpoint = checkpoint_map.get(checkpoint_id)
        if checkpoint is None:
            return False
        local_certificate = checkpoint.finalize_certificate or checkpoint.lock_certificate
        if local_certificate is None:
            return False
        if self._certificate_to_dict(local_certificate) != certificate_data:
            return False
        if certificate_data.get("committee_digest") != self.committee_digest():
            return False
        committee_ids = {member.identity_id for member in self.finality_committee()}
        signer_set = set(certificate_data.get("signer_set", []))
        if not signer_set.issubset(committee_ids):
            return False
        return float(certificate_data.get("quorum_weight", 0.0)) >= (2.0 / 3.0)

    def verify_finality_evidence(self, checkpoint_data: dict, certificate_data: dict) -> bool:
        checkpoint_id = checkpoint_data.get("checkpoint_id")
        if not checkpoint_id:
            return False
        return self.verify_finality_checkpoint(checkpoint_data) and self.verify_finality_certificate(
            checkpoint_id,
            certificate_data,
        )

    def verify_finality_vote(self, checkpoint_data: dict, vote_data: dict) -> bool:
        if not self.verify_finality_checkpoint(checkpoint_data):
            return False
        checkpoint_id = checkpoint_data.get("checkpoint_id")
        if vote_data.get("checkpoint_id") != checkpoint_id:
            return False
        if vote_data.get("vote_type") != "lock":
            return False
        if vote_data.get("epoch") != checkpoint_data.get("epoch"):
            return False
        if vote_data.get("round") != checkpoint_data.get("round"):
            return False
        if vote_data.get("committee_digest") != checkpoint_data.get("committee_digest"):
            return False
        voter_id = vote_data.get("voter_id")
        if not voter_id:
            return False
        weight_map = self.finality_weight_map()
        if voter_id not in weight_map:
            return False
        expected_weight = weight_map[voter_id]
        if round(float(vote_data.get("voter_weight", -1.0)), 12) != round(expected_weight, 12):
            return False
        expected_digest = self._finality_vote_digest(
            epoch=int(vote_data["epoch"]),
            round_index=int(vote_data["round"]),
            vote_type=str(vote_data["vote_type"]),
            checkpoint_id=str(checkpoint_id),
            committee_digest=str(vote_data["committee_digest"]),
            voter_id=str(voter_id),
            voter_weight=float(vote_data["voter_weight"]),
        )
        return vote_data.get("vote_digest") == expected_digest

    def verify_external_finality_certificate(self, checkpoint_data: dict, certificate_data: dict) -> bool:
        if not self.verify_finality_checkpoint(checkpoint_data):
            return False
        checkpoint_id = checkpoint_data.get("checkpoint_id")
        if certificate_data.get("checkpoint_id") != checkpoint_id:
            return False
        if certificate_data.get("vote_type") not in {"lock", "finalize"}:
            return False
        if certificate_data.get("epoch") != checkpoint_data.get("epoch"):
            return False
        if certificate_data.get("committee_digest") != checkpoint_data.get("committee_digest"):
            return False
        signer_set = sorted(set(certificate_data.get("signer_set", [])))
        if not signer_set:
            return False
        weight_map = self.finality_weight_map()
        if any(signer not in weight_map for signer in signer_set):
            return False
        quorum_weight = sum(weight_map[signer] for signer in signer_set)
        if round(float(certificate_data.get("quorum_weight", -1.0)), 12) != round(quorum_weight, 12):
            return False
        if quorum_weight < self.finality_quorum_threshold():
            return False
        expected_digest = self._hash_json(
            {
                "epoch": int(certificate_data["epoch"]),
                "round": int(certificate_data["round"]),
                "vote_type": str(certificate_data["vote_type"]),
                "checkpoint_id": str(checkpoint_id),
                "committee_digest": str(certificate_data["committee_digest"]),
                "quorum_weight": round(quorum_weight, 12),
                "signers": signer_set,
            }
        )
        return certificate_data.get("certificate_digest") == expected_digest

    def resolved_virtual_blocks(self) -> List[dict]:
        spent_inputs: set[Tuple[str, int]] = set()
        claimed_slots: set[Tuple[str, int]] = set()
        resolved: List[dict] = []
        for block_hash in self.virtual_order():
            block = self.block_by_hash[block_hash]
            accepted_txids: List[str] = []
            rejected_txids: List[str] = []
            for tx in block.transactions:
                if self._transaction_conflicts_in_virtual_order(tx, spent_inputs, claimed_slots):
                    rejected_txids.append(tx.txid)
                    continue
                accepted_txids.append(tx.txid)
                for tx_input in tx.inputs:
                    spent_inputs.add((tx_input.prev_txid, tx_input.output_index))
                if tx.sender != "GENESIS":
                    claimed_slots.add((self._tx_identity_id(tx), tx.sequence))
            resolved.append(
                {
                    "block_hash": block_hash,
                    "accepted_txids": accepted_txids,
                    "rejected_txids": rejected_txids,
                }
            )
        return resolved

    def accepted_virtual_transactions(self) -> List[str]:
        accepted: List[str] = []
        for item in self.resolved_virtual_blocks():
            accepted.extend(item["accepted_txids"])
        return accepted

    def confirmed_reward_for_block(self, block_hash: str) -> float:
        if block_hash not in self.block_by_hash:
            raise ValidationError("unknown block for reward accounting")
        block = self.block_by_hash[block_hash]
        if block.index == 0 or not self.is_confirmed(block_hash):
            return 0.0
        if block.producer_id == "GENESIS":
            return 0.0
        state = self._identity_state(block.producer_id)
        return self.reward_amount_for_block(block.index) * self.cold_start.reward_share(state)

    def confirmed_reward_totals(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for block_hash in self.confirmed_order():
            block = self.block_by_hash[block_hash]
            reward = self.confirmed_reward_for_block(block_hash)
            if reward <= 0:
                continue
            totals[block.producer_id] = totals.get(block.producer_id, 0.0) + reward
        return totals

    def producer_is_eligible(self, producer: str) -> bool:
        state = self._identity_state(producer)
        if state.phase == "penalized":
            return False
        if state.phase == "mature":
            return True
        if state.phase == "probation":
            return self.allow_probationary_producers
        if state.phase == "new":
            return self.allow_new_producers
        return False

    def producer_priority(self, producer: str, proposed_timestamp: Optional[int] = None) -> tuple:
        identity_state = self._identity_state(producer)
        sender_state = self.sender_states.get(producer, SenderTrajectoryState(sender=producer))
        hot_state = self.identity_store.get(producer)
        phase_rank = self._phase_rank(identity_state.phase)
        ordering_score = hot_state.ordering_score if hot_state is not None else self.cold_start.ordering_score(identity_state)
        average_delta = identity_state.average_delta
        branch_conflicts = sender_state.branch_conflicts
        timestamp = proposed_timestamp if proposed_timestamp is not None else int(time.time())
        return (
            -phase_rank,
            -ordering_score,
            average_delta,
            branch_conflicts,
            timestamp,
            producer,
        )

    def reward_amount_for_block(self, block_index: int) -> float:
        reward = self.tail_reward_floor
        for stage in self.emission_schedule:
            if block_index >= stage["start_block"]:
                reward = stage["reward"]
            else:
                break
        return max(float(reward), float(self.tail_reward_floor))

    def _select_utxos(self, owner: str, amount: int) -> Tuple[List[TxInput], int]:
        selected: List[TxInput] = []
        running_total = 0
        for (txid, output_index), output in self.utxos.items():
            if output.recipient != owner:
                continue
            selected.append(TxInput(prev_txid=txid, output_index=output_index, owner=owner))
            running_total += output.amount
            if running_total >= amount:
                return selected, running_total
        raise ValidationError(f"insufficient balance for {owner}")

    def _build_reward_transaction(self, producer_id: str) -> Transaction:
        timestamp = int(time.time())
        key = StructurePrivateKey("producer-reward", "genesis-seed")
        genesis_policy = PolicyCommitment.from_values(epsilon=10.0)
        policy_hash = self._policy_hash(genesis_policy)
        reward_amount = self.reward_amount_for_block(len(self.blocks))
        head_commitment = self._head_commitment("GENESIS", None, len(self.blocks))
        message = self._tx_message(
            sender="GENESIS",
            identity_id="GENESIS",
            action_type="reward",
            action_key="GENESIS",
            inputs=[],
            outputs=[TxOutput(amount=int(reward_amount), recipient=producer_id)],
            trajectory_id=None,
            prev=None,
            sequence=len(self.blocks),
            epoch=timestamp,
            policy_hash=policy_hash,
            sender_head_commitment=head_commitment,
            pending_recovery_id=None,
            recovery_policy_version=None,
        )
        return Transaction(
            txid=self._hash_json({"type": "reward", "producer": producer_id, "height": len(self.blocks)}),
            sender="GENESIS",
            trajectory_id=None,
            prev=None,
            sequence=len(self.blocks),
            epoch=timestamp,
            policy_hash=policy_hash,
            delta=0.0,
            sender_head_commitment=head_commitment,
            inputs=[],
            outputs=[TxOutput(amount=int(reward_amount), recipient=producer_id)],
            message=message,
            policy=genesis_policy,
            signature=key.sign(
                message=message,
                policy=genesis_policy,
                amount=int(reward_amount),
                recipients=[producer_id],
            ),
            timestamp=timestamp,
            identity_id="GENESIS",
            action_type="reward",
            action_key="GENESIS",
        )

    def _l1_transaction_record(self, tx: Transaction, block: Block) -> dict:
        return {
            "txid": tx.txid,
            "sender": tx.sender,
            "identity_id": self._tx_identity_id(tx),
            "action_type": tx.action_type,
            "action_key": self._tx_action_key(tx),
            "trajectory_id": tx.trajectory_id,
            "prev": tx.prev,
            "sequence": tx.sequence,
            "epoch": tx.epoch,
            "policy_hash": tx.policy_hash,
            "delta": tx.delta,
            "sender_head_commitment": tx.sender_head_commitment,
            "recovery_policy_version": tx.recovery_policy_version,
            "pending_recovery_id": tx.pending_recovery_id,
            "inputs": [
                {
                    "prev_txid": tx_input.prev_txid,
                    "output_index": tx_input.output_index,
                    "owner": tx_input.owner,
                }
                for tx_input in tx.inputs
            ],
            "outputs": [
                {
                    "amount": output.amount,
                    "recipient": output.recipient,
                }
                for output in tx.outputs
            ],
            "block_hash": block.block_hash,
            "producer_id": block.producer_id,
            "producer_phase": block.producer_phase,
            "producer_ordering_score": block.producer_ordering_score,
            "block_timestamp": block.timestamp,
        }

    def _accepted_txids_for_blocks(self, block_hashes: List[str]) -> List[str]:
        resolved_map = {item["block_hash"]: item for item in self.resolved_virtual_blocks()}
        accepted: List[str] = []
        for block_hash in block_hashes:
            accepted.extend(resolved_map.get(block_hash, {}).get("accepted_txids", []))
        return accepted

    def _build_finality_certificate(
        self,
        epoch: int,
        round_index: int,
        vote_type: str,
        checkpoint_id: str,
        committee_digest: str,
        quorum_weight: float,
        signers: List[str],
    ) -> FinalityCertificate:
        certificate_digest = self._hash_json(
            {
                "epoch": epoch,
                "round": round_index,
                "vote_type": vote_type,
                "checkpoint_id": checkpoint_id,
                "committee_digest": committee_digest,
                "quorum_weight": round(quorum_weight, 12),
                "signers": signers,
            }
        )
        return FinalityCertificate(
            epoch=epoch,
            round=round_index,
            vote_type=vote_type,
            checkpoint_id=checkpoint_id,
            quorum_weight=quorum_weight,
            committee_digest=committee_digest,
            signer_set=list(signers),
            certificate_digest=certificate_digest,
        )

    def _finality_vote_digest(
        self,
        epoch: int,
        round_index: int,
        vote_type: str,
        checkpoint_id: str,
        committee_digest: str,
        voter_id: str,
        voter_weight: float,
    ) -> str:
        return self._hash_json(
            {
                "epoch": epoch,
                "round": round_index,
                "vote_type": vote_type,
                "checkpoint_id": checkpoint_id,
                "committee_digest": committee_digest,
                "voter_id": voter_id,
                "voter_weight": round(voter_weight, 12),
            }
        )

    def _finality_cache_key(self) -> str:
        mature_identities = [
            {
                "identity_id": identity_id,
                "phase": identity_state.phase,
                "ordering_score": round(max(self.cold_start.ordering_score(identity_state), 0.0), 12),
            }
            for identity_id, identity_state in sorted(self.identity_states.items())
            if identity_state.phase == "mature"
        ]
        return self._hash_json(
            {
                "epoch": self.finality_epoch(),
                "config_digest": self.config_digest(),
                "confirmed_order": self.confirmed_order(),
                "mature_identities": mature_identities,
            }
        )

    def _ensure_finality_state(self) -> None:
        cache_key = self._finality_cache_key()
        if self._finality_state_cache.get("cache_key") != cache_key:
            self._refresh_finality_state(cache_key=cache_key)

    def _refresh_finality_state(self, cache_key: Optional[str] = None) -> None:
        cache_key = cache_key or self._finality_cache_key()
        committee = self._compute_finality_committee()
        checkpoints = self._compute_finality_checkpoints(committee)
        summary = self._build_finality_summary(committee, checkpoints)
        self._finality_state_cache = {
            "cache_key": cache_key,
            "committee": committee,
            "checkpoints": checkpoints,
            "summary": summary,
        }

    def _compute_finality_committee(self) -> List[FinalityCommitteeMember]:
        epoch = self.finality_epoch()
        candidates: List[tuple[str, ColdStartState, float]] = []
        for identity_id, identity_state in self.identity_states.items():
            if identity_state.phase != "mature":
                continue
            ordering_score = max(self.cold_start.ordering_score(identity_state), 0.0)
            if ordering_score <= 0.0:
                continue
            candidates.append((identity_id, identity_state, ordering_score))
        if not candidates:
            return []
        total_score = sum(item[2] for item in candidates)
        weight_cap = 2.0 / 3.0
        return [
            FinalityCommitteeMember(
                identity_id=identity_id,
                phase=identity_state.phase,
                ordering_score=ordering_score,
                finality_weight=min(ordering_score / total_score, weight_cap),
                committee_epoch=epoch,
            )
            for identity_id, identity_state, ordering_score in sorted(
                candidates,
                key=lambda item: (-item[2], item[0]),
            )
        ]

    def _compute_finality_checkpoints(
        self,
        committee: List[FinalityCommitteeMember],
    ) -> List[FinalityCheckpoint]:
        confirmed_blocks = self.confirmed_order()
        if not confirmed_blocks:
            return []
        committee_digest = self._committee_digest_for(committee)
        total_weight = sum(item.finality_weight for item in committee)
        signers = [item.identity_id for item in committee]
        checkpoints: List[FinalityCheckpoint] = []
        for round_index, block_hash in enumerate(confirmed_blocks, start=1):
            prefix = confirmed_blocks[:round_index]
            ordered_prefix_digest = self._hash_json({"scope": "finalized-prefix", "block_hashes": prefix})
            confirmed_batch_digest = self._hash_json(
                {
                    "scope": "finalized-batch",
                    "block_hashes": prefix,
                    "txids": self._accepted_txids_for_blocks(prefix),
                }
            )
            checkpoint_id = self._hash_json(
                {
                    "epoch": self.finality_epoch(),
                    "round": round_index,
                    "anchor_block_hash": block_hash,
                    "ordered_prefix_digest": ordered_prefix_digest,
                    "confirmed_batch_digest": confirmed_batch_digest,
                    "committee_digest": committee_digest,
                    "config_digest": self.config_digest(),
                }
            )
            lock_certificate = None
            if total_weight > 0.0:
                lock_certificate = self._build_finality_certificate(
                    epoch=self.finality_epoch(),
                    round_index=round_index,
                    vote_type="lock",
                    checkpoint_id=checkpoint_id,
                    committee_digest=committee_digest,
                    quorum_weight=total_weight,
                    signers=signers,
                )
            checkpoints.append(
                FinalityCheckpoint(
                    checkpoint_id=checkpoint_id,
                    epoch=self.finality_epoch(),
                    round=round_index,
                    anchor_block_hash=block_hash,
                    finalized_parent=checkpoints[-1].checkpoint_id if checkpoints else None,
                    ordered_prefix_end=round_index - 1,
                    ordered_prefix_digest=ordered_prefix_digest,
                    confirmed_batch_digest=confirmed_batch_digest,
                    committee_digest=committee_digest,
                    config_digest=self.config_digest(),
                    lock_certificate=lock_certificate,
                )
            )
        if total_weight > 0.0:
            for index in range(len(checkpoints) - 1):
                checkpoint = checkpoints[index]
                descendant = checkpoints[index + 1]
                checkpoints[index] = replace(
                    checkpoint,
                    finalize_certificate=self._build_finality_certificate(
                        epoch=checkpoint.epoch,
                        round_index=descendant.round,
                        vote_type="finalize",
                        checkpoint_id=checkpoint.checkpoint_id,
                        committee_digest=committee_digest,
                        quorum_weight=total_weight,
                        signers=signers,
                    ),
                )
        return checkpoints

    def _build_finality_summary(
        self,
        committee: List[FinalityCommitteeMember],
        checkpoints: List[FinalityCheckpoint],
    ) -> dict:
        latest_locked = checkpoints[-1] if checkpoints else None
        finalized = [item for item in checkpoints if item.finalize_certificate is not None]
        latest_finalized = finalized[-1] if finalized else None
        finalized_order = (
            self.confirmed_order()[: latest_finalized.ordered_prefix_end + 1]
            if latest_finalized is not None
            else []
        )
        committee_digest = self._committee_digest_for(committee)
        return {
            "epoch": self.finality_epoch(),
            "config_digest": self.config_digest(),
            "committee_size": len(committee),
            "committee_digest": committee_digest,
            "latest_locked_checkpoint": latest_locked.checkpoint_id if latest_locked is not None else None,
            "latest_finalized_checkpoint": latest_finalized.checkpoint_id if latest_finalized is not None else None,
            "finalized_prefix_digest": latest_finalized.ordered_prefix_digest if latest_finalized is not None else None,
            "finalized_height": len(finalized_order),
            "latest_lock_certificate_digest": (
                latest_locked.lock_certificate.certificate_digest
                if latest_locked is not None and latest_locked.lock_certificate is not None
                else None
            ),
            "latest_finalize_certificate_digest": (
                latest_finalized.finalize_certificate.certificate_digest
                if latest_finalized is not None and latest_finalized.finalize_certificate is not None
                else None
            ),
            "finalized_order": finalized_order,
            "checkpoint_count": len(checkpoints),
        }

    def _committee_digest_for(self, committee: List[FinalityCommitteeMember]) -> str:
        members = [self._committee_member_to_dict(item) for item in committee]
        return self._hash_json({"epoch": self.finality_epoch(), "members": members})

    def _export_finality_state_cache(self) -> dict:
        self._ensure_finality_state()
        return {
            "cache_key": self._finality_state_cache["cache_key"],
            "committee": [self._committee_member_to_dict(item) for item in self._finality_state_cache["committee"]],
            "checkpoints": [self._checkpoint_to_dict(item) for item in self._finality_state_cache["checkpoints"]],
            "summary": dict(self._finality_state_cache["summary"]),
        }

    def _restore_finality_state(self, finality_state: dict) -> None:
        restored = {
            "cache_key": finality_state.get("cache_key"),
            "committee": [
                FinalityCommitteeMember(**item)
                for item in finality_state.get("committee", [])
            ],
            "checkpoints": [
                self._checkpoint_from_dict(item)
                for item in finality_state.get("checkpoints", [])
            ],
            "summary": dict(finality_state.get("summary", {})),
        }
        self._finality_state_cache = restored
        current_key = self._finality_cache_key()
        if restored["cache_key"] != current_key:
            self._refresh_finality_state(cache_key=current_key)
            return
        expected = self._build_finality_summary(restored["committee"], restored["checkpoints"])
        if restored["summary"] != expected:
            self._refresh_finality_state(cache_key=current_key)
        else:
            self._finality_state_cache["summary"] = expected

    def _config_view(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "producer_reward": self.producer_reward,
            "emission_schedule": self.emission_schedule,
            "tail_reward_floor": self.tail_reward_floor,
            "rate_limit_window": self.rate_limit_window,
            "max_txs_per_window": self.max_txs_per_window,
            "min_tx_gap": self.min_tx_gap,
            "allow_probationary_producers": self.allow_probationary_producers,
            "allow_new_producers": self.allow_new_producers,
            "confirmation_threshold": self.confirmation_threshold,
        }

    @staticmethod
    def _committee_member_to_dict(member: FinalityCommitteeMember) -> dict:
        return {
            "identity_id": member.identity_id,
            "phase": member.phase,
            "ordering_score": member.ordering_score,
            "finality_weight": member.finality_weight,
            "committee_epoch": member.committee_epoch,
        }

    @classmethod
    def _certificate_to_dict(cls, certificate: Optional[FinalityCertificate]) -> Optional[dict]:
        if certificate is None:
            return None
        return {
            "epoch": certificate.epoch,
            "round": certificate.round,
            "vote_type": certificate.vote_type,
            "checkpoint_id": certificate.checkpoint_id,
            "quorum_weight": certificate.quorum_weight,
            "committee_digest": certificate.committee_digest,
            "signer_set": list(certificate.signer_set),
            "certificate_digest": certificate.certificate_digest,
        }

    @staticmethod
    def _certificate_from_dict(data: Optional[dict]) -> Optional[FinalityCertificate]:
        if data is None:
            return None
        return FinalityCertificate(
            epoch=data["epoch"],
            round=data["round"],
            vote_type=data["vote_type"],
            checkpoint_id=data["checkpoint_id"],
            quorum_weight=data["quorum_weight"],
            committee_digest=data["committee_digest"],
            signer_set=list(data["signer_set"]),
            certificate_digest=data["certificate_digest"],
        )

    @classmethod
    def _checkpoint_to_dict(cls, checkpoint: FinalityCheckpoint) -> dict:
        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "epoch": checkpoint.epoch,
            "round": checkpoint.round,
            "anchor_block_hash": checkpoint.anchor_block_hash,
            "finalized_parent": checkpoint.finalized_parent,
            "ordered_prefix_end": checkpoint.ordered_prefix_end,
            "ordered_prefix_digest": checkpoint.ordered_prefix_digest,
            "confirmed_batch_digest": checkpoint.confirmed_batch_digest,
            "committee_digest": checkpoint.committee_digest,
            "config_digest": checkpoint.config_digest,
            "lock_certificate": cls._certificate_to_dict(checkpoint.lock_certificate),
            "finalize_certificate": cls._certificate_to_dict(checkpoint.finalize_certificate),
        }

    @classmethod
    def _checkpoint_from_dict(cls, data: dict) -> FinalityCheckpoint:
        return FinalityCheckpoint(
            checkpoint_id=data["checkpoint_id"],
            epoch=data["epoch"],
            round=data["round"],
            anchor_block_hash=data["anchor_block_hash"],
            finalized_parent=data["finalized_parent"],
            ordered_prefix_end=data["ordered_prefix_end"],
            ordered_prefix_digest=data["ordered_prefix_digest"],
            confirmed_batch_digest=data["confirmed_batch_digest"],
            committee_digest=data["committee_digest"],
            config_digest=data["config_digest"],
            lock_certificate=cls._certificate_from_dict(data.get("lock_certificate")),
            finalize_certificate=cls._certificate_from_dict(data.get("finalize_certificate")),
        )

    def _build_block(
        self,
        transactions: List[Transaction],
        producer_id: str,
        parents: Optional[List[str]] = None,
    ) -> Block:
        parents = parents or self._select_block_parents(producer_id)
        index = len(self.blocks)
        timestamp = int(time.time())
        merkle_root = self._merkle_root(transactions)
        identity_state = self._identity_state(producer_id)
        self._sync_identity_legitimacy(producer_id)
        hot_state = self.identity_store.get(producer_id)
        producer_phase = identity_state.phase
        producer_ordering_score = hot_state.ordering_score if hot_state is not None else self.cold_start.ordering_score(identity_state)
        producer_weight_snapshot = producer_ordering_score
        dynamic_k_snapshot = self.dynamic_k()
        aggregate_delta = self._aggregate_delta(transactions)
        trajectory_commitment = self._producer_trajectory_commitment(producer_id)
        virtual_order_hint = self._virtual_order_hint(producer_id, producer_ordering_score, timestamp)
        nonce = 0
        while True:
            block_hash = self._hash_block_payload(
                index,
                parents,
                timestamp,
                nonce,
                producer_id,
                producer_phase,
                producer_ordering_score,
                producer_weight_snapshot,
                dynamic_k_snapshot,
                aggregate_delta,
                trajectory_commitment,
                virtual_order_hint,
                transactions,
                merkle_root,
            )
            if block_hash.startswith("0" * self.difficulty):
                return Block(
                    index=index,
                    parents=parents,
                    timestamp=timestamp,
                    nonce=nonce,
                    difficulty=self.difficulty,
                    producer_id=producer_id,
                    producer_phase=producer_phase,
                    producer_ordering_score=producer_ordering_score,
                    producer_weight_snapshot=producer_weight_snapshot,
                    dynamic_k_snapshot=dynamic_k_snapshot,
                    aggregate_delta=aggregate_delta,
                    trajectory_commitment=trajectory_commitment,
                    virtual_order_hint=virtual_order_hint,
                    transactions=transactions,
                    merkle_root=merkle_root,
                    block_hash=block_hash,
                )
            nonce += 1

    def _apply_block(self, block: Block) -> None:
        self._validate_block_structure(block)
        for tx in self.mempool:
            self._apply_transaction(tx)
        self._apply_transaction(block.transactions[-1])
        self.blocks.append(block)
        self.block_by_hash[block.block_hash] = block
        self.children_by_hash.setdefault(block.block_hash, [])
        for parent in block.parents:
            self.children_by_hash.setdefault(parent, []).append(block.block_hash)
            if parent in self.frontier:
                self.frontier.remove(parent)
        if block.block_hash not in self.frontier:
            self.frontier.append(block.block_hash)

    def _apply_transaction(self, tx: Transaction) -> None:
        for tx_input in tx.inputs:
            del self.utxos[(tx_input.prev_txid, tx_input.output_index)]
        for output_index, output in enumerate(tx.outputs):
            self.utxos[(tx.txid, output_index)] = output
        if tx.sender != "GENESIS":
            identity_id = self._tx_identity_id(tx)
            self._ensure_identity_registration(identity_id, self._tx_action_key(tx))
            sender_state = self.sender_states.get(
                identity_id,
                SenderTrajectoryState(sender=identity_id),
            )
            sender_state.trajectory_id = tx.trajectory_id
            sender_state.head_txid = tx.txid
            sender_state.sequence = tx.sequence
            sender_state.recent_epochs = self._trim_epochs(
                [*sender_state.recent_epochs, tx.epoch],
                tx.epoch,
            )
            identity_state = self._identity_state(identity_id)
            self.cold_start.record_compliant_tx(identity_state, tx.delta)
            self.sender_states[identity_id] = sender_state
            self.identity_transition_engine.apply_finalized_action(
                self._identity_action_from_transaction(tx),
                finalized_epoch=tx.epoch,
            )
            self._sync_sender_phase(identity_id)

    @staticmethod
    def _policy_outputs(tx: Transaction) -> List[TxOutput]:
        outputs = [output for output in tx.outputs if output.recipient != tx.sender]
        return outputs or tx.outputs

    @staticmethod
    def _tx_message(
        sender: str,
        identity_id: Optional[str],
        action_type: str,
        action_key: Optional[str],
        inputs: Iterable[TxInput],
        outputs: Iterable[TxOutput],
        trajectory_id: Optional[str],
        prev: Optional[str],
        sequence: int,
        epoch: int,
        policy_hash: str,
        sender_head_commitment: str,
        pending_recovery_id: Optional[str],
        recovery_policy_version: Optional[int],
    ) -> str:
        in_part = ",".join(f"{item.prev_txid}:{item.output_index}" for item in inputs)
        out_part = ",".join(f"{item.recipient}:{item.amount}" for item in outputs)
        trajectory_part = trajectory_id or "null"
        prev_part = prev or "null"
        identity_part = identity_id or sender
        action_key_part = action_key or sender
        pending_part = pending_recovery_id or "null"
        policy_version_part = "null" if recovery_policy_version is None else str(recovery_policy_version)
        return (
            f"{sender}|{identity_part}|{action_type}|{action_key_part}|{trajectory_part}|"
            f"{prev_part}|{sequence}|{epoch}|{policy_hash}|{sender_head_commitment}|"
            f"{pending_part}|{policy_version_part}|{in_part}|{out_part}"
        )

    @staticmethod
    def _merkle_root(transactions: List[Transaction]) -> str:
        if not transactions:
            return "0" * 64
        layer = [tx.txid for tx in transactions]
        while len(layer) > 1:
            if len(layer) % 2 == 1:
                layer.append(layer[-1])
            layer = [
                hashlib.sha256((layer[i] + layer[i + 1]).encode("utf-8")).hexdigest()
                for i in range(0, len(layer), 2)
            ]
        return layer[0]

    @staticmethod
    def _hash_json(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _hash_block_payload(
        self,
        index: int,
        parents: List[str],
        timestamp: int,
        nonce: int,
        producer_id: str,
        producer_phase: str,
        producer_ordering_score: float,
        producer_weight_snapshot: float,
        dynamic_k_snapshot: float,
        aggregate_delta: float,
        trajectory_commitment: str,
        virtual_order_hint: str,
        transactions: List[Transaction],
        merkle_root: str,
    ) -> str:
        payload = {
            "index": index,
            "parents": parents,
            "timestamp": timestamp,
            "nonce": nonce,
            "difficulty": self.difficulty,
            "producer_id": producer_id,
            "producer_phase": producer_phase,
            "producer_ordering_score": producer_ordering_score,
            "producer_weight_snapshot": producer_weight_snapshot,
            "dynamic_k_snapshot": dynamic_k_snapshot,
            "aggregate_delta": aggregate_delta,
            "trajectory_commitment": trajectory_commitment,
            "virtual_order_hint": virtual_order_hint,
            "txids": [tx.txid for tx in transactions],
            "merkle_root": merkle_root,
        }
        return self._hash_json(payload)

    @staticmethod
    def _transaction_to_dict(tx: Transaction) -> dict:
        return {
            "txid": tx.txid,
            "sender": tx.sender,
            "identity_id": tx.identity_id,
            "action_type": tx.action_type,
            "action_key": tx.action_key,
            "trajectory_id": tx.trajectory_id,
            "prev": tx.prev,
            "sequence": tx.sequence,
            "epoch": tx.epoch,
            "policy_hash": tx.policy_hash,
            "delta": tx.delta,
            "sender_head_commitment": tx.sender_head_commitment,
            "approvals": list(tx.approvals),
            "action_payload": dict(tx.action_payload),
            "recovery_policy_version": tx.recovery_policy_version,
            "pending_recovery_id": tx.pending_recovery_id,
            "inputs": [
                {
                    "prev_txid": item.prev_txid,
                    "output_index": item.output_index,
                    "owner": item.owner,
                }
                for item in tx.inputs
            ],
            "outputs": [
                {
                    "amount": item.amount,
                    "recipient": item.recipient,
                }
                for item in tx.outputs
            ],
            "message": tx.message,
            "policy": {
                "epsilon": tx.policy.epsilon,
                "max_amount": tx.policy.max_amount,
                "allowed_recipients": list(tx.policy.allowed_recipients),
            },
            "signature": asdict(tx.signature),
            "timestamp": tx.timestamp,
        }

    @staticmethod
    def _transaction_from_dict(data: dict) -> Transaction:
        return Transaction(
            txid=data["txid"],
            sender=data["sender"],
            trajectory_id=data["trajectory_id"],
            prev=data["prev"],
            sequence=data["sequence"],
            epoch=data["epoch"],
            policy_hash=data["policy_hash"],
            delta=data["delta"],
            sender_head_commitment=data["sender_head_commitment"],
            inputs=[TxInput(**item) for item in data["inputs"]],
            outputs=[TxOutput(**item) for item in data["outputs"]],
            message=data["message"],
            policy=PolicyCommitment.from_values(
                epsilon=data["policy"]["epsilon"],
                max_amount=data["policy"]["max_amount"],
                allowed_recipients=data["policy"]["allowed_recipients"],
            ),
            signature=StructureSignature(**data["signature"]),
            timestamp=data["timestamp"],
            identity_id=data.get("identity_id"),
            action_type=data.get("action_type", "transfer"),
            action_key=data.get("action_key"),
            approvals=list(data.get("approvals", [])),
            action_payload=dict(data.get("action_payload", {})),
            recovery_policy_version=data.get("recovery_policy_version"),
            pending_recovery_id=data.get("pending_recovery_id"),
        )

    def _block_to_dict(self, block: Block) -> dict:
        return {
            "index": block.index,
            "parents": list(block.parents),
            "timestamp": block.timestamp,
            "nonce": block.nonce,
            "difficulty": block.difficulty,
            "producer_id": block.producer_id,
            "producer_phase": block.producer_phase,
            "producer_ordering_score": block.producer_ordering_score,
            "producer_weight_snapshot": block.producer_weight_snapshot,
            "dynamic_k_snapshot": block.dynamic_k_snapshot,
            "aggregate_delta": block.aggregate_delta,
            "trajectory_commitment": block.trajectory_commitment,
            "virtual_order_hint": block.virtual_order_hint,
            "transactions": [self._transaction_to_dict(tx) for tx in block.transactions],
            "merkle_root": block.merkle_root,
            "block_hash": block.block_hash,
        }

    def _block_from_dict(self, data: dict) -> Block:
        return Block(
            index=data["index"],
            parents=list(data["parents"]),
            timestamp=data["timestamp"],
            nonce=data["nonce"],
            difficulty=data["difficulty"],
            producer_id=data["producer_id"],
            producer_phase=data["producer_phase"],
            producer_ordering_score=data["producer_ordering_score"],
            producer_weight_snapshot=data.get("producer_weight_snapshot", data["producer_ordering_score"]),
            dynamic_k_snapshot=data.get("dynamic_k_snapshot", 0.0),
            aggregate_delta=data["aggregate_delta"],
            trajectory_commitment=data["trajectory_commitment"],
            virtual_order_hint=data["virtual_order_hint"],
            transactions=[self._transaction_from_dict(tx) for tx in data["transactions"]],
            merkle_root=data["merkle_root"],
            block_hash=data["block_hash"],
        )

    def _validate_trajectory(self, tx: Transaction) -> None:
        identity_id = self._tx_identity_id(tx)
        sender_state, pending_txs = self._sender_context(identity_id)
        expected_trajectory_id = sender_state.trajectory_id or tx.trajectory_id or self._trajectory_id_for(identity_id)
        expected_prev = pending_txs[-1].txid if pending_txs else sender_state.head_txid
        expected_sequence = (pending_txs[-1].sequence if pending_txs else sender_state.sequence) + 1
        if tx.trajectory_id != expected_trajectory_id:
            raise ValidationError("transaction does not match identity trajectory")
        if tx.prev != expected_prev:
            raise ValidationError("transaction prev does not extend identity head")
        if tx.sequence != expected_sequence:
            raise ValidationError("transaction sequence is not continuous")
        if tx.sender_head_commitment != self._head_commitment(identity_id, tx.prev, tx.sequence):
            raise ValidationError("identity head commitment is invalid")
        for pending_tx in pending_txs:
            if pending_tx.prev == tx.prev:
                raise ValidationError("branch conflict: same prev already used by pending transaction")
            if pending_tx.sequence == tx.sequence:
                raise ValidationError("branch conflict: same identity sequence already present")
            if pending_tx.trajectory_id != tx.trajectory_id:
                raise ValidationError("hidden trajectory reset is not allowed")
        recent_epochs = self._effective_recent_epochs(sender_state, pending_txs)
        recent_in_window = self._trim_epochs(recent_epochs, tx.epoch)
        if len(recent_in_window) >= self.max_txs_per_window:
            raise ValidationError("rate limit exceeded for identity")
        if recent_epochs and (tx.epoch - recent_epochs[-1]) < self.min_tx_gap:
            raise ValidationError("minimum transaction gap violated")

    def _sender_context(self, identity_id: str) -> Tuple[SenderTrajectoryState, List[Transaction]]:
        state = self.sender_states.get(identity_id, SenderTrajectoryState(sender=identity_id))
        pending = [tx for tx in self.mempool if self._tx_identity_id(tx) == identity_id]
        return state, pending

    def _effective_recent_epochs(
        self,
        sender_state: SenderTrajectoryState,
        pending_txs: List[Transaction],
    ) -> List[int]:
        epochs = list(sender_state.recent_epochs)
        epochs.extend(tx.epoch for tx in pending_txs)
        return epochs

    def _identity_state(self, identity_id: str) -> ColdStartState:
        if identity_id not in self.identity_states:
            self.identity_states[identity_id] = self.cold_start.register_identity(identity_id)
        return self.identity_states[identity_id]

    def _sync_sender_phase(self, identity_id: str) -> None:
        sender_state = self.sender_states.setdefault(identity_id, SenderTrajectoryState(sender=identity_id))
        sender_state.phase = self._identity_state(identity_id).phase
        sender_state.branch_conflicts = self._identity_state(identity_id).branch_conflicts
        self._sync_identity_legitimacy(identity_id)

    def _looks_like_branch_conflict(self, tx: Transaction) -> bool:
        identity_id = self._tx_identity_id(tx)
        sender_state, pending_txs = self._sender_context(identity_id)
        expected_prev = pending_txs[-1].txid if pending_txs else sender_state.head_txid
        expected_sequence = (pending_txs[-1].sequence if pending_txs else sender_state.sequence) + 1
        return tx.prev != expected_prev or tx.sequence != expected_sequence

    def _txid_for(self, tx: Transaction) -> str:
        return self._hash_json(
            {
                "sender": tx.sender,
                "identity_id": self._tx_identity_id(tx),
                "action_type": tx.action_type,
                "action_key": self._tx_action_key(tx),
                "trajectory_id": tx.trajectory_id,
                "prev": tx.prev,
                "sequence": tx.sequence,
                "epoch": tx.epoch,
                "policy_hash": tx.policy_hash,
                "delta": tx.delta,
                "sender_head_commitment": tx.sender_head_commitment,
                "approvals": tx.approvals,
                "action_payload": tx.action_payload,
                "recovery_policy_version": tx.recovery_policy_version,
                "pending_recovery_id": tx.pending_recovery_id,
                "inputs": [(i.prev_txid, i.output_index) for i in tx.inputs],
                "outputs": [(o.recipient, o.amount) for o in tx.outputs],
                "message": tx.message,
            }
        )

    @staticmethod
    def _policy_hash(policy: PolicyCommitment) -> str:
        payload = {
            "epsilon": policy.epsilon,
            "max_amount": policy.max_amount,
            "allowed_recipients": list(policy.allowed_recipients),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _normalize_emission_schedule(emission_schedule: List[dict]) -> List[dict]:
        normalized = []
        for stage in emission_schedule:
            normalized.append(
                {
                    "start_block": int(stage["start_block"]),
                    "reward": float(stage["reward"]),
                }
            )
        normalized.sort(key=lambda item: item["start_block"])
        return normalized

    @staticmethod
    def _tx_identity_id(tx: Transaction) -> str:
        return tx.identity_id or tx.sender

    @staticmethod
    def _tx_action_key(tx: Transaction) -> str:
        return tx.action_key or tx.sender

    def _ensure_identity_registration(self, identity_id: str, action_key: str) -> IdentityState:
        state = self.identity_store.get(identity_id)
        if state is None:
            state = self.register_identity(identity_id, [action_key])
        elif action_key and not state.active_action_keys and not state.pending_recovery:
            state.active_action_keys.append(action_key)
            if action_key not in state.active_producer_keys:
                state.active_producer_keys.append(action_key)
            self.identity_store.put(state)
        return state

    def _identity_action_from_transaction(self, tx: Transaction) -> IdentityAction:
        payload = dict(tx.action_payload)
        if tx.pending_recovery_id is not None:
            payload.setdefault("pending_recovery_id", tx.pending_recovery_id)
        if tx.recovery_policy_version is not None:
            payload.setdefault("recovery_policy_version", tx.recovery_policy_version)
        if tx.approvals:
            payload.setdefault("approvals", list(tx.approvals))
        if tx.action_type == "transfer":
            payload.setdefault(
                "inputs",
                [
                    {
                        "prev_txid": tx_input.prev_txid,
                        "output_index": tx_input.output_index,
                        "owner": tx_input.owner,
                    }
                    for tx_input in tx.inputs
                ],
            )
            payload.setdefault(
                "outputs",
                [
                    {
                        "recipient": output.recipient,
                        "amount": output.amount,
                    }
                    for output in tx.outputs
                ],
            )
        return IdentityAction(
            action_id=tx.txid,
            identity_id=self._tx_identity_id(tx),
            action_type=tx.action_type,
            prev_action_id=tx.prev,
            sequence=tx.sequence,
            timestamp=tx.epoch,
            authorizing_key=self._tx_action_key(tx),
            payload=payload,
            policy_hash=tx.policy_hash,
            signature={"approvals": list(tx.approvals)},
        )

    def _validate_identity_action(self, tx: Transaction) -> None:
        identity_id = self._tx_identity_id(tx)
        state = self._ensure_identity_registration(identity_id, self._tx_action_key(tx))
        action = self._identity_action_from_transaction(tx)
        try:
            self.identity_action_validator.validate_against_state(action, state)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def _sync_identity_legitimacy(self, identity_id: str) -> None:
        store_state = self.identity_store.get(identity_id)
        if store_state is None:
            return
        cold_state = self._identity_state(identity_id)
        store_state.phase = cold_state.phase
        store_state.ordering_score = self.cold_start.ordering_score(cold_state)
        store_state.equivocation_count = cold_state.branch_conflicts
        self.identity_store.put(store_state)

    def _rebuild_identity_store(self) -> None:
        self.identity_store = IdentityStateStore()
        for identity_id, sender_state in sorted(self.sender_states.items()):
            cold_state = self._identity_state(identity_id)
            self.identity_store.put(
                IdentityState(
                    identity_id=identity_id,
                    active_action_keys=[identity_id],
                    active_producer_keys=[identity_id],
                    trajectory_head=sender_state.head_txid,
                    sequence=sender_state.sequence,
                    phase=cold_state.phase,
                    ordering_score=self.cold_start.ordering_score(cold_state),
                    equivocation_count=sender_state.branch_conflicts,
                )
            )

    @staticmethod
    def _trajectory_id_for(sender: str) -> str:
        return hashlib.sha256(f"trajectory:{sender}".encode("utf-8")).hexdigest()

    @staticmethod
    def _head_commitment(sender: str, prev: Optional[str], sequence: int) -> str:
        return hashlib.sha256(
            f"{sender}|{prev or 'null'}|{sequence}".encode("utf-8")
        ).hexdigest()

    def _trim_epochs(self, epochs: List[int], current_epoch: int) -> List[int]:
        cutoff = current_epoch - self.rate_limit_window
        return [epoch for epoch in epochs if epoch >= cutoff]

    @staticmethod
    def _transaction_conflicts_in_virtual_order(
        tx: Transaction,
        spent_inputs: set[Tuple[str, int]],
        claimed_slots: set[Tuple[str, int]],
    ) -> bool:
        for tx_input in tx.inputs:
            if (tx_input.prev_txid, tx_input.output_index) in spent_inputs:
                return True
        if tx.sender != "GENESIS" and (Blockchain._tx_identity_id(tx), tx.sequence) in claimed_slots:
            return True
        return False

    def _select_block_parents(self, producer_id: str) -> List[str]:
        main_parent = self.blocks[-1].block_hash
        extra_parents = sorted(parent for parent in self.frontier if parent != main_parent)
        # Keep the first version conservative: one main parent plus a small merge set.
        return [main_parent, *extra_parents[:2]]

    def _validate_block_structure(self, block: Block) -> None:
        if block.index == 0:
            if block.parents:
                raise ValidationError("genesis block must not have parents")
            return
        if not block.parents:
            raise ValidationError("non-genesis block must reference at least one parent")
        for parent in block.parents:
            if parent not in self.block_by_hash:
                raise ValidationError("block references unknown parent")

    def _virtual_order_key(self, block_hash: str) -> tuple:
        dagknight = self._dagknight_state()
        block = self.block_by_hash[block_hash]
        is_blue = 0 if block_hash in dagknight["blue_set"] else 1
        return (
            is_blue,
            -dagknight["cascade_votes"][block_hash],
            -dagknight["subdag_score"][block_hash],
            -block.producer_weight_snapshot,
            *self.producer_priority(block.producer_id, block.timestamp),
            len(block.parents),
            block.block_hash,
        )

    def _dagknight_state(self) -> dict:
        topological_order = [block.block_hash for block in self.blocks]
        ancestors: Dict[str, set[str]] = {}
        indegree: Dict[str, int] = {}
        children: Dict[str, List[str]] = {block_hash: [] for block_hash in topological_order}
        weights: Dict[str, float] = {}
        for block in self.blocks:
            block_hash = block.block_hash
            indegree[block_hash] = len([parent for parent in block.parents if parent in children])
            block_ancestors: set[str] = set()
            for parent in block.parents:
                if parent not in children:
                    continue
                children[parent].append(block_hash)
                block_ancestors.add(parent)
                block_ancestors.update(ancestors[parent])
            ancestors[block_hash] = block_ancestors
            weights[block_hash] = self._block_weight(block_hash)

        descendants: Dict[str, set[str]] = {block_hash: set() for block_hash in topological_order}
        for block_hash in reversed(topological_order):
            for child in children[block_hash]:
                descendants[block_hash].add(child)
                descendants[block_hash].update(descendants[child])

        anticone_members: Dict[str, List[str]] = {}
        anticone_weight: Dict[str, float] = {}
        pairwise_conflicts: Dict[str, set[str]] = {block_hash: set() for block_hash in topological_order}
        for block_hash in topological_order:
            anticone: List[str] = []
            for other_hash in topological_order:
                if other_hash == block_hash:
                    continue
                if other_hash in ancestors[block_hash]:
                    continue
                if block_hash in ancestors[other_hash]:
                    continue
                anticone.append(other_hash)
                pairwise_conflicts[block_hash].add(other_hash)
            anticone_members[block_hash] = anticone
            anticone_weight[block_hash] = sum(weights[other_hash] for other_hash in anticone)

        subdag_score = {
            block_hash: weights[block_hash] + sum(weights[item] for item in descendants[block_hash])
            for block_hash in topological_order
        }

        dynamic_k = self._compute_dynamic_k(topological_order, weights, anticone_weight, pairwise_conflicts, subdag_score)
        blue_set = self._select_blue_set(topological_order, weights, anticone_weight, pairwise_conflicts, dynamic_k)
        cascade_votes = {
            block_hash: sum(
                subdag_score[ancestor]
                for ancestor in ancestors[block_hash]
                if ancestor in blue_set
            ) + (subdag_score[block_hash] if block_hash in blue_set else 0.0)
            for block_hash in topological_order
        }

        ready = [block_hash for block_hash in topological_order if indegree[block_hash] == 0]
        virtual_order: List[str] = []
        local_indegree = dict(indegree)

        def local_virtual_order_key(block_hash: str) -> tuple:
            block = self.block_by_hash[block_hash]
            is_blue = 0 if block_hash in blue_set else 1
            return (
                is_blue,
                -cascade_votes[block_hash],
                -subdag_score[block_hash],
                -block.producer_weight_snapshot,
                *self.producer_priority(block.producer_id, block.timestamp),
                len(block.parents),
                block.block_hash,
            )

        while ready:
            ready.sort(key=local_virtual_order_key)
            current = ready.pop(0)
            virtual_order.append(current)
            for child in children[current]:
                local_indegree[child] -= 1
                if local_indegree[child] == 0:
                    ready.append(child)

        return {
            "topological_order": topological_order,
            "ancestors": ancestors,
            "descendants": descendants,
            "children": children,
            "weights": weights,
            "anticone_members": anticone_members,
            "anticone_weight": anticone_weight,
            "pairwise_conflicts": pairwise_conflicts,
            "subdag_score": subdag_score,
            "dynamic_k": dynamic_k,
            "blue_set": blue_set,
            "cascade_votes": cascade_votes,
            "virtual_order": virtual_order,
        }

    def _compute_dynamic_k(
        self,
        topological_order: List[str],
        weights: Dict[str, float],
        anticone_weight: Dict[str, float],
        pairwise_conflicts: Dict[str, set[str]],
        subdag_score: Dict[str, float],
    ) -> float:
        candidates = [block_hash for block_hash in topological_order if block_hash != self.blocks[0].block_hash]
        if not candidates:
            return 0.0
        total_weight = sum(weights[block_hash] for block_hash in candidates)
        target_weight = total_weight / 2.0
        thresholds = sorted({round(anticone_weight[block_hash], 12) for block_hash in candidates})
        if 0.0 not in thresholds:
            thresholds.insert(0, 0.0)
        ordered_candidates = sorted(
            candidates,
            key=lambda block_hash: (-subdag_score[block_hash], -weights[block_hash], block_hash),
        )
        for k_value in thresholds:
            cluster: List[str] = []
            cluster_weight = 0.0
            for block_hash in ordered_candidates:
                if anticone_weight[block_hash] > k_value:
                    continue
                if any(
                    other_hash in pairwise_conflicts[block_hash]
                    and max(anticone_weight[block_hash], anticone_weight[other_hash]) > k_value
                    for other_hash in cluster
                ):
                    continue
                cluster.append(block_hash)
                cluster_weight += weights[block_hash]
                if cluster_weight >= target_weight:
                    return k_value
        return max(thresholds) if thresholds else 0.0

    def _select_blue_set(
        self,
        topological_order: List[str],
        weights: Dict[str, float],
        anticone_weight: Dict[str, float],
        pairwise_conflicts: Dict[str, set[str]],
        dynamic_k: float,
    ) -> set[str]:
        blue: set[str] = set()
        for block_hash in topological_order:
            if block_hash == self.blocks[0].block_hash:
                blue.add(block_hash)
                continue
            if anticone_weight[block_hash] > dynamic_k:
                continue
            conflicting_blue_weight = sum(
                weights[other_hash]
                for other_hash in blue
                if other_hash in pairwise_conflicts[block_hash]
            )
            if conflicting_blue_weight <= dynamic_k:
                blue.add(block_hash)
        return blue

    def _block_weight(self, block_hash: str) -> float:
        block = self.block_by_hash[block_hash]
        if block_hash == self.blocks[0].block_hash:
            return 1.0
        identity_state = self.identity_store.get(block.producer_id)
        if identity_state is not None:
            return max(identity_state.ordering_score, 0.0)
        return max(block.producer_weight_snapshot, 0.0)

    @staticmethod
    def _aggregate_delta(transactions: List[Transaction]) -> float:
        non_genesis = [tx.delta for tx in transactions if tx.sender != "GENESIS"]
        if not non_genesis:
            return 0.0
        return sum(non_genesis) / len(non_genesis)

    def _producer_trajectory_commitment(self, producer_id: str) -> str:
        identity_state = self.identity_store.get(producer_id)
        if identity_state is not None:
            return self._head_commitment(producer_id, identity_state.trajectory_head, identity_state.sequence)
        state = self.sender_states.get(producer_id, SenderTrajectoryState(sender=producer_id))
        return self._head_commitment(producer_id, state.head_txid, state.sequence)

    @staticmethod
    def _virtual_order_hint(producer_id: str, ordering_score: float, timestamp: int) -> str:
        return hashlib.sha256(
            f"{producer_id}|{ordering_score:.12f}|{timestamp}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _phase_rank(phase: str) -> int:
        ranks = {
            "mature": 3,
            "probation": 2,
            "new": 1,
            "penalized": 0,
        }
        return ranks.get(phase, -1)
