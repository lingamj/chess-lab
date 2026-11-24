#!/usr/bin/env python3
"""Phase-A importer final test suite."""

import os, sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pgn_utils_v2 as pu

DB_TEST = Path("test_phase_a_v2.db")
if DB_TEST.exists():
    DB_TEST.unlink()
os.environ["CHESS_AI_TEST_DB"] = str(DB_TEST)

import database_v2 as db

def count_games():
    conn = sqlite3.connect(DB_TEST)
    n = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    conn.close()
    return n

results = []
def check(name, condition):
    results.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}: {name}")

pgn_platform_game = '''[Event "Test"]
[Site "https://www.chess.com/game/live/879785452"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 *'''

recs = pu.parse_pgn_content_detailed(pgn_platform_game)
assert len(recs) == 1
summary = db.insert_game_audited(recs, source="test", source_file="test.pgn")
check("T01 new=1", summary["new"] == 1 and count_games() == 1)

summary = db.insert_game_audited(recs, source="test", source_file="test.pgn")
check("T02 duplicate_exact=1", summary["duplicate_exact"] == 1 and count_games() == 1)

pgn_variant = '''[Event "Test"]
[Site "Chess.com"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "1-0"]

1. e4 {[%clk 0:05:00]} e5 {[%clk 0:04:58]} 2. Nf3 Nc6'''
recs_var = pu.parse_pgn_content_detailed(pgn_variant)
summary = db.insert_game_audited(recs_var, source="test", source_file="test.pgn")
check("T03 duplicate_semantic=1", summary["duplicate_semantic"] == 1 and count_games() == 1)

pgn_platform_same = '''[Event "Test"]
[White "PlayerA"]
[Black "PlayerB"]
[Site "https://www.chess.com/game/live/879785452"]
[Date "2026.08.10"]
[Result "1-0"]

1. e4 {same game} e5 2. Nf3 Nc6'''
recs_platform_same = pu.parse_pgn_content_detailed(pgn_platform_same)
summary = db.insert_game_audited(recs_platform_same, source="test", source_file="test.pgn")
check("T04 duplicate_platform=1", summary["duplicate_platform"] == 1 and count_games() == 1)

pgn_conflict = '''[Event "Test"]
[Site "https://www.chess.com/game/live/879785452"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "1-0"]

1. d4 d5 2. c4'''
recs_conflict = pu.parse_pgn_content_detailed(pgn_conflict)
summary = db.insert_game_audited(recs_conflict, source="test", source_file="test.pgn")
check("T05 metadata_conflict=1", summary["metadata_conflict"] == 1 and count_games() == 1)

pgn_same = '''[Event "Test"]
[Site "Chess.com"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6'''
recs_same = pu.parse_pgn_content_detailed(pgn_same)
summary = db.insert_game_audited(recs_same, source="test", source_file="test.pgn")
check("T06 duplicate_semantic=1", summary["duplicate_semantic"] == 1 and count_games() == 1)

pgn_diff_result = '''[Event "Test"]
[Site "Chess.com"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "0-1"]

1. e4 e5 2. Nf3 Nc6'''
recs_diff_res = pu.parse_pgn_content_detailed(pgn_diff_result)
summary = db.insert_game_audited(recs_diff_res, source="test", source_file="test.pgn")
check("T07 possible_duplicate=1", summary["possible_duplicate"] == 1 and count_games() == 1)

pgn_reverse = '''[Event "Test"]
[Site "Chess.com"]
[Date "2026.08.10"]
[White "PlayerB"]
[Black "PlayerA"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6'''
recs_reverse = pu.parse_pgn_content_detailed(pgn_reverse)
summary = db.insert_game_audited(recs_reverse, source="test", source_file="test.pgn")
check("T08 reverse new=1", summary["new"] == 1 and count_games() == 2)

pgn_zero = '''[Event "Test"]
[Site "Chess.com"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "0-1"]
[Termination "game abandoned"]

0-1'''
recs_zero = pu.parse_pgn_content_detailed(pgn_zero)
summary = db.insert_game_audited(recs_zero, source="test", source_file="test.pgn")
check("T09 zero_move=1", summary["zero_move"] == 1)

pgn_bad = '''[Event "Test"]
[Site "Chess.com"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "1-0"]

1. e4 e5 2. Qh7'''
recs_bad = pu.parse_pgn_content_detailed(pgn_bad)
summary = db.insert_game_audited(recs_bad, source="test", source_file="test.pgn")
check("T10 illegal_move recorded", summary["invalid"] >= 1)

h1 = pu.parse_pgn_content_detailed(pgn_platform_game)[0]["raw_pgn_hash"]
h2 = pu.parse_pgn_content_detailed(pgn_platform_game)[0]["raw_pgn_hash"]
check("T11 deterministic raw hash", h1 == h2)

mixed = pgn_platform_game + "\n\n" + pgn_zero + "\n\n" + pgn_bad + "\n\n" + pgn_platform_game
all_recs = pu.parse_pgn_content_detailed(mixed)
summary = db.insert_game_audited(all_recs, source="test", source_file="test.pgn")
check("T12 no new on repeat", summary["new"] == 0)
check("T13 reconciliation", summary["source_records"] == 4)

pgn_nag = pgn_platform_game.replace("1. e4 e5", "1. e4 $1 e5 $2")
recs_nag = pu.parse_pgn_content_detailed(pgn_nag)
check("T14 NAGs removed", len(recs_nag) == 1 and recs_nag[0]["parser_status"] == "accepted")

pgn_crlf = pgn_platform_game.replace("\n", "\r\n")
recs_crlf = pu.parse_pgn_content_detailed(pgn_crlf)
check("T15 CRLF handled", len(recs_crlf) == 1 and recs_crlf[0]["parser_status"] == "accepted")

pgn_unsupported = '''[Event "Test"]
[Site "https://www.chess.com/game/live/999999999"]
[Date "2026.08.10"]
[White "PlayerA"]
[Black "PlayerB"]
[Result "1-0"]
[Variant "Chess960"]

1. e4 e5'''
recs_unsup = pu.parse_pgn_content_detailed(pgn_unsupported)
check("T16 unsupported_variant", len(recs_unsup) == 1 and recs_unsup[0]["parser_status"] == "unsupported_variant")
check("T17 platform_id retained for unsupported variant", recs_unsup[0]["platform_game_id"] is not None)

print("\n=== TEST SUMMARY ===")
passed = sum(1 for _, ok in results if ok)
print(f"Passed {passed}/{len(results)}")
if passed != len(results):
    sys.exit(1)
