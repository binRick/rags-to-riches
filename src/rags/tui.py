import webbrowser

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import cache, github, search as search_mod

console = Console()

STYLE = Style([
    ("qmark",       "fg:#89b4fa bold"),
    ("question",    "fg:#cdd6f4 bold"),
    ("answer",      "fg:#a6e3a1 bold"),
    ("pointer",     "fg:#89b4fa bold"),
    ("highlighted", "fg:#89b4fa bold"),
    ("selected",    "fg:#a6e3a1"),
    ("separator",   "fg:#6c7086"),
    ("instruction", "fg:#6c7086 italic"),
    ("text",        "fg:#cdd6f4"),
])

MAX_CHOICES = 30  # max repos shown in a select list


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ask(fn, *args, **kwargs):
    """Run a questionary prompt; return None if user hits Ctrl-C."""
    try:
        return fn(*args, **kwargs, style=STYLE).ask()
    except KeyboardInterrupt:
        return None


def _repo_choice(repo: dict) -> questionary.Choice:
    stars = repo.get("stargazers_count", 0)
    lang  = f"[{repo.get('language') or '?'}]"
    desc  = (repo.get("description") or "")[:55]
    title = f"{repo['full_name']:<35}  {lang:<12}  ⭐ {stars:>6}   {desc}"
    return questionary.Choice(title=title, value=repo)


def _show_repo(repo: dict) -> None:
    body = Text()
    body.append(repo["html_url"] + "\n", style="dim cyan")
    if repo.get("description"):
        body.append(repo["description"] + "\n", style="#cdd6f4")
    body.append(f"\n⭐ {repo.get('stargazers_count', 0):,}  ", style="#f9e2af")
    if repo.get("language"):
        body.append(f"  {repo['language']}  ", style="#a6e3a1")
    if repo.get("topics"):
        body.append("  " + "  ".join(repo["topics"][:6]), style="#6c7086")
    console.print(Panel(body, title=f"[bold #89b4fa]{repo['full_name']}[/]", border_style="#313244"))


def _fetch() -> list[dict]:
    token = github.get_token()
    if not token:
        console.print("[red]No GitHub token found.[/red] Set [bold]GITHUB_TOKEN[/bold] env var.")
        return []

    console.print("")
    repos: list[dict] = []

    def on_page(page: int, total: int) -> None:
        console.print(f"  [dim]page {page} — {total} repos fetched[/dim]")

    try:
        repos = github.fetch_starred(token, on_page=on_page)
        cache.save(repos)
        console.print(f"\n[green]Cached {len(repos)} starred repos.[/green]\n")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")

    return repos


# ── Repo detail ───────────────────────────────────────────────────────────────

def _repo_actions(repo: dict, repos: list[dict]) -> str:
    """Show repo detail and action menu. Returns 'back' or 'menu'."""
    console.print("")
    _show_repo(repo)

    action = _ask(
        questionary.select,
        "What would you like to do?",
        choices=[
            questionary.Choice("Open in browser", value="open"),
            questionary.Choice("Search similar repos", value="similar"),
            questionary.Separator(),
            questionary.Choice("Back", value="back"),
            questionary.Choice("Main menu", value="menu"),
        ],
    )

    if action == "open":
        webbrowser.open(repo["html_url"])
        console.print(f"[dim]Opened {repo['html_url']}[/dim]")
        return _repo_actions(repo, repos)
    if action == "similar":
        query = repo.get("name", "")
        results = search_mod.search(repos, query)
        results = [r for r in results if r["full_name"] != repo["full_name"]]
        return _select_from_results(results[:MAX_CHOICES], repos, f"Similar to {repo['full_name']}")
    return action or "menu"


def _select_from_results(results: list[dict], repos: list[dict], title: str = "Results") -> str:
    if not results:
        console.print("[yellow]No results.[/yellow]")
        return "back"

    choices = [_repo_choice(r) for r in results[:MAX_CHOICES]]
    choices += [questionary.Separator(), questionary.Choice("↩  Back", value=None)]

    repo = _ask(
        questionary.select,
        f"{title} ({len(results)} found):",
        choices=choices,
    )

    if repo is None:
        return "back"
    return _repo_actions(repo, repos)


# ── Flows ─────────────────────────────────────────────────────────────────────

def _search_flow(repos: list[dict]) -> None:
    while True:
        query = _ask(questionary.text, "Search query:")
        if not query:
            return

        results = search_mod.search(repos, query.strip())
        outcome = _select_from_results(results, repos, f'Results for "{query}"')
        if outcome == "menu":
            return
        if outcome == "back":
            continue
        return


def _language_flow(repos: list[dict]) -> None:
    langs = sorted({r.get("language") or "" for r in repos if r.get("language")})
    lang = _ask(
        questionary.select,
        "Choose a language:",
        choices=["All"] + langs,
    )
    if lang is None:
        return

    filtered = repos if lang == "All" else [r for r in repos if r.get("language") == lang]

    sort = _ask(
        questionary.select,
        "Sort by:",
        choices=["Stars", "Name", "Updated"],
    )
    if sort is None:
        return

    if sort == "Stars":
        filtered = sorted(filtered, key=lambda r: r.get("stargazers_count", 0), reverse=True)
    elif sort == "Name":
        filtered = sorted(filtered, key=lambda r: r["full_name"].lower())
    elif sort == "Updated":
        filtered = sorted(filtered, key=lambda r: r.get("updated_at", ""), reverse=True)

    label = lang if lang != "All" else "All languages"
    _select_from_results(filtered[:MAX_CHOICES], repos, f"{label} — {sort}")


def _browse_flow(repos: list[dict]) -> None:
    sort = _ask(
        questionary.select,
        "Sort by:",
        choices=["Stars", "Name", "Updated"],
    )
    if sort is None:
        return

    if sort == "Stars":
        sorted_repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)
    elif sort == "Name":
        sorted_repos = sorted(repos, key=lambda r: r["full_name"].lower())
    else:
        sorted_repos = sorted(repos, key=lambda r: r.get("updated_at", ""), reverse=True)

    _select_from_results(sorted_repos[:MAX_CHOICES], repos, f"All repos — {sort}")


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    console.print(Panel(
        "[bold #89b4fa]Rags to Riches[/bold #89b4fa]  [#6c7086]GitHub Stars Explorer[/#6c7086]",
        border_style="#313244",
        padding=(0, 2),
    ))

    repos, timestamp = cache.load()

    if not repos:
        console.print("[yellow]No cache found.[/yellow] Fetching starred repos from GitHub...\n")
        repos = _fetch()
        if not repos:
            return
    else:
        from datetime import datetime
        age = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        console.print(f"[dim]Loaded {len(repos)} repos from cache (fetched {age})[/dim]\n")

    while True:
        action = _ask(
            questionary.select,
            "What would you like to do?",
            choices=[
                questionary.Choice("Search repos", value="search"),
                questionary.Choice("Browse by language", value="language"),
                questionary.Choice("Browse all", value="browse"),
                questionary.Separator(),
                questionary.Choice("Refresh cache", value="refresh"),
                questionary.Choice("Quit", value="quit"),
            ],
        )

        if action is None or action == "quit":
            console.print("[dim]Bye.[/dim]")
            break
        elif action == "search":
            _search_flow(repos)
        elif action == "language":
            _language_flow(repos)
        elif action == "browse":
            _browse_flow(repos)
        elif action == "refresh":
            repos = _fetch()
