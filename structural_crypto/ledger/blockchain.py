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
        confirmation_threshold: float = 1.5,
    ):
        self.difficulty = difficulty
        self.mining_reward = mining_reward
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
        self.cold_start = ColdStartEngine()
        self._create_genesis_block()

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
        self.block_by_hash[self.blocks[0].block_hash] = self.blocks[0]
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
        block = self._build_block(transactions, miner_address)
        self._apply_block(block)
        self.mempool.clear()
        return block

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
                block.aggregate_delta,
                block.trajectory_commitment,
                block.virtual_order_hint,
                block.transactions,
                block.merkle_root,
            ) != block.block_hash:
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
            }
            for sender, state in self.sender_states.items()
        }

    def virtual_order(self) -> List[str]:
        indegree: Dict[str, int] = {block.block_hash: 0 for block in self.blocks}
        children: Dict[str, List[str]] = {block.block_hash: [] for block in self.blocks}
        for block in self.blocks:
            for parent in block.parents:
                if parent in indegree:
                    indegree[block.block_hash] += 1
                    children[parent].append(block.block_hash)

        ready = [block.block_hash for block in self.blocks if indegree[block.block_hash] == 0]
        ordered: List[str] = []
        while ready:
            ready.sort(key=self._virtual_order_key)
            current = ready.pop(0)
            ordered.append(current)
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        return ordered

    def confirmation_score(self, block_hash: str) -> float:
        if block_hash not in self.block_by_hash:
            raise ValidationError("unknown block for confirmation score")
        visited = set()
        queue = list(self.children_by_hash.get(block_hash, []))
        score = 0.0
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            block = self.block_by_hash[current]
            score += max(block.producer_ordering_score, 0.0)
            queue.extend(self.children_by_hash.get(current, []))
        return score

    def is_confirmed(self, block_hash: str) -> bool:
        if block_hash == self.blocks[0].block_hash:
            return True
        return self.confirmation_score(block_hash) >= self.confirmation_threshold

    def confirmed_order(self) -> List[str]:
        return [block_hash for block_hash in self.virtual_order() if self.is_confirmed(block_hash)]

    def confirmed_reward_for_block(self, block_hash: str) -> float:
        if block_hash not in self.block_by_hash:
            raise ValidationError("unknown block for reward accounting")
        block = self.block_by_hash[block_hash]
        if block.index == 0 or not self.is_confirmed(block_hash):
            return 0.0
        if block.producer_id == "GENESIS":
            return 0.0
        state = self._identity_state(block.producer_id)
        return self.mining_reward * self.cold_start.reward_share(state)

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
        phase_rank = self._phase_rank(identity_state.phase)
        ordering_score = self.cold_start.ordering_score(identity_state)
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
        producer_phase = identity_state.phase
        producer_ordering_score = self.cold_start.ordering_score(identity_state)
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
        parents: List[str],
        timestamp: int,
        nonce: int,
        producer_id: str,
        producer_phase: str,
        producer_ordering_score: float,
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
            "aggregate_delta": aggregate_delta,
            "trajectory_commitment": trajectory_commitment,
            "virtual_order_hint": virtual_order_hint,
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
        block = self.block_by_hash[block_hash]
        return (
            *self.producer_priority(block.producer_id, block.timestamp),
            len(block.parents),
            block.block_hash,
        )

    @staticmethod
    def _aggregate_delta(transactions: List[Transaction]) -> float:
        non_genesis = [tx.delta for tx in transactions if tx.sender != "GENESIS"]
        if not non_genesis:
            return 0.0
        return sum(non_genesis) / len(non_genesis)

    def _producer_trajectory_commitment(self, producer_id: str) -> str:
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
