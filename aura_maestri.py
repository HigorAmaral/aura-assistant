"""CLI Inter-Agentes estilo `omaestri` para o Quadro Maestri 2D da AURA OS."""
import json
import sys
from maestri_orchestrator import (
    ipc_check,
    ipc_ask,
    ipc_spawn,
    run_maestro_mode,
    detect_installed_clis,
)


def main():
    if len(sys.argv) < 2:
        print("Uso: python aura_maestri.py <check|ask|spawn|maestro|clis> [args...]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "check":
        print(json.dumps(ipc_check(), ensure_ascii=False, indent=2))
    elif cmd == "clis":
        print(json.dumps(detect_installed_clis(), ensure_ascii=False, indent=2))
    elif cmd == "ask" and len(sys.argv) >= 4:
        print(json.dumps(ipc_ask(sys.argv[2], " ".join(sys.argv[3:])), ensure_ascii=False, indent=2))
    elif cmd == "spawn" and len(sys.argv) >= 4:
        prompt = " ".join(sys.argv[4:]) if len(sys.argv) >= 5 else ""
        print(json.dumps(ipc_spawn(sys.argv[2], sys.argv[3], prompt), ensure_ascii=False, indent=2))
    elif cmd == "maestro" and len(sys.argv) >= 3:
        print(json.dumps(run_maestro_mode(" ".join(sys.argv[2:])), ensure_ascii=False, indent=2))
    else:
        print("Argumentos inválidos. Exemplos:")
        print('  python aura_maestri.py check')
        print('  python aura_maestri.py ask "Pesquisador" "resuma as novidades de Python"')
        print('  python aura_maestri.py spawn "Revisor Git" "Analisa commits" "verifique git status"')
        print('  python aura_maestri.py maestro "auditar meu PC e listar repos do github"')
        sys.exit(1)


if __name__ == "__main__":
    main()
