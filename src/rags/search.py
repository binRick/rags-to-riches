def score_repo(repo: dict, query: str) -> int:
    q = query.lower()
    name = repo.get("name", "").lower()
    full_name = repo.get("full_name", "").lower()
    description = (repo.get("description") or "").lower()
    topics = " ".join(repo.get("topics") or []).lower()
    language = (repo.get("language") or "").lower()

    if q == name:
        return 100
    if name.startswith(q):
        return 80
    if q in name:
        return 60
    if q in full_name:
        return 50
    if q in topics:
        return 40
    if q in description:
        return 30
    if q in language:
        return 20
    return 0


def search(repos: list[dict], query: str) -> list[dict]:
    scored = [(score_repo(r, query), r) for r in repos]
    matched = [(s, r) for s, r in scored if s > 0]
    matched.sort(key=lambda x: (-x[0], x[1]["full_name"]))
    return [r for _, r in matched]
