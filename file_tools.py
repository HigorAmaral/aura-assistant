import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from storage import log_activity

FOLDER_SHORTCUTS: Dict[str, Path] = {
    "downloads": Path.home() / "Downloads",
    "documentos": Path.home() / "Documents",
    "documents": Path.home() / "Documents",
    "desktop": Path.home() / "Desktop",
    "area de trabalho": Path.home() / "Desktop",
    "área de trabalho": Path.home() / "Desktop",
    "imagens": Path.home() / "Pictures",
    "pictures": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "músicas": Path.home() / "Music",
    "home": Path.home(),
}

FILE_CATEGORIES: Dict[str, List[str]] = {
    "Imagens": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"],
    "Documentos": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".pptx", ".ppt"],
    "Planilhas_Dados": [".xls", ".xlsx", ".csv", ".json", ".xml", ".parquet"],
    "Compactados": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Instaladores_Apps": [".exe", ".msi", ".bat", ".cmd"],
    "Audio_Video": [".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac", ".ogg"],
    "Codigo": [".py", ".js", ".ts", ".html", ".css", ".sql", ".ipynb", ".cpp", ".java"],
}


def resolve_folder(folder_input: str) -> Path:
    clean = (folder_input or "downloads").strip().lower()
    if clean in FOLDER_SHORTCUTS:
        return FOLDER_SHORTCUTS[clean]
    for key, path in FOLDER_SHORTCUTS.items():
        if key in clean:
            return path
    p = Path(folder_input).expanduser()
    if p.exists() and p.is_dir():
        return p
    return Path.home() / "Downloads"


def search_local_files(query: str, folder: str = "downloads", max_results: int = 25) -> Dict[str, Any]:
    """Search files by name or extension inside the target directory (up to 3 levels deep)."""
    base_dir = resolve_folder(folder)
    if not base_dir.exists():
        return {"success": False, "folder": str(base_dir), "files": [], "message": f"Pasta não encontrada: {base_dir}"}

    q = (query or "").strip().lower()
    results: List[Dict[str, Any]] = []

    try:
        for root, dirs, files in os.walk(base_dir):
            # Limit recursion depth to keep search super fast
            rel_parts = Path(root).relative_to(base_dir).parts
            if len(rel_parts) > 2:
                dirs[:] = []
                continue
            # Skip hidden/node_modules/.git folders
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".venv")]

            for fname in files:
                if not q or q in fname.lower():
                    fpath = Path(root) / fname
                    try:
                        stat = fpath.stat()
                        size_kb = round(stat.st_size / 1024, 1)
                        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                        results.append(
                            {
                                "name": fname,
                                "path": str(fpath),
                                "ext": fpath.suffix.lower(),
                                "size_kb": size_kb,
                                "modified": mtime,
                            }
                        )
                    except Exception:
                        continue
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
    except Exception as e:
        return {"success": False, "folder": str(base_dir), "files": [], "message": f"Erro ao buscar arquivos: {e}"}

    log_activity("ARQUIVOS", f"Busca por '{query or '*'}' em {base_dir.name}: {len(results)} encontrado(s)")
    return {
        "success": True,
        "folder": str(base_dir),
        "query": query,
        "count": len(results),
        "files": results,
    }


def organize_directory(folder: str = "downloads", dry_run: bool = True) -> Dict[str, Any]:
    """Group loose files in a directory into categorized subfolders. Supports dry_run preview."""
    base_dir = resolve_folder(folder)
    if not base_dir.exists():
        return {"success": False, "folder": str(base_dir), "actions": [], "message": f"Pasta não encontrada: {base_dir}"}

    actions: List[Dict[str, str]] = []
    category_counts: Dict[str, int] = {}

    for item in base_dir.iterdir():
        if not item.is_file() or item.name.startswith(".") or item.name.lower() == "desktop.ini":
            continue
        ext = item.suffix.lower()
        target_cat = None
        for cat, ext_list in FILE_CATEGORIES.items():
            if ext in ext_list:
                target_cat = cat
                break
        if not target_cat:
            target_cat = "Outros"

        dest_folder = base_dir / target_cat
        dest_file = dest_folder / item.name

        # Avoid overwriting if same filename exists in subfolder
        if dest_file.exists():
            stem = item.stem
            timestamp = datetime.now().strftime("%H%M%S")
            dest_file = dest_folder / f"{stem}_{timestamp}{item.suffix}"

        actions.append(
            {
                "file": item.name,
                "category": target_cat,
                "destination": str(dest_file),
            }
        )
        category_counts[target_cat] = category_counts.get(target_cat, 0) + 1

        if not dry_run:
            dest_folder.mkdir(exist_ok=True)
            try:
                shutil.move(str(item), str(dest_file))
            except Exception:
                continue

    mode_label = "Simulação (Dry-Run)" if dry_run else "Organização Concluída"
    log_activity("AUTOMAÇÃO", f"{mode_label} em {base_dir.name}: {len(actions)} arquivo(s)")
    return {
        "success": True,
        "folder": str(base_dir),
        "dry_run": dry_run,
        "total_files": len(actions),
        "summary_by_category": category_counts,
        "actions": actions[:40],
    }


def create_text_file(filename: str, content: str, folder: str = "documentos") -> Dict[str, Any]:
    """Create a text or markdown file inside the chosen folder."""
    base_dir = resolve_folder(folder)
    base_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    if not safe_name.endswith((".txt", ".md", ".json", ".csv", ".py", ".html")):
        safe_name += ".txt"
    target_path = base_dir / safe_name
    target_path.write_text(content, encoding="utf-8")
    log_activity("ARQUIVOS", f"Arquivo criado: {target_path}")
    return {
        "success": True,
        "path": str(target_path),
        "message": f"Arquivo salvo em {target_path}",
    }
