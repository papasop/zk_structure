"""A minimal policy-enforced UTXO blockchain."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Tuple

from structural_crypto.consensus import ColdStartEngine, ColdStartState
from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.crypto.signature import StructurePrivateKey
from .models import Block, SenderTrajectoryState, Transaction, TxInput, TxOutput


class ValidationError(ValueError):
    """Raised when a transaction or block is invalid."""


class Blockchain:
    def __init__(
        self,
        difficulty: int = 3,
        mining_reward: int = 25,
        rate_limit_window: int = 60,
        max_txs_per_window: int = 3,
        min_tx_gap: int = 1,
        allow_probationary_producers: bool = False,
        allow_new_producers: bool = False,
    ):
        self.difficulty = difficulty
        self.mining_reward = mining_reward
        self.rate_limit_window = rate_limit_window
        self.max_txs_per_window = max_txs_per_window
        self.min_tx_gap = min_tx_gap
        self.allow_probationary_producers = allow_probationary_producers
        self.allow_new_producers = allow_new_producers
        self.blocks: List[Block] = []
        self.mempool: List[Transaction] = []
        self.utxos: Dict[Tuple[str, int], TxOutput] = {}
        self.sender_states: Dict[str, SenderTrajectoryState] = {}
        self.identity_states: Dict[str, ColdStartState] = {}
        self.cold_start = ColdStartEngine()
        self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        block = Block(
            index=0,
            prev_hash="0" * 64,
            timestamp=int(time.time()),
            nonce=0,
            difficulty=self.difficulty,
            transactions=[],
            merkle_root=self._merkle_root([]),
            block_hash="0" * 64,
        )
        self.blocks.append(block)

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
                inputs=[],
                outputs=[TxOutput(amount=amount, recipient=recipient)],
                trajectory_id=None,
                prev=None,
                sequence=0,
                epoch=timestamp,
                policy_hash=policy_hash,
                sender_head_commitment=self._head_commitment("GENESIS", None, 0),
            ),
            policy=genesis_policy,
            signature=genesis_key.sign(
                message=self._tx_message(
                    sender="GENESIS",
                    inputs=[],
                    outputs=[TxOutput(amount=amount, recipient=recipient)],
                    trajectory_id=None,
                    prev=None,
                    sequence=0,
                    epoch=timestamp,
                    policy_hash=policy_hash,
                    sender_head_commitment=self._head_commitment("GENESIS", None, 0),
                ),
                policy=genesis_policy,
                amount=amount,
                recipients=[recipient],
            ),
            timestamp=timestamp,
        )
        self._apply_transaction(tx)
        genesis = self.blocks[0]
        genesis_transactions = [*genesis.transactions, tx]
        self.blocks[0] = replace(
            genesis,
            transactions=genesis_transactions,
            merkle_root=self._merkle_root(genesis_transactions),
        )
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
        sender_state, pending_txs = self._sender_context(key.public_key)
        trajectory_id = sender_state.trajectory_id or self._trajectory_id_for(key.public_key)
        prev = pending_txs[-1].txid if pending_txs else sender_state.head_txid
        sequence = (pending_txs[-1].sequence if pending_txs else sender_state.sequence) + 1
        timestamp = timestamp or int(time.time())
        policy_hash = self._policy_hash(policy)
        head_commitment = self._head_commitment(key.public_key, prev, sequence)
        message = self._tx_message(
            sender=key.public_key,
            inputs=selected_inputs,
            outputs=outputs,
            trajectory_id=trajectory_id,
            prev=prev,
            sequence=sequence,
            epoch=timestamp,
            policy_hash=policy_hash,
            sender_head_commitment=head_commitment,
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
                    "trajectory_id": trajectory_id,
                    "prev": prev,
                    "sequence": sequence,
                    "epoch": timestamp,
                    "policy_hash": policy_hash,
                    "delta": signature.delta,
                    "sender_head_commitment": head_commitment,
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
        )
        self.validate_transaction(tx, signer_seed=key.seed)
        return tx

    def add_transaction(self, tx: Transaction, signer_seed: str) -> None:
        try:
            self.validate_transaction(tx, signer_seed=signer_seed)
        except ValidationError:
            if tx.sender != "GENESIS":
                self._identity_state(tx.sender)
                self.cold_start.record_rejected_tx(
                    self.identity_states[tx.sender],
                    branch_conflict=self._looks_like_branch_conflict(tx),
                )
                self._sync_sender_phase(tx.sender)
            raise
        self.mempool.append(tx)

    def validate_transaction(self, tx: Transaction, signer_seed: str) -> None:
        if tx.message != self._tx_message(
            sender=tx.sender,
            inputs=tx.inputs,
            outputs=tx.outputs,
            trajectory_id=tx.trajectory_id,
            prev=tx.prev,
            sequence=tx.sequence,
            epoch=tx.epoch,
            policy_hash=tx.policy_hash,
            sender_head_commitment=tx.sender_head_commitment,
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
        if not tx.inputs and tx.sender != "GENESIS":
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
            self._validate_trajectory(tx)

    def mine_block(self, miner_address: str) -> Block:
        if not self.producer_is_eligible(miner_address):
            raise ValidationError("producer is not eligible to mine blocks")
        reward_tx = self._build_reward_transaction(miner_address)
        transactions = [*self.mempool, reward_tx]
        block = self._build_block(transactions)
        self._apply_block(block)
        self.mempool.clear()
        return block

    def validate_chain(self) -> bool:
        temp_utxos: Dict[Tuple[str, int], TxOutput] = {}
        temp_sender_states: Dict[str, SenderTrajectoryState] = {}
        previous_hash = "0" * 64
        for index, block in enumerate(self.blocks):
            if index == 0:
                for tx in block.transactions:
                    for output_index, output in enumerate(tx.outputs):
                        temp_utxos[(tx.txid, output_index)] = output
                previous_hash = block.block_hash
                continue
            if block.prev_hash != previous_hash:
                return False
            if not block.block_hash.startswith("0" * block.difficulty):
                return False
            if self._hash_block_payload(block.index, block.prev_hash, block.timestamp, block.nonce, block.transactions, block.merkle_root) != block.block_hash:
                return False
            for tx in block.transactions:
                if tx.sender != "GENESIS":
                    temp_state = temp_sender_states.get(
                        tx.sender,
                        SenderTrajectoryState(sender=tx.sender),
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
                    temp_sender_states[tx.sender] = temp_state
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
                "prev_hash": block.prev_hash,
                "transactions": [tx.txid for tx in block.transactions],
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
            }
            for sender, state in self.sender_states.items()
        }

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

    def _build_reward_transaction(self, miner_address: str) -> Transaction:
        timestamp = int(time.time())
        key = StructurePrivateKey("miner-reward", "genesis-seed")
        genesis_policy = PolicyCommitment.from_values(epsilon=10.0)
        policy_hash = self._policy_hash(genesis_policy)
        head_commitment = self._head_commitment("GENESIS", None, len(self.blocks))
        message = self._tx_message(
            sender="GENESIS",
            inputs=[],
            outputs=[TxOutput(amount=self.mining_reward, recipient=miner_address)],
            trajectory_id=None,
            prev=None,
            sequence=len(self.blocks),
            epoch=timestamp,
            policy_hash=policy_hash,
            sender_head_commitment=head_commitment,
        )
        return Transaction(
            txid=self._hash_json({"type": "reward", "miner": miner_address, "height": len(self.blocks)}),
            sender="GENESIS",
            trajectory_id=None,
            prev=None,
            sequence=len(self.blocks),
            epoch=timestamp,
            policy_hash=policy_hash,
            delta=0.0,
            sender_head_commitment=head_commitment,
            inputs=[],
            outputs=[TxOutput(amount=self.mining_reward, recipient=miner_address)],
            message=message,
            policy=genesis_policy,
            signature=key.sign(
                message=message,
                policy=genesis_policy,
                amount=self.mining_reward,
                recipients=[miner_address],
            ),
            timestamp=timestamp,
        )

    def _build_block(self, transactions: List[Transaction]) -> Block:
        prev_hash = self.blocks[-1].block_hash
        index = len(self.blocks)
        timestamp = int(time.time())
        merkle_root = self._merkle_root(transactions)
        nonce = 0
        while True:
            block_hash = self._hash_block_payload(
                index, prev_hash, timestamp, nonce, transactions, merkle_root
            )
            if block_hash.startswith("0" * self.difficulty):
                return Block(
                    index=index,
                    prev_hash=prev_hash,
                    timestamp=timestamp,
                    nonce=nonce,
                    difficulty=self.difficulty,
                    transactions=transactions,
                    merkle_root=merkle_root,
                    block_hash=block_hash,
                )
            nonce += 1

    def _apply_block(self, block: Block) -> None:
        for tx in self.mempool:
            self._apply_transaction(tx)
        self._apply_transaction(block.transactions[-1])
        self.blocks.append(block)

    def _apply_transaction(self, tx: Transaction) -> None:
        for tx_input in tx.inputs:
            del self.utxos[(tx_input.prev_txid, tx_input.output_index)]
        for output_index, output in enumerate(tx.outputs):
            self.utxos[(tx.txid, output_index)] = output
        if tx.sender != "GENESIS":
            sender_state = self.sender_states.get(
                tx.sender,
                SenderTrajectoryState(sender=tx.sender),
            )
            sender_state.trajectory_id = tx.trajectory_id
            sender_state.head_txid = tx.txid
            sender_state.sequence = tx.sequence
            sender_state.recent_epochs = self._trim_epochs(
                [*sender_state.recent_epochs, tx.epoch],
                tx.epoch,
            )
            identity_state = self._identity_state(tx.sender)
            self.cold_start.record_compliant_tx(identity_state, tx.delta)
            self.sender_states[tx.sender] = sender_state
            self._sync_sender_phase(tx.sender)

    @staticmethod
    def _policy_outputs(tx: Transaction) -> List[TxOutput]:
        outputs = [output for output in tx.outputs if output.recipient != tx.sender]
        return outputs or tx.outputs

    @staticmethod
    def _tx_message(
        sender: str,
        inputs: Iterable[TxInput],
        outputs: Iterable[TxOutput],
        trajectory_id: Optional[str],
        prev: Optional[str],
        sequence: int,
        epoch: int,
        policy_hash: str,
        sender_head_commitment: str,
    ) -> str:
        in_part = ",".join(f"{item.prev_txid}:{item.output_index}" for item in inputs)
        out_part = ",".join(f"{item.recipient}:{item.amount}" for item in outputs)
        trajectory_part = trajectory_id or "null"
        prev_part = prev or "null"
        return (
            f"{sender}|{trajectory_part}|{prev_part}|{sequence}|{epoch}|"
            f"{policy_hash}|{sender_head_commitment}|{in_part}|{out_part}"
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
        prev_hash: str,
        timestamp: int,
        nonce: int,
        transactions: List[Transaction],
        merkle_root: str,
    ) -> str:
        payload = {
            "index": index,
            "prev_hash": prev_hash,
            "timestamp": timestamp,
            "nonce": nonce,
            "difficulty": self.difficulty,
            "txids": [tx.txid for tx in transactions],
            "merkle_root": merkle_root,
        }
        return self._hash_json(payload)

    def _validate_trajectory(self, tx: Transaction) -> None:
        sender_state, pending_txs = self._sender_context(tx.sender)
        expected_trajectory_id = sender_state.trajectory_id or tx.trajectory_id or self._trajectory_id_for(tx.sender)
        expected_prev = pending_txs[-1].txid if pending_txs else sender_state.head_txid
        expected_sequence = (pending_txs[-1].sequence if pending_txs else sender_state.sequence) + 1
        if tx.trajectory_id != expected_trajectory_id:
            raise ValidationError("transaction does not match sender trajectory")
        if tx.prev != expected_prev:
            raise ValidationError("transaction prev does not extend sender head")
        if tx.sequence != expected_sequence:
            raise ValidationError("transaction sequence is not continuous")
        if tx.sender_head_commitment != self._head_commitment(tx.sender, tx.prev, tx.sequence):
            raise ValidationError("sender head commitment is invalid")
        for pending_tx in pending_txs:
            if pending_tx.prev == tx.prev:
                raise ValidationError("branch conflict: same prev already used by pending transaction")
            if pending_tx.sequence == tx.sequence:
                raise ValidationError("branch conflict: same sender sequence already present")
            if pending_tx.trajectory_id != tx.trajectory_id:
                raise ValidationError("hidden trajectory reset is not allowed")
        recent_epochs = self._effective_recent_epochs(sender_state, pending_txs)
        recent_in_window = self._trim_epochs(recent_epochs, tx.epoch)
        if len(recent_in_window) >= self.max_txs_per_window:
            raise ValidationError("rate limit exceeded for sender")
        if recent_epochs and (tx.epoch - recent_epochs[-1]) < self.min_tx_gap:
            raise ValidationError("minimum transaction gap violated")

    def _sender_context(self, sender: str) -> Tuple[SenderTrajectoryState, List[Transaction]]:
        state = self.sender_states.get(sender, SenderTrajectoryState(sender=sender))
        pending = [tx for tx in self.mempool if tx.sender == sender]
        return state, pending

    def _effective_recent_epochs(
        self,
        sender_state: SenderTrajectoryState,
        pending_txs: List[Transaction],
    ) -> List[int]:
        epochs = list(sender_state.recent_epochs)
        epochs.extend(tx.epoch for tx in pending_txs)
        return epochs

    def _identity_state(self, sender: str) -> ColdStartState:
        if sender not in self.identity_states:
            self.identity_states[sender] = self.cold_start.register_identity(sender)
        return self.identity_states[sender]

    def _sync_sender_phase(self, sender: str) -> None:
        sender_state = self.sender_states.setdefault(sender, SenderTrajectoryState(sender=sender))
        sender_state.phase = self._identity_state(sender).phase
        sender_state.branch_conflicts = self._identity_state(sender).branch_conflicts

    def _looks_like_branch_conflict(self, tx: Transaction) -> bool:
        sender_state, pending_txs = self._sender_context(tx.sender)
        expected_prev = pending_txs[-1].txid if pending_txs else sender_state.head_txid
        expected_sequence = (pending_txs[-1].sequence if pending_txs else sender_state.sequence) + 1
        return tx.prev != expected_prev or tx.sequence != expected_sequence

    def _txid_for(self, tx: Transaction) -> str:
        return self._hash_json(
            {
                "sender": tx.sender,
                "trajectory_id": tx.trajectory_id,
                "prev": tx.prev,
                "sequence": tx.sequence,
                "epoch": tx.epoch,
                "policy_hash": tx.policy_hash,
                "delta": tx.delta,
                "sender_head_commitment": tx.sender_head_commitment,
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
