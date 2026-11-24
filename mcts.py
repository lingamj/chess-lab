#!/usr/bin/env python3
"""Monte Carlo Tree Search – zero‑copy (make/undo), uses global move indexing."""

import math
import random
import numpy as np
from board import ChessBoard
from nn import DualNet
from move_helpers import move_to_index, index_to_move, NUM_MOVES

class MCTSNode:
    __slots__ = ('move', 'parent', 'children', 'visits', 'total_value',
                 'prior', 'board_hash')
    def __init__(self, move=None, parent=None, prior=0.0, board_hash=None):
        self.move = move
        self.parent = parent
        self.children = {}
        self.visits = 0
        self.total_value = 0.0
        self.prior = prior
        self.board_hash = board_hash

class MCTS:
    def __init__(self, nn, num_simulations=800, c_puct=1.4, dirichlet_alpha=0.3, dirichlet_frac=0.25):
        self.nn = nn
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.dirichlet_alpha = dirichlet_alpha
        self.dirichlet_frac = dirichlet_frac

    def search(self, board, temperature=1.0):
        """Run MCTS and return a policy dictionary mapping moves to probabilities."""
        legal_moves = board.generate_legal_moves()
        if not legal_moves:
            return {}

        # Temporarily disable repetition tracking for speed
        original_track = board.track_repetition if hasattr(board, 'track_repetition') else True
        board.track_repetition = False

        try:
            root = MCTSNode(board_hash=board.hash)
            _, policy_logits = self.nn.evaluate(board)

            if len(policy_logits) != NUM_MOVES:
                raise ValueError(f"Expected {NUM_MOVES} policy logits, got {len(policy_logits)}")

            # Build move indices with safety check
            move_indices = []
            for move in legal_moves:
                idx = move_to_index(move)
                if idx < 0:
                    raise ValueError(f"Invalid move index for {move}")
                move_indices.append(idx)

            logits = np.array([policy_logits[idx] for idx in move_indices], dtype=np.float32)
            policy = self._softmax(logits)

            if self.dirichlet_alpha > 0 and len(policy) > 1:
                noise = np.random.dirichlet([self.dirichlet_alpha] * len(policy))
                policy = (1 - self.dirichlet_frac) * policy + self.dirichlet_frac * noise

            for i, move in enumerate(legal_moves):
                root.children[move] = MCTSNode(move=move, parent=root, prior=policy[i],
                                               board_hash=board.hash)

            for _ in range(self.num_simulations):
                node = root
                path = [node]
                undo_stack = []

                # Selection
                while node.children:
                    best_score = -float('inf')
                    best_move = None
                    best_child = None
                    total_visits = node.visits
                    for move, child in node.children.items():
                        q = child.total_value / (child.visits + 1e-8)
                        u = self.c_puct * child.prior * math.sqrt(total_visits + 1) / (1 + child.visits)
                        score = q + u
                        if score > best_score:
                            best_score = score
                            best_move = move
                            best_child = child
                    undo = board.make_move(best_move)
                    undo_stack.append(undo)
                    node = best_child
                    path.append(node)

                # Expansion and evaluation
                value, policy_logits = self.nn.evaluate(board)
                if board.is_checkmate():
                    value = -1.0
                elif board.is_draw():
                    value = 0.0

                legal = board.generate_legal_moves()
                if legal and not board.is_draw() and not board.is_checkmate():
                    if len(policy_logits) != NUM_MOVES:
                        raise ValueError(f"Expected {NUM_MOVES} policy logits, got {len(policy_logits)}")
                    move_indices = []
                    for move in legal:
                        idx = move_to_index(move)
                        if idx < 0:
                            raise ValueError(f"Invalid move index for {move}")
                        move_indices.append(idx)
                    logits = np.array([policy_logits[idx] for idx in move_indices], dtype=np.float32)
                    policy = self._softmax(logits)
                    for i, move in enumerate(legal):
                        node.children[move] = MCTSNode(move=move, parent=node, prior=policy[i],
                                                       board_hash=board.hash)

                # Backpropagation
                for n in reversed(path):
                    n.visits += 1
                    n.total_value += value
                    value = -value

                # Undo moves
                for undo in reversed(undo_stack):
                    board.undo_move(undo)

        finally:
            # Restore repetition tracking
            board.track_repetition = original_track

        # Compute final policy
        total_visits = sum(child.visits for child in root.children.values())
        final_policy = {}
        if total_visits == 0:
            for move in root.children:
                final_policy[move] = 1.0 / len(root.children)
        else:
            for move, child in root.children.items():
                if temperature == 0:
                    final_policy[move] = child.visits
                else:
                    final_policy[move] = (child.visits ** (1.0 / temperature))
            total = sum(final_policy.values())
            if total > 0:
                for move in final_policy:
                    final_policy[move] /= total
            else:
                for move in final_policy:
                    final_policy[move] = 1.0 / len(final_policy)

        return final_policy

    def _softmax(self, x):
        if x.size == 0:
            return np.array([])
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()
