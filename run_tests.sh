#!/bin/bash
cd ~/chess_ai
echo "=== Running complete verification suite ==="
echo ""
python test_hash.py          && echo "" && \
python test_move_index.py    && echo "" && \
python audit_move_table.py   && echo "" && \
python test_search_contract.py && echo "" && \
python benchmark.py          && echo "" && \
python perft_test.py
status=$?
if [ "$status" -eq 0 ]; then
    echo ""
    echo "=== All tests passed ==="
else
    echo ""
    echo "=== TEST SUITE FAILED (exit $status) ==="
    exit "$status"
fi
