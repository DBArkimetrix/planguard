from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_framework.planning.generate_plan import generate_plan


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python scripts/generate_plan.py "Implement pricing engine"')
        return 1

    prompt = " ".join(sys.argv[1:]).strip()
    plan_dir = generate_plan(prompt)
    print(f"Generated plan scaffold at: {plan_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
