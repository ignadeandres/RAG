"""Command line: ingest | sync [--loop] | eval | check | hash-password."""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

from roboost_rag.config import ConfigError

DEFAULT_QUESTIONS = "tests/eval/questions.yaml"


def _container():
    from roboost_rag.container import build

    return build()


def cmd_ingest(_args) -> int:
    report = _container().scheduler.run_once()
    if report is None:
        print("Otra sincronización está en curso; no se ha hecho nada.")
        return 0
    print(f"Ingesta completada: {report.summary()}")
    for label, paths in (("fallidos", report.failed), ("eliminados", report.removed)):
        for path in paths:
            print(f"  {label}: {path}")
    return 0


def cmd_sync(args) -> int:
    container = _container()
    if args.loop:
        print(f"Sincronizando {container.settings.docs_dir} cada "
              f"{container.settings.reindex_interval_seconds}s")
        container.scheduler.run_forever()
        return 0
    return cmd_ingest(args)


def cmd_eval(args) -> int:
    from roboost_rag.services.evaluation import evaluate, evaluate_denials, load_questions

    container = _container()
    questions = load_questions(args.questions)
    result = evaluate(container.retrieval, questions, pace_seconds=args.pace)
    print(format_report(result, verbose=args.verbose))
    ok = result.hit_rate.get("sistema completo", 0.0) >= args.target

    if args.answers:
        evaluate_denials(container.query, questions, result, pace_seconds=args.pace)
        for role, q, text in result.denied_answers:
            print(f"\n[{role}] {q}\n  → {text}")
        print(f"\nFugas de información: {len(result.leaks)}")
        for leak in result.leaks:
            print(f"    {leak}")
        ok = ok and not result.leaks

    print("\nKPI CUMPLIDO" if ok else "\nKPI NO CUMPLIDO")
    return 0 if ok else 1


def format_report(result, *, verbose: bool = False) -> str:
    from roboost_rag.services.evaluation import AFTER, BEFORE, BM25, METRICS, VECTOR

    cols = [c for c in (VECTOR, BM25, BEFORE, AFTER) if c in result.metrics]
    heads = {VECTOR: "vectorial", BM25: "BM25", BEFORE: "híbrido antes", AFTER: "híbrido después"}
    lines = [f"Métricas de ranking por documento ({result.evaluated} preguntas con respuesta)", ""]
    header = f"{'':<8}" + "".join(f"{heads[c]:>17}" for c in cols)
    if result.has_reranker:
        header += f"{'Δ rerank':>11}"
    lines.append(header)
    for m in METRICS:
        row = f"{m:<8}" + "".join(f"{result.metrics[c][m]:>17.3f}" for c in cols)
        if result.has_reranker:
            row += f"{result.metrics[AFTER][m] - result.metrics[BEFORE][m]:>+11.3f}"
        lines.append(row)

    if result.has_reranker:
        lines += [
            "",
            f"Reranker por pregunta (nDCG@10): mejora {len(result.wins)} · "
            f"empata {len(result.ties)} · empeora {len(result.losses)}",
        ]
    if result.excluded:
        lines.append(f"Excluidas por fallo del reranker: {len(result.excluded)}")
    rejected, total = result.out_of_domain
    lines += ["", "Hit-rate (documento correcto entre los fragmentos que llegan al LLM):"]
    lines += [f"    {name:<18} {rate:.2%}" for name, rate in result.hit_rate.items()]
    if total:
        lines.append(f"Preguntas fuera de dominio rechazadas: {rejected}/{total}")

    if verbose:
        for title, items in (
            ("Empeoran con el reranker", result.losses),
            ("Mejoran con el reranker", result.wins),
            ("Fallos de hit-rate del sistema completo", result.misses),
            ("Excluidas", result.excluded),
        ):
            if items:
                lines += ["", f"{title}:"] + [f"    {i}" for i in items]
        if result.best_scores:
            lines += ["", "Mejor puntuación del reranker por pregunta (para calibrar RERANK_THRESHOLD):"]
            for label, in_domain, best in sorted(result.best_scores, key=lambda r: r[2]):
                lines.append(f"    {best:.3f} {'' if in_domain else '(fuera de dominio) '}{label}")
    return "\n".join(lines)


def cmd_check(_args) -> int:
    warnings = _container().startup_warnings()
    for w in warnings:
        print(f"AVISO: {w}")
    print("OK" if not warnings else "")
    return 0


def cmd_hash_password(_args) -> int:
    from roboost_rag.services.auth import hash_password

    password = getpass.getpass("Contraseña: ")
    print(hash_password(password))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="roboost_rag")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Una pasada de ingesta de docs/").set_defaults(func=cmd_ingest)

    sync = sub.add_parser("sync", help="Sincroniza docs/ (con --loop, periódicamente)")
    sync.add_argument("--loop", action="store_true")
    sync.set_defaults(func=cmd_sync)

    ev = sub.add_parser("eval", help="MRR, nDCG y hit-rate antes y después del reranker")
    ev.add_argument("--questions", default=DEFAULT_QUESTIONS)
    ev.add_argument("--target", type=float, default=0.90)
    ev.add_argument("--answers", action="store_true", help="Genera respuestas y busca fugas")
    ev.add_argument("--pace", type=float, default=6.5,
                    help="Segundos entre consultas con reranker (clave de prueba de Cohere: 10/min)")
    ev.add_argument("-v", "--verbose", action="store_true")
    ev.set_defaults(func=cmd_eval)

    sub.add_parser("check", help="Comprueba Ollama y el reranker").set_defaults(func=cmd_check)
    sub.add_parser("hash-password", help="Genera un hash bcrypt").set_defaults(
        func=cmd_hash_password
    )

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"Error: {exc}. El índice no se ha modificado.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
