"""Admin and evaluation commands that must not be reachable over HTTP.

    python -m app.cli create-recruiter alice@company.com
    python -m app.cli promote bob@company.com
    python -m app.cli eval-grading --runs 3
    python -m app.cli recalibrate
    python -m app.cli label-grading

In Docker: `docker compose exec api python -m app.cli create-recruiter ...`.

Recruiters can read every candidate's answers, so the role is granted by
someone with shell access to the server — never chosen on a sign-up form.
The password is prompted for (not passed as an argument, which would land in
shell history); set INTERVIEWIQ_PASSWORD to script it.

The eval commands touch no database and enqueue nothing. They grade a
hand-labelled golden set through the same code the pipeline uses, so a change
to scoring can be defended with a number instead of an impression.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.user import UserRole
from app.services.user_service import EmailAlreadyRegistered, UserService

# --- user administration ---------------------------------------------------


async def create_recruiter(db: AsyncSession, email: str, password: str) -> str:
    try:
        user = await UserService(db).register(email, password, role=UserRole.recruiter)
    except EmailAlreadyRegistered:
        return f"{email} already has an account — use `promote` instead."
    return f"Created recruiter {user.email}."


async def promote(db: AsyncSession, email: str) -> str:
    service = UserService(db)
    user = await service.get_by_email(email)
    if user is None:
        return f"No account for {email}."
    await service.set_role(user, UserRole.recruiter)
    return f"{user.email} is now a recruiter."


def _password() -> str:
    if from_env := os.environ.get("INTERVIEWIQ_PASSWORD"):
        return from_env
    first = getpass.getpass("Password (min 8 characters): ")
    if len(first) < 8 or first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 8 characters.")
    return first


async def _run_user_command(args: argparse.Namespace) -> str:
    async with async_session_factory() as db:
        if args.command == "create-recruiter":
            message = await create_recruiter(db, args.email, _password())
        else:
            message = await promote(db, args.email)
        await db.commit()
        return message


# --- evaluation ------------------------------------------------------------


async def _eval_grading(args: argparse.Namespace) -> None:
    from app.embedders import get_embedder, resolved_embedding_provider
    from app.eval.golden import load_golden
    from app.eval.grading_eval import evaluate, write_baseline
    from app.providers import get_provider

    items = load_golden()
    embedder = get_embedder()
    provider = get_provider()

    print(
        f"Grading {len(items)} golden items — llm={provider.name}, "
        f"embedder={embedder.name} ({resolved_embedding_provider()}), runs={args.runs}\n"
    )
    report, results = await evaluate(
        items, embedder=embedder, provider=provider, runs=args.runs
    )
    print(report.table())

    if args.write:
        path = write_baseline(report, results, name=args.name, embedder=embedder)
        print(f"\nBaseline written to {path}")
    else:
        print("\n(--no-write: nothing saved)")


async def _recalibrate(args: argparse.Namespace) -> None:
    from app.core.config import settings
    from app.embedders import get_embedder
    from app.eval.golden import load_golden
    from app.eval.grading_eval import sweep_coverage_threshold
    from app.providers import get_provider

    candidates: list[float] = []
    value = args.min
    while value <= args.max + 1e-9:
        candidates.append(round(value, 4))
        value += args.step

    items = load_golden()
    embedder = get_embedder()
    print(
        f"Sweeping EVAL_COVERAGE_THRESHOLD over {len(candidates)} values "
        f"with embedder={embedder.name} (current setting: "
        f"{settings.EVAL_COVERAGE_THRESHOLD})\n"
    )
    rows = await sweep_coverage_threshold(
        items, embedder=embedder, provider=get_provider(), candidates=candidates
    )

    print(f"  {'threshold':>10}  {'mae':>7}  {'kappa':>7}  {'review':>7}")
    for threshold, report in rows:
        marker = " <- current" if abs(threshold - settings.EVAL_COVERAGE_THRESHOLD) < 1e-9 else ""
        print(
            f"  {threshold:>10.2f}  {report.mae:>7.3f}  {report.kappa:>7.3f}  "
            f"{report.review_rate:>6.1%}{marker}"
        )

    # Lowest error wins; kappa breaks a tie, because two thresholds can sit the
    # same distance from the labels while disagreeing on the pass/fail calls.
    best_threshold, best = min(rows, key=lambda row: (row[1].mae, -row[1].kappa))
    print(
        f"\nBest: EVAL_COVERAGE_THRESHOLD={best_threshold:.2f} "
        f"(mae {best.mae:.3f}, kappa {best.kappa:.3f})"
    )
    if abs(best_threshold - settings.EVAL_COVERAGE_THRESHOLD) > 1e-9:
        print(f"Set it in .env:  EVAL_COVERAGE_THRESHOLD={best_threshold:.2f}")
    else:
        print("The current setting is already the best of the candidates.")


_KEY_TO_SCORE = {"0": 0.0, "1": 0.25, "2": 0.5, "3": 0.75, "4": 1.0}


def _label_grading(args: argparse.Namespace) -> None:
    """Replace bootstrap labels with real ones, one keypress at a time.

    The bootstrap labels make the harness runnable today; they cannot make it
    *meaningful*, because a set labelled by the same family of model being
    measured only reports self-consistency. This is the tool that fixes that.
    """
    from app.eval.golden import load_golden, save_golden

    items = load_golden()
    todo = [i for i in items if args.all or i.labeled_by != "human"]
    if not todo:
        print("Every item already carries a human label. Use --all to revisit them.")
        return

    print(
        f"{len(todo)} item(s) to label.  "
        f"0=0.00  1=0.25  2=0.50  3=0.75  4=1.00  |  [s]kip  [q]uit and save\n"
        "Score how well the answer covers the expected concepts.\n"
    )

    changed = 0
    for n, item in enumerate(todo, start=1):
        concepts = "\n".join(f"      - {c}" for c in item.expected_concepts)
        print("=" * 78)
        print(f"[{n}/{len(todo)}]  {item.id}  ({item.topic})")
        print(f"\n  Q: {item.question}")
        print(f"\n  Expected concepts:\n{concepts}")
        print(f"\n  Answer:\n      {item.answer}")
        print(f"\n  current: {item.label:.2f} ({item.labeled_by}) — {item.note}")

        while True:
            try:
                choice = input("\n  score > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"
            if choice in _KEY_TO_SCORE:
                item.label = _KEY_TO_SCORE[choice]
                item.labeled_by = "human"
                changed += 1
                break
            if choice == "s":
                break
            if choice == "q":
                save_golden(items)
                print(f"\nSaved. {changed} item(s) relabelled.")
                return
            print("  Enter 0-4, or s to skip, or q to quit.")

    save_golden(items)
    print(f"\nDone. {changed} item(s) relabelled.")


# --- entry point -----------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("create-recruiter", help="new recruiter account").add_argument("email")
    commands.add_parser("promote", help="make an existing account a recruiter").add_argument(
        "email"
    )

    run_eval = commands.add_parser("eval-grading", help="score the golden set, print metrics")
    run_eval.add_argument(
        "--runs", type=int, default=1, help="grade each item N times to measure stability"
    )
    run_eval.add_argument("--name", default="grading", help="baseline filename stem")
    run_eval.add_argument(
        "--no-write", dest="write", action="store_false", help="print only, save nothing"
    )

    recal = commands.add_parser(
        "recalibrate", help="sweep EVAL_COVERAGE_THRESHOLD against the golden set"
    )
    recal.add_argument("--min", type=float, default=0.20)
    recal.add_argument("--max", type=float, default=0.90)
    recal.add_argument("--step", type=float, default=0.05)

    label = commands.add_parser("label-grading", help="hand-label the golden set")
    label.add_argument(
        "--all", action="store_true", help="revisit items that already have a human label"
    )

    args = parser.parse_args()

    match args.command:
        case "create-recruiter" | "promote":
            print(asyncio.run(_run_user_command(args)))
        case "eval-grading":
            asyncio.run(_eval_grading(args))
        case "recalibrate":
            asyncio.run(_recalibrate(args))
        case "label-grading":
            _label_grading(args)


if __name__ == "__main__":
    main()
