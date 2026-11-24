#!/usr/bin/env python3
"""Benchmark harness v2.4 – final frozen version."""
import time, os, sys, random, platform
from collections import OrderedDict
from datetime import datetime
from board import ChessBoard
from nn import DualNet
from search import SearchEngine, NN_SCALE, MATE_SCORE

MODEL_PATH = 'distilled_nn.pkl'
BENCHMARK_VERSION = "2.4"
BENCH_DEPTH = 15
BENCH_TIME_MS = 1000
TT_SIZE = 100000
SELFPLAY_TIME_MS = 100
SELFPLAY_DEPTH = 5
SELFPLAY_GAMES = 10
MATE_IN_1_SCORE = MATE_SCORE - 1

class CountingOrderedDict(OrderedDict):
    """Instrument TT operations while preserving OrderedDict semantics.

    Subclasses OrderedDict, not dict, because production SearchEngine
    uses OrderedDict for its TT. Two consequences of subclassing dict:
    - popitem(last=False) at search.py:1449 raises TypeError on plain dict
    - dict.get() is faster than OrderedDict.get(), distorting NPS metrics
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hits = 0
        self.writes = 0
        self.probes = 0
    def get(self, key, *args, **kwargs):
        self.probes += 1
        res = super().get(key, *args, **kwargs)
        if res is not None:
            self.hits += 1
        return res
    def __setitem__(self, key, value):
        self.writes += 1
        super().__setitem__(key, value)

MATES = {
    # P5.15I.1: verified legal positions with unique mate-in-1 moves.
    "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4": "h5f7",
    "7k/6pp/8/8/8/8/8/R6K w - - 0 1": "a1a8",
    "7k/5ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 1": "d1d8",
    "6rk/6pp/7N/8/8/8/8/7K w - - 0 1": "h6f7",
}

MATES_DEEP = {
    # P5.15J: mate-in-3 and mate-in-5 fixtures, each confirmed
    # against Stockfish 19 and re-verified against the live engine.
    # Value is (expected_uci, expected_score, depth, time_limit_ms).
    "6k1/5pp1/8/8/8/8/5PP1/1R1Q2K1 w - - 0 1": ("b1b8", MATE_SCORE - 3, 5, 5000),
    "8/8/8/8/n7/K7/4Q3/2k5 w - - 0 1": ("a3a4", MATE_SCORE - 5, 7, 10000),
    "8/8/8/8/K7/6R1/8/1k6 w - - 0 1": ("a4b3", MATE_SCORE - 5, 5, 10000),
}


def tactical_test(nn, time_ms=500, log=print):
    correct = total = 0
    from move_helpers import move_to_str

    for fen, expected in MATES.items():
        board = ChessBoard()
        board.set_fen(fen)
        engine = SearchEngine(nn=nn, max_depth=10, tt_max=TT_SIZE)
        move, score, depth, nodes = engine.search(
            board, time_limit=time_ms, depth=10
        )

        # Count every fixture, including a search returning no move.
        total += 1

        if move is None:
            log(f"    FAIL  {fen[:48]:<50} expected={expected} "
                f"engine=None score={score} depth={depth} nodes={nodes}")
            continue

        uci = move_to_str(move)
        ok = (uci == expected and score == MATE_IN_1_SCORE)
        if ok:
            correct += 1

        log(f"    {'PASS' if ok else 'FAIL'}  {fen[:48]:<50} "
            f"expected={expected} engine={uci} "
            f"score={score} depth={depth} nodes={nodes}")

    return correct, total


def tactical_deep_test(nn, log=print):
    correct = total = 0
    from move_helpers import move_to_str

    for fen, (expected, expected_score, depth, time_ms) in MATES_DEEP.items():
        board = ChessBoard()
        board.set_fen(fen)
        engine = SearchEngine(nn=nn, max_depth=depth, tt_max=TT_SIZE)
        move, score, reached, nodes = engine.search(
            board, time_limit=time_ms, depth=depth
        )

        total += 1

        if move is None:
            log(f"    FAIL  {fen[:48]:<50} expected={expected} "
                f"engine=None score={score}")
            continue

        uci = move_to_str(move)
        accepted = engine.accepted_root_depth
        if accepted < depth:
            log(f"    WARN  accepted depth {accepted} < requested {depth} for {fen[:32]}")
        ok = (uci == expected and score == expected_score)
        if ok:
            correct += 1

        log(f"    {'PASS' if ok else 'FAIL'}  {fen[:48]:<50} "
            f"expected={expected}@{expected_score} "
            f"engine={uci}@{score} accepted={accepted} "
            f"nodes={nodes}")

    return correct, total


def search_perf_test(nn, fen, time_ms=BENCH_TIME_MS, depth=BENCH_DEPTH):
    engine = SearchEngine(nn=nn, max_depth=20, tt_max=TT_SIZE)
    cdict = CountingOrderedDict()
    engine.tt = cdict
    board = ChessBoard()
    board.set_fen(fen)
    start = time.time()
    move, score, reached_depth, nodes = engine.search(board, time_limit=time_ms, depth=depth)
    elapsed = time.time() - start
    nps = nodes / elapsed if elapsed > 0 else 0
    return (nodes, nps, reached_depth, elapsed,
            cdict.probes, cdict.hits, cdict.writes)

def main():
    random.seed(0)
    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)
    run_time = datetime.now()
    log("=" * 60)
    log(f"             ENGINE BENCHMARK v{BENCHMARK_VERSION}")
    log("=" * 60)
    log(f"Run time   : {run_time.isoformat(timespec='seconds')}")
    log(f"Python     : {platform.python_version()}")
    log(f"Platform   : {platform.platform()}")

    nn = DualNet()
    if not nn.load(MODEL_PATH):
        log(f"ERROR: {MODEL_PATH} not found.")
        sys.exit(1)

    log(f"\nConfiguration:")
    log(f"  Model        : {MODEL_PATH}")
    log(f"  Bench depth  : {BENCH_DEPTH}")
    log(f"  Bench time   : {BENCH_TIME_MS} ms")
    log(f"  TT size      : {TT_SIZE}")
    log(f"  NN scale     : {NN_SCALE}")
    log(f"  Random seed  : 0")

    log("\n[1] Search speed (5 positions, 1 sec each)")
    test_fens = [
        ChessBoard().to_fen(),
        "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/8/8/8/8/3k4/8/3QK3 w - - 0 1",
        "rnbq1k1r/pppp1ppp/4pn2/8/2BPP3/5N2/PPP2PPP/RNBQK2R b KQ - 2 4",
    ]
    total_nodes = total_time = total_probes = total_hits = total_writes = 0
    per_pos_nps = []
    for fen in test_fens:
        (nodes, nps, depth, elapsed, probes, hits, writes) = search_perf_test(nn, fen, BENCH_TIME_MS, BENCH_DEPTH)
        total_nodes += nodes
        total_time += elapsed
        total_probes += probes
        total_hits += hits
        total_writes += writes
        per_pos_nps.append(nps)
        log(f"  {fen[:40]}... nodes={nodes:>6} depth={depth:>2} NPS={int(nps):>6} time={elapsed:.2f}s")
    overall_nps = total_nodes / total_time if total_time > 0 else 0
    avg_pos_nps = sum(per_pos_nps) / len(per_pos_nps) if per_pos_nps else 0
    hit_rate = (total_hits / total_probes * 100) if total_probes > 0 else 0
    log(f"\n  Search summary:")
    log(f"    Overall NPS    : {int(overall_nps):>8}")
    log(f"    Average pos NPS: {int(avg_pos_nps):>8}")
    log(f"    TT probes      : {total_probes:>8}")
    log(f"    TT hits        : {total_hits:>8}  ({hit_rate:.1f}%)")
    log(f"    TT writes      : {total_writes:>8}")

    log("\n[2] Tactical (mate‑in‑1) accuracy")
    correct, total = tactical_test(nn, time_ms=500, log=log)
    log(f"  Solved {correct}/{total}")
    if total == 0 or correct != total:
        log("  FATAL: mandatory mate-in-1 benchmark gate failed")
        raise SystemExit(1)

    log("\n[2b] Tactical (mate-in-3 and mate-in-5) accuracy")
    deep_correct, deep_total = tactical_deep_test(nn, log=log)
    log(f"  Solved {deep_correct}/{deep_total}")
    if deep_total == 0 or deep_correct != deep_total:
        log("  FATAL: mandatory deep-tactical benchmark gate failed")
        raise SystemExit(1)

    log("\n[3] Self‑play stability (10 games, 100ms/move)")
    illegal = crashes = 0
    game_lengths = []
    total_nodes_self = 0
    for game_num in range(SELFPLAY_GAMES):
        board = ChessBoard()
        engine = SearchEngine(nn=nn, max_depth=20, tt_max=TT_SIZE)
        engine.tt.clear()
        moves = 0
        try:
            for move_num in range(80):
                legal = board.generate_legal_moves()
                if not legal or board.is_checkmate() or board.is_draw():
                    break
                move, score, depth, nodes = engine.search(board, time_limit=SELFPLAY_TIME_MS, depth=SELFPLAY_DEPTH)
                if move is None or move not in legal:
                    illegal += 1
                    break
                board.make_move(move)
                moves += 1
                total_nodes_self += nodes
            game_lengths.append(moves)
        except Exception as e:
            crashes += 1
            log(f"    Crash in game {game_num+1}: {e}")
    avg_len = sum(game_lengths)/len(game_lengths) if game_lengths else 0
    log(f"  Games: {SELFPLAY_GAMES}  Illegal moves: {illegal}  Crashes: {crashes}")
    log(f"  Avg game length: {avg_len:.1f} plies  Avg nodes/game: {total_nodes_self//SELFPLAY_GAMES}")
    if illegal > 0 or crashes > 0:
        log("  FATAL: self-play stability gate failed")
        raise SystemExit(1)

    log("\n" + "=" * 60)
    log("Benchmark complete.")
    log("=" * 60)

    timestamp = run_time.strftime("%Y%m%d_%H%M%S")
    log_path = f"benchmark_{timestamp}.txt"
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nResults saved to {log_path}")

if __name__ == '__main__':
    main()
