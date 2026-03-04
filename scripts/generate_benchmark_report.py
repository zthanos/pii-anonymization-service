#!/usr/bin/env python3
"""Generate HTML benchmark report with visualizations from benchmark results."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import argparse


def load_benchmark_results(json_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load benchmark results from JSON file.
    
    Args:
        json_path: Path to benchmark_results.json
        
    Returns:
        Dictionary with 'anonymization' and 'deanonymization' results
    """
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Benchmark results file not found: {json_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in benchmark results: {e}")
        sys.exit(1)


def generate_performance_plots(results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, str]:
    """
    Generate performance plots using matplotlib.
    
    Args:
        results: Benchmark results dictionary
        
    Returns:
        Dictionary mapping plot names to base64-encoded PNG data
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        import io
        import base64
    except ImportError:
        print("Warning: matplotlib not installed, skipping plot generation")
        print("Install with: uv pip install matplotlib")
        return {}
    
    plots = {}
    
    # Extract data for anonymization
    rest_anon_results = results.get('rest_anonymization', results.get('anonymization', []))
    grpc_anon_results = results.get('grpc_anonymization', [])
    deanon_results = results.get('rest_deanonymization', results.get('deanonymization', []))
    
    if not rest_anon_results:
        print("Warning: No anonymization results found")
        return plots
    
    # REST vs gRPC Throughput Comparison
    if grpc_anon_results:
        fig, ax = plt.subplots(figsize=(10, 6))
        record_counts = [r['total_records'] for r in rest_anon_results]
        rest_throughputs = [r['throughput_records_per_sec'] for r in rest_anon_results]
        grpc_throughputs = [r['throughput_records_per_sec'] for r in grpc_anon_results]
        
        ax.plot(record_counts, rest_throughputs, marker='o', linewidth=2, markersize=8, label='REST', color='blue')
        ax.plot(record_counts, grpc_throughputs, marker='s', linewidth=2, markersize=8, label='gRPC', color='green')
        ax.axhline(y=50000, color='r', linestyle='--', label='Target (50k records/sec)')
        
        ax.set_xlabel('Number of Records', fontsize=12)
        ax.set_ylabel('Throughput (records/sec)', fontsize=12)
        ax.set_title('REST vs gRPC Throughput Comparison', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xscale('log')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plots['rest_vs_grpc_throughput'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
    
    # Throughput plot (original)
    fig, ax = plt.subplots(figsize=(10, 6))
    record_counts = [r['total_records'] for r in rest_anon_results]
    throughputs = [r['throughput_records_per_sec'] for r in rest_anon_results]
    
    ax.plot(record_counts, throughputs, marker='o', linewidth=2, markersize=8, label='REST Anonymization')
    
    if grpc_anon_results:
        grpc_throughputs = [r['throughput_records_per_sec'] for r in grpc_anon_results]
        ax.plot(record_counts, grpc_throughputs, marker='s', linewidth=2, markersize=8, label='gRPC Anonymization')
    
    if deanon_results:
        deanon_throughputs = [r['throughput_records_per_sec'] for r in deanon_results]
        ax.plot(record_counts, deanon_throughputs, marker='^', linewidth=2, markersize=8, label='REST De-anonymization')
    
    ax.axhline(y=50000, color='r', linestyle='--', label='Target (50k records/sec)')
    ax.set_xlabel('Number of Records', fontsize=12)
    ax.set_ylabel('Throughput (records/sec)', fontsize=12)
    ax.set_title('Throughput Performance', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale('log')
    
    # Save to base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plots['throughput'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    
    # REST vs gRPC Latency Comparison
    if grpc_anon_results:
        fig, ax = plt.subplots(figsize=(10, 6))
        rest_latency_p95 = [r['latency_p95_ms'] for r in rest_anon_results]
        grpc_latency_p95 = [r['latency_p95_ms'] for r in grpc_anon_results]
        
        ax.plot(record_counts, rest_latency_p95, marker='o', linewidth=2, markersize=8, label='REST p95', color='blue')
        ax.plot(record_counts, grpc_latency_p95, marker='s', linewidth=2, markersize=8, label='gRPC p95', color='green')
        ax.axhline(y=5.0, color='r', linestyle='--', label='Target (5ms p95)')
        
        ax.set_xlabel('Number of Records', fontsize=12)
        ax.set_ylabel('Latency (ms)', fontsize=12)
        ax.set_title('REST vs gRPC Latency Comparison', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xscale('log')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plots['rest_vs_grpc_latency'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
    
    # Latency plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    latency_p50 = [r['latency_p50_ms'] for r in rest_anon_results]
    latency_p95 = [r['latency_p95_ms'] for r in rest_anon_results]
    latency_p99 = [r['latency_p99_ms'] for r in rest_anon_results]
    
    ax.plot(record_counts, latency_p50, marker='o', linewidth=2, markersize=8, label='p50')
    ax.plot(record_counts, latency_p95, marker='s', linewidth=2, markersize=8, label='p95')
    ax.plot(record_counts, latency_p99, marker='^', linewidth=2, markersize=8, label='p99')
    
    ax.axhline(y=5.0, color='r', linestyle='--', label='Target (5ms p95)')
    ax.set_xlabel('Number of Records', fontsize=12)
    ax.set_ylabel('Latency (ms)', fontsize=12)
    ax.set_title('REST Anonymization Latency Percentiles', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale('log')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plots['latency_anon'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    
    # gRPC Latency plot
    if grpc_anon_results:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        grpc_latency_p50 = [r['latency_p50_ms'] for r in grpc_anon_results]
        grpc_latency_p95 = [r['latency_p95_ms'] for r in grpc_anon_results]
        grpc_latency_p99 = [r['latency_p99_ms'] for r in grpc_anon_results]
        
        ax.plot(record_counts, grpc_latency_p50, marker='o', linewidth=2, markersize=8, label='p50')
        ax.plot(record_counts, grpc_latency_p95, marker='s', linewidth=2, markersize=8, label='p95')
        ax.plot(record_counts, grpc_latency_p99, marker='^', linewidth=2, markersize=8, label='p99')
        
        ax.axhline(y=5.0, color='r', linestyle='--', label='Target (5ms p95)')
        ax.set_xlabel('Number of Records', fontsize=12)
        ax.set_ylabel('Latency (ms)', fontsize=12)
        ax.set_title('gRPC Anonymization Latency Percentiles', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xscale('log')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plots['latency_grpc'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
    
    # De-anonymization latency plot
    if deanon_results:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        deanon_latency_p50 = [r['latency_p50_ms'] for r in deanon_results]
        deanon_latency_p95 = [r['latency_p95_ms'] for r in deanon_results]
        deanon_latency_p99 = [r['latency_p99_ms'] for r in deanon_results]
        
        ax.plot(record_counts, deanon_latency_p50, marker='o', linewidth=2, markersize=8, label='p50')
        ax.plot(record_counts, deanon_latency_p95, marker='s', linewidth=2, markersize=8, label='p95')
        ax.plot(record_counts, deanon_latency_p99, marker='^', linewidth=2, markersize=8, label='p99')
        
        ax.axhline(y=3.0, color='r', linestyle='--', label='Target (3ms p95)')
        ax.set_xlabel('Number of Records', fontsize=12)
        ax.set_ylabel('Latency (ms)', fontsize=12)
        ax.set_title('De-anonymization Latency Percentiles', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xscale('log')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plots['latency_deanon'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
    
    # Memory usage plot
    fig, ax = plt.subplots(figsize=(10, 6))
    memory_usage = [r['memory_usage_mb'] for r in rest_anon_results]
    
    ax.plot(record_counts, memory_usage, marker='o', linewidth=2, markersize=8, color='blue', label='REST Anonymization')
    
    if grpc_anon_results:
        grpc_memory = [r['memory_usage_mb'] for r in grpc_anon_results]
        ax.plot(record_counts, grpc_memory, marker='s', linewidth=2, markersize=8, color='green', label='gRPC Anonymization')
    
    if deanon_results:
        deanon_memory = [r['memory_usage_mb'] for r in deanon_results]
        ax.plot(record_counts, deanon_memory, marker='^', linewidth=2, markersize=8, color='orange', label='REST De-anonymization')
    
    ax.set_xlabel('Number of Records', fontsize=12)
    ax.set_ylabel('Memory Usage (MB)', fontsize=12)
    ax.set_title('Memory Usage', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale('log')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plots['memory'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    
    # CPU utilization plot
    fig, ax = plt.subplots(figsize=(10, 6))
    cpu_usage = [r['cpu_utilization_percent'] for r in rest_anon_results]
    
    ax.plot(record_counts, cpu_usage, marker='o', linewidth=2, markersize=8, color='blue', label='REST Anonymization')
    
    if grpc_anon_results:
        grpc_cpu = [r['cpu_utilization_percent'] for r in grpc_anon_results]
        ax.plot(record_counts, grpc_cpu, marker='s', linewidth=2, markersize=8, color='green', label='gRPC Anonymization')
    
    if deanon_results:
        deanon_cpu = [r['cpu_utilization_percent'] for r in deanon_results]
        ax.plot(record_counts, deanon_cpu, marker='^', linewidth=2, markersize=8, color='orange', label='REST De-anonymization')
    
    ax.set_xlabel('Number of Records', fontsize=12)
    ax.set_ylabel('CPU Utilization (%)', fontsize=12)
    ax.set_title('CPU Utilization', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xscale('log')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plots['cpu'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    
    return plots


def generate_results_table(results: List[Dict[str, Any]], operation: str, target_throughput: float = None, target_latency: float = None) -> str:
    """
    Generate HTML table for benchmark results.
    
    Args:
        results: List of benchmark results
        operation: Operation name (e.g., "Anonymization")
        target_throughput: Target throughput in records/sec (optional)
        target_latency: Target p95 latency in ms (optional)
        
    Returns:
        HTML table string
    """
    if not results:
        return f"<p>No {operation.lower()} results available.</p>"
    
    html = f"""
    <h3>{operation} Results</h3>
    <table>
        <thead>
            <tr>
                <th>Records</th>
                <th>Execution Time (s)</th>
                <th>Throughput (rec/s)</th>
                <th>Latency p50 (ms)</th>
                <th>Latency p95 (ms)</th>
                <th>Latency p99 (ms)</th>
                <th>Latency p999 (ms)</th>
                <th>Memory (MB)</th>
                <th>CPU (%)</th>
                <th>Errors</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for result in results:
        # Determine pass/fail status
        status_items = []
        
        if target_throughput is not None:
            if result['throughput_records_per_sec'] >= target_throughput:
                status_items.append('<span class="pass">✓ Throughput</span>')
            else:
                status_items.append('<span class="fail">✗ Throughput</span>')
        
        if target_latency is not None:
            if result['latency_p95_ms'] <= target_latency:
                status_items.append('<span class="pass">✓ Latency</span>')
            else:
                status_items.append('<span class="fail">✗ Latency</span>')
        
        status = '<br>'.join(status_items) if status_items else 'N/A'
        
        html += f"""
            <tr>
                <td>{result['total_records']:,}</td>
                <td>{result['execution_time_seconds']:.2f}</td>
                <td>{result['throughput_records_per_sec']:,.0f}</td>
                <td>{result['latency_p50_ms']:.2f}</td>
                <td>{result['latency_p95_ms']:.2f}</td>
                <td>{result['latency_p99_ms']:.2f}</td>
                <td>{result['latency_p999_ms']:.2f}</td>
                <td>{result['memory_usage_mb']:.2f}</td>
                <td>{result['cpu_utilization_percent']:.1f}</td>
                <td>{result['errors']}</td>
                <td>{status}</td>
            </tr>
        """
    
    html += """
        </tbody>
    </table>
    """
    
    return html


def generate_html_report(results: Dict[str, List[Dict[str, Any]]], plots: Dict[str, str], output_path: str):
    """
    Generate HTML report with results table and visualizations.
    
    Args:
        results: Benchmark results dictionary
        plots: Dictionary of base64-encoded plot images
        output_path: Path to save HTML report
    """
    rest_anon_results = results.get('rest_anonymization', results.get('anonymization', []))
    grpc_anon_results = results.get('grpc_anonymization', [])
    deanon_results = results.get('rest_deanonymization', results.get('deanonymization', []))
    
    # Generate tables
    rest_anon_table = generate_results_table(rest_anon_results, "REST Anonymization", target_throughput=50000, target_latency=5.0)
    grpc_anon_table = generate_results_table(grpc_anon_results, "gRPC Streaming Anonymization", target_throughput=50000, target_latency=5.0) if grpc_anon_results else ""
    deanon_table = generate_results_table(deanon_results, "REST De-anonymization", target_latency=3.0)
    
    # Generate comparison summary
    comparison_html = ""
    if grpc_anon_results and rest_anon_results:
        comparison_html = """
        <h2>REST vs gRPC Performance Comparison</h2>
        <div class="comparison">
            <table>
                <thead>
                    <tr>
                        <th>Records</th>
                        <th>REST Throughput</th>
                        <th>gRPC Throughput</th>
                        <th>Improvement</th>
                        <th>REST p95 Latency</th>
                        <th>gRPC p95 Latency</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i in range(min(len(rest_anon_results), len(grpc_anon_results))):
            rest = rest_anon_results[i]
            grpc = grpc_anon_results[i]
            
            if grpc['throughput_records_per_sec'] > rest['throughput_records_per_sec']:
                improvement = ((grpc['throughput_records_per_sec'] / rest['throughput_records_per_sec']) - 1) * 100
                improvement_text = f'<span class="pass">+{improvement:.1f}% (gRPC faster)</span>'
            else:
                improvement = ((rest['throughput_records_per_sec'] / grpc['throughput_records_per_sec']) - 1) * 100
                improvement_text = f'<span class="fail">-{improvement:.1f}% (REST faster)</span>'
            
            comparison_html += f"""
                    <tr>
                        <td>{rest['total_records']:,}</td>
                        <td>{rest['throughput_records_per_sec']:,.0f} rec/s</td>
                        <td>{grpc['throughput_records_per_sec']:,.0f} rec/s</td>
                        <td>{improvement_text}</td>
                        <td>{rest['latency_p95_ms']:.2f}ms</td>
                        <td>{grpc['latency_p95_ms']:.2f}ms</td>
                    </tr>
            """
        
        comparison_html += """
                </tbody>
            </table>
        </div>
        """
    
    # Generate plots HTML
    plots_html = ""
    if plots:
        # Add REST vs gRPC comparison plots first
        if 'rest_vs_grpc_throughput' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['rest_vs_grpc_throughput']}" alt="REST vs gRPC Throughput">
            </div>
            """
        
        if 'rest_vs_grpc_latency' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['rest_vs_grpc_latency']}" alt="REST vs gRPC Latency">
            </div>
            """
        
        if 'throughput' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['throughput']}" alt="Throughput Performance">
            </div>
            """
        
        if 'latency_anon' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['latency_anon']}" alt="REST Anonymization Latency">
            </div>
            """
        
        if 'latency_grpc' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['latency_grpc']}" alt="gRPC Anonymization Latency">
            </div>
            """
        
        if 'latency_deanon' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['latency_deanon']}" alt="De-anonymization Latency">
            </div>
            """
        
        if 'memory' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['memory']}" alt="Memory Usage">
            </div>
            """
        
        if 'cpu' in plots:
            plots_html += f"""
            <div class="plot">
                <img src="data:image/png;base64,{plots['cpu']}" alt="CPU Utilization">
            </div>
            """
    else:
        plots_html = "<p><em>Plots not available. Install matplotlib to generate visualizations.</em></p>"
    
    total_tests = len(rest_anon_results) + len(grpc_anon_results) + len(deanon_results)
    total_records = sum(r['total_records'] for r in rest_anon_results) + sum(r['total_records'] for r in grpc_anon_results)
    
    # Generate full HTML
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PII Anonymization Service - Benchmark Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        
        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            font-size: 1.8em;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        
        h3 {{
            color: #34495e;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 1.4em;
        }}
        
        .subtitle {{
            color: #7f8c8d;
            font-size: 1.1em;
            margin-bottom: 30px;
        }}
        
        .summary {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }}
        
        .summary h3 {{
            margin-top: 0;
        }}
        
        .summary ul {{
            list-style: none;
            padding-left: 0;
        }}
        
        .summary li {{
            padding: 8px 0;
            border-bottom: 1px solid #bdc3c7;
        }}
        
        .summary li:last-child {{
            border-bottom: none;
        }}
        
        .comparison {{
            margin: 20px 0;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 0.9em;
        }}
        
        th {{
            background: #3498db;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .pass {{
            color: #27ae60;
            font-weight: 600;
        }}
        
        .fail {{
            color: #e74c3c;
            font-weight: 600;
        }}
        
        .plot {{
            margin: 30px 0;
            text-align: center;
        }}
        
        .plot img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        
        .targets {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
        }}
        
        .targets h4 {{
            margin-top: 0;
            color: #856404;
        }}
        
        .targets ul {{
            margin: 10px 0 0 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PII Anonymization Service</h1>
        <p class="subtitle">Performance Benchmark Report</p>
        
        <div class="summary">
            <h3>Executive Summary</h3>
            <ul>
                <li><strong>Total Tests:</strong> {total_tests}</li>
                <li><strong>REST Anonymization Tests:</strong> {len(rest_anon_results)}</li>
                <li><strong>gRPC Anonymization Tests:</strong> {len(grpc_anon_results)}</li>
                <li><strong>De-anonymization Tests:</strong> {len(deanon_results)}</li>
                <li><strong>Total Records Tested:</strong> {total_records:,}</li>
            </ul>
        </div>
        
        <div class="targets">
            <h4>Performance Targets</h4>
            <ul>
                <li><strong>Anonymization Throughput:</strong> ≥50,000 records/second (gRPC streaming)</li>
                <li><strong>Anonymization Latency:</strong> ≤5ms p95</li>
                <li><strong>De-anonymization Latency:</strong> ≤3ms p95</li>
            </ul>
        </div>
        
        {comparison_html}
        
        <h2>Performance Visualizations</h2>
        {plots_html}
        
        <h2>Detailed Results</h2>
        {rest_anon_table}
        {grpc_anon_table}
        {deanon_table}
        
        <div class="footer">
            <p>Generated by PII Anonymization Service Benchmark Suite</p>
        </div>
    </div>
</body>
</html>
    """
    
    # Write HTML to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML report generated: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Generate benchmark report from JSON results')
    parser.add_argument(
        '--input',
        default='benchmark_results.json',
        help='Path to benchmark results JSON file (default: benchmark_results.json)'
    )
    parser.add_argument(
        '--output',
        default='benchmark_report.html',
        help='Path to output HTML report (default: benchmark_report.html)'
    )
    
    args = parser.parse_args()
    
    print(f"Loading benchmark results from {args.input}...")
    results = load_benchmark_results(args.input)
    
    print("Generating performance plots...")
    plots = generate_performance_plots(results)
    
    print(f"Generating HTML report...")
    generate_html_report(results, plots, args.output)
    
    print(f"\n✓ Report generation complete!")
    print(f"  Open {args.output} in your browser to view the report.")


if __name__ == "__main__":
    main()
