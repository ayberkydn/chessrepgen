#!/usr/bin/env python3
"""
Profiling script to measure actual time spent in suspected bottlenecks.
Run with: python profile_bottlenecks.py
"""

import cProfile
import functools
import io
import logging
import os
import pstats
import sys
import time
from collections import defaultdict
from contextlib import contextmanager

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# Timing storage
TIMING_DATA = defaultdict(lambda: {"calls": 0, "total_time": 0.0, "times": []})


def timed(name):
    """Decorator to time function calls."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                TIMING_DATA[name]["calls"] += 1
                TIMING_DATA[name]["total_time"] += elapsed
                TIMING_DATA[name]["times"].append(elapsed)

        return wrapper

    return decorator


def patch_for_profiling():
    """Monkey-patch key functions to add timing instrumentation."""
    from services import cache, pruner, repertoire_builder

    # 1. Cache connection overhead
    original_get_connection = cache.ChessCache._get_connection

    @contextmanager
    def timed_get_connection(self):
        start = time.perf_counter()
        with original_get_connection(self) as conn:
            elapsed = time.perf_counter() - start
            TIMING_DATA["cache._get_connection"]["calls"] += 1
            TIMING_DATA["cache._get_connection"]["total_time"] += elapsed
            TIMING_DATA["cache._get_connection"]["times"].append(elapsed)
            yield conn

    cache.ChessCache._get_connection = timed_get_connection

    # 2. Cache get operations
    original_get_lichess = cache.ChessCache.get_lichess_stats

    def timed_get_lichess(self, fen, ratings, time_controls):
        start = time.perf_counter()
        result = original_get_lichess(self, fen, ratings, time_controls)
        elapsed = time.perf_counter() - start
        TIMING_DATA["cache.get_lichess_stats"]["calls"] += 1
        TIMING_DATA["cache.get_lichess_stats"]["total_time"] += elapsed
        TIMING_DATA["cache.get_lichess_stats"]["times"].append(elapsed)
        return result

    cache.ChessCache.get_lichess_stats = timed_get_lichess

    original_get_master = cache.ChessCache.get_master_stats

    def timed_get_master(self, fen):
        start = time.perf_counter()
        result = original_get_master(self, fen)
        elapsed = time.perf_counter() - start
        TIMING_DATA["cache.get_master_stats"]["calls"] += 1
        TIMING_DATA["cache.get_master_stats"]["total_time"] += elapsed
        TIMING_DATA["cache.get_master_stats"]["times"].append(elapsed)
        return result

    cache.ChessCache.get_master_stats = timed_get_master

    # 3. _reconstruct_move_sequence
    original_reconstruct = (
        repertoire_builder.RepertoireBuilder._reconstruct_move_sequence
    )

    def timed_reconstruct(self, node):
        start = time.perf_counter()
        result = original_reconstruct(self, node)
        elapsed = time.perf_counter() - start
        TIMING_DATA["_reconstruct_move_sequence"]["calls"] += 1
        TIMING_DATA["_reconstruct_move_sequence"]["total_time"] += elapsed
        TIMING_DATA["_reconstruct_move_sequence"]["times"].append(elapsed)
        return result

    repertoire_builder.RepertoireBuilder._reconstruct_move_sequence = timed_reconstruct

    # 4. _ensure_position_data
    original_ensure = repertoire_builder.RepertoireBuilder._ensure_position_data

    def timed_ensure(self, node, *, depth=None, line=None):
        start = time.perf_counter()
        result = original_ensure(self, node, depth=depth, line=line)
        elapsed = time.perf_counter() - start
        TIMING_DATA["_ensure_position_data"]["calls"] += 1
        TIMING_DATA["_ensure_position_data"]["total_time"] += elapsed
        TIMING_DATA["_ensure_position_data"]["times"].append(elapsed)
        return result

    repertoire_builder.RepertoireBuilder._ensure_position_data = timed_ensure

    # 5. _propagate_ancestors
    original_propagate = repertoire_builder.RepertoireBuilder._propagate_ancestors

    def timed_propagate(self, node, ancestors):
        start = time.perf_counter()
        result = original_propagate(self, node, ancestors)
        elapsed = time.perf_counter() - start
        TIMING_DATA["_propagate_ancestors"]["calls"] += 1
        TIMING_DATA["_propagate_ancestors"]["total_time"] += elapsed
        TIMING_DATA["_propagate_ancestors"]["times"].append(elapsed)
        return result

    repertoire_builder.RepertoireBuilder._propagate_ancestors = timed_propagate

    # 6. _expand_node
    original_expand = repertoire_builder.RepertoireBuilder._expand_node

    def timed_expand(self, node, heap):
        start = time.perf_counter()
        result = original_expand(self, node, heap)
        elapsed = time.perf_counter() - start
        TIMING_DATA["_expand_node"]["calls"] += 1
        TIMING_DATA["_expand_node"]["total_time"] += elapsed
        TIMING_DATA["_expand_node"]["times"].append(elapsed)
        return result

    repertoire_builder.RepertoireBuilder._expand_node = timed_expand

    # 7. get_position_data (full fetch including API/cache)
    original_get_position = repertoire_builder.RepertoireBuilder.get_position_data

    def timed_get_position(self, fen, *, depth=None, line=None):
        start = time.perf_counter()
        result = original_get_position(self, fen, depth=depth, line=line)
        elapsed = time.perf_counter() - start
        TIMING_DATA["get_position_data"]["calls"] += 1
        TIMING_DATA["get_position_data"]["total_time"] += elapsed
        TIMING_DATA["get_position_data"]["times"].append(elapsed)
        return result

    repertoire_builder.RepertoireBuilder.get_position_data = timed_get_position

    # 8. Terminal advantage computation
    original_compute_terminal = pruner.RepertoirePruner._compute_terminal_advantage

    def timed_compute_terminal(self, node, cache_dict):
        start = time.perf_counter()
        result = original_compute_terminal(self, node, cache_dict)
        elapsed = time.perf_counter() - start
        TIMING_DATA["_compute_terminal_advantage"]["calls"] += 1
        TIMING_DATA["_compute_terminal_advantage"]["total_time"] += elapsed
        TIMING_DATA["_compute_terminal_advantage"]["times"].append(elapsed)
        return result

    pruner.RepertoirePruner._compute_terminal_advantage = timed_compute_terminal

    # 9. _calculate_position_advantage
    original_calc_advantage = pruner.RepertoirePruner._calculate_position_advantage

    def timed_calc_advantage(self, node):
        start = time.perf_counter()
        result = original_calc_advantage(self, node)
        elapsed = time.perf_counter() - start
        TIMING_DATA["_calculate_position_advantage"]["calls"] += 1
        TIMING_DATA["_calculate_position_advantage"]["total_time"] += elapsed
        TIMING_DATA["_calculate_position_advantage"]["times"].append(elapsed)
        return result

    pruner.RepertoirePruner._calculate_position_advantage = timed_calc_advantage

    # 10. evaluate_position
    from services import evaluator

    original_evaluate = evaluator.MoveEvaluator.evaluate_position

    def timed_evaluate(
        self, lichess_stats, player_reference_stats, is_player_turn, depth=0
    ):
        start = time.perf_counter()
        result = original_evaluate(
            self, lichess_stats, player_reference_stats, is_player_turn, depth
        )
        elapsed = time.perf_counter() - start
        TIMING_DATA["evaluate_position"]["calls"] += 1
        TIMING_DATA["evaluate_position"]["total_time"] += elapsed
        TIMING_DATA["evaluate_position"]["times"].append(elapsed)
        return result

    evaluator.MoveEvaluator.evaluate_position = timed_evaluate


def print_timing_report():
    """Print a formatted timing report."""
    print("\n" + "=" * 80)
    print("PROFILING RESULTS - TIME SPENT IN EACH FUNCTION")
    print("=" * 80)

    # Sort by total time descending
    sorted_data = sorted(
        TIMING_DATA.items(), key=lambda x: x[1]["total_time"], reverse=True
    )

    total_measured = sum(d["total_time"] for _, d in sorted_data)

    print(
        f"\n{'Function':<40} {'Calls':>10} {'Total (s)':>12} {'Avg (ms)':>12} {'%':>8}"
    )
    print("-" * 80)

    for name, data in sorted_data:
        calls = data["calls"]
        total = data["total_time"]
        avg_ms = (total / calls * 1000) if calls > 0 else 0
        pct = (total / total_measured * 100) if total_measured > 0 else 0

        print(f"{name:<40} {calls:>10} {total:>12.3f} {avg_ms:>12.3f} {pct:>7.1f}%")

    print("-" * 80)
    print(f"{'TOTAL MEASURED':<40} {'':<10} {total_measured:>12.3f}")
    print()

    # Additional analysis
    print("\n" + "=" * 80)
    print("DETAILED ANALYSIS")
    print("=" * 80)

    # Cache connection analysis
    if "cache._get_connection" in TIMING_DATA:
        conn_data = TIMING_DATA["cache._get_connection"]
        print(f"\nCache Connections:")
        print(f"  Total connections created: {conn_data['calls']}")
        print(f"  Total time: {conn_data['total_time']:.3f}s")
        print(
            f"  Average per connection: {conn_data['total_time'] / conn_data['calls'] * 1000:.3f}ms"
        )

    # _reconstruct_move_sequence analysis
    if "_reconstruct_move_sequence" in TIMING_DATA:
        recon_data = TIMING_DATA["_reconstruct_move_sequence"]
        print(f"\nMove Sequence Reconstruction:")
        print(f"  Total calls: {recon_data['calls']}")
        print(f"  Total time: {recon_data['total_time']:.3f}s")
        if recon_data["calls"] > 0:
            print(
                f"  Average per call: {recon_data['total_time'] / recon_data['calls'] * 1000:.3f}ms"
            )

    # _ensure_position_data vs _expand_node ratio
    if "_ensure_position_data" in TIMING_DATA and "_expand_node" in TIMING_DATA:
        ensure_data = TIMING_DATA["_ensure_position_data"]
        expand_data = TIMING_DATA["_expand_node"]
        print(f"\nPosition Data Fetching:")
        print(f"  _ensure_position_data calls: {ensure_data['calls']}")
        print(f"  _expand_node calls: {expand_data['calls']}")
        if expand_data["calls"] > 0:
            ratio = ensure_data["calls"] / expand_data["calls"]
            print(f"  Ratio (ensure/expand): {ratio:.2f}x")
            print(
                f"  (This shows how many times position data is fetched per node expansion)"
            )


def run_profiled():
    """Run the repertoire builder with profiling enabled."""
    from config import load_config, parse_arguments
    from services.repertoire_builder import RepertoireBuilder

    # Reduce logging noise
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)

    # Parse args with minimal config for faster profiling
    class Args:
        config = "config.yaml"
        depth = 3  # Reduced depth for faster profiling
        output = None
        log_level = "WARNING"
        ratings = None
        time_controls = None

    args = Args()
    config = load_config(args)

    # Override to use just one opening for faster profiling
    # Comment out to test with full config
    config.initial_moves_white = ["e4"]
    config.initial_moves_black = []
    config.depth = 3  # Smaller depth for profiling
    # Fix ratings if they contain None values
    config.ratings = [r for r in config.ratings if r is not None]

    print(f"Starting profiled run with depth={config.depth}")
    print(f"Initial moves: {config.initial_moves_white}")
    print("This will use cached data only (no API calls expected)")
    print()

    overall_start = time.perf_counter()

    builder = RepertoireBuilder(config, side="white")
    lines = builder.build_repertoire()

    if lines:
        roots = [line.root for line in lines]
        builder.compute_terminal_advantages(roots)

    overall_elapsed = time.perf_counter() - overall_start

    print(f"\nTotal repertoire build time: {overall_elapsed:.3f}s")
    print(f"Positions in graph: {len(builder.nodes_by_key)}")

    return overall_elapsed


def run_cprofile():
    """Run with cProfile for additional insights."""
    from config import load_config
    from services.repertoire_builder import RepertoireBuilder

    logging.basicConfig(level=logging.WARNING)

    class Args:
        config = "config.yaml"
        depth = 3
        output = None
        log_level = "WARNING"
        ratings = None
        time_controls = None

    args = Args()
    config = load_config(args)
    config.initial_moves_white = ["e4"]
    config.initial_moves_black = []
    config.depth = 3
    config.ratings = [r for r in config.ratings if r is not None]

    profiler = cProfile.Profile()
    profiler.enable()

    builder = RepertoireBuilder(config, side="white")
    lines = builder.build_repertoire()
    if lines:
        roots = [line.root for line in lines]
        builder.compute_terminal_advantages(roots)

    profiler.disable()

    # Print top functions by cumulative time
    print("\n" + "=" * 80)
    print("cProfile TOP 30 FUNCTIONS BY CUMULATIVE TIME")
    print("=" * 80)

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(30)
    print(stream.getvalue())


if __name__ == "__main__":
    print("Chess Repertoire Generator - Performance Profiling")
    print("=" * 80)

    # First, apply instrumentation patches
    patch_for_profiling()

    # Run with custom timing
    run_profiled()

    # Print detailed timing report
    print_timing_report()

    # Also run cProfile for additional insights
    print("\n\nRunning cProfile analysis...")
    run_cprofile()
