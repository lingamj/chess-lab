#!/usr/bin/env python3
"""UCI Engine – uses DualNet value head."""

import sys, os, time, threading, argparse

parser = argparse.ArgumentParser()
parser.add_argument('--max-depth', type=int, default=20)
parser.add_argument('--hash-size', type=int, default=500000)
parser.add_argument('--threads', type=int, default=2)
args, unknown = parser.parse_known_args()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
MODEL_PATH = os.path.join(SCRIPT_DIR, 'chess_nn.pkl')

from board import ChessBoard
from nn import DualNet
from search import SearchEngine
from parallel_search import ParallelSearch
from move_helpers import move_to_str, str_to_move

class UCIBoard:
    def __init__(self, fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"):
        self.board = ChessBoard()
        self.set_fen(fen)

    def set_fen(self, fen):
        self.board.set_fen(fen)

    def make_move_uci(self, uci):
        move = str_to_move(uci)
        for m in self.board.generate_legal_moves():
            if m == move:
                self.board.make_move(m)
                return True
        return False

class UCIEngine:
    def __init__(self, max_depth=10, tt_max=100000, num_threads=1):
        self.nn = DualNet()
        if self.nn.load(MODEL_PATH):
            sys.stderr.write(f"UCI: loaded {MODEL_PATH}\n")
        else:
            sys.stderr.write(f"UCI: WARNING – could not load {MODEL_PATH}, using untrained network\n")

        if num_threads > 1:
            self.searcher = ParallelSearch(nn_evaluator=self.nn,
                                           max_depth=max_depth,
                                           tt_max=tt_max,
                                           num_threads=num_threads)
        else:
            self.searcher = SearchEngine(nn=self.nn,
                                         max_depth=max_depth,
                                         tt_max=tt_max)
        self.board = UCIBoard()
        self.search_thread = None

    def send(self, msg):
        print(msg, flush=True)

    def handle(self, cmd):
        cmd = cmd.strip()
        if cmd == 'uci':
            self.send('id name ChessAI_Neural')
            self.send('id author PhoneTrained')
            self.send('uciok')
        elif cmd == 'isready':
            self.send('readyok')
        elif cmd == 'ucinewgame':
            self.board = UCIBoard()
            self.nn.load(MODEL_PATH)
            self.searcher.tt.clear()
            if args.threads > 1:
                self.searcher = ParallelSearch(nn_evaluator=self.nn,
                                               max_depth=self.searcher.max_depth,
                                               tt_max=self.searcher.tt_max,
                                               num_threads=args.threads)
            else:
                self.searcher = SearchEngine(nn=self.nn,
                                             max_depth=self.searcher.max_depth,
                                             tt_max=self.searcher.tt_max)
        elif cmd.startswith('position'):
            if 'startpos' in cmd:
                self.board = UCIBoard()
                moves_part = cmd.split('moves')
                if len(moves_part) > 1:
                    for m in moves_part[1].strip().split():
                        if not self.board.make_move_uci(m):
                            self.send('info string Illegal move ignored')
                            break
            elif 'fen' in cmd:
                fen = cmd[cmd.find('fen')+4:].split(' moves')[0] if ' moves' in cmd else cmd[cmd.find('fen')+4:]
                self.board = UCIBoard(fen)
                if 'moves' in cmd:
                    for m in cmd.split('moves')[-1].split():
                        if not self.board.make_move_uci(m):
                            self.send('info string Illegal move ignored')
                            break
        elif cmd.startswith('go'):
            mt = 3000
            parts = cmd.split()
            for i, p in enumerate(parts):
                if p == 'movetime' and i+1 < len(parts):
                    mt = int(parts[i+1])
                elif p == 'wtime' and self.board.board.white_turn and i+1 < len(parts):
                    mt = min(mt, int(parts[i+1]) // 20)
                elif p == 'btime' and not self.board.board.white_turn and i+1 < len(parts):
                    mt = min(mt, int(parts[i+1]) // 20)

            if self.search_thread and self.search_thread.is_alive():
                self.searcher.stop_event.set()
                self.search_thread.join(timeout=1)

            self.nn.load(MODEL_PATH)
            if args.threads > 1:
                self.searcher = ParallelSearch(nn_evaluator=self.nn,
                                               max_depth=self.searcher.max_depth,
                                               tt_max=self.searcher.tt_max,
                                               num_threads=args.threads)
            else:
                self.searcher = SearchEngine(nn=self.nn,
                                             max_depth=self.searcher.max_depth,
                                             tt_max=self.searcher.tt_max)

            def search_and_report():
                res = self.searcher.search(self.board.board, mt)
                move, score, depth, nodes = res
                nodes = self.searcher.nodes
                elapsed = int((time.time() - self.searcher.start_time)*1000) if self.searcher.start_time else 0
                nps = int(nodes / (elapsed / 1000)) if elapsed > 0 else 0
                self.send(f'info depth {depth} score cp {int(score)} nodes {nodes} nps {nps} time {elapsed}')
                if move:
                    self.send(f'bestmove {move_to_str(move)}')

            self.searcher.stop_event.clear()
            self.searcher.start_time = time.time()
            self.search_thread = threading.Thread(target=search_and_report)
            self.search_thread.start()
        elif cmd == 'stop':
            self.searcher.stop_event.set()
            if self.search_thread and self.search_thread.is_alive():
                self.search_thread.join(timeout=1)
        elif cmd == 'quit':
            self.searcher.stop_event.set()
            if self.search_thread and self.search_thread.is_alive():
                self.search_thread.join(timeout=1)
            self.send('info string shutting down')
            sys.exit(0)

def main():
    engine = UCIEngine(max_depth=args.max_depth, tt_max=args.hash_size, num_threads=args.threads)
    while True:
        try:
            cmd = sys.stdin.readline()
            if not cmd:
                break
            engine.handle(cmd)
        except Exception as e:
            print(f"info string error: {e}", flush=True)

if __name__ == '__main__':
    main()
