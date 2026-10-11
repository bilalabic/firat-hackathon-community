"""Local LLM benchmark for URL import extraction (V1.2 part C, docs/research/LLM_BENCHMARK.md).

    uv run python bench/extraction_bench.py run --models qwen3.5:4b-q4_K_M gemma4:e2b-it-qat
    uv run python bench/extraction_bench.py run --models ... --pages devpost-qloo tr-datamedx
    uv run python bench/extraction_bench.py rating-sheet bench/data/results/<run>.json

`run` takes each page from bench/data/pages/<id>.html (saved by fetch_pages.py; nothing is
fetched again), pushes it through page loader -> extractor for every model, scores the
result against bench/data/gold/<id>.json (see scoring.py) and writes
bench/data/results/<run>.json and <run>.md. bench/data/ is gitignored (third-party pages).

Wiring. The loader and the extractor are created in `make_pipeline`, the only place that
knows their constructors. They are imported lazily: importing/page.py and
importing/extraction.py may not exist yet. Until they do, `--loader builtin` (a tiny
stdlib HTML-to-text loader) and the structured-output call of the LLM provider alone
cannot run, so `run` exits with a clear message instead. Adjust the two marked lines when
the real classes land.

Metrics per model: schema validity (extraction finished without `llm_error`; the provider
already includes its one repair retry), per-field accuracy, hallucinations (a field filled
although the gold file says the page does not state it), wall time per page (p50/p95/max),
GPU memory peak (nvidia-smi sampled every 0.5 s).
"""

import argparse
import importlib
import json
import random
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

import httpx2
from scoring import Outcome, percentile, score_page, summarize

from fhc_api.common.http import SafeFetcher
from fhc_api.importing.models import (
    EXTRACTABLE_FIELDS,
    MAX_TEXT_CHARS,
    ExtractionResult,
    PageContent,
)
from fhc_api.llm.ollama import OllamaProvider

BENCH_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCH_DIR / "data"
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_TIMEOUT_SECONDS = 300.0
VRAM_SAMPLE_SECONDS = 0.5
NVIDIA_SMI = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]


# --- wiring ------------------------------------------------------------------------------


class LoaderLike(Protocol):
    def load_page(self, url: str) -> PageContent: ...


class ExtractorLike(Protocol):
    def extract(self, page: PageContent) -> ExtractionResult: ...


@dataclass
class Pipeline:
    loader: LoaderLike
    extractor: ExtractorLike
    close: Callable[[], None] = lambda: None


class _TextParser(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "svg", "head"})
    _BREAK = frozenset({"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "section"})

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title: str | None = None
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            self.title = data.strip() or None
        if not self._skip_depth:
            self.parts.append(data)


class BuiltinLoader:
    """Stand-in for the real page loader: saved HTML -> plain text, no structured data."""

    def __init__(self, pages: dict[str, bytes]) -> None:
        self._pages = pages

    def load_page(self, url: str) -> PageContent:
        parser = _TextParser()
        parser.feed(self._pages[url].decode("utf-8", errors="replace"))
        lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
        text = "\n".join(line for line in lines if line)
        return PageContent(
            requested_url=url,
            final_url=url,
            fetched_at=datetime.now(UTC),
            title=parser.title,
            text=text[:MAX_TEXT_CHARS],
            text_truncated=len(text) > MAX_TEXT_CHARS,
        )


def _saved_fetcher(pages: dict[str, bytes]) -> SafeFetcher:
    """A SafeFetcher that serves the saved HTML, so the real loader runs unchanged."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        # SafeFetcher connects to the pinned IP; the original host is in the Host header.
        url = request.url.copy_with(netloc=request.headers["host"].encode("ascii"))
        body = pages.get(str(url))
        if body is None:
            return httpx2.Response(404)
        return httpx2.Response(200, content=body, headers={"content-type": "text/html"})

    return SafeFetcher(
        transport=httpx2.MockTransport(handler), resolver=lambda _h, _p: ["93.184.216.34"]
    )


def make_pipeline(model: str, pages: dict[str, bytes], loader_kind: str) -> Pipeline:
    """Create loader + extractor for one model. The only code that knows their constructors."""
    provider = OllamaProvider(OLLAMA_URL, model, OLLAMA_TIMEOUT_SECONDS)
    if loader_kind == "builtin":
        loader: LoaderLike = BuiltinLoader(pages)
    else:
        page_module = importlib.import_module("fhc_api.importing.page")
        loader = page_module.HtmlPageLoader(_saved_fetcher(pages))
    extraction_module = importlib.import_module("fhc_api.importing.extraction")
    extractor: ExtractorLike = extraction_module.LLMExtractor(provider, model_label=model)
    return Pipeline(loader, extractor, provider.close)


# --- GPU memory ----------------------------------------------------------------------------


class VramSampler:
    """Samples `nvidia-smi` memory.used (MiB) every VRAM_SAMPLE_SECONDS in a thread."""

    def __init__(self) -> None:
        self.samples: list[int] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def read() -> int | None:
        try:
            out = subprocess.run(  # noqa: S603
                NVIDIA_SMI, capture_output=True, text=True, timeout=5, check=False
            ).stdout
            return int(out.strip().splitlines()[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            value = self.read()
            if value is not None:
                self.samples.append(value)
            self._stop.wait(VRAM_SAMPLE_SECONDS)

    def __enter__(self) -> "VramSampler":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    @property
    def peak(self) -> int | None:
        return max(self.samples) if self.samples else None


# --- running -------------------------------------------------------------------------------


@dataclass
class PageRun:
    page_id: str
    seconds: float
    schema_valid: bool
    error: str | None
    predictions: dict[str, Any] = field(default_factory=dict)
    snippets: dict[str, str | None] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    outcomes: dict[str, Outcome] = field(default_factory=dict)


def _json_value(value: object) -> object:
    return value if isinstance(value, bool | int | str) else str(value)


def run_page(pipeline: Pipeline, entry: dict[str, str], gold: dict[str, Any]) -> PageRun:
    started = time.perf_counter()
    try:
        result = pipeline.extractor.extract(pipeline.loader.load_page(entry["url"]))
    except Exception as exc:
        return PageRun(
            entry["id"], time.perf_counter() - started, False, f"{type(exc).__name__}: {exc}"[:200]
        )
    seconds = time.perf_counter() - started
    predictions: dict[str, Any] = {n: _json_value(p.value) for n, p in result.fields.items()}
    run = PageRun(
        page_id=entry["id"],
        seconds=seconds,
        schema_valid=result.llm_error is None and result.extracted_by is not None,
        error=result.llm_error,
        predictions=predictions,
        snippets={name: p.snippet for name, p in result.fields.items()},
        flags=[f"{flag.field}:{flag.kind}" for flag in result.flags],
    )
    run.outcomes = dict(score_page(result_values(result), gold["fields"]))
    return run


def result_values(result: ExtractionResult) -> dict[str, object]:
    return {name: proposal.value for name, proposal in result.fields.items()}


def run_model(
    model: str, entries: list[dict[str, str]], gold: dict[str, dict[str, Any]], loader_kind: str
) -> dict[str, Any]:
    pages = {e["url"]: (DATA_DIR / "pages" / f"{e['id']}.html").read_bytes() for e in entries}
    baseline = VramSampler.read()
    pipeline = make_pipeline(model, pages, loader_kind)
    runs: list[PageRun] = []
    try:
        with VramSampler() as sampler:
            for entry in entries:
                run = run_page(pipeline, entry, gold[entry["id"]])
                runs.append(run)
                print(
                    f"  {model} {entry['id']}: {run.seconds:5.1f}s valid={run.schema_valid}",
                    flush=True,
                )
    finally:
        pipeline.close()
    seconds = [r.seconds for r in runs]
    scored = [r for r in runs if r.outcomes]
    return {
        "model": model,
        "pages": len(runs),
        "schema_validity": sum(r.schema_valid for r in runs) / len(runs) if runs else None,
        "seconds_p50": percentile(seconds, 0.5),
        "seconds_p95": percentile(seconds, 0.95),
        "seconds_max": max(seconds) if seconds else None,
        "first_page_seconds": seconds[0] if seconds else None,  # includes model load (cold)
        "vram_baseline_mib": baseline,
        "vram_peak_mib": sampler.peak,
        **summarize([r.outcomes for r in scored]),
        "runs": [r.__dict__ for r in runs],
    }


# --- reports -------------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_report(results: dict[str, Any]) -> str:
    models = results["models"]
    lines = [
        f"# Extraction benchmark {results['started_at']}",
        "",
        f"Pages: {results['page_count']}; loader: `{results['loader']}`; gold needs owner check.",
        "",
        "| Model | Valid | Acc. | Date acc. | Halluc. | Fab. dates "
        "| p50 s | p95 s | max s | VRAM MiB |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in models:
        lines.append(
            f"| `{m['model']}` | {_pct(m['schema_validity'])} | {_pct(m['accuracy'])} "
            f"| {_pct(m['date_accuracy'])} | {m['hallucinations']} | {m['fabricated_dates']} "
            f"| {_num(m['seconds_p50'])} | {_num(m['seconds_p95'])} | {_num(m['seconds_max'])} "
            f"| {m['vram_peak_mib'] if m['vram_peak_mib'] is not None else 'n/a'} |"
        )
    lines += [
        "",
        "## Per-field accuracy",
        "",
        "| Field | " + " | ".join(f"`{m['model']}`" for m in models) + " |",
    ]
    lines.append("|---|" + "---|" * len(models))
    for name in EXTRACTABLE_FIELDS:
        cells = [_pct(m["per_field"].get(name)) for m in models]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Pass criteria (LOCAL_LLM_RESEARCH §3): schema validity >= 95%, 0 fabricated dates, "
        "date accuracy >= 90%, < 60 s per page, Turkish quality >= 3.5/5 (blind rating).",
    ]
    return "\n".join(lines) + "\n"


def build_rating_sheet(results: dict[str, Any], seed: int = 1) -> tuple[str, dict[str, Any]]:
    """Markdown sheet with the Turkish summaries under letters A, B, C (model names hidden)
    and the key that maps letters back to models. The mapping is shuffled per page."""
    rng = random.Random(seed)  # noqa: S311 - reproducible shuffle, not security
    models = [m["model"] for m in results["models"]]
    by_model = {m["model"]: {r["page_id"]: r for r in m["runs"]} for m in results["models"]}
    page_ids = sorted({pid for runs in by_model.values() for pid in runs})
    lines = [
        "# Turkish summary rating sheet",
        "",
        "Rate each summary 1-5 (1 = unusable, 5 = natural Turkish). Model names are hidden.",
        "",
    ]
    key: dict[str, dict[str, str]] = {}
    for page_id in page_ids:
        order = models[:]
        rng.shuffle(order)
        lines += [f"## {page_id}", ""]
        key[page_id] = {}
        for letter, model in zip("ABCDEFGH", order, strict=False):
            run = by_model[model].get(page_id)
            summary = (run or {}).get("predictions", {}).get("summary") or "(no summary)"
            key[page_id][letter] = model
            lines += [f"**{letter}** - rating: __ / 5", "", f"> {summary}", ""]
    return "\n".join(lines) + "\n", key


# --- CLI -----------------------------------------------------------------------------------


def load_gold(ids: list[str]) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = {}
    for page_id in ids:
        path = DATA_DIR / "gold" / f"{page_id}.json"
        gold[page_id] = json.loads(path.read_text(encoding="utf-8"))
    return gold


def cmd_run(args: argparse.Namespace) -> None:
    entries = json.loads((BENCH_DIR / "dataset.json").read_text(encoding="utf-8"))
    if args.pages:
        entries = [e for e in entries if e["id"] in args.pages]
    gold = load_gold([e["id"] for e in entries])
    started = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    results: dict[str, Any] = {
        "started_at": started,
        "page_count": len(entries),
        "loader": args.loader,
        "models": [],
    }
    for model in args.models:
        print(f"model {model}", flush=True)
        try:
            results["models"].append(run_model(model, entries, gold, args.loader))
        except ImportError as exc:
            raise SystemExit(
                f"Loader/extractor not available yet ({exc}); see the module docstring."
            ) from exc
    out_dir = DATA_DIR / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{started}.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = render_report(results)
    (out_dir / f"{started}.md").write_text(report, encoding="utf-8")
    print(report)


def cmd_rating_sheet(args: argparse.Namespace) -> None:
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    sheet, key = build_rating_sheet(results)
    base = Path(args.results).with_suffix("")
    Path(f"{base}.rating.md").write_text(sheet, encoding="utf-8")
    Path(f"{base}.rating-key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"wrote {base}.rating.md (give the owner) and {base}.rating-key.json (keep hidden)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--models", nargs="+", required=True)
    run.add_argument("--pages", nargs="*", default=[])
    run.add_argument("--loader", choices=["real", "builtin"], default="real")
    run.set_defaults(func=cmd_run)
    sheet = sub.add_parser("rating-sheet")
    sheet.add_argument("results")
    sheet.set_defaults(func=cmd_rating_sheet)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
