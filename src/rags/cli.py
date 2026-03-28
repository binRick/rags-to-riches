import webbrowser

import click
from rich.console import Console
from rich.table import Table

from . import cache, github, search as search_mod

console = Console()


def _get_repos(force: bool = False) -> list[dict]:
    repos, timestamp = cache.load()

    if force or repos is None or (timestamp is not None and cache.is_stale(timestamp)):
        token = github.get_token()
        if not token:
            console.print(
                "[red]No GitHub token found.[/red] "
                "Set [bold]GITHUB_TOKEN[/bold] env var or install the [bold]gh[/bold] CLI."
            )
            raise SystemExit(1)

        with console.status("Fetching starred repos from GitHub..."):
            repos = github.fetch_starred(token)

        cache.save(repos)
        age = "fresh" if force else "updated"
        console.print(f"[green]Cached {len(repos)} starred repos ({age}).[/green]")

    return repos


@click.group()
def cli():
    """Search your GitHub starred repositories."""


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=20, show_default=True, help="Max results to show.")
@click.option("--open", "-o", "open_url", is_flag=True, help="Open top result in browser.")
@click.option("--refresh", "-r", is_flag=True, help="Refresh cache before searching.")
def search(query: str, limit: int, open_url: bool, refresh: bool) -> None:
    """Search starred repos by name, description, topic, or language."""
    repos = _get_repos(force=refresh)
    results = search_mod.search(repos, query)

    if not results:
        console.print(f"[yellow]No results for '[bold]{query}[/bold]'.[/yellow]")
        return

    if open_url:
        url = results[0]["html_url"]
        console.print(f"Opening [cyan]{url}[/cyan]")
        webbrowser.open(url)
        return

    table = Table(show_header=True, header_style="bold magenta", expand=False)
    table.add_column("Repository", style="cyan", no_wrap=True)
    table.add_column("Description", max_width=55)
    table.add_column("Language", style="green", no_wrap=True)
    table.add_column("Stars", justify="right", style="yellow", no_wrap=True)
    table.add_column("URL", style="dim")

    for repo in results[:limit]:
        table.add_row(
            repo["full_name"],
            repo.get("description") or "",
            repo.get("language") or "",
            str(repo.get("stargazers_count", 0)),
            repo["html_url"],
        )

    console.print(table)
    shown = min(limit, len(results))
    console.print(f"[dim]{shown} of {len(results)} result(s)[/dim]")


@cli.command()
def refresh() -> None:
    """Force refresh the local stars cache."""
    _get_repos(force=True)
