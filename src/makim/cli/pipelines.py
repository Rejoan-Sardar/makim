"""Pipeline command handling functions."""

from typing import Optional
import typer
import time
import sqlite3
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import networkx as nx
from asciinet import graph_to_ascii
from makim.core import Makim
from makim.pipelines import MakimPipelineEngine
from makim.cli.auto_generator import create_dynamic_command_pipeline


def _create_pipeline_table() -> Table:
    """Create a table for displaying defined pipelines."""
    table = Table(show_header=True, header_style='bold magenta')
    table.add_column('Name', style='cyan')
    table.add_column('Steps', style='blue')
    table.add_column('Help', style='green')
    return table


def _handle_pipeline_commands(makim_instance: Makim) -> typer.Typer:
    """Create and handle pipeline-related commands."""
    typer_pipeline = typer.Typer(
        help='Pipeline execution and visualization',
        invoke_without_command=True,
    )

    pipelines = makim_instance.global_data.get("pipelines", {})

    for pipeline_name, pipeline_data in pipelines.items():
        create_dynamic_command_pipeline(
            makim_instance,
            typer_pipeline,
            pipeline_name,
            pipeline_data or {},
        )

    @typer_pipeline.command(help='List all defined pipelines')
    def list() -> None:
        """List pipelines defined in .makim.yaml."""
        if not pipelines:
            typer.echo("No pipelines defined in .makim.yaml")
            return

        console = Console()
        table = _create_pipeline_table()

        for name, config in pipelines.items():
            step_count = len(config.get("steps", []))
            help_text = config.get("help", "—")
            table.add_row(name, f"{step_count} step(s)", help_text)

        console.print(table)

    @typer_pipeline.command(help='Show pipeline structure')
    def show(name: str) -> None:
        """Visualize a pipeline's structure using NetworkX and asciinet."""
        pipeline = pipelines.get(name)
        if not pipeline:
            typer.echo(f"Pipeline '{name}' not found.")
            raise typer.Exit(1)

        steps = pipeline.get("steps", [])

        typer.echo(f"DEBUG: Pipeline '{name}' has {len(steps)} steps.")

        if not steps:
            typer.echo(f"Pipeline '{name}' has no steps defined.")
            raise typer.Exit(1)

        G = nx.DiGraph()

        previous_step = None
        for step in steps:
            step_name = step["target"]
            typer.echo(f"DEBUG: Adding step '{step_name}' to graph.")
            G.add_node(step_name)
            if previous_step:
                G.add_edge(previous_step, step_name)
            previous_step = step_name

        ascii_graph = graph_to_ascii(G)

        console = Console()
        console.print(Panel(ascii_graph, title=f"Pipeline: {name}", subtitle="Execution Order"))

    @typer_pipeline.command(help="Run a single pipeline with execution mode")
    def run(
        name: str = typer.Argument(..., help="Pipeline name to run"),
        parallel: bool = typer.Option(False, "--parallel", help="Run pipeline in parallel"),
        sequential: bool = typer.Option(False, "--sequential", help="Run pipeline sequentially"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate execution without running tasks"),
        debug: bool = typer.Option(False, "--debug", help="Enable detailed debug output"),
        max_workers: Optional[int] = typer.Option(None, "--max-workers", help="Limit parallel execution workers"),
    ) -> None:
        """Execute a single pipeline in sequential or parallel mode."""
        
        if parallel and sequential:
            typer.echo("❌ Conflicting options: --parallel and --sequential cannot be used together.")
            raise typer.Exit(1)

        pipeline = pipelines.get(name)
        if not pipeline:
            typer.echo(f"❌ Pipeline '{name}' not found.")
            raise typer.Exit(1)

        steps = pipeline.get("steps", [])
        if not steps:
            typer.echo(f"⚠️ Pipeline '{name}' has no steps defined.")
            return

        engine = MakimPipelineEngine(config_file=makim_instance.file)

        if dry_run:
            typer.echo(f"📝 DRY RUN: Showing steps for pipeline '{name}':")
            for step in steps:
                typer.echo(f"   - {step['target']} {step.get('args', {})}")
            typer.echo("✅ Dry run complete. No steps were executed.")
            return

        if debug:
            typer.echo(f"🔍 DEBUG MODE ENABLED: Running pipeline '{name}' with detailed logs")

        if parallel:
            typer.echo(f"🚀 Running pipeline '{name}' in PARALLEL mode...")
            engine.run_pipeline_parallel(name, steps, debug=debug, max_workers=max_workers, dry_run=dry_run)
        else:
            typer.echo(f"🔄 Running pipeline '{name}' in SEQUENTIAL mode...")
            engine.run_pipeline_sequential(name, steps, debug=debug, dry_run=dry_run)

        typer.echo(f"✅ Pipeline '{name}' executed successfully.")

    def run_all(
        parallel: bool = typer.Option(False, "--parallel", help="Run all pipelines in parallel"),
        sequential: bool = typer.Option(False, "--sequential", help="Run all pipelines sequentially"),
        max_workers: Optional[int] = typer.Option(None, "--max-workers", help="Limit parallel execution workers"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Simulate execution without running tasks"),
        debug: bool = typer.Option(False, "--debug", help="Enable detailed debug output"),
    ) -> None:
        """Execute all pipelines in sequential or parallel mode with optional dry-run and debug mode."""

        if parallel and sequential:
            typer.echo("❌ Conflicting options: --parallel and --sequential cannot be used together.")
            raise typer.Exit(1)

        if not pipelines:
            typer.echo("⚠️ No pipelines found in .makim.yaml.")
            return

        engine = MakimPipelineEngine(config_file=makim_instance.file)

        if dry_run:
            typer.echo("📝 DRY RUN: Listing all pipelines and their steps...")
            for name, pipeline in pipelines.items():
                typer.echo(f"▶ Pipeline: {name}")
                for step in pipeline.get("steps", []):
                    typer.echo(f"   - {step['target']} {step.get('args', {})}")
            typer.echo("✅ Dry run complete. No steps were executed.")
            return

        if parallel:
            typer.echo("🚀 Running ALL pipelines in PARALLEL mode...")
            for name, pipeline in pipelines.items():
                steps = pipeline.get("steps", [])
                engine.run_pipeline_parallel(name, steps, debug=debug, max_workers=max_workers, dry_run=dry_run)
        else:
            typer.echo("🔄 Running ALL pipelines in SEQUENTIAL mode...")
            for name, pipeline in pipelines.items():
                steps = pipeline.get("steps", [])
                engine.run_pipeline_sequential(name, steps, debug=debug, dry_run=dry_run)

        typer.echo("✅ All pipelines executed successfully.")


    def _execute_pipeline(name, pipeline_data, parallel, sequential, dry_run, debug, max_workers):
        """Helper function to execute a single pipeline with the given options."""
        steps = pipeline_data.get("steps", [])
        if not steps:
            typer.echo(f"⚠️ Pipeline '{name}' has no steps defined.")
            return

        engine = MakimPipelineEngine(config_file=makim_instance.file)

        if dry_run:
            typer.echo(f"📝 DRY RUN: Showing steps for pipeline '{name}':")
            for step in steps:
                typer.echo(f"   - {step['target']} {step.get('args', {})}")
            typer.echo("✅ Dry run complete. No steps were executed.")
            return

        if debug:
            typer.echo(f"🔍 DEBUG MODE ENABLED: Running pipeline '{name}' with detailed logs")

        if parallel:
            typer.echo(f"🚀 Running pipeline '{name}' in PARALLEL mode...")
            engine.run_pipeline_parallel(name, steps, debug=debug, max_workers=max_workers, dry_run=dry_run)
        elif sequential or not parallel:
            typer.echo(f"🔄 Running pipeline '{name}' in SEQUENTIAL mode...")
            engine.run_pipeline_sequential(name, steps, debug=debug, dry_run=dry_run)


    @typer_pipeline.command(help="Show recent pipeline logs or clear them")
    def logs(
        pipeline: Optional[str] = typer.Argument(None, help="Pipeline name to filter logs"),
        named_pipeline: Optional[str] = typer.Option(None, "--pipeline", "-p", help="Pipeline name to filter logs"),
        last: int = typer.Option(10, "--last", "-l", help="Number of recent logs to display"),
        clear: bool = typer.Option(False, "--clear", "-c", help="Clear all pipeline logs"),
        follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs in real-time"),
        status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter logs by status (e.g., 'failed', 'success')"),
    ) -> None:

        """Print, follow, or clear pipeline run logs from SQLite."""
        pipeline_name = named_pipeline or pipeline
        if clear:
            _clear_pipeline_logs(pipeline_name)
            typer.echo("✅ Pipeline logs cleared successfully.")
            return

        if follow:
            typer.echo(f"📡 Following logs for pipeline '{pipeline_name or 'ALL'}'... (Press Ctrl+C to stop)")
            _follow_logs(pipeline_name)
            return

        logs = _get_pipeline_logs(pipeline_name, last, status)
        _display_logs(logs)

    @typer_pipeline.command(help="Schedule a pipeline for automatic execution.")
    def schedule(
        name: str = typer.Argument(..., help="Pipeline name to schedule"),
        cron: Optional[str] = typer.Option(None, help="Cron expression (e.g., '0 9 * * *' for daily at 9 AM)"),
        interval: Optional[int] = typer.Option(None, help="Interval in seconds"),
    ) -> None:
        """Schedule a pipeline execution using cron or interval."""
        if not cron and not interval:
            typer.echo("❌ Please provide either a cron expression (--cron) or an interval (--interval).")
            raise typer.Exit(1)

        engine = MakimPipelineEngine(config_file=makim_instance.file)
        engine.schedule_pipeline(name, cron_expression=cron, interval_seconds=interval)
        typer.echo(f"✅ Scheduled pipeline '{name}' successfully.")


    @typer_pipeline.command(help="List all scheduled pipelines.")
    def scheduled() -> None:
        """List scheduled pipelines."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        schedules = engine.list_scheduled_pipelines()

        if not schedules:
            typer.echo("No pipelines are scheduled.")
            return

        console = Console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Pipeline", style="cyan")
        table.add_column("Cron Expression")
        table.add_column("Interval (seconds)")

        for pipeline, cron_exp, interval in schedules:
            table.add_row(pipeline, cron_exp or "-", str(interval or "-"))

        console.print(table)

    @typer_pipeline.command(help="Remove a scheduled pipeline.")
    def unschedule(name: str) -> None:
        """Unscheduled a pipeline (remove from SQLite and scheduler)."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        engine.unschedule_pipeline(name)
    
    @typer_pipeline.command(help="Retry the last failed execution of a pipeline.")
    def retry(name: str) -> None:
        """Retries the last failed execution of a pipeline."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        engine.retry_pipeline(name)


    @typer_pipeline.command(help="Cancel a running pipeline.")
    def cancel(name: str) -> None:
        """Cancels a running pipeline."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        engine.cancel_pipeline(name)

    @typer_pipeline.command(help="Show past executions of pipelines.")
    def history(
        name: Optional[str] = typer.Argument(None, help="Pipeline name to filter history."),
        limit: int = typer.Option(10, help="Number of past executions to show.")
    ) -> None:
        """Displays past pipeline executions."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        history_data = engine.get_pipeline_history(name, limit)

        if not history_data:
            typer.echo(f"❌ No execution history found for pipeline '{name}'." if name else "No execution history found.")
            return

        console = Console()
        table = Table(show_header=True, header_style="bold yellow")
        table.add_column("Pipeline", style="cyan")
        table.add_column("Step")
        table.add_column("Status")
        table.add_column("Time", style="dim")

        for entry in history_data:
            table.add_row(*map(str, entry))

        console.print(Panel(table, title="📜 Pipeline Execution History"))


    @typer_pipeline.command(help="Retry all failed executions of a pipeline.")
    def retry(
        name: str = typer.Argument(..., help="Pipeline name to retry."),
        all_failed: bool = typer.Option(False, "--all", help="Retry all failed steps.")
    ) -> None:
        """Retries pipeline failures."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)

        if all_failed:
            engine.retry_all_failed(name)
        else:
            engine.retry_pipeline(name)

    @typer_pipeline.command(help="Start a scheduled pipeline manually via cron")
    def start(
        name: str = typer.Argument(..., help="Pipeline name to start"),
    ) -> None:
        """Manually start a pipeline through cron."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        
        if not engine.is_pipeline_scheduled(name):
            typer.echo(f"❌ Pipeline '{name}' is not scheduled.")
            raise typer.Exit(1)
        
        typer.echo(f"🚀 Starting scheduled pipeline: {name}")
        engine.run_pipeline_sequential(name, engine.get_pipeline_steps(name))


    @typer_pipeline.command(help="Stop a scheduled pipeline manually via cron")
    def stop(
        name: str = typer.Argument(..., help="Pipeline name to stop"),
    ) -> None:
        """Manually stop a pipeline through cron."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        
        if not engine.is_pipeline_scheduled(name):
            typer.echo(f"❌ Pipeline '{name}' is not scheduled.")
            raise typer.Exit(1)
        
        engine.unschedule_pipeline(name)
        typer.echo(f"🛑 Stopped scheduled pipeline: {name}")

    @typer_pipeline.command(help="Show running and scheduled pipelines.")
    def status() -> None:
        """Displays the status of pipelines (Running, Scheduled, Recent Executions)."""
        engine = MakimPipelineEngine(config_file=makim_instance.file)
        status_data = engine.get_pipeline_status()

        console = Console()

        if status_data["scheduled"]:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Pipeline", style="cyan")
            table.add_column("Cron Expression")
            table.add_column("Interval (seconds)")

            for pipeline, cron_exp, interval in status_data["scheduled"]:
                table.add_row(pipeline, cron_exp or "-", str(interval or "-"))

            console.print(Panel(table, title="📅 Scheduled Pipelines"))

        if status_data["running"]:
            running_table = Table(show_header=True, header_style="bold green")
            running_table.add_column("Pipeline", style="cyan")
            running_table.add_column("Next Run Time", style="blue")

            for job in status_data["running"]:
                running_table.add_row(job.id, str(job.next_run_time))

            console.print(Panel(running_table, title="🚀 Running Pipelines"))

        if status_data["recent_executions"]:
            exec_table = Table(show_header=True, header_style="bold yellow")
            exec_table.add_column("Pipeline", style="cyan")
            exec_table.add_column("Step")
            exec_table.add_column("Status")
            exec_table.add_column("Time", style="dim")

            for entry in status_data["recent_executions"]:
                exec_table.add_row(*map(str, entry))

            console.print(Panel(exec_table, title="📝 Recent Executions"))

    return typer_pipeline

def _get_pipeline_logs(pipeline: Optional[str], limit: int, status: Optional[str] = None):
    """Retrieve execution logs for pipelines from SQLite."""
    db_path = Path.home() / ".makim" / "pipelines.sqlite"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT pipeline_name, step, status, timestamp, output, error FROM pipeline_runs ORDER BY timestamp DESC LIMIT ?"
    params = (limit,)

    if pipeline and status:
        query = "SELECT pipeline_name, step, status, timestamp, output, error FROM pipeline_runs WHERE pipeline_name = ? AND status = ? ORDER BY timestamp DESC LIMIT ?"
        params = (pipeline, status, limit)
    elif pipeline:
        query = "SELECT pipeline_name, step, status, timestamp, output, error FROM pipeline_runs WHERE pipeline_name = ? ORDER BY timestamp DESC LIMIT ?"
        params = (pipeline, limit)
    elif status:
        query = "SELECT pipeline_name, step, status, timestamp, output, error FROM pipeline_runs WHERE status = ? ORDER BY timestamp DESC LIMIT ?"
        params = (status, limit)

    cursor.execute(query, params)
    logs = cursor.fetchall()
    conn.close()

    return logs

def _display_logs(logs):
    """Print pipeline logs in a formatted table."""
    if not logs:
        typer.echo("No pipeline execution logs found.")
        raise typer.Exit(0)

    console = Console()
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Pipeline", style="cyan")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Time", style="dim")
    table.add_column("Output", style="green")
    table.add_column("Error", style="red")

    for log in logs:
        pipeline_name, step, status, timestamp, output, error = log
        table.add_row(pipeline_name, step, status, timestamp, output or "-", error or "-")

    console.print(table)

def _follow_logs(pipeline: Optional[str] = None):
    """Continuously fetch and display logs in real-time."""
    db_path = Path.home() / ".makim" / "pipelines.sqlite"
    
    last_timestamp = None

    try:
        while True:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            query = "SELECT pipeline_name, step, status, timestamp, output, error FROM pipeline_runs ORDER BY timestamp DESC LIMIT 5"
            params = ()

            if pipeline:
                query = "SELECT pipeline_name, step, status, timestamp, output, error FROM pipeline_runs WHERE pipeline_name = ? ORDER BY timestamp DESC LIMIT 5"
                params = (pipeline,)

            cursor.execute(query, params)
            logs = cursor.fetchall()
            conn.close()

            for log in logs[::-1]:
                pipeline_name, step, status, timestamp, output, error = log
                if last_timestamp and timestamp <= last_timestamp:
                    continue
                
                last_timestamp = timestamp
                typer.echo(f"📡 [{timestamp}] {pipeline_name} | {step} | {status} | {output or '-'} | {error or '-'}")

            time.sleep(2)

    except KeyboardInterrupt:
        typer.echo("🛑 Stopped following logs.")

def _clear_pipeline_logs(pipeline: Optional[str] = None) -> None:
    """Clear logs for a specific pipeline or all logs."""
    db_path = Path.home() / ".makim" / "pipelines.sqlite"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if pipeline:
        cursor.execute("DELETE FROM pipeline_runs WHERE pipeline_name = ?", (pipeline,))
    else:
        cursor.execute("DELETE FROM pipeline_runs")

    conn.commit()
    conn.close()
