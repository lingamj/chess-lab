#!/usr/bin/env python3
"""P5.15E v2 applier. search.py MultiPV root algorithm."""
import hashlib, sys
from pathlib import Path

HERE = Path.home() / "chess_ai"
SEARCH = HERE / "search.py"
SEARCH_SHA = "6071876bf02573bf9b4923bb5ab0d3d8baebff5987bb7030d4fa11078170acf7"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def guarded_edit(path, expected_sha, edits):
    got = sha(path)
    if got != expected_sha:
        print("REFUSING: sha mismatch on " + path.name)
        print("  expected " + expected_sha)
        print("  actual   " + got)
        sys.exit(1)
    text = path.read_text()
    for i, (old, new) in enumerate(edits, 1):
        n = text.count(old)
        if n != 1:
            print("REFUSING edit %d: anchor count %d, expected 1" % (i, n))
            print("  anchor (first 160 chars):")
            print("   " + old[:160].replace("\n", "\\n"))
            sys.exit(2)
        text = text.replace(old, new)
    path.write_text(text)
    print("OK: %d edit(s) applied; new sha %s" % (len(edits), sha(path)))


EDITS = [
    (
        "        self.accepted_root_source_type = None\n"
        "        self.accepted_root_source_depth = None\n"
        "        self.tt_version = CURRENT_TT_VERSION\n",
        "        self.accepted_root_source_type = None\n"
        "        self.accepted_root_source_depth = None\n"
        "        self.accepted_root_multipv = {}\n"
        "        self.root_move_candidates = {}\n"
        "        self.tt_version = CURRENT_TT_VERSION\n",
    ),
    (
        "        if iteration_move is None:\n"
        "            return result.source_type == \"terminal\"\n"
        "        return iteration_move in legal_moves\n"
        "\n"
        "    def search(self, board, time_limit=3000, depth=None,\n",
        "        if iteration_move is None:\n"
        "            return result.source_type == \"terminal\"\n"
        "        return iteration_move in legal_moves\n"
        "\n"
        "    def _root_full_window_research(self, board, move, depth):\n"
        "        undo = board.make_move(move)\n"
        "        try:\n"
        "            child = self._pvs_result(\n"
        "                board, -MATE_SCORE, MATE_SCORE, depth - 1, 1\n"
        "            )\n"
        "        finally:\n"
        "            board.undo_move(undo)\n"
        "        if not child.valid:\n"
        "            return None\n"
        "        if child.source_type not in AUTHORITATIVE_ROOT_SOURCES:\n"
        "            return None\n"
        "        if child.bound != \"exact\":\n"
        "            return None\n"
        "        return -child.score\n"
        "\n"
        "    def _build_multipv_lines(self, board, depth, primary_move,\n"
        "                             primary_score, multipv):\n"
        "        legal = board.generate_legal_moves()\n"
        "        if primary_move not in legal:\n"
        "            return {primary_move: primary_score}\n"
        "\n"
        "        candidates = self.root_move_candidates\n"
        "        exact = {}\n"
        "        bound_only = []\n"
        "\n"
        "        for move in legal:\n"
        "            if move == primary_move:\n"
        "                continue\n"
        "            cand = candidates.get(move)\n"
        "            if (\n"
        "                cand is not None\n"
        "                and cand.valid\n"
        "                and cand.bound == \"exact\"\n"
        "                and cand.source_type in AUTHORITATIVE_ROOT_SOURCES\n"
        "            ):\n"
        "                exact[move] = cand.score\n"
        "            else:\n"
        "                priority = (\n"
        "                    cand.score if cand is not None else float(\"-inf\")\n"
        "                )\n"
        "                bound_only.append((priority, move))\n"
        "\n"
        "        if len(exact) + 1 < multipv:\n"
        "            bound_only.sort(key=lambda x: -x[0])\n"
        "            for _, move in bound_only:\n"
        "                if len(exact) + 1 >= multipv:\n"
        "                    break\n"
        "                if self._time_up():\n"
        "                    break\n"
        "                try:\n"
        "                    score = self._root_full_window_research(\n"
        "                        board, move, depth\n"
        "                    )\n"
        "                except SearchTimeout:\n"
        "                    break\n"
        "                if score is not None:\n"
        "                    exact[move] = score\n"
        "\n"
        "        ranked_secondaries = sorted(\n"
        "            exact.items(), key=lambda x: -x[1]\n"
        "        )\n"
        "        lines = [(primary_move, primary_score)] + ranked_secondaries\n"
        "        seen = set()\n"
        "        deduped = []\n"
        "        for move, score in lines:\n"
        "            if move in seen:\n"
        "                continue\n"
        "            seen.add(move)\n"
        "            deduped.append((move, score))\n"
        "            if len(deduped) >= multipv:\n"
        "                break\n"
        "        return dict(deduped)\n"
        "\n"
        "    def search(self, board, time_limit=3000, depth=None,\n",
    ),
    (
        "    def search(self, board, time_limit=3000, depth=None,\n"
        "               on_accepted_iteration=None, unlimited=False,\n"
        "               continue_from=None):\n"
        "        self.start_time = time.time()\n"
        "        self.time_limit = None if time_limit is None else time_limit / 1000.0\n",
        "    def search(self, board, time_limit=3000, depth=None,\n"
        "               on_accepted_iteration=None, unlimited=False,\n"
        "               continue_from=None, multipv=1):\n"
        "        self.start_time = time.time()\n"
        "        self.time_limit = None if time_limit is None else time_limit / 1000.0\n"
        "\n"
        "        if type(multipv) is not int or multipv < 1 or multipv > 8:\n"
        "            raise ValueError(\n"
        "                \"multipv must be an int in [1, 8]; got %r\" % (multipv,)\n"
        "            )\n",
    ),
    (
        "            self.accepted_root_source_type = None\n"
        "            self.accepted_root_source_depth = None\n"
        "            self._clear_heuristics()\n",
        "            self.accepted_root_source_type = None\n"
        "            self.accepted_root_source_depth = None\n"
        "            self.accepted_root_multipv = {}\n"
        "            self._clear_heuristics()\n",
    ),
    (
        "            for d in depth_iter:\n"
        "                self.current_depth = d\n"
        "                self.q_nodes = 0\n"
        "                self.alpha_beta_calls = 0\n"
        "                _iter_t0 = time.perf_counter()\n"
        "                _iter_nodes0 = self.nodes\n",
        "            for d in depth_iter:\n"
        "                self.current_depth = d\n"
        "                self.q_nodes = 0\n"
        "                self.alpha_beta_calls = 0\n"
        "                self.root_move_candidates = {}\n"
        "                _iter_t0 = time.perf_counter()\n"
        "                _iter_nodes0 = self.nodes\n",
    ),
    (
        "                if d > 1 and abs(best_score) < MATE_SCORE - 100:\n"
        "                    alpha = best_score - 50\n"
        "                    beta = best_score + 50\n"
        "                else:\n"
        "                    alpha = -MATE_SCORE\n"
        "                    beta = MATE_SCORE\n",
        "                if (d > 1 and abs(best_score) < MATE_SCORE - 100\n"
        "                        and multipv == 1):\n"
        "                    alpha = best_score - 50\n"
        "                    beta = best_score + 50\n"
        "                else:\n"
        "                    alpha = -MATE_SCORE\n"
        "                    beta = MATE_SCORE\n",
    ),
    (
        "                    if on_accepted_iteration is not None:\n"
        "                        on_accepted_iteration(\n"
        "                            d, iteration_move,\n"
        "                            result.score, pv_snapshot\n"
        "                        )\n"
        "                else:\n",
        "                    if on_accepted_iteration is not None:\n"
        "                        on_accepted_iteration(\n"
        "                            d, iteration_move,\n"
        "                            result.score, pv_snapshot\n"
        "                        )\n"
        "\n"
        "                    if multipv > 1:\n"
        "                        try:\n"
        "                            self.accepted_root_multipv = (\n"
        "                                self._build_multipv_lines(\n"
        "                                    board, d, iteration_move,\n"
        "                                    result.score, multipv\n"
        "                                )\n"
        "                            )\n"
        "                        except SearchTimeout:\n"
        "                            pass\n"
        "                else:\n",
    ),
    (
        "        if self.accepted_root_depth > 0:\n"
        "            self.sorted_root_scores = sorted(\n"
        "                self.accepted_root_scores.items(),\n"
        "                key=lambda x: -x[1]\n"
        "            )\n"
        "        else:\n"
        "            self.sorted_root_scores = sorted(\n"
        "                self.root_scores.items(),\n"
        "                key=lambda x: -x[1]\n"
        "            )\n",
        "        if self.accepted_root_depth > 0:\n"
        "            if multipv > 1 and self.accepted_root_multipv:\n"
        "                self.sorted_root_scores = sorted(\n"
        "                    self.accepted_root_multipv.items(),\n"
        "                    key=lambda x: -x[1]\n"
        "                )\n"
        "            else:\n"
        "                self.sorted_root_scores = sorted(\n"
        "                    self.accepted_root_scores.items(),\n"
        "                    key=lambda x: -x[1]\n"
        "                )\n"
        "        else:\n"
        "            self.sorted_root_scores = sorted(\n"
        "                self.root_scores.items(),\n"
        "                key=lambda x: -x[1]\n"
        "            )\n",
    ),
    (
        "            candidate = SearchResult(\n"
        "                parent_score,\n"
        "                parent_bound,\n"
        "                child.valid,\n"
        "                \"search\",\n"
        "                depth\n"
        "            )\n"
        "\n"
        "            if best_result is None or parent_score > best_score:\n",
        "            candidate = SearchResult(\n"
        "                parent_score,\n"
        "                parent_bound,\n"
        "                child.valid,\n"
        "                \"search\",\n"
        "                depth\n"
        "            )\n"
        "\n"
        "            if ply == 0:\n"
        "                self.root_move_candidates[move] = candidate\n"
        "\n"
        "            if best_result is None or parent_score > best_score:\n",
    ),
]


if __name__ == "__main__":
    guarded_edit(SEARCH, SEARCH_SHA, EDITS)
