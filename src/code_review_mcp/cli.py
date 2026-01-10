"""
CLI commands for Code Review MCP.

Provides utility commands like init-rules to set up Cursor rules.
"""

import shutil
from pathlib import Path
from typing import Literal

import click


def get_rules_dir() -> Path:
    """Get the path to the bundled rules directory."""
    return Path(__file__).parent / "rules"


@click.group(invoke_without_command=True)
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["stdio", "sse", "websocket"]),
    default=None,
    help="Transport mode: stdio (default), sse, or websocket",
)
@click.option(
    "--host",
    "-H",
    default="0.0.0.0",
    help="Host for SSE/WebSocket server (default: 0.0.0.0)",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    type=int,
    help="Port for SSE/WebSocket server (default: 8000)",
)
@click.version_option()
@click.pass_context
def cli(
    ctx: click.Context,
    transport: Literal["stdio", "sse", "websocket"] | None,
    host: str,
    port: int,
) -> None:
    """
    Code Review MCP - AI-powered code review for GitHub/GitLab.

    Run without subcommand to start the MCP server (default: stdio transport).

    Examples:

        # Start MCP server (stdio mode, for Cursor/Claude Desktop)
        code-review-mcp

        # Start with SSE transport
        code-review-mcp --transport sse --port 8000

        # Initialize Cursor rules in your project
        code-review-mcp init-rules
    """
    # If no subcommand is provided, run the server
    if ctx.invoked_subcommand is None:
        import asyncio

        from .server import run_sse, run_stdio, run_websocket

        transport_mode = transport or "stdio"

        if transport_mode == "stdio":
            asyncio.run(run_stdio())
        elif transport_mode == "sse":
            run_sse(host, port)
        else:
            run_websocket(host, port)


@cli.command("init-rules")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing rules if they exist",
)
@click.option(
    "--target",
    "-t",
    type=click.Path(),
    default=".",
    help="Target directory (default: current directory)",
)
def init_rules(force: bool, target: str) -> None:
    """
    Initialize Cursor rules for code review in your project.

    This command copies the code review rules to your project's
    .cursor/rules/ directory, enabling AI-assisted code review
    with best practices.

    Examples:

        # Initialize rules in current directory
        code-review-mcp init-rules

        # Initialize rules in a specific directory
        code-review-mcp init-rules --target /path/to/project

        # Overwrite existing rules
        code-review-mcp init-rules --force
    """
    target_path = Path(target).resolve()
    rules_target = target_path / ".cursor" / "rules"
    source_rules = get_rules_dir()

    if not source_rules.exists():
        click.echo(click.style("Error: Rules directory not found in package.", fg="red"))
        raise SystemExit(1)

    # Check if rules already exist
    existing_rules = []
    for rule_file in source_rules.glob("*.mdc"):
        target_file = rules_target / rule_file.name
        if target_file.exists() and not force:
            existing_rules.append(rule_file.name)

    if existing_rules:
        click.echo(click.style("The following rules already exist:", fg="yellow"))
        for rule in existing_rules:
            click.echo(f"  - {rule}")
        click.echo("\nUse --force to overwrite existing rules.")
        raise SystemExit(1)

    # Create target directory
    rules_target.mkdir(parents=True, exist_ok=True)

    # Copy rules
    copied = []
    for rule_file in source_rules.glob("*.mdc"):
        target_file = rules_target / rule_file.name
        shutil.copy2(rule_file, target_file)
        copied.append(rule_file.name)

    if copied:
        click.echo(click.style("✓ Cursor rules installed successfully!", fg="green"))
        click.echo(f"\nInstalled to: {rules_target}")
        click.echo("\nRules installed:")
        for rule in copied:
            click.echo(f"  - {rule}")
        click.echo(
            "\n" + click.style("Next steps:", fg="cyan") + "\n"
            "1. Open your project in Cursor\n"
            "2. The rules will be automatically loaded\n"
            "3. Use @code-review or @code-review-en to reference the rules"
        )
    else:
        click.echo(click.style("No rules found to install.", fg="yellow"))


@cli.command("list-rules")
def list_rules() -> None:
    """List available Cursor rules."""
    source_rules = get_rules_dir()

    if not source_rules.exists():
        click.echo(click.style("Error: Rules directory not found.", fg="red"))
        raise SystemExit(1)

    rules = list(source_rules.glob("*.mdc"))

    if not rules:
        click.echo("No rules available.")
        return

    click.echo(click.style("Available Cursor Rules:", fg="cyan"))
    click.echo()
    for rule_file in rules:
        # Read first few lines to get description
        content = rule_file.read_text()
        description = ""
        for line in content.split("\n"):
            if line.startswith("description:"):
                description = line.replace("description:", "").strip()
                break

        click.echo(f"  {click.style(rule_file.name, fg='green')}")
        if description:
            click.echo(f"    {description}")
        click.echo()


if __name__ == "__main__":
    cli()
