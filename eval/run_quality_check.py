"""Quality check: asks the questions in eval/questions.json and marks the answers."""
import argparse
import json
import time
from pathlib import Path

from app import db
from app.chunker import CHUNK_SIZE
from app.config import get_settings
from app.ingest import add_document
from app.ollama_client import OllamaClient
from app.rag import MAX_DISTANCE, NOT_FOUND_MESSAGE, TOP_K, ask

EVAL_DIR = Path(__file__).parent
WORKSPACE = "Quality check"


# --- setting up the exam room ---

def rebuild_workspace(conn, ollama, uploads_dir: Path, chunk_size: int) -> int:
    # Start fresh every run, so chunks of an older size never mix in.
    for workspace in db.list_workspaces(conn):
        if workspace["name"] == WORKSPACE:
            for name in db.delete_workspace(conn, workspace["id"]):
                (uploads_dir / name).unlink(missing_ok=True)

    workspace_id = db.create_workspace(conn, WORKSPACE)
    for path in sorted((EVAL_DIR / "docs").iterdir()):
        add_document(conn, ollama, uploads_dir, workspace_id, path.name, path.read_bytes(), chunk_size)
    return workspace_id


# --- marking one question ---

def is_hit(chunks: list[dict], item: dict) -> bool:
    # Hit: the expected file (and page, for the PDF) is among the chunks found.
    return any(
        chunk["filename"] == item["expected_file"]
        and (item["expected_page"] is None or chunk["page"] == item["expected_page"])
        for chunk in chunks
    )


def check(conn, ollama, workspace_id: int, item: dict, max_distance: float) -> dict:
    # Search ourselves too, to see what the search found and how close it was.
    chunks = db.search_chunks(conn, workspace_id, ollama.embed_query(item["question"]), TOP_K)
    answer = ask(conn, ollama, workspace_id, item["question"], max_distance)
    said_not_found = answer.text == NOT_FOUND_MESSAGE

    if item["answerable"]:
        hit = is_hit(chunks, item)
        text = answer.text.lower()
        correct = not said_not_found and any(word.lower() in text for word in item["must_contain"])
    else:
        hit = None  # nothing to find
        correct = said_not_found

    return {
        "answerable": item["answerable"],
        "hit": hit,
        "correct": correct,
        "distance": chunks[0]["distance"],
        "answer": answer.text,
    }


# --- the report card ---

def print_line(item: dict, result: dict) -> None:
    mark = "OK  " if result["correct"] else "MISS"
    found = {True: "found", False: "LOST ", None: "  -  "}[result["hit"]]
    print(f"{mark} {found} {result['distance']:.3f}  {item['question']}")
    print(f"                    -> {result['answer'][:110].replace(chr(10), ' ')}")


def print_summary(results: list[dict], seconds: float) -> None:
    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]

    def total(rows, key):
        return sum(1 for r in rows if r[key])

    def average_distance(rows):
        return sum(r["distance"] for r in rows) / len(rows)

    print()
    print(f"Right chunk found (top {TOP_K}):  {total(answerable, 'hit')}/{len(answerable)}")
    print(f"Answered correctly:          {total(answerable, 'correct')}/{len(answerable)}")
    print(f"Said 'not found' correctly:  {total(unanswerable, 'correct')}/{len(unanswerable)}")
    print(f"Average best distance:       answerable {average_distance(answerable):.3f}, "
          f"unanswerable {average_distance(unanswerable):.3f}")
    print(f"Time for {len(results)} questions:     {seconds:.0f} seconds")


# --- running it ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the quality check questions.")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--model", help="chat model to use (default: the one from .env)")
    parser.add_argument("--max-distance", type=float, default=MAX_DISTANCE)
    args = parser.parse_args()

    settings = get_settings()
    model = args.model or settings.chat_model
    conn = db.connect(settings.db_conninfo)
    db.init_db(conn)
    ollama = OllamaClient(settings.ollama_url, settings.embed_model, model)
    questions = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))

    print(f"Chunk size {args.chunk_size}, model {model}, max distance {args.max_distance}")
    workspace_id = rebuild_workspace(conn, ollama, settings.uploads_dir, args.chunk_size)
    print(f"Workspace '{WORKSPACE}' rebuilt: {db.count_chunks(conn, workspace_id)} chunks")
    print()

    start = time.perf_counter()
    results = []
    for item in questions:
        result = check(conn, ollama, workspace_id, item, args.max_distance)
        print_line(item, result)
        results.append(result)

    print_summary(results, time.perf_counter() - start)
    conn.close()


if __name__ == "__main__":
    main()