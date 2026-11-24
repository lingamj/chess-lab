#!/usr/bin/env python3
"""Phase-A parser + identity engine (final corrected)."""

import re, hashlib
from board import ChessBoard
from pgn_utils import pgn_to_move, _remove_variations
from move_helpers import move_to_str


def _norm_text(s):
    return s.strip().casefold()


def _normalize_date(d):
    if not d or d == "?":
        return ""
    m = re.search(r"(\d{4})[-.](\d{2})[-.](\d{2})", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return d.strip()


def _extract_platform_id(headers):
    raw = " ".join(headers.get(k, "") for k in ("link", "site", "url", "ecourl"))
    m = re.search(r"chess\.com/game/(?:live|daily)/(\d+)", raw)
    if m:
        return f"chess.com:{m.group(1)}"
    m = re.search(r"lichess\.org/([A-Za-z0-9]{8})", raw)
    if m:
        return f"lichess:{m.group(1)}"
    return None


def deterministic_split_pgn(pgn_text):
    normalized = pgn_text.replace('\r\n', '\n').replace('\r', '\n')
    parts = re.split(r'\n(?=\[Event\s)', normalized)
    return [p.strip() for p in parts if p.strip()]


def parse_pgn_content_detailed(pgn_text):
    blocks = deterministic_split_pgn(pgn_text)
    records = []

    for source_index, raw_block in enumerate(blocks, 1):
        headers = {}
        for key, value in re.findall(r'\[(\w+)\s+"([^"]*)"\]', raw_block):
            headers[key.lower()] = value

        white = headers.get("white", "?")
        black = headers.get("black", "?")
        result = headers.get("result", "*").strip()
        date_value = headers.get("utcdate") or headers.get("date")
        normalized_date = _normalize_date(date_value)

        raw_pgn_hash = hashlib.sha256(raw_block.encode("utf-8")).hexdigest()
        platform_id = _extract_platform_id(headers)

        variant = headers.get("variant", "").strip()
        if variant and variant.lower() not in ("", "standard"):
            records.append({
                "source_index": source_index,
                "raw_pgn": raw_block,
                "headers": headers,
                "normalized_date": normalized_date,
                "moves": [],
                "uci_sequence": [],
                "raw_pgn_hash": raw_pgn_hash,
                "platform_game_id": platform_id,
                "canonical_game_hash": None,
                "structural_game_hash": None,
                "parser_status": "unsupported_variant",
                "failure_reason": f"Unsupported variant: {variant}",
                "failing_ply": None,
                "failing_token": None,
            })
            continue

        moves_text = re.sub(r'\[.*?\]', '', raw_block)
        moves_text = re.sub(r'\{[^}]*\}', '', moves_text, flags=re.DOTALL)
        moves_text = _remove_variations(moves_text)
        moves_text = re.sub(r'\d+\.\.\.', '', moves_text)
        moves_text = re.sub(r'\d+\.', ' ', moves_text)
        moves_text = re.sub(r'\$[0-9]+', '', moves_text)
        moves_text = moves_text.replace('1-0', '').replace('0-1', '').replace('1/2-1/2', '').replace('*', '')
        moves_text = re.sub(r'[!?+#]*', '', moves_text)
        tokens = moves_text.split()

        board = ChessBoard()
        internal_moves = []
        parser_status = "accepted"
        failure_reason = None
        failing_ply = None
        failing_token = None

        if not tokens:
            parser_status = "zero_move"
            failure_reason = "No mainline moves"
        else:
            for ply, token in enumerate(tokens, 1):
                try:
                    move = pgn_to_move(token, board)
                except Exception as e:
                    parser_status = "invalid_pgn"
                    failure_reason = f"exception: {e}"
                    failing_ply = ply
                    failing_token = token
                    break

                if move is None:
                    parser_status = "illegal_move"
                    failure_reason = f"illegal move: {token}"
                    failing_ply = ply
                    failing_token = token
                    break

                internal_moves.append(move)
                board.make_move(move)

        uci_sequence = [move_to_str(m) for m in internal_moves]

        if parser_status == "accepted":
            canonical_payload = (
                f"{_norm_text(white)}|{_norm_text(black)}|{normalized_date}|{result}|"
                + "|".join(uci_sequence)
            )
            canonical_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

            structural_payload = (
                f"{_norm_text(white)}|{_norm_text(black)}|" + "|".join(uci_sequence)
            )
            structural_hash = hashlib.sha256(structural_payload.encode("utf-8")).hexdigest()
        else:
            canonical_hash = None
            structural_hash = None

        records.append({
            "source_index": source_index,
            "raw_pgn": raw_block,
            "headers": headers,
            "normalized_date": normalized_date,
            "moves": internal_moves,
            "uci_sequence": uci_sequence,
            "raw_pgn_hash": raw_pgn_hash,
            "platform_game_id": platform_id,
            "canonical_game_hash": canonical_hash,
            "structural_game_hash": structural_hash,
            "parser_status": parser_status,
            "failure_reason": failure_reason,
            "failing_ply": failing_ply,
            "failing_token": failing_token,
        })

    return records
