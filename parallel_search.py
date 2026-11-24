#!/usr/bin/env python3
"""Parallel search using Lazy SMP – shares TT, stop event, and heuristics."""

import threading, time
from search import SearchEngine

class ParallelSearch:
    def __init__(self, nn_evaluator=None, max_depth=10, tt_max=100000, num_threads=2):
        self.nn = nn_evaluator
        self.max_depth = max_depth
        self.tt_max = tt_max
        self.num_threads = num_threads
        self.shared_tt = {}
        self.best_move = None
        self.best_score = None
        self.actual_depth = 0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.start_time = 0
        self.nodes = 0
        self.nodes_lock = threading.Lock()

    def _worker(self, board, time_ms, thread_id):
        searcher = SearchEngine(nn=self.nn,
                                max_depth=self.max_depth,
                                tt_max=self.tt_max)
        searcher.tt = self.shared_tt
        searcher.stop_event = self.stop_event

        local_board = board.copy()
        move, score, depth, nodes = searcher.search(local_board, time_limit=time_ms, depth=self.max_depth)

        if move is not None:
            with self.lock:
                if self.best_move is None or score > self.best_score:
                    self.best_move = move
                    self.best_score = score
                    self.actual_depth = depth

        with self.nodes_lock:
            self.nodes += nodes

    def search(self, board, time_ms=2000):
        self.best_move = None
        self.best_score = None
        self.actual_depth = 0
        self.nodes = 0
        self.shared_tt.clear()
        self.stop_event.clear()
        self.start_time = time.time()

        threads = []
        for i in range(self.num_threads):
            t = threading.Thread(target=self._worker, args=(board, time_ms, i))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return self.best_move, self.best_score, self.actual_depth, self.nodes
