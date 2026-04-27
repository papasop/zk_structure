"""A minimal policy-enforced UTXO blockchain."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from typing import Dict, Iterable, List, Tuple

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.crypto.signature import StructurePrivateKey
from .models import Block, Transaction, TxInput, TxOutput


class ValidationError(ValueError):
    """Raised when a transaction or block is invalid."""


class Blockchain:
    def __init__(self, difficulty: int = 3, mining_reward: int = 25):
        self.difficulty = difficulty
        self.mining_reward = mining_reward
        self.blocks: List[Block] = []
        self.mempool: List[Transaction] = []
        self.utxos: Dict[Tuple[str, int], TxOutput] = {}
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
        tx = Transaction(
            txid=self._hash_json({"type": "faucet", "recipient": recipient, "amount": amount, "at": len(self.blocks)}),
            sender="GENESIS",
            inputs=[],
            outputs=[TxOutput(amount=amount, recipient=recipient)],
            message=f"GENESIS->{recipient}:{amount}",
            policy=genesis_policy,
            signature=genesis_key.sign(
                message=f"GENESIS->{recipient}:{amount}",
                policy=genesis_policy,
                amount=amount,
                recipients=[recipient],
            ),
            timestamp=int(time.time()),
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
    ) -> Transaction:
        total_amount = sum(amount for _, amount in recipients)
        selected_inputs, input_total = self._select_utxos(key.public_key, total_amount)
        outputs = [TxOutput(amount=amount, recipient=recipient) for recipient, amount in recipients]
        if input_total > total_amount:
            outputs.append(TxOutput(amount=input_total - total_amount, recipient=key.public_key))
        message = self._tx_message(key.public_key, selected_inputs, outputs)
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
                    "inputs": [(i.prev_txid, i.output_index) for i in selected_inputs],
                    "outputs": [(o.recipient, o.amount) for o in outputs],
                    "message": message,
                }
            ),
            sender=key.public_key,
            inputs=selected_inputs,
            outputs=outputs,
            message=message,
            policy=policy,
            signature=signature,
            timestamp=int(time.time()),
        )
        self.validate_transaction(tx, signer_seed=key.seed)
        return tx

    def add_transaction(self, tx: Transaction, signer_seed: str) -> None:
        self.validate_transaction(tx, signer_seed=signer_seed)
        self.mempool.append(tx)

    def validate_transaction(self, tx: Transaction, signer_seed: str) -> None:
        input_total = 0
        for tx_input in tx.inputs:
            key = (tx_input.prev_txid, tx_input.output_index)
            if key not in self.utxos:
                raise ValidationError(f"missing UTXO {key}")
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

    def mine_block(self, miner_address: str) -> Block:
        reward_tx = self._build_reward_transaction(miner_address)
        transactions = [*self.mempool, reward_tx]
        block = self._build_block(transactions)
        self._apply_block(block)
        self.mempool.clear()
        return block

    def validate_chain(self) -> bool:
        temp_utxos: Dict[Tuple[str, int], TxOutput] = {}
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
                    for tx_input in tx.inputs:
                        key = (tx_input.prev_txid, tx_input.output_index)
                        if key not in temp_utxos:
                            return False
                        del temp_utxos[key]
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
        message = f"REWARD->{miner_address}:{self.mining_reward}@{len(self.blocks)}"
        key = StructurePrivateKey("miner-reward", "genesis-seed")
        genesis_policy = PolicyCommitment.from_values(epsilon=10.0)
        return Transaction(
            txid=self._hash_json({"type": "reward", "miner": miner_address, "height": len(self.blocks)}),
            sender="GENESIS",
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
            timestamp=int(time.time()),
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

    @staticmethod
    def _policy_outputs(tx: Transaction) -> List[TxOutput]:
        outputs = [output for output in tx.outputs if output.recipient != tx.sender]
        return outputs or tx.outputs

    @staticmethod
    def _tx_message(sender: str, inputs: Iterable[TxInput], outputs: Iterable[TxOutput]) -> str:
        in_part = ",".join(f"{item.prev_txid}:{item.output_index}" for item in inputs)
        out_part = ",".join(f"{item.recipient}:{item.amount}" for item in outputs)
        return f"{sender}|{in_part}|{out_part}"

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
