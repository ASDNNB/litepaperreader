"""LitePaperReader CLI - unified command-line interface.

Usage: litepaper process|serve|watch|ask|index
Environment: LITEPAPER_API_KEY, LITEPAPER_API_BASE, LITEPAPER_MODEL, LITEPAPER_MODE
"""

import argparse, asyncio, json, logging, os, sys, hashlib, time, subprocess
from pathlib import Path

_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.knowledge.answer import AnswerGenerator
from litepaperreader.knowledge.package import KnowledgePackage, StructuredCard
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.pipeline.watcher import PipelineDB, FileWatcher
from litepaperreader.connectors.base import ResourceRef

logger = logging.getLogger("litepaper")


def _default_registry():
    reg = SchemaRegistry()
    for tid, desc, flds in [
        ("paper","Academic paper",[("title","Paper title"),("method","Core method"),("finding","Key finding")]),
        ("person","Person profile",[("name","Full name"),("title","Job title"),("organization","Company")]),
        ("product","Product description",[("name","Product name"),("feature","Key feature"),("price","Price")]),
        ("code","Code file",[("module","Module purpose"),("function","Function defined"),("class","Class defined"),("api","Public API")]),
    ]:
        reg.register(SchemaTemplate(template_id=tid, description=desc,
            fields=tuple(FieldSpec(name=n, description=d) for n, d in flds)))
    return reg


def _get_config():
    return {
        "api_key": os.environ.get("LITEPAPER_API_KEY", ""),
        "api_base": os.environ.get("LITEPAPER_API_BASE", "https://api.deepseek.com/v1"),
        "model": os.environ.get("LITEPAPER_MODEL", "deepseek-chat"),
        "mode": os.environ.get("LITEPAPER_MODE", "deepseek"),
    }


async def cmd_process(path, args):
    config = _get_config()
    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    pipeline.with_schema_extractor(_default_registry(),
        template_id=args.template or "paper",
        mode=config["mode"] if config["api_key"] else "mock",
        model=config["model"], api_base=config["api_base"], api_key=config["api_key"])
    kp = await pipeline.run_file(path)
    print(f"\nProcessed: {path}")
    print(f"  Cells: {kp.metadata.get('num_cells',0)}")
    print(f"  Total chars: {kp.metadata.get('total_chars',0)}")
    print(f"  Extraction cards: {len(kp.cards)}\n")
    for card in kp.cards:
        print(f"  [{card.schema_id}] cell={card.source_cell_id}")
        for k,v in card.fields.items():
            if v: print(f"    {k}: {v}")
        print()
    if args.output:
        out = {"path":path,"metadata":kp.metadata,"cards":[
            {"schema_id":c.schema_id,"fields":c.fields,"source_cell_id":c.source_cell_id} for c in kp.cards]}
        with open(args.output,"w",encoding="utf-8") as f: json.dump(out,f,indent=2,ensure_ascii=False)
        print(f"Saved to {args.output}")


async def cmd_ask(question, args):
    if not args.db:
        print("Error: --db required",file=sys.stderr); sys.exit(1)
    db = PipelineDB(args.db)
    config = _get_config()
    cards_data = db.search_cards(question,limit=20)
    cards = [StructuredCard(schema_id=cd["schema_id"],fields=cd.get("fields",{}),
        source_cell_id=cd["cell_id"],confidence=cd.get("confidence",1.0)) for cd in cards_data]
    if not cards:
        print("No indexed documents found. Run: litepaper index <dir>"); return
    kp = KnowledgePackage(cards=cards,metadata={"resources":len(cards),"num_cards":len(cards)})
    gen = AnswerGenerator(model=config["model"],mode=config["mode"] if config["api_key"] else "mock",
        api_key=config["api_key"],api_base=config["api_base"])
    answer = await gen.answer(question,kp)
    print(f"\n{answer.text}\n")
    if answer.citations:
        print("Sources:")
        for c in answer.citations: print(f"  - {c.cell_id}")


def cmd_index(path, args):
    config = _get_config()
    db = PipelineDB(args.db or "litepaper_index.db")
    p = Path(path)
    if not p.exists():
        print(f"Error: {path} does not exist",file=sys.stderr); sys.exit(1)
    supported = {".html",".htm",".txt",".md",".csv",".py",".js",".ts",".rs",".go",".java",".pdf",".xlsx"}
    if p.is_file() and p.suffix.lower() in supported:
        files = [p]
    else:
        files = sorted([f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in supported])
    print(f"Found {len(files)} file(s) to index\n")
    hint_map = {".py":"python",".js":"javascript",".ts":"typescript",".csv":"csv",
        ".html":"html",".htm":"html",".xlsx":"xlsx",".pdf":"pdf",".txt":"text",".md":"markdown"}
    for f in files:
        ext = f.suffix.lower()
        hint = hint_map.get(ext,"unknown")
        ref = ResourceRef(connector="fs",resource_path=str(f),content_type_hint=hint)
        with open(f,"rb") as fh: raw = fh.read()
        try:
            pipeline = DataPipeline()
            pipeline.add_default_adapters()
            code_exts = {".py",".js",".ts",".rs",".go",".java"}
            tmpl = "code" if ext in code_exts else (args.template or "paper")
            pipeline.with_schema_extractor(_default_registry(),template_id=tmpl,
                mode=config["mode"] if config["api_key"] else "mock",
                model=config["model"],api_base=config["api_base"],api_key=config["api_key"])
            kp = asyncio.run(pipeline.run_raw(ref,raw))
            chk = hashlib.sha256(raw).hexdigest()[:16]
            sid = f"index_{f.stem}_{int(time.time())}"
            db.save_file(str(f),chk,f.stat().st_size,sid)
            db.save_results(sid,[],kp.cards)
            print(f"  OK {f.name}: {len(kp.cards)} card(s)")
        except Exception as e:
            print(f"  SKIP {f.name}: {e}")
    dbp = args.db or "litepaper_index.db"
    print(f"\nIndex saved to {dbp}")
    print(f"Run: litepaper ask '<question>' --db {dbp} to query.")

def main():
    parser = argparse.ArgumentParser(prog="litepaper",
        description="LitePaperReader - Universal Data Flow Intelligence Engine")
    subs = parser.add_subparsers(dest="command"); subs.required = True
    p = subs.add_parser("process", help="Process a file through the pipeline")
    p.add_argument("path"); p.add_argument("--template","-t"); p.add_argument("--output","-o")
    p = subs.add_parser("serve", help="Start MCP server")
    p.add_argument("--port","-p",type=int,default=0); p.add_argument("--db")
    p = subs.add_parser("watch", help="Watch directory for changes")
    p.add_argument("path"); p.add_argument("--db",default="litepaper_index.db")
    p.add_argument("--template","-t",default="paper"); p.add_argument("--interval",type=int,default=30)
    p = subs.add_parser("ask", help="Ask questions from indexed documents")
    p.add_argument("question"); p.add_argument("--db",required=True)
    p = subs.add_parser("index", help="Index files to SQLite")
    p.add_argument("path"); p.add_argument("--db",default="litepaper_index.db"); p.add_argument("--template","-t")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "process": asyncio.run(cmd_process(args.path,args))
    elif args.command == "serve":
        cmd = [sys.executable, str(_project_root/"mcp_server.py")]
        if args.db: cmd.extend(["--db",args.db])
        if args.port: cmd.extend(["--port",str(args.port)])
        print(f"Starting MCP server (port={args.port or 'stdio'})...")
        subprocess.run(cmd)
    elif args.command == "watch":
        config = _get_config()
        db = PipelineDB(args.db)
        watcher = FileWatcher(watch_dir=args.path,db=db,schema_registry=_default_registry(),
            template_id=args.template,
            mode=config["mode"] if config["api_key"] else "mock",
            model=config["model"],api_base=config["api_base"],interval=args.interval)
        print(f"Watching {args.path} (poll every {args.interval}s)...")
        watcher.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop(); print("\nShutdown")
    elif args.command == "ask": asyncio.run(cmd_ask(args.question,args))
    elif args.command == "index": cmd_index(args.path,args)


if __name__ == "__main__":
    main()
